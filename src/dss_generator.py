import pandas as pd
from pydsstools.heclib.dss import HecDss
from pydsstools.core import TimeSeriesContainer
import numpy as np
import os
import logging
import shutil
import tempfile
from datetime import datetime

class DssGenerator:
    def __init__(self, config) -> list:
        self.config = config
        logging.info("DssGenerator initialized.")

    def get_dss(self):
        if os.path.exists(self.config.dss_file):
            logging.info("Existing DSS will be replaced only after validated data is written; a backup will be kept.")
        return self.create_dss_file()
 
    def create_dss_file(self) -> list:
        try:
            filtered_df = self._read_validated_period()
        except FileNotFoundError:
            logging.error(f"CSV file not found at {self.config.csv_file}.")
            return []
        
        logging.info(f"Data after filtering ({self.config.start_date} to {self.config.end_date}): {len(filtered_df)} lines.")

        if filtered_df.empty:
            logging.warning("No data found in CSV for the time period.")
            return []
        
            
        gage_entries = []
        dss_path = self.config.dss_file
        output_dir = os.path.dirname(dss_path)
        os.makedirs(output_dir, exist_ok=True)
        expected_gage_count = filtered_df["raster_val"].nunique()

        # Build separately so a failed write leaves the active DSS untouched.
        with tempfile.TemporaryDirectory(prefix=".dss_build_", dir=output_dir) as build_dir:
            staged_dss_path = os.path.join(build_dir, os.path.basename(dss_path))
            with HecDss.Open(staged_dss_path, version=7) as dss:
                for i, (sub_id, sub_df) in enumerate(filtered_df.groupby("raster_val")):
                    sub_df = sub_df.sort_values("date")
                    values = sub_df["precipitation"].values.astype(float)
                    start_date = sub_df["date"].iloc[0]
                    pathname_save = self.config.build_dss_pathname(
                        sub_id, start_date.strftime("%d%b%Y")
                    )
                    pathname_ref = self.config.build_dss_pathname(sub_id)
                    tsc = self.build_tsc(pathname_save, start_date, values)
                    dss.put_ts(tsc)
                    logging.info(f"Data saved for subbasin {sub_id}.")
                    gage_entries.append({
                        "id": f"Gage-{i}",
                        "name": f"S_{sub_id}",
                        "subbasin": str(sub_df["name"].iloc[0]),
                        "dss_file": os.path.basename(dss_path),
                        "dss_path": pathname_ref
                    })

            if len(gage_entries) != expected_gage_count:
                raise RuntimeError(
                    f"DSS contains {len(gage_entries)} gages; expected {expected_gage_count}."
                )

            if os.path.exists(dss_path):
                backup_dir = os.path.join(output_dir, "dss_backups")
                os.makedirs(backup_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
                backup_path = os.path.join(
                    backup_dir, f"{os.path.basename(dss_path)}.{timestamp}.bak"
                )
                shutil.copy2(dss_path, backup_path)
                logging.info(f"Previous DSS preserved at {backup_path}.")

            os.replace(staged_dss_path, dss_path)

        logging.info(f"Validated DSS created at {dss_path} with {len(gage_entries)} entries.")
        return gage_entries

    def _read_validated_period(self):
        """Load the requested inclusive period and require one daily value per basin."""
        df = pd.read_csv(self.config.csv_file, parse_dates=['date'])
        required_columns = {'date', 'raster_val', 'name', 'precipitation'}
        missing_columns = required_columns - set(df.columns)
        if missing_columns:
            raise ValueError(f"CSV is missing required columns: {sorted(missing_columns)}")
        if df['date'].isna().any() or df['raster_val'].isna().any() or df['name'].isna().any():
            raise ValueError("CSV contains rows with missing dates, IDs, or HEC-HMS names.")

        df["raster_val"] = pd.to_numeric(df["raster_val"], errors="coerce")
        raster_ids = df["raster_val"].to_numpy(dtype=np.float64)
        if not np.isfinite(raster_ids).all() or (raster_ids <= 0).any() or (raster_ids % 1 != 0).any():
            raise ValueError("CSV contains invalid subbasin IDs.")
        df["raster_val"] = df["raster_val"].astype("int64")
        df["name"] = df["name"].astype("string").str.strip()
        if df["name"].eq("").any():
            raise ValueError("CSV contains empty HEC-HMS subbasin names.")
        names_per_id = df.groupby("raster_val")["name"].agg(set)
        ids_per_name = df.groupby("name")["raster_val"].nunique()
        if any(names != {f"S{sub_id}"} for sub_id, names in names_per_id.items()) or (ids_per_name != 1).any():
            raise ValueError(
                "CSV must preserve the one-to-one mapping S<N> → raster_val N."
            )

        # Compare normalized calendar days, but reject times that would make
        # otherwise identical daily records ambiguous.
        normalized_dates = df['date'].dt.normalize()
        has_time = df['date'].ne(normalized_dates)
        if has_time.any():
            raise ValueError("Daily CSV dates must not contain a time of day.")
        df = df.assign(date=normalized_dates)
        df["precipitation"] = pd.to_numeric(df["precipitation"], errors="coerce")
        precipitation = df["precipitation"].to_numpy(dtype=np.float64)
        if not np.isfinite(precipitation).all() or (precipitation < 0).any():
            raise ValueError("Daily precipitation must contain finite, non-negative values.")
        period_start = pd.Timestamp(self.config.start_date).normalize()
        period_end = pd.Timestamp(self.config.end_date).normalize()
        df = df[(df['date'] >= period_start) & (df['date'] <= period_end)].copy()
        if df.empty:
            return df

        expected_dates = pd.date_range(period_start, period_end, freq='D')
        issues = []
        for sub_id, sub_df in df.groupby('raster_val', sort=False):
            duplicated = sub_df.loc[sub_df['date'].duplicated(keep=False), 'date'].dt.strftime('%Y-%m-%d').unique()
            actual_dates = pd.DatetimeIndex(sub_df['date'].unique()).sort_values()
            missing = expected_dates.difference(actual_dates)
            if len(duplicated):
                issues.append(f"subbasin {sub_id}: {len(duplicated)} duplicate date(s), e.g. {', '.join(duplicated[:5])}")
            if len(missing):
                issues.append(f"subbasin {sub_id}: {len(missing)} missing date(s), e.g. {', '.join(missing.strftime('%Y-%m-%d')[:5])}")
        if issues:
            preview = "; ".join(issues[:10])
            remaining = len(issues) - 10
            suffix = f"; plus {remaining} more subbasin issue(s)" if remaining > 0 else ""
            raise ValueError("Daily data validation failed: " + preview + suffix)
        return df

    def build_tsc(self, pathname, start_date, values) -> TimeSeriesContainer:

        if hasattr(values, "to_numpy"):
            valid_values = values.to_numpy(dtype=np.float64)
        else:
            valid_values = np.asarray(values, dtype=np.float64)
        
        count = len(valid_values)
        interval = self.config.INTERVAL

        tsc = TimeSeriesContainer(pathname, count, interval)
                
        tsc.start_time = start_date.strftime("%d%b%Y 2400").upper()       
        tsc.values = valid_values
        tsc.data_units = self.config.UNITS
        tsc.data_type = self.config.DATA_TYPE

        return tsc

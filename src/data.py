import ee
import geemap
import pandas as pd
import numpy as np
import os
import sys
import tempfile
import hashlib
import json
import shutil
from datetime import datetime
from datetime import timedelta
from shapely.geometry import mapping

class PrecipitationDownloader:    
    def __init__(self, config):
        self.config = config
        self.csv_folder = os.path.join(self.config.exit_path, "csv_blocks")
        os.makedirs(self.csv_folder, exist_ok=True)
        self.new_block_paths = set()
        self.unified_csv_backed_up_for_parameter_change = False
        print("PrecipitationDownloader initilized.")

    def download_data(self, gdf_wgs84):
        try:
            print("\n--- Data extraction from Google Earth Engine initialized---")
            
            print("Preparing FeatureCollection for GEE...")
            fc = self._create_feature_collection(gdf_wgs84)
            expected_subbasins = dict(
                zip(gdf_wgs84["raster_val"].astype(int), gdf_wgs84["name"].astype(str))
            )
            cache_parameters = self._cache_parameters(gdf_wgs84)
            self._prepare_cache(cache_parameters, expected_subbasins)
            
            for current_start, current_end in self._date_blocks():
                last_day = current_end - timedelta(days=1)
                print(f"Processing precipitation from {current_start.date()} to {last_day.date()}...")
                
                csv_filename = f"precip_{current_start.date()}_{last_day.date()}.csv"
                csv_path = os.path.join(self.csv_folder, csv_filename)

                if os.path.exists(csv_path):
                    print(f"Data already collected, skipping {csv_filename}")
                    continue
                image_collection = self._get_image_collection(fc, current_start, current_end)
                
                all_stats = image_collection.map(lambda img: self._zonal_mean(img, fc)).flatten()
                
                df_block = geemap.ee_to_df(all_stats)
                self._validate_daily_coverage(
                    df_block,
                    expected_subbasins,
                    current_start,
                    last_day,
                )
                self._write_block_atomically(df_block, csv_path)
                self.new_block_paths.add(csv_path)
                print(f"CSV salvo: {csv_path}")
            
            self._merge_csvs(expected_subbasins)

        except Exception as e:
            print(f"FATAL ERROR during download from GEE: {e}")
            sys.exit(1)

    def _date_blocks(self):
        """Yield non-overlapping blocks covering the inclusive configured period."""
        end_exclusive = self.config.end_date + timedelta(days=1)
        current_start = self.config.start_date
        while current_start < end_exclusive:
            current_end = min(current_start + timedelta(days=30), end_exclusive)
            yield current_start, current_end
            current_start = current_end

    def _cache_parameters(self, gdf_wgs84):
        geometry_rows = sorted(
            (str(row["raster_val"]), str(row["name"]), self._canonical_geometry(row.geometry))
            for _, row in gdf_wgs84.iterrows()
        )
        legacy_geometry_rows = sorted(
            (str(row["raster_val"]), row.geometry.wkb_hex)
            for _, row in gdf_wgs84.iterrows()
        )
        self._legacy_geometry_digest = hashlib.sha256(
            json.dumps(legacy_geometry_rows, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        geometry_digest = hashlib.sha256(
            json.dumps(geometry_rows, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {
            "schema_version": 3,
            "collection": "UCSB-CHG/CHIRPS/DAILY",
            "band": "precipitation",
            "reducer": "weighted_mean_with_interior_pixel_fallback",
            "scale_meters": self.config.precipitation_scale,
            "block_days": 30,
            "start_date": self.config.start_date.strftime("%Y-%m-%d"),
            "end_date_inclusive": self.config.end_date.strftime("%Y-%m-%d"),
            "geometry_crs": str(gdf_wgs84.crs),
            "geometry_sha256": geometry_digest,
        }

    @classmethod
    def _canonical_geometry(cls, geometry):
        """Serialize geometry independent of ring orientation and start vertex."""
        geometry_type = geometry.geom_type
        if geometry_type == "Polygon":
            return {
                "type": geometry_type,
                "exterior": cls._canonical_ring(geometry.exterior.coords),
                "interiors": sorted(
                    cls._canonical_ring(ring.coords) for ring in geometry.interiors
                ),
            }
        if geometry_type in ("MultiPolygon", "GeometryCollection"):
            return {
                "type": geometry_type,
                "geometries": sorted(
                    (
                        json.dumps(cls._canonical_geometry(part), sort_keys=True)
                        for part in geometry.geoms
                    )
                ),
            }
        if geometry_type == "LineString":
            return {"type": geometry_type, "coordinates": cls._canonical_ring(geometry.coords)}
        if geometry_type == "MultiLineString":
            return {
                "type": geometry_type,
                "geometries": sorted(
                    cls._canonical_ring(part.coords) for part in geometry.geoms
                ),
            }
        if geometry_type == "Point":
            return {
                "type": geometry_type,
                "coordinates": [round(float(value), 8) for value in geometry.coords[0]],
            }
        if geometry_type == "MultiPoint":
            return {
                "type": geometry_type,
                "geometries": sorted(
                    tuple(round(float(value), 8) for value in part.coords[0])
                    for part in geometry.geoms
                ),
            }
        raise ValueError(f"Unsupported geometry type in precipitation cache: {geometry_type}")

    @staticmethod
    def _canonical_ring(coordinates):
        # Rounding to 1e-8 degrees suppresses serialization noise below about a
        # millimeter while preserving meaningful changes to subbasin boundaries.
        points = [tuple(round(float(value), 8) for value in point) for point in coordinates]
        if len(points) > 1 and points[0] == points[-1]:
            points.pop()
        if not points:
            return []

        smallest_point = min(points)
        rotations = [
            points[index:] + points[:index]
            for index, point in enumerate(points)
            if point == smallest_point
        ]
        reversed_points = list(reversed(points))
        rotations.extend(
            reversed_points[index:] + reversed_points[:index]
            for index, point in enumerate(reversed_points)
            if point == smallest_point
        )
        canonical = min(rotations)
        return [list(point) for point in canonical]

    def _prepare_cache(self, parameters, expected_subbasins):
        manifest_path = os.path.join(self.csv_folder, "cache_manifest.json")
        unified_path = os.path.join(
            self.config.exit_path, "precipitacao_diaria_subbacias_unificado.csv"
        )
        block_paths = [
            os.path.join(self.csv_folder, filename)
            for filename in os.listdir(self.csv_folder)
            if filename.startswith("precip_") and filename.endswith(".csv")
        ]

        previous_parameters = None
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as manifest_file:
                    previous_parameters = json.load(manifest_file).get("parameters")
            except (OSError, json.JSONDecodeError):
                previous_parameters = None

        parameters_changed = previous_parameters != parameters
        if parameters_changed and previous_parameters:
            previous_without_geometry = dict(previous_parameters)
            current_without_geometry = dict(parameters)
            previous_geometry_digest = previous_without_geometry.pop("geometry_sha256", None)
            current_without_geometry.pop("geometry_sha256", None)
            if (
                previous_without_geometry == current_without_geometry
                and previous_geometry_digest == getattr(self, "_legacy_geometry_digest", None)
            ):
                # Upgrade manifests created with the former raw-WKB fingerprint
                # without discarding resumable blocks from the interrupted run.
                parameters_changed = False
                print("Manifesto antigo compatível; atualizando hash geométrico sem limpar o cache.")
        has_previous_data = bool(block_paths) or os.path.isfile(unified_path)
        if parameters_changed and has_previous_data:
            backup_dir = self._create_csv_backup(
                reason="parameters_changed",
                parameters=previous_parameters,
                block_paths=block_paths,
                manifest_path=manifest_path if os.path.isfile(manifest_path) else None,
                unified_path=unified_path if os.path.isfile(unified_path) else None,
            )
            self.unified_csv_backed_up_for_parameter_change = os.path.isfile(unified_path)
            # These files are safely archived; remove them from the active cache
            # so blocks generated with old settings cannot be reused by filename.
            for path in block_paths:
                os.remove(path)
            if os.path.isfile(manifest_path):
                os.remove(manifest_path)
            print(
                f"Cache anterior arquivado em {backup_dir}; os blocos serão reextraídos. "
                "O CSV unificado anterior permanecerá disponível até a nova extração ser validada."
            )
        elif parameters_changed:
            print("Parâmetros novos detectados; iniciando cache sem dados anteriores.")
        else:
            print("Parâmetros da extração inalterados; cache compatível.")

        self._write_cache_manifest(manifest_path, parameters)
        self._restore_compatible_backup_blocks(parameters, expected_subbasins)

    def _restore_compatible_backup_blocks(self, parameters, expected_subbasins):
        """Restore validated local blocks from backups made with matching settings."""
        backup_root = os.path.join(self.config.exit_path, "csv_backups")
        if not os.path.isdir(backup_root):
            return

        expected_blocks = {}
        for block_start, block_end in self._date_blocks():
            last_day = block_end - timedelta(days=1)
            filename = f"precip_{block_start.date()}_{last_day.date()}.csv"
            expected_blocks[filename] = (block_start, last_day)

        restored = set()
        backup_dirs = sorted(
            (
                os.path.join(backup_root, name)
                for name in os.listdir(backup_root)
                if os.path.isdir(os.path.join(backup_root, name))
            ),
            reverse=True,
        )
        for backup_dir in backup_dirs:
            metadata_path = os.path.join(backup_dir, "backup_manifest.json")
            try:
                with open(metadata_path, "r", encoding="utf-8") as metadata_file:
                    metadata = json.load(metadata_file)
            except (OSError, json.JSONDecodeError):
                continue

            if not self._parameters_match(metadata.get("previous_parameters"), parameters):
                continue

            archived_files = set(metadata.get("files", []))
            for filename, (period_start, period_end) in expected_blocks.items():
                destination = os.path.join(self.csv_folder, filename)
                source = os.path.join(backup_dir, filename)
                if filename in restored or os.path.exists(destination):
                    continue
                if filename not in archived_files or not os.path.isfile(source):
                    continue

                try:
                    block = pd.read_csv(source, parse_dates=["date"])
                    self._validate_daily_coverage(
                        block,
                        expected_subbasins,
                        period_start,
                        period_end,
                    )
                    temp_path = None
                    try:
                        with tempfile.NamedTemporaryFile(
                            suffix=".csv",
                            prefix=".restored_block_",
                            dir=self.csv_folder,
                            delete=False,
                        ) as temp_file:
                            temp_path = temp_file.name
                        shutil.copy2(source, temp_path)
                        os.replace(temp_path, destination)
                    finally:
                        if temp_path and os.path.exists(temp_path):
                            os.remove(temp_path)
                    restored.add(filename)
                    print(f"Bloco local restaurado do backup: {filename}")
                except Exception as error:
                    print(f"Backup ignorado para {filename}; validação falhou: {error}")

        if restored:
            print(f"Cache local recuperado: {len(restored)} bloco(s) restaurado(s).")

    def _parameters_match(self, candidate, current):
        if candidate == current:
            return True
        if not isinstance(candidate, dict):
            return False

        candidate_without_geometry = dict(candidate)
        current_without_geometry = dict(current)
        candidate_digest = candidate_without_geometry.pop("geometry_sha256", None)
        current_without_geometry.pop("geometry_sha256", None)
        return (
            candidate_without_geometry == current_without_geometry
            and candidate_digest == getattr(self, "_legacy_geometry_digest", None)
        )

    def _write_cache_manifest(self, manifest_path, parameters):
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", prefix=".cache_manifest_",
                dir=self.csv_folder, delete=False, encoding="utf-8"
            ) as temp_file:
                temp_path = temp_file.name
                json.dump({"parameters": parameters}, temp_file, indent=2, sort_keys=True)
                temp_file.write("\n")
            os.replace(temp_path, manifest_path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    def _create_csv_backup(
        self, reason, parameters, block_paths=None, manifest_path=None, unified_path=None
    ):
        backup_root = os.path.join(self.config.exit_path, "csv_backups")
        os.makedirs(backup_root, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        backup_dir = os.path.join(backup_root, timestamp)
        os.makedirs(backup_dir)

        archived = []
        for source in block_paths or []:
            shutil.copy2(source, os.path.join(backup_dir, os.path.basename(source)))
            archived.append(os.path.basename(source))
        for source in (manifest_path, unified_path):
            if source and os.path.isfile(source):
                shutil.copy2(source, os.path.join(backup_dir, os.path.basename(source)))
                archived.append(os.path.basename(source))

        backup_metadata = {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "reason": reason,
            "previous_parameters": parameters,
            "files": archived,
        }
        with open(os.path.join(backup_dir, "backup_manifest.json"), "w", encoding="utf-8") as metadata_file:
            json.dump(backup_metadata, metadata_file, indent=2, sort_keys=True)
            metadata_file.write("\n")
        return backup_dir

    def _write_block_atomically(self, data, csv_path):
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".csv", prefix=".precip_block_",
                dir=self.csv_folder, delete=False, encoding="utf-8", newline=""
            ) as temp_file:
                temp_path = temp_file.name
                data.to_csv(temp_file, index=False)
            os.replace(temp_path, csv_path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    def _create_feature_collection(self, gdf_wgs84):
        features = []
        for _, row in gdf_wgs84.iterrows():
            geom = ee.Geometry(mapping(row.geometry))
            props = row.drop("geometry").to_dict()
            sample_point = row.geometry.representative_point()
            props["sample_lon"] = float(sample_point.x)
            props["sample_lat"] = float(sample_point.y)
            features.append(ee.Feature(geom, props))
        return ee.FeatureCollection(features)

    def _get_image_collection(self, fc, start_date, end_date):
        return (
            ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
            .filterBounds(fc)
            .filterDate(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
            .select("precipitation")
            .map(lambda img: img.set("date", img.date().format("YYYY-MM-dd")))
        )

    def _zonal_mean(self, img, fc):
        stats = img.reduceRegions(
            collection=fc,
            reducer=ee.Reducer.mean(),
            scale=self.config.precipitation_scale
        )
        stats = stats.map(lambda f: f.set("date", img.get("date")))

        def set_precipitation(feature):
            area_mean = feature.get("mean")
            sample_point = ee.Geometry.Point([
                feature.get("sample_lon"),
                feature.get("sample_lat"),
            ])
            point_value = img.reduceRegion(
                reducer=ee.Reducer.first(),
                geometry=sample_point,
                crs=img.projection(),
            ).get("precipitation")
            use_point_fallback = ee.Algorithms.IsEqual(area_mean, None)
            precipitation = ee.Algorithms.If(
                use_point_fallback, point_value, area_mean
            )
            method = ee.Algorithms.If(
                use_point_fallback, "interior_pixel_fallback", "area_mean"
            )
            return ee.Feature(feature.geometry(), {
                "raster_val": feature.get("raster_val"),
                "name": feature.get("name"),
                "date": feature.get("date"),
                "precipitation": precipitation,
                "precipitation_method": method,
            })

        return stats.map(set_precipitation)

    def _merge_csvs(self, expected_subbasins=None):
        print("Unificando arquivos CSV...")
        csv_files = []
        missing_files = []
        for block_start, block_end in self._date_blocks():
            last_day = block_end - timedelta(days=1)
            filename = f"precip_{block_start.date()}_{last_day.date()}.csv"
            path = os.path.join(self.csv_folder, filename)
            if os.path.isfile(path):
                csv_files.append(path)
            else:
                missing_files.append(filename)
        if missing_files:
            raise FileNotFoundError(
                "Expected precipitation blocks are missing: " + ", ".join(missing_files)
            )

        all_data = pd.concat([pd.read_csv(path, parse_dates=["date"]) for path in csv_files], ignore_index=True)
        self._validate_daily_coverage(all_data, expected_subbasins)
        final_csv_path = os.path.join(self.config.exit_path, "precipitacao_diaria_subbacias_unificado.csv")
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".csv", prefix=".precipitacao_", dir=self.config.exit_path,
                delete=False, encoding="utf-8", newline=""
            ) as temp_file:
                temp_path = temp_file.name
                all_data.to_csv(temp_file, index=False)
            if os.path.isfile(final_csv_path) and self._csv_data_equal(temp_path, final_csv_path):
                print("CSV unificado já está atualizado; nenhum backup foi criado.")
                return
            if os.path.isfile(final_csv_path):
                if self.unified_csv_backed_up_for_parameter_change:
                    print("CSV unificado anterior já foi arquivado pela alteração de parâmetros.")
                else:
                    manifest_path = os.path.join(self.csv_folder, "cache_manifest.json")
                    previous_block_paths = [
                        path for path in csv_files if path not in self.new_block_paths
                    ]
                    backup_dir = self._create_csv_backup(
                        reason="new_data",
                        parameters=self._read_cache_parameters(),
                        block_paths=previous_block_paths,
                        manifest_path=manifest_path,
                        unified_path=final_csv_path,
                    )
                    print(f"CSV unificado anterior arquivado em {backup_dir}.")
            os.replace(temp_path, final_csv_path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
        print(f"✅ CSV Unificado salvo em: {final_csv_path}")

    def _read_cache_parameters(self):
        manifest_path = os.path.join(self.csv_folder, "cache_manifest.json")
        if not os.path.isfile(manifest_path):
            return None
        with open(manifest_path, "r", encoding="utf-8") as manifest_file:
            return json.load(manifest_file).get("parameters")

    @staticmethod
    def _csv_data_equal(first_path, second_path):
        first = pd.read_csv(first_path, parse_dates=["date"])
        second = pd.read_csv(second_path, parse_dates=["date"])
        columns = sorted(set(first.columns) | set(second.columns))
        if set(first.columns) != set(second.columns):
            return False
        sort_columns = [column for column in ("raster_val", "date") if column in columns]
        first = first[columns].sort_values(sort_columns).reset_index(drop=True)
        second = second[columns].sort_values(sort_columns).reset_index(drop=True)
        try:
            pd.testing.assert_frame_equal(
                first, second, check_dtype=False, check_exact=True
            )
        except AssertionError:
            return False
        return True

    def _validate_daily_coverage(
        self, data, expected_subbasins=None, period_start=None, period_end=None
    ):
        required_columns = {
            "date", "raster_val", "name", "precipitation", "precipitation_method"
        }
        missing_columns = required_columns - set(data.columns)
        if missing_columns:
            raise ValueError(f"CSV blocks are missing required columns: {sorted(missing_columns)}")
        if data["date"].isna().any() or data["raster_val"].isna().any() or data["name"].isna().any():
            raise ValueError("CSV blocks contain rows with missing dates, IDs, or HEC-HMS names.")

        data = data.copy()
        data["date"] = pd.to_datetime(data["date"], errors="coerce")
        if data["date"].isna().any():
            raise ValueError("CSV blocks contain unparseable dates.")
        normalized_dates = data["date"].dt.normalize()
        if data["date"].ne(normalized_dates).any():
            raise ValueError("Daily CSV dates must not contain a time of day.")
        data["date"] = normalized_dates

        data["raster_val"] = pd.to_numeric(data["raster_val"], errors="coerce")
        raster_ids = data["raster_val"].to_numpy(dtype=np.float64)
        if not np.isfinite(raster_ids).all() or (raster_ids <= 0).any() or (raster_ids % 1 != 0).any():
            raise ValueError("CSV blocks contain invalid subbasin IDs.")
        data["raster_val"] = data["raster_val"].astype("int64")
        data["name"] = data["name"].astype("string").str.strip()
        if data["name"].eq("").any():
            raise ValueError("CSV blocks contain empty HEC-HMS subbasin names.")
        data["precipitation_method"] = data["precipitation_method"].astype("string")
        valid_methods = {"area_mean", "interior_pixel_fallback"}
        unexpected_methods = set(data["precipitation_method"].dropna()) - valid_methods
        if data["precipitation_method"].isna().any() or unexpected_methods:
            raise ValueError(
                "CSV blocks contain missing or unsupported precipitation methods: "
                f"{sorted(unexpected_methods)}"
            )

        data["precipitation"] = pd.to_numeric(data["precipitation"], errors="coerce")
        precipitation = data["precipitation"].to_numpy(dtype=np.float64)
        if not np.isfinite(precipitation).all() or (precipitation < 0).any():
            invalid = ~np.isfinite(precipitation) | (precipitation < 0)
            preview_columns = [column for column in ("date", "raster_val", "name", "precipitation") if column in data]
            preview = data.loc[invalid, preview_columns].head(10).to_dict("records")
            raise ValueError(
                "CSV blocks contain missing, non-finite, or negative precipitation values; "
                f"examples: {preview}"
            )

        start = pd.Timestamp(period_start or self.config.start_date).normalize()
        end = pd.Timestamp(period_end or self.config.end_date).normalize()
        expected_dates = pd.date_range(start, end, freq="D")
        outside_period = ~data["date"].between(start, end)
        if outside_period.any():
            raise ValueError("CSV blocks contain dates outside the configured inclusive period.")

        if expected_subbasins is not None:
            expected_names = (
                {int(sub_id): str(name) for sub_id, name in expected_subbasins.items()}
                if isinstance(expected_subbasins, dict)
                else None
            )
            expected_ids = set(expected_names if expected_names is not None else expected_subbasins)
            actual_ids = set(data["raster_val"].unique())
            if actual_ids != expected_ids:
                missing_ids = sorted(expected_ids - actual_ids)
                unexpected_ids = sorted(actual_ids - expected_ids)
                raise ValueError(
                    f"Subbasin IDs do not match the input geometries; missing={missing_ids}, "
                    f"unexpected={unexpected_ids}."
                )

            if expected_names is not None:
                actual_names = data.groupby("raster_val")["name"].agg(lambda values: set(values))
                mismatched_names = {
                    int(sub_id): sorted(names)
                    for sub_id, names in actual_names.items()
                    if names != {expected_names[int(sub_id)]}
                }
                if mismatched_names:
                    raise ValueError(
                        "CSV HEC-HMS names do not match the input geometries: "
                        f"{mismatched_names}"
                    )

        duplicate_names = data.groupby("name")["raster_val"].nunique()
        duplicate_names = duplicate_names[duplicate_names > 1]
        if not duplicate_names.empty:
            raise ValueError(
                "A HEC-HMS subbasin name maps to multiple IDs: "
                + ", ".join(duplicate_names.index.astype(str))
            )

        grouped = data.groupby("raster_val", sort=False)
        issues = []
        for sub_id, sub_data in grouped:
            duplicated = sub_data.loc[sub_data["date"].duplicated(keep=False), "date"].dt.strftime("%Y-%m-%d").unique()
            actual_dates = pd.DatetimeIndex(sub_data["date"].unique()).sort_values()
            missing_dates = expected_dates.difference(actual_dates)
            if len(duplicated):
                issues.append(f"subbasin {sub_id}: duplicate {len(duplicated)} dates (e.g. {', '.join(duplicated[:5])})")
            if len(missing_dates):
                issues.append(f"subbasin {sub_id}: missing {len(missing_dates)} dates (e.g. {', '.join(missing_dates.strftime('%Y-%m-%d')[:5])})")
        if issues:
            preview = "; ".join(issues[:10])
            remaining = len(issues) - 10
            suffix = f"; plus {remaining} more subbasin issue(s)" if remaining > 0 else ""
            raise ValueError("Daily CSV validation failed: " + preview + suffix)

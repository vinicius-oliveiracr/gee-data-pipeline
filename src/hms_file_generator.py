from jinja2 import Template
from datetime import datetime
from datetime import timedelta
import logging
import os
import re
import math

class HmsFileGenerator:
    def __init__(self, config):
        self.config = config
        logging.info("HmsFileGenerator initialized.")

    def _format_hec_date(self, date_obj):
        months = {
            1: "January",
            2: "February",
            3: "March",
            4: "April",
            5: "May",
            6: "June",
            7: "July",
            8: "August",
            9: "September",
            10: "October",
            11: "November",
            12: "December"
        }

        if isinstance(date_obj, str):
            return date_obj
        return date_obj.strftime("%d %B %Y")
   
    def generate_gage_file(self, gages_data: list):
        if not gages_data:
            logging.warning("No entry for gage file.")
            return

        now = datetime.now()
        str_date = self._format_hec_date(now)
        str_time = now.strftime("%H:%M:%S")

        formatted_gages = []
        for g in gages_data:
            gage_name = (
                g.get("name") if isinstance(g, dict) else getattr(g, "name", "S_1")
            )

            formatted_gages.append({
                "name": gage_name,
                "date": str_date,
                "time": str_time,
                "dss_file": self.config.hms_dss_filename,
                "pathname": g.get("dss_path") if isinstance(g, dict) else None,
                "start_time": self.config.start_date.strftime("%d %B %Y %H:%M:%S"),
                "end_time": (self.config.end_date + timedelta(days=1)).strftime("%d %B %Y %H:%M:%S"),
                "height_units": "Meters",
                "height": "10.0",
                "units": self.config.UNITS,
                "data_type": self.config.DATA_TYPE,
            })

        template = Template(self.config.GAGE_TEMPLATE)
        output = template.render(
            gages=formatted_gages, date_str=str_date, time_str=str_time
        )

        try:
            with open(self.config.gage_file, "w", encoding="ascii", newline="\r\n") as f:
                f.write(output.strip() + "\r\n")
                logging.info(
                    f"Gage file created successfully at {self.config.gage_file}."
                )
        except IOError as e:
            logging.error(f"Unable to write gage file: {e}")

    def generate_met_file(self, subbasins_data: list):
        if not subbasins_data:
            logging.warning("No subbasins provided for the meteorological model.")
            return

        subbasin_names = []
        gage_names = []
        for item in subbasins_data:
            if "subbasin" not in item or "gage" not in item:
                logging.error(
                f"Invalid format in subbasins_data: {item}. Key-value pairs for 'subbasin' and 'gage' are required.")

        subbasin_names = [item["subbasin"] for item in subbasins_data]
        gage_names = [item["gage"] for item in subbasins_data]
        if len(set(subbasin_names)) != len(subbasin_names):
            raise ValueError("Meteorology data contains duplicate subbasin names.")
        if len(set(gage_names)) != len(gage_names):
            raise ValueError("Meteorology data contains duplicate gage names.")

        basin_path = self.config.basin_file
        if os.path.isfile(basin_path):
            with open(basin_path, "r", encoding="ascii", errors="strict") as basin_file:
                basin_names = set(re.findall(
                    r"^Subbasin:\s*(.+?)\s*$", basin_file.read(), re.MULTILINE
                ))
            if set(subbasin_names) != basin_names:
                raise ValueError(
                    "Meteorology subbasins do not match the HEC-HMS basin model; "
                    f"missing={sorted(basin_names - set(subbasin_names))}, "
                    f"unexpected={sorted(set(subbasin_names) - basin_names)}."
                )
    
        template = Template(self.config.MET_TEMPLATE)
        now = datetime.now()

        content = template.render(
            met_name=self.config.met_model_name,
            basin_name=self.config.basin_name,
            date_str=self._format_hec_date(now),
            time_str=now.strftime("%H:%M:%S"),
            subbasins=subbasins_data,
        )

        try:
            with open(
                self.config.met_file, "w", encoding="ascii", newline="\r\n") as f:
                f.write(content.strip() + "\r\n")
            logging.info(f".Meteorology file generated: {self.config.met_file}")
        except IOError as e:
            logging.error(f"Error writing .met file: {e}")


    def generate_control_file(self):

        template = Template(self.config.CONTROL_TEMPLATE)
        now = datetime.now()

        control_name = (
            os.path.basename(self.config.control_file)
            .replace(".control", "")
            .strip()
        )

        content = template.render(
            control_name=control_name,
            date_str=self._format_hec_date(now),
            time_str=now.strftime("%H:%M"),
            start_date=self._format_hec_date(self.config.start_date),
            # The control window is a half-open interval. Close it at
            # midnight after the final included daily precipitation value.
            end_date=self._format_hec_date(self.config.end_date + timedelta(days=1)),
        )

        try:
            with open(
                self.config.control_file, "w", encoding="ascii", newline="\r\n") as f:
                f.write(content.strip() + "\r\n")
            logging.info(f".Control file generated: {self.config.control_file}")
        except IOError as e:
            logging.error(f"Error writing .control file: {e}")

    def update_basin_curve_numbers(self):
        """Apply each GeoJSON GCN value to its matching HEC-HMS subbasin."""
        import geopandas as gpd

        basin_path = self.config.basin_file
        geojson_path = self.config.gcn_geojson_path
        if not os.path.isfile(basin_path):
            raise FileNotFoundError(f"HEC-HMS basin file not found: {basin_path}")
        if not os.path.isfile(geojson_path):
            raise FileNotFoundError(f"Subbasin GCN GeoJSON not found: {geojson_path}")

        geojson = gpd.read_file(geojson_path)
        if "name" not in geojson.columns or "gcn" not in geojson.columns:
            raise ValueError("GCN GeoJSON must contain 'name' and 'gcn' properties.")
        if geojson["name"].isna().any():
            raise ValueError("GCN GeoJSON contains subbasins without HEC-HMS names.")

        curve_numbers = {}
        for name, value in zip(geojson["name"], geojson["gcn"]):
            name = str(name).strip()
            if not name or name in curve_numbers:
                raise ValueError(f"Missing or duplicate subbasin name in GCN GeoJSON: {name!r}")
            curve_number = float(value)
            if not 0 < curve_number <= 100:
                raise ValueError(f"Curve Number for {name} is outside (0, 100]: {curve_number}")
            curve_numbers[name] = curve_number

        with open(basin_path, "r", encoding="ascii", errors="strict", newline="") as basin_file:
            original_content = basin_file.read()

        lines = original_content.splitlines()
        updated_names = set()
        index = 0
        while index < len(lines):
            match = re.fullmatch(r"Subbasin:\s*(.+?)\s*", lines[index])
            if not match:
                index += 1
                continue

            subbasin_name = match.group(1)
            end_index = index + 1
            while end_index < len(lines) and lines[end_index].strip() != "End:":
                end_index += 1
            if end_index == len(lines):
                raise ValueError(f"Unterminated subbasin block in {basin_path}: {subbasin_name}")

            if subbasin_name in curve_numbers:
                updated_names.add(subbasin_name)
                block = lines[index + 1:end_index]
                loss_index = next(
                    (i for i, line in enumerate(block)
                     if re.match(r"\s*LossRate\s*:", line, re.IGNORECASE)),
                    None,
                )
                if loss_index is None:
                    raise ValueError(f"LossRate field missing for {subbasin_name} in {basin_path}")

                indent = re.match(r"\s*", block[loss_index]).group(0)
                # HEC-HMS stores the SCS Curve Number loss method as "SCS"
                # in the .basin file, even though the UI shows its full name.
                block[loss_index] = f"{indent}LossRate: SCS"
                impervious_percent = 0.0
                found_impervious = False
                normalized_block = []
                for line in block:
                    impervious_match = re.match(
                        r"\s*(?:Percent\s*Impervious(?:\s*Area)?|percentimperviousarea)\s*:\s*(.*?)\s*$",
                        line,
                        re.IGNORECASE,
                    )
                    if impervious_match:
                        # Prefer the recognized field if both it and a legacy alias exist.
                        value = impervious_match.group(1)
                        if not found_impervious or re.match(
                            r"\s*Percent\s+Impervious\s*:", line, re.IGNORECASE
                        ):
                            try:
                                impervious_percent = float(value)
                            except ValueError as exc:
                                raise ValueError(
                                    f"Invalid impervious percentage for {subbasin_name}: {value!r}"
                                ) from exc
                            found_impervious = True
                        continue

                    # Remove Curve Number aliases so the generated value occurs once.
                    if re.match(r"\s*Curve\s*Number\s*:", line, re.IGNORECASE):
                        continue
                    normalized_block.append(line)

                if not 0 <= impervious_percent <= 100:
                    raise ValueError(
                        f"Percent impervious for {subbasin_name} is outside [0, 100]: "
                        f"{impervious_percent}"
                    )

                block = normalized_block
                loss_index = next(i for i, line in enumerate(block)
                                  if re.match(r"\s*LossRate\s*:", line, re.IGNORECASE))
                block.insert(loss_index + 1, f"{indent}Curve Number: {curve_numbers[subbasin_name]:.6f}")
                block.insert(
                    loss_index + 2,
                    f"{indent}Percent Impervious Area: {impervious_percent:.6f}",
                )
                lines[index + 1:end_index] = block
                end_index = index + len(block) + 1
            index = end_index + 1

        missing_names = set(curve_numbers) - updated_names
        if missing_names:
            raise ValueError(
                "GeoJSON subbasins have no matching elements in HEC-HMS basin file: "
                + ", ".join(sorted(missing_names))
            )

        basin_names = set(re.findall(r"^Subbasin:\s*(.+?)\s*$", original_content, re.MULTILINE))
        unmatched_basin_names = basin_names - set(curve_numbers)
        if unmatched_basin_names:
            raise ValueError(
                "HEC-HMS subbasins have no Curve Number in GeoJSON: "
                + ", ".join(sorted(unmatched_basin_names))
            )

        updated_content = "\r\n".join(lines) + "\r\n"
        if updated_content != original_content:
            with open(basin_path, "w", encoding="ascii", newline="") as basin_file:
                basin_file.write(updated_content)
        logging.info(
            "Applied SCS Curve Number to %d HEC-HMS subbasins in %s.",
            len(updated_names), basin_path,
        )

    def update_basin_scs_transform_lags(self):
        """Apply Kirpich-derived SCS unit-hydrograph lag times to the basin model."""
        import geopandas as gpd

        basin_path = self.config.basin_file
        geojson_path = self.config.gcn_geojson_path
        geojson = gpd.read_file(geojson_path)
        required = {"name", "tc_kirpich_min", "lag_scs_min"}
        if not required.issubset(geojson.columns):
            raise ValueError(
                "Hydrologic GeoJSON must contain: " + ", ".join(sorted(required))
            )

        lag_times = {}
        for name, tc, lag in zip(
            geojson["name"], geojson["tc_kirpich_min"], geojson["lag_scs_min"]
        ):
            name = str(name).strip()
            if not name or name in lag_times:
                raise ValueError(f"Missing or duplicate subbasin name in GeoJSON: {name!r}")
            tc, lag = float(tc), float(lag)
            if not (math.isfinite(tc) and tc > 0 and math.isfinite(lag) and lag > 0):
                raise ValueError(f"Invalid Tc/lag for {name}: Tc={tc}, lag={lag}")
            lag_times[name] = lag

        with open(basin_path, "r", encoding="ascii", errors="strict", newline="") as basin_file:
            original_content = basin_file.read()

        lines = original_content.splitlines()
        updated_names = set()
        index = 0
        while index < len(lines):
            match = re.fullmatch(r"Subbasin:\s*(.+?)\s*", lines[index])
            if not match:
                index += 1
                continue
            subbasin_name = match.group(1)
            end_index = index + 1
            while end_index < len(lines) and lines[end_index].strip() != "End:":
                end_index += 1
            if end_index == len(lines):
                raise ValueError(f"Unterminated subbasin block in {basin_path}: {subbasin_name}")

            if subbasin_name in lag_times:
                updated_names.add(subbasin_name)
                block = lines[index + 1:end_index]
                transform_index = next(
                    (i for i, line in enumerate(block)
                     if re.match(r"\s*Transform\s*:", line, re.IGNORECASE)),
                    None,
                )
                if transform_index is None:
                    raise ValueError(f"Transform field missing for {subbasin_name} in {basin_path}")
                indent = re.match(r"\s*", block[transform_index]).group(0)
                block[transform_index] = f"{indent}Transform: SCS"

                # Use the field names expected by the HEC-HMS .basin format.
                block = [
                    line for line in block
                    if not re.match(
                        r"\s*(?:Clark\s+Method|SCS\s+Method|Graph\s+Type|"
                        r"Lag(?:\s+Time)?|Unitgraph\s+Type|Time\s+Area\s+Method)\s*:",
                        line,
                        re.IGNORECASE,
                    )
                ]
                transform_index = next(
                    i for i, line in enumerate(block)
                    if re.match(r"\s*Transform\s*:", line, re.IGNORECASE)
                )
                indent = re.match(r"\s*", block[transform_index]).group(0)
                block[transform_index + 1:transform_index + 1] = [
                    f"{indent}Lag: {lag_times[subbasin_name]:.6f}",
                    f"{indent}Unitgraph Type: STANDARD",
                ]
                lines[index + 1:end_index] = block
                end_index = index + len(block) + 1
            index = end_index + 1

        missing_names = set(lag_times) - updated_names
        if missing_names:
            raise ValueError(
                "GeoJSON subbasins have no matching elements in HEC-HMS basin file: "
                + ", ".join(sorted(missing_names))
            )
        basin_names = set(re.findall(r"^Subbasin:\s*(.+?)\s*$", original_content, re.MULTILINE))
        if basin_names != set(lag_times):
            raise ValueError(
                "HEC-HMS subbasins and GeoJSON lag records do not match; "
                f"missing={sorted(basin_names - set(lag_times))}, "
                f"unexpected={sorted(set(lag_times) - basin_names)}."
            )

        updated_content = "\r\n".join(lines) + "\r\n"
        if updated_content != original_content:
            with open(basin_path, "w", encoding="ascii", newline="") as basin_file:
                basin_file.write(updated_content)
        logging.info(
            "Applied SCS Unit Hydrograph transform and lag time to %d subbasins in %s.",
            len(updated_names), basin_path,
        )

    def sync_hms_project(self):
        hms_path = getattr(self.config, "hms_file", None)

        if not hms_path:
            project_dir = getattr(self.config, "project_dir", ".")
            projetct_name = getattr(self.config, "project_name", "tcc")
            hms_path = os.path.join(project_dir, f"{projetct_name}.hms")

        if not os.path.exists(hms_path):
            logging.warning(f"HMS file path is invalid or does not exist: {hms_path}")
            return

        met_name = self.config.met_model_name
        control_name = (
          os.path.basename(self.config.control_file)
          .replace(".control", "")
          .strip()
      )

        now = datetime.now()
        date_str = self._format_hec_date(datetime.now())
        time_str = datetime.now().strftime("%H:%M")

        with open(hms_path, 'r', encoding='ascii', errors='ignore') as file:
            original_content = file.read()
        content = original_content

        # HEC-HMS registers a meteorologic model under the Precipitation
        # identifier in the project file. Remove the old invalid block before
        # synchronizing so existing projects are repaired and reruns stay clean.
        lines = content.splitlines()
        cleaned_lines = []
        in_project_block = False
        project_dss_updated = False
        project_dss_filename = self.config.hms_dss_filename
        generated_headers = {
            f"Precipitation: {met_name}",
            f"Control: {control_name}",
            f"Control:{control_name}",
        }
        skipping_generated_block = False
        for line in lines:
            stripped_line = line.strip()
            if stripped_line.startswith("Project:"):
                in_project_block = True
            if in_project_block and stripped_line.startswith("DSS File Name:"):
                indentation = line[:len(line) - len(line.lstrip())]
                cleaned_lines.append(
                    f"{indentation}DSS File Name: {project_dss_filename}"
                )
                project_dss_updated = True
                continue
            if in_project_block and stripped_line == "End:":
                if not project_dss_updated:
                    cleaned_lines.append(
                        f"     DSS File Name: {project_dss_filename}"
                    )
                    project_dss_updated = True
                in_project_block = False
            if stripped_line.startswith("Meteorology:") or stripped_line in generated_headers:
                skipping_generated_block = True
                continue
            if skipping_generated_block:
                if line.strip() == "End:":
                    skipping_generated_block = False
                continue
            cleaned_lines.append(line)
        content = "\n".join(cleaned_lines).rstrip()

        met_file = os.path.basename(self.config.met_file)
        control_file = os.path.basename(self.config.control_file)
        new_blocks = [
            f"Precipitation: {met_name}\n"
            f"     Filename: {met_file}\n"
            f"     Description: Gerado via automacao Python\n"
            f"     Last Modified Date: {date_str}\n"
            f"     Last Modified Time: {time_str}\n"
            f"End:\n",
            f"Control: {control_name}\n"
            f"     Filename: {control_file}\n"
            f"     Description: Gerado via automacao Python\n"
            f"     Last Modified Date: {date_str}\n"
            f"     Last Modified Time: {time_str}\n"
            f"End:\n",
        ]

        updated_content = content.rstrip()
        if new_blocks:
            updated_content += "\n\n" + "\n".join(new_blocks).rstrip()

        if updated_content != original_content.rstrip():
            with open(hms_path, 'w', encoding='ascii', newline='\r\n') as f:
                f.write(updated_content + "\n")
            logging.info(".hms file updated and synchronized with success!")
        else:
            logging.info("All components were already registered in the .hms file.")
        return True

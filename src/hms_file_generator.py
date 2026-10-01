from jinja2 import Template
from datetime import datetime
import logging
import os

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

        template = Template(self.config.GAGE_TEMPLATE)
        output = template.render(gages= gages_data)

        if not gages_data:
            logging.warning("No entry for gage file. ")
            return
        
        now = datetime.now()
        str_date = self._format_hec_date(now)
        str_time = now.strftime("%H:%M")

        for g in gages_data:
            g['date'] = str_date
            g['time'] = str_time     

        try:
            with open(self.config.gage_file, 'w', encoding="ascii", newline="\r\n") as f:
                f.write(output.strip() + "\r\n")
            logging.info(f"Gage file created successfully at {self.config.gage_file}.")
        except IOError as e:
            logging.error(f"Unable to write gage file: {e}")

    def generate_met_file(self, subbasins_data: list):
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
            logging.info(f"Arquivo .met gerado: {self.config.met_file}")
        except IOError as e:
            logging.error(f"Erro ao escrever .met: {e}")


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
            end_date=self._format_hec_date(self.config.end_date),
        )

        try:
            with open(
                self.config.control_file, "w", encoding="ascii", newline="\r\n") as f:
                f.write(content.strip() + "\r\n")
            logging.info(f"Arquivo .control gerado: {self.config.control_file}")
        except IOError as e:
            logging.error(f"Erro ao escrever .control: {e}")

    def sync_hms_project(self):
        hms_path = self.config.hms_file
        if not hms_path or not os.path.exists(hms_path):
            logging.error(f"HMS file path is invalid or does not exist: {hms_path}")
            return False

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
            content = file.read()

        new_blocks = []

        if f'Meteorology: {met_name}' not in content:
            met_file = os.path.basename(self.config.met_file)
            new_blocks.append(f"Meteorology: {met_name}\r\n"
                f"     Filename: {met_file}\r\n"
                f"     Description: Gerado via automacao Python\r\n"
                f"     Last Modified Date: {date_str}\r\n"
                f"     Last Modified Time: {time_str}\r\n"
                f"End:\r\n"
            )

        if f'Control: {control_name}' not in content:
            control_file = os.path.basename(self.config.control_file)
            new_blocks.append(f"Control:{control_name}\r\n"
                f"     Filename: {control_file}\r\n"
                f"     Description: Gerado via automacao Python\r\n"
                f"     Last Modified Date: {date_str}\r\n"
                f"     Last Modified Time: {time_str}\r\n"
                f"End:\r\n"
            )

        if new_blocks:
            with open(hms_path, 'a', encoding='ascii', newline='\r\n') as f:
                f.write("\r\n" + "\r\n".join(new_blocks))
            logging.info(".hms file updated and synchronized with success!")
        else:
            logging.info("All components were already registered in the .hms file.")
        return True
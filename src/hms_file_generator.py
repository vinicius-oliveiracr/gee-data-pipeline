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
            1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
            7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December"
        }

        return f"{date_obj.day:02d}{months[date_obj.month]}{date_obj.year}"

    def sync_hms_project(self, gage_names: list):
        hms_path = self.config.hms_file
        if not hms_path or not os.path.exists(hms_path):
            logging.error(f"HMS file path is invalid or does not exist: {hms_path}")
            return False

        project_name = self.config.project_name
        met_name = self.config.met_model_name
        control_name = self.config.control_file

        date_str = self._format_hec_date(datetime.now())
        time_str = datetime.now().strftime("%H:%M")

        with open(hms_path, 'r', encoding='ascii', errors='ignore') as file:
            content = file.read()

        new_blocks = []

        if f'Meteorology: {met_name}' not in content:
            met_file = os.path.basename(self.config.met_file)
            new_blocks.append(f"Meteorology: {met_name}\n"
                f"     Filename: {met_file}\n"
                f"     Description: Gerado via automacao Python\n"
                f"     Last Modified Date: {date_str}\n"
                f"     Last Modified Time: {time_str}\n"
                f"End:\n\n"
            )

        if f'Control: {control_name}' not in content:
            control_file = os.path.basename(self.config.control_file)
            new_blocks.append(f"Control: {control_name}\n"
                f"     Filename: {control_file}\n"
                f"     Description: Gerado via automacao Python\n"
                f"     Last Modified Date: {date_str}\n"
                f"     Last Modified Time: {time_str}\n"
                f"End:\n\n"
            )

        gage_file = os.path.basename(self.config.gage_file)
        for g_name in gage_names:
            if f"Gage: {g_name}" not in content:
                new_blocks.append(
                    f"Gage: {g_name}\n"
                    f"     Filename: {gage_file}\n"
                    f"     Description: Gerado via automacao Python\n"
                    f"     Last Modified Date: {date_str}\n"
                    f"     Last Modified Time: {time_str}\n"
                    f"End:\n\n"
                )

        if new_blocks:
            with open(hms_path, 'a', encoding='ascii', newline='\r\n') as f:
                f.write("\r\n" + "".join(new_blocks))
            logging.info(".hms file updated and synchronized with success!")
        else:
            logging.info("All components were already registered in the .hms file.")

        return True

    
    def generate_gage_file(self, gage_data: list):
        if not gage_data:
            logging.warning("No entry for gage file. ")
            return
        
        now = datetime.now()
        str_date = self._format_hec_date(now)
        str_time = now.strftime("%H:%M")

        for g in gage_data:
            g['date'] = str_date
            g['time'] = str_time

        template = Template(self.config.GAGE_TEMPLATE)
        output = template.render(gages= gage_data)

        try:
            with open(self.config.gage_file, 'w') as f:
                f.write(output)
            logging.info(f"Gage file created successfully at {self.config.gage_file}.")
        except IOError as e:
            logging.error(f"Unable to write gage file: {e}")

    def generate_met_file(self, gage_data: list):
        if not gage_data:
            logging.warning("No subbasin found. Met file will not be created.")
            return
        
        assignments = []
        
        for entry in gage_data:
            try:
                subbasin_id = entry['name'].split('_')[-1]
                
                assignments.append({
                    'subbasin': f"Subbasin-{subbasin_id}",
                    "gage": entry['name']
                })
            except Exception as e:
                logging.warning(f"Error processing gage '{entry['name']}': {e}")
        

        template = Template(self.config.MET_TEMPLATE)
        output_context = template.render(
            met_name = self.config.met_model_name,
            basin_name = self.config.BASIN_MODEL_NAME,
            subbasins = assignments,
            dt = datetime.now()
        )

        output_context = output_context.replace('\xa0', ' ')
        output_context = output_context.replace('\nend', '\nEnd')
        lines = [line.rstrip() for line in output_context.splitlines() if line.strip()]

        final_content = "\r\n".join(lines) + "\r\n"

        try:
            with open(self.config.met_file, 'w', encoding='ascii', newline='\r\n') as file:
                file.write(final_content)
                logging.info(f"Met file created successfully at {self.config.met_file}.")
        except IOError as e:
            logging.error(f"Writing met file failed: {e}")

    def generate_control_file(self):
        start_str = self._format_hec_date(self.config.start_date)
        end_str = self._format_hec_date(self.config.end_date)

        control_content = f"""Control: Control_file
    Start Date: {start_str}
    Start Time: 00:00
    End Date: {end_str}
    End Time: 00:00
    Time Interval: 1440
End:
"""
            
        try:
            with open(self.config.control_file, 'w') as f:
                f.write(control_content)
            logging.info(f"Control file created successfully: {self.config.control_file}")
        except UnicodeEncodeError:
            logging.error("Error: Non-ASCII characters found in basin or gage name.")
        except IOError as e:
            logging.error(f"Failed to create control file: {e}.")
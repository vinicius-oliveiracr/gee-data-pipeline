import inspect
import os
import shutil
import textwrap
from pathlib import Path
from pathlib import PureWindowsPath
from dotenv import load_dotenv
from datetime import datetime
import logging

load_dotenv()
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def parse_date(date_val):
    if isinstance(date_val, str):
        try:
            return datetime.strptime(date_val, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid date format: {date_val}. Expected format: YYYY-MM-DD")

        
class Config:
    def __init__(self,
                 shp_path=None,
                 exit_path=None,
                 start_date=None,
                 end_date=None,
                 old_gage_file=None,
                 dss_file=None,
                 project_name=None,
                 control_file=None):

        self.shp_path = shp_path or os.getenv("FILE_PATH")
        self.exit_path = exit_path or os.getenv("EXIT_PATH")

        self.default_start = datetime(2018, 1, 1)
        self.default_end = datetime(2022, 12, 31)
        
        # Tratamento de erro na conversão de datas (onde um ValueError PODE acontecer)
        try:
            self.start_date = parse_date(start_date) if start_date else self.default_start
            self.end_date = parse_date(end_date) if end_date else self.default_end
        except ValueError as e:
            logging.error(f"Erro ao converter data: {e}")
            raise e

        self.precipitation_scale = int(os.getenv("PRECIPITATION_SCALE", "5000"))
        if self.precipitation_scale <= 0:
            raise ValueError("PRECIPITATION_SCALE must be a positive number of meters.")

        self.old_gage_file = old_gage_file or os.getenv("OLD_GAGE_FILE")
        self.dss_file = dss_file or os.getenv("DSS_FILE")
        self.project_name = project_name or os.getenv("PROJECT_NAME")
        self.control_file = control_file or os.getenv("CONTROL_FILE")
        self.gcn_raster_path = os.path.join(BASE_DIR, "assets", "GCN.tif")
        self.gcn_geojson_path = os.path.join(
            BASE_DIR, "saidas", "subbacias_corrigidas_com_gcn.geojson"
        )
        self.api_key = os.getenv("API_KEY")
        self.account = os.getenv("EE_ACCOUNT")
        self.private_key_path = os.getenv("PRIVATE_KEY_PATH")

        # Validação explícita de presença de valores essenciais
        essential_vars = {
            "PRIVATE_KEY_PATH": self.private_key_path,
            "PROJECT_NAME": self.project_name,
            "FILE_PATH (shp_path)": self.shp_path,
            "EXIT_PATH": self.exit_path
        }
        
        missing = [key for key, value in essential_vars.items() if not value]
        if missing:
            logging.warning(f"Essential variables missing: {', '.join(missing)}")
            


class DssConfig:
    def __init__(self, 
                dss_file=None,
                hms_file = None,
                project_name=None,
                gage_file=None,
                met_file=None,
                basin_name=None,
                csv_file=None,
                control_file=None,
                start_date=None,
                end_date=None):
        self.default_start = datetime(2018, 1, 1)
        self.default_end = datetime(2022, 12, 31)
        self.csv_file = csv_file or os.getenv("CSV_FILE")
        self.hms_file = hms_file or os.getenv("HMS_FILE")
        self.basin_name = basin_name or os.getenv("BASIN_NAME")
        self.start_date = parse_date(start_date) if start_date else self.default_start
        self.end_date = parse_date(end_date) if end_date else self.default_end

        if not self.hms_file:
            raise ValueError("Selecione ou configure o arquivo do projeto HEC-HMS (.hms).")

        # Accept Windows paths in .env when the pipeline runs under WSL.
        windows_path = PureWindowsPath(self.hms_file)
        if os.name != "nt" and windows_path.drive:
            drive = windows_path.drive.rstrip(":").lower()
            self.hms_file = str(Path("/mnt") / drive / Path(*windows_path.parts[1:]))

        self.hms_file = os.path.abspath(os.path.expanduser(self.hms_file))
        if not self.hms_file.lower().endswith(".hms"):
            raise ValueError(f"O arquivo do projeto deve ter extensão .hms: {self.hms_file}")
        if not os.path.isfile(self.hms_file):
            raise FileNotFoundError(f"Arquivo HEC-HMS não encontrado: {self.hms_file}")

        self.project_dir = os.path.dirname(self.hms_file)
        self.project_name = os.path.splitext(os.path.basename(self.hms_file))[0]
        try:
            self.project_name.encode("ascii")
        except UnicodeEncodeError as error:
            raise ValueError(
                "O nome do projeto HMS precisa usar caracteres ASCII para os arquivos HEC-HMS gerados."
            ) from error
        if project_name and project_name != self.project_name:
            logging.warning(
                "PROJECT_NAME/HMS_PROJECT_NAME ignorado; o nome do projeto será derivado do arquivo .hms."
            )

        if not self.basin_name:
            self.basin_name = "pds"
        self.basin_file = os.path.join(self.project_dir, f"{self.basin_name}.basin")

        base_dir = Path(__file__).resolve().parent.parent
        self.gcn_geojson_path = str(
            base_dir / "saidas" / "subbacias_corrigidas_com_gcn.geojson"
        )
        self.local_output_dir = base_dir / "saidas" / "hms_export" / self.project_name
        self.local_output_dir.mkdir(parents=True, exist_ok=True)

        self.dss_file = str(self.local_output_dir / f"{self.project_name}.dss")
        self.gage_file = str(self.local_output_dir / f"{self.project_name}.gage")
        self.met_file = str(self.local_output_dir / f"{self.project_name}.met")
        self.control_file = str(self.local_output_dir / f"{self.project_name}.control")
        self.hms_dss_filename = str(PureWindowsPath("data") / f"{self.project_name}.dss")

        if not self.csv_file:
            logging.warning("CSV_FILE is not configured; DSS generation will require a CSV path.")

        self.B_PART = "PRECIP"
        self.C_PART = "PRECIP-INC"       
        self.E_PART = "1DAY"             
        self.F_PART = "GPM-CHIRPS"
        self.INTERVAL = 1                
        self.DATA_TYPE = "PER-INC"
        self.UNITS = "MM"

        self.met_model_name = self.project_name
        self.control_name = self.project_name
        self.GAGE_TEMPLATE = textwrap.dedent("""\
{% for gage in gages %}
Gage: {{ gage.name }}
     Gage: {{ gage.name }}
     Gage Type: Precipitation
     Precipitation Type: Incremental
     Last Modified Date: {{ date_str }}
     Last Modified Time: {{ time_str }}
     Reference Height Units: {{ gage.height_units | default('Meters') }}
     Reference Height: {{ gage.height | default('10.0') }}
     Units: {{ gage.units }}
     Data Type: {{ gage.data_type }}
     Data Source Type: Single Record HEC-DSS
     Variant: Variant-1
     Last Variant Modified Date: {{ date_str }}
     Last Variant Modified Time: {{ time_str }}
     Default Variant: Yes
     DSS File Name: {{ gage.dss_file }}
     DSS Pathname: {{ gage.pathname }}
     Start Time: {{ gage.start_time }}
     End Time: {{ gage.end_time }}
     End Variant: Variant-1
End:

{% endfor %}""")

        self.MET_TEMPLATE = textwrap.dedent("""
Meteorology:{{ met_name }}
     Description: Met model gerado automaticamente
     Last Modified Date: {{ date_str }}
     Last Modified Time: {{ time_str }}
     Version: 4.13
     Unit System: Metric
     Set Missing Data to Default: No
     Precipitation Method: Specified Average
     Use Basin Model: {{ basin_name }}
End:

Precip Method Parameters: Specified Average
     Allow Depth Override: No
End:

{% for item in subbasins %}
Subbasin: {{ item.subbasin }}
     Gage: {{ item.gage }}
End:
{% endfor %}""")

        self.CONTROL_TEMPLATE = textwrap.dedent(
"""Control: {{ control_name }}
     Last Modified Date: {{ date_str }}
     Last Modified Time: {{ time_str }}
     Version: 4.13
     Description: Automacao Python TCC
     Start Date: {{ start_date }}
     Start Time: 00:00
     End Date: {{ end_date }}
     End Time: 00:00
     Time Interval: 1440
End:""")

    def build_dss_pathname(self, subbasin_id, date_part=""):
        """Build a six-part DSS pathname for storage or HEC-HMS references."""
        parts = (
            str(subbasin_id),
            self.B_PART,
            self.C_PART,
            date_part,
            self.E_PART,
            self.F_PART,
        )
        return "/" + "/".join(parts) + "/"

    def export_to_hec_hms_dir(self):
        print(f"Copiando arquivos de saída para {self.project_dir}...")
        for src_file in self.local_output_dir.glob("*.*"):
            if src_file.suffix.lower() == ".dss":
                data_dir = os.path.join(self.project_dir, "data")
                os.makedirs(data_dir, exist_ok=True)
                dest_file = os.path.join(data_dir, src_file.name)
            else:
                dest_file = os.path.join(self.project_dir, src_file.name)
            shutil.copy2(src_file, dest_file)
        print("✅ Files exported with success to HEC-HMS!")

    HMS_CONFIG = {
        "project_name": "tcc",
        "description": "automação hidrológica para o tcc",
        "version": "4.13",
        "filepath_separator": "\\",
        "dss_file": "tcc.dss",
        "timezone": "America/Sao_Paulo",
        "basin": {
            "name": "pds",
            "filename": "pds.basin"
        },
        "Meteorology": {
            "name": "met_automatico",
            "filename": "met_automatico.met"
        },
        "control": {
            "name": "control_automatico",
            "filename": "control_automatico.control"
        },
        "gages": [f"S_{i}" for i in range(1, 61)],
        "gage_filename": "tcc.gage"
    }

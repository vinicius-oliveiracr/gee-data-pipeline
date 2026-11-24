import ee
import sys
from google.oauth2 import service_account

def initialize_gee(config):
    """Authenticate with the configured service account and initialize Earth Engine."""
    try:
        credentials = service_account.Credentials.from_service_account_file(
            config.private_key_path,
            scopes = [
                'https://www.googleapis.com/auth/earthengine',
                'https://www.googleapis.com/auth/cloud-platform'
            ]
        )

        ee.Initialize(credentials, project = config.project_name)
        print("Earth Engine authenticated successfully using google-auth!")
    except Exception as e:
        print(f"Fatal error while authenticating EE: {e}.")
        sys.exit(1)


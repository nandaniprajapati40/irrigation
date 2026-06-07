import ee
import json
import logging
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_EE_INITIALIZED = False


def init_ee():
    global _EE_INITIALIZED

    if _EE_INITIALIZED:
        return

    try:
        # Path from docker environment
        key_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

        if not key_file:
            raise RuntimeError(
                "GOOGLE_APPLICATION_CREDENTIALS environment variable not set"
            )

        if not os.path.exists(key_file):
            raise RuntimeError(
                f"Service account key file not found: {key_file}"
            )

        # Load service account email from JSON key
        with open(key_file) as f:
            service_account = json.load(f)["client_email"]

        # Create credentials
        credentials = ee.ServiceAccountCredentials(
            service_account,
            key_file
        )

        # Optional project ID
        project_id = os.getenv("EE_PROJECT_ID")

        if project_id:
            ee.Initialize(
                credentials=credentials,
                project=project_id
            )
        else:
            ee.Initialize(credentials=credentials)

        # Test request
        ee.Number(1).getInfo()

        _EE_INITIALIZED = True

        logger.info(
            f"Earth Engine initialized successfully "
            f"with service account: {service_account}"
        )

    except Exception as e:
        logger.exception("Earth Engine initialization failed")

        raise RuntimeError(
            f"Earth Engine initialization failed: {e}"
        )
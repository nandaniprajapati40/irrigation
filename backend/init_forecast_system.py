import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.append(str(Path(__file__).parent))

from config import SARIMAX_CONFIG, GEOSERVER, DIRECTORIES
from init_geoserver import GeoServerAPI
import rasterio
import numpy as np

def initialize_system():
    """Initialize the forecast system"""
    print("=" * 60)
    print("INITIALIZING FORECAST SYSTEM")
    print("=" * 60)
    
    # 1. Check SARIMAX model exists
    model_path = SARIMAX_CONFIG["model_path"]
    if not model_path.exists():
        print(f"SARIMAX model not found at: {model_path}")
        print("Please train the model first using models.py")
        return False
    else:
        print(f"SARIMAX model found: {model_path}")
    
    # 2. Initialize GeoServer
    print("\nInitializing GeoServer...")
    try:
        geoserver = GeoServerAPI()
        
        # Create workspace and datastore
        geoserver.create_workspace()
        geoserver.create_datastores()
        
        # Create CWR forecast layer
        layer_name = GEOSERVER['layers']['cwr']['name']
        
        # Check if we have a template raster
        template_path = SARIMAX_CONFIG["raster_template"]
        if template_path.exists():
            print(f"Uploading template raster to GeoServer...")
            # Enable time dimension
            geoserver.enable_time_dimension(layer_name)
            print(f"GeoServer layer '{layer_name}' ready with time dimension")
        else:
            print(f"Template raster not found: {template_path}")
            print("Creating basic layer configuration...")
    
    except Exception as e:
        print(f"GeoServer initialization failed: {e}")
        return False
    
    # 3. Create forecast directory structure
    print("\nCreating directory structure...")
    forecast_dir = SARIMAX_CONFIG["forecast_raster_dir"]
    forecast_dir.mkdir(parents=True, exist_ok=True)
    print(f"Forecast directory: {forecast_dir}")
    
    # 4. Get system info
    print("\nSystem Information:")
    print(f"   Max Forecast Days: {SARIMAX_CONFIG['max_forecast_days']}")
    print(f"   Last Observed Date: {SARIMAX_CONFIG['last_observed_date']}")
    print(f"   Historical Data: {DIRECTORIES['processed']['cwr']}")
    print(f"   Forecast Output: {forecast_dir}")
    print("\n" + "=" * 60)
    print("FORECAST SYSTEM INITIALIZED SUCCESSFULLY")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Access the API: http://localhost:8000/docs")
    print("2. Use date picker in UI to select dates")
    print("3. Historical dates will show existing data")
    print("4. Future dates will trigger SARIMAX forecasts")
    print("5. Forecasts are cached for future use")
    
    return True

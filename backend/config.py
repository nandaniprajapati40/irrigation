import os
import logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# The service intentionally does not emit or persist application logs.
logging.disable(logging.CRITICAL)

BASE_DIR = Path(__file__).resolve().parent


# ─────────────────────────────────────────────────────────────────────────────
# BOUNDARY HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _gadm_boundary() -> dict | None:
    """
    Fetch Udham Singh Nagar district boundary from the GADM v4.1
    public REST endpoint.  Returns the same shape as get_exact_boundary()
    or None on failure.
    """
    try:
        import urllib.request, json

        url = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_IND_2.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())

        features = [
            f for f in data.get("features", [])
            if f.get("properties", {}).get("NAME_1", "").lower() == "uttarakhand"
            and "udham" in f.get("properties", {}).get("NAME_2", "").lower()
        ]
        if not features:
            print("[config] GADM: district not found in response")
            return None

        feature = features[0]
        geom    = feature["geometry"]

        def _all_coords(g):
            gt = g["type"]
            if gt == "Polygon":
                for ring in g["coordinates"]:
                    yield from ring
            elif gt == "MultiPolygon":
                for poly in g["coordinates"]:
                    for ring in poly:
                        yield from ring

        lons = [c[0] for c in _all_coords(geom)]
        lats = [c[1] for c in _all_coords(geom)]
        west, east = min(lons), max(lons)
        south, north = min(lats), max(lats)

        print(f"[config] GADM boundary loaded — bbox: W={west:.4f} E={east:.4f} "
              f"S={south:.4f} N={north:.4f}")
        return {
            "bounds": {"north": north, "south": south, "west": west, "east": east},
            "center": [(west + east) / 2, (south + north) / 2],
            "geojson": {"type": "FeatureCollection", "features": [feature]},
        }
    except Exception as e:
        print(f"[config] GADM fetch failed: {e}")
        return None

def _osm_boundary() -> dict | None:
    """
    Load boundary from local GeoJSON file.
    """
    try:
        import json

        boundary_file = BASE_DIR / "data" / "boundaries" / "usn_boundary.geojson"

        with open(boundary_file, "r") as f:
            data = json.load(f)

        features = data.get("features", [])
        if not features:
            print("[config] Local boundary file has no features")
            return None

        feature = features[0]

        bbox = feature.get("bbox")

        if not bbox:
            # compute bbox manually
            geom = feature["geometry"]

            def _all_coords(g):
                gt = g["type"]
                if gt == "Polygon":
                    for ring in g["coordinates"]:
                        yield from ring
                elif gt == "MultiPolygon":
                    for poly in g["coordinates"]:
                        for ring in poly:
                            yield from ring

            lons = [c[0] for c in _all_coords(geom)]
            lats = [c[1] for c in _all_coords(geom)]

            west, east = min(lons), max(lons)
            south, north = min(lats), max(lats)
        else:
            west, south, east, north = bbox

        center = [(west + east) / 2, (south + north) / 2]

        print("[config] Local boundary loaded successfully")

        return {
            "bounds": {
                "north": north,
                "south": south,
                "west": west,
                "east": east,
            },
            "center": center,
            "geojson": {
                "type": "FeatureCollection",
                "features": [feature],
            },
        }

    except Exception as e:
        print(f"[config] Local boundary load failed: {e}")
        return None

def get_exact_boundary() -> dict:
    """
    Return boundary dict with keys: bounds, center, geojson.

    Priority:
      1. OSM / Nominatim  — matches CartoDB Street basemap exactly
      2. GADM v4.1        — Census-2011 accurate
      3. Static fallback  — hand-verified tight bbox
    """
    result = _osm_boundary()
    if result:
        return result

    result = _gadm_boundary()
    if result:
        return result

    print("[config] Using static hand-verified bbox fallback for USN district")
    return {
        "bounds": {
            "north": 29.4400,
            "south": 28.8900,
            "west":  78.8800,
            "east":  80.1040,
        },
        "center": [79.4920, 29.1650],
        "geojson": {"type": "FeatureCollection", "features": []},
    }


# Load boundary once at module level
EXACT_BOUNDARY = get_exact_boundary()


# ─────────────────────────────────────────────────────────────────────────────
# STUDY AREA
# ─────────────────────────────────────────────────────────────────────────────
STUDY_AREA = {
    "name":             "Udham Singh Nagar",
    "state":            "Uttarakhand",
    "district_code":    "UA",
    "bounds":           EXACT_BOUNDARY["bounds"],
    "center":           EXACT_BOUNDARY["center"],
    "area_sqkm":        3055,
    "crs":              "EPSG:4326",
    "geojson":          EXACT_BOUNDARY["geojson"],
    "boundary_source":  "OSM/Nominatim → GADM v4.1",
}


# ─────────────────────────────────────────────────────────────────────────────
# DATABASE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
MONGODB = {
    "uri":      os.getenv("MONGODB_URI", "mongodb://mongodb:27017"),
    #"uri":      os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
    "database": os.getenv("MONGODB_DB",  "irrigation_db"),
}


# ─────────────────────────────────────────────────────────────────────────────
# DIRECTORIES
# ─────────────────────────────────────────────────────────────────────────────
DIRECTORIES = {
    "raw": {
        "sentinel2":  BASE_DIR / "data" / "raw" / "sentinel2",
        "insat_pet":  BASE_DIR / "data" / "raw" / "insat_pet",
        "insat_rain": BASE_DIR / "data" / "raw" / "insat_rain",
    },
    "processed": {
        "savi":  BASE_DIR / "data" / "processed" / "savi",
        "kc":    BASE_DIR / "data" / "processed" / "kc",
        "cwr":   BASE_DIR / "data" / "processed" / "cwr",
        "iwr":   BASE_DIR / "data" / "processed" / "iwr",
        "masks": BASE_DIR / "data" / "processed" / "masks",
        "ETc":   BASE_DIR / "data" / "processed" / "ETc",
    },
    "export": {
        "geoserver": BASE_DIR / "data" / "export" / "geoserver",
    },
    "models": BASE_DIR / "data" / "models",
}

SENTINEL2_BAND_INDICES = {
    "blue":  1,   # B2  – 490 nm
    "green": 2,   # B3  – 560 nm
    "red":   3,   # B4  – 670 nm  (used for SAVI/NDVI)
    "nir":   4,   # B8  – 842 nm  (used for SAVI/NDVI)
}


SENTINEL2_EXPECTED_BANDS = 4

# ─────────────────────────────────────────────────────────────────────────────
# WHEAT CROP PARAMETERS  (FAO-56 Rabi wheat)
# ─────────────────────────────────────────────────────────────────────────────
WHEAT_PARAMS = {
    "crop":           "wheat",
    "season":         "rabi",
    "planting_month": 11,    # November — used by compute_seasonal_total
    "planting_day":   1,    # Nov 15 = earliest Rabi start (thesis Table 4)
    "harvest_month":  4,
    "harvest_day":    30,    # Apr 16 = latest scene in thesis Table 4
    "growth_stages": {
        "initial":     {"days": 30, "kc": 0.30},
        "development": {"days": 40, "kc": 0.70},
        "mid":         {"days": 50, "kc": 1.15},
        "late":        {"days": 30, "kc": 0.40},
    },
    "savi_kc": {
        "slope":     1.2088,
        "intercept": 0.5378,
    },
    "root_depth": {"initial": 0.3, "max": 1.15},
}
SARIMAX_CONFIG = {
    "model_path":           BASE_DIR / "data" / "models" / "sarimax_wheat_cwr.pkl",
    "iwr_model_path":       BASE_DIR / "data" / "models" / "sarimax_wheat_iwr.pkl",
    "max_forecast_days":    15,
    "historical_data_path": BASE_DIR / "data" / "processed" / "cwr",
    # FIX-CONFIG-3: "raster_template" key removed to avoid confusion with
    # rasterio profile templates.  The actual template raster for writing
    # forecast arrays is derived at runtime from the most-recent Kc history
    # raster (see history_path("kc", "today") in main.py).
    "forecast_raster_dir":  BASE_DIR / "data" / "export" / "forecast" / "rasters",
}

# ─────────────────────────────────────────────────────────────────────────────
# GEOSERVER CONFIG
# ─────────────────────────────────────────────────────────────────────────────
GEOSERVER = {
    "url":       os.getenv("GEOSERVER_URL",      "http://localhost/geoserver"),
    #"url":       os.getenv("GEOSERVER_URL",      "http://localhost:8080/geoserver"),
    "workspace": os.getenv("GEOSERVER_WORKSPACE", "irrigation"),
    "username":  os.getenv("GEOSERVER_USER",      "admin"),
    "password":  os.getenv("GEOSERVER_PASS",      "geoserver"),
}


# ─────────────────────────────────────────────────────────────────────────────
# AUTO-CREATE DIRECTORIES
# ─────────────────────────────────────────────────────────────────────────────
def create_directories():
    for category in DIRECTORIES.values():
        if isinstance(category, dict):
            for path in category.values():
                path.mkdir(parents=True, exist_ok=True)
        else:
            category.mkdir(parents=True, exist_ok=True)


create_directories()

print(f"[config] Base dir  : {BASE_DIR}")
print(f"[config] Bounds    : {STUDY_AREA['bounds']}")
print(f"[config] Center    : {STUDY_AREA['center']}")
print(f"[config] DB        : {MONGODB['uri']} / {MONGODB['database']}")
print(f"[config] S2 bands  : Red=Band{SENTINEL2_BAND_INDICES['red']}  "
      f"NIR=Band{SENTINEL2_BAND_INDICES['nir']}  "
      f"(in {SENTINEL2_EXPECTED_BANDS}-band GeoTIFF export)")

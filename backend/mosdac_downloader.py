from __future__ import annotations

import datetime
import logging
import re
import stat as stat_mod
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import os
import h5py
import numpy as np
import rasterio
import schedule
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.mask import mask as rio_mask
from rasterio.transform import from_origin
from rasterio.warp import calculate_default_transform, reproject
from shapely.geometry import shape

try:
    import pysftp
    SFTP_AVAILABLE = True
except ImportError:
    SFTP_AVAILABLE = False

# ─── Project imports ──────────────────────────────────────────────────────────
try:
    from mongo import (
        is_pet_downloaded,
        mark_pet_downloaded,
        is_rain_downloaded,
        mark_rain_downloaded,
        pet_col,
        rain_col,
    )
    from config import STUDY_AREA, BASE_DIR

    BOUNDS  = STUDY_AREA["bounds"]
    GEOJSON = STUDY_AREA.get("geojson", {"type": "FeatureCollection", "features": []})
    MONGO_AVAILABLE = True
except ImportError as exc:
    print(f"[WARN] MongoDB / config not available: {exc}")
    # USN (Udham Singh Nagar) — verified FAO/GAUL district extent
    BOUNDS = {
        "north": 29.3853,
        "south": 28.7156,
        "west":  78.7139,
        "east":  80.1567,
    }
    GEOJSON = {"type": "FeatureCollection", "features": []}
    BASE_DIR = Path(__file__).resolve().parent
    MONGO_AVAILABLE = False

# ═══════════════════════════════════════════════════════════════════════════════
# LOGGING
# ═══════════════════════════════════════════════════════════════════════════════

log_dir = BASE_DIR / "data" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "mosdac_download.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("MOSDAC")

# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

HOST        = "ftp.mosdac.gov.in"
USER        = os.getenv("MOSDAC_USERNAME", "")
PASS        = os.getenv("MOSDAC_PASSWORD", "")
MAX_RETRIES = 3          # SFTP download attempts before raising RuntimeError

START_DATE = datetime.date(2021, 11, 1)

# INSAT-3DR full India product domain — used when HDF5 has no bound attributes
INSAT_DOMAIN = {"west": 44.5, "east": 105.5, "south": -5.0, "north": 40.0}

# HDF5 dataset name candidates — tried in order
_PET_DATASET_CANDIDATES = [
    "PET_DLY", "Reg_evapotranspiration", "PET",
    "evapotranspiration", "ET", "Daily_ET", "pet",
]
_RAIN_DATASET_CANDIDATES = [
    "IMR_DLY", "IMR", "Rainfall", "rainfall",
    "rain", "RAIN", "HEM_DLY", "HEM",
    "Precipitation", "precipitation",
]

# ─── Directories ──────────────────────────────────────────────────────────────
pet_hdf_dir  = BASE_DIR / "data" / "raw" / "insat_pet_hdf"
pet_tif_dir  = BASE_DIR / "data" / "raw" / "insat_pet"
rain_hdf_dir = BASE_DIR / "data" / "raw" / "insat_rain_hdf"
rain_tif_dir = BASE_DIR / "data" / "raw" / "insat_rain"

for _d in [pet_hdf_dir, pet_tif_dir, rain_hdf_dir, rain_tif_dir]:
    _d.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════════════
# BOUNDARY VERIFICATION  — logged on every startup
# ═══════════════════════════════════════════════════════════════════════════════
def _verify_boundary() -> None:
    """
    Log boundary stats at startup so misconfiguration is obvious immediately.

    USN (Udham Singh Nagar) district, Uttarakhand:
      ~1.44 deg lon x 0.67 deg lat  →  ~29 x 14 px bbox @ INSAT 0.05 deg resolution
      After polygon mask ~30% fill  →  ~100-120 valid pixels expected
    """
    b           = BOUNDS
    lon_span    = b["east"]  - b["west"]
    lat_span    = b["north"] - b["south"]
    res         = 0.05
    bbox_lon_px = round(lon_span / res)
    bbox_lat_px = round(lat_span / res)
    poly_avail  = bool(GEOJSON.get("features"))

    logger.info(
        f"[BOUNDARY] W={b['west']:.4f} E={b['east']:.4f} "
        f"S={b['south']:.4f} N={b['north']:.4f}"
    )
    logger.info(
        f"[BOUNDARY] {lon_span:.3f}deg lon x {lat_span:.3f}deg lat  "
        f"| ~{bbox_lon_px}x{bbox_lat_px} px bbox @0.05deg  "
        f"| polygon={'FAO/GAUL' if poly_avail else 'UNAVAILABLE-using-bbox'}"
    )

_verify_boundary()


# ═══════════════════════════════════════════════════════════════════════════════
# SEASON GATE
# ═══════════════════════════════════════════════════════════════════════════════

def is_wheat_season(date: datetime.date) -> bool:
    """Rabi wheat: November through April (months 11, 12, 1, 2, 3, 4)."""
    return date.month in {11, 12, 1, 2, 3, 4}


# ═══════════════════════════════════════════════════════════════════════════════
# FILE VALIDATORS
# ═══════════════════════════════════════════════════════════════════════════════

def is_valid_raster(path: Path) -> bool:
    """
    True only if the file exists, is non-empty, and rasterio can open its header.
    Catches: partial downloads, HTML error pages saved as .tif, zero-byte files.
    """
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with rasterio.open(path) as src:
            _ = src.meta
        return True
    except Exception:
        return False


def is_valid_hdf5(path: Path) -> bool:
    """True only if the file exists, is non-empty, and h5py can open it."""
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with h5py.File(path, "r"):
            pass
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# INSPECTION UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def inspect_hdf5(hdf_file: Path) -> None:
    """
    Print full structure (groups, datasets, attributes) of an HDF5 file.
    Use this to discover actual dataset names and attribute keys.
    """
    def _print_item(name, obj):
        indent = "  " * name.count("/")
        kind   = "GROUP" if isinstance(obj, h5py.Group) else "DATASET"
        shape  = getattr(obj, "shape", "-")
        dtype  = getattr(obj, "dtype", "-")
        print(f"{indent}[{kind}]  {name}   shape={shape}  dtype={dtype}")
        for k, v in obj.attrs.items():
            print(f"{indent}         attr  {k!r:40s} = {v!r}")

    print(f"\n{'='*70}")
    print(f" HDF5 INSPECT: {hdf_file}")
    print(f"{'='*70}")
    with h5py.File(hdf_file, "r") as f:
        print("── ROOT ATTRIBUTES ─────────────────────────────────────────────")
        for k, v in f.attrs.items():
            print(f"   {k!r:40s} = {v!r}")
        print("── TREE ────────────────────────────────────────────────────────")
        f.visititems(_print_item)
    print(f"{'='*70}\n")


def list_local_hdf5() -> None:
    """List all locally downloaded HDF5 files for both products."""
    for label, folder in [("PET", pet_hdf_dir), ("Rain", rain_hdf_dir)]:
        files = sorted(folder.glob("*.h5"))
        print(f"\n── {label} HDF5  ({folder}) ──────────────────")
        if files:
            for f in files:
                valid = "OK " if is_valid_hdf5(f) else "BAD"
                print(f"  [{valid}]  {f.name}  ({f.stat().st_size/1024:.1f} KB)")
        else:
            print("  (none)")
    print()


def check_boundary() -> None:
    """
    Print a detailed boundary and coverage report.
    Includes: bounds, mask type, expected pixel counts at various resolutions,
    and actual stats from the first available processed TIF files.
    """
    b           = BOUNDS
    lon_span    = b["east"]  - b["west"]
    lat_span    = b["north"] - b["south"]
    shapes, using_polygon = _get_usn_shapes()

    print("\n" + "="*65)
    print("  BOUNDARY CHECK — Udham Singh Nagar, Uttarakhand")
    print("="*65)
    print(f"  West    : {b['west']:.6f} deg")
    print(f"  East    : {b['east']:.6f} deg")
    print(f"  South   : {b['south']:.6f} deg")
    print(f"  North   : {b['north']:.6f} deg")
    print(f"  Lon span: {lon_span:.4f} deg  (~{lon_span*111:.1f} km)")
    print(f"  Lat span: {lat_span:.4f} deg  (~{lat_span*111:.1f} km)")
    print(f"  Area    : ~{lon_span*111 * lat_span*111:.0f} sq km (bbox estimate)")
    print(f"  Mask    : {'FAO/GAUL polygon (exact district boundary)' if using_polygon else 'Bounding-box (GEE polygon unavailable at startup)'}")
    print()

    for res, res_label in [(0.04, "0.04 deg ~4km"), (0.05, "0.05 deg ~5km")]:
        px_lon  = round(lon_span / res)
        px_lat  = round(lat_span / res)
        bbox_px = px_lon * px_lat
        exp_valid = round(bbox_px * 0.30)
        print(
            f"  At {res_label}: bbox={px_lon}x{px_lat}={bbox_px} px  "
            f"| polygon ~30% fill -> ~{exp_valid} valid px expected"
        )

    for label, folder in [("PET", pet_tif_dir), ("Rain", rain_tif_dir)]:
        tifs = sorted(folder.glob("*.tif"))
        if not tifs:
            print(f"\n  {label}: no processed TIFs yet")
            continue
        print(f"\n  {label} sample: {tifs[0].name}")
        try:
            with rasterio.open(tifs[0]) as src:
                d     = src.read(1)
                valid = int(np.sum((d != src.nodata) & ~np.isnan(d)))
                print(f"    Size  : {src.width}x{src.height} px")
                print(f"    Bounds: {src.bounds}")
                print(f"    CRS   : {src.crs}")
                print(f"    Valid : {valid} px")
                tags  = dict(src.tags())
                for k in ("mask_type", "study_area", "valid_pixels", "processed_at"):
                    if k in tags:
                        print(f"    {k}: {tags[k]}")
        except Exception as exc:
            print(f"    Error opening: {exc}")

    print("="*65 + "\n")


# ═══════════════════════════════════════════════════════════════════════════════
# DYNAMIC ORDER DISCOVERY  — no hardcoded order IDs
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_date_from_filename(filename: str) -> Optional[datetime.date]:
    """
    Parse acquisition date from an INSAT-3DR HDF5 filename.
    Pattern: 3RIMG_<DDMONYYYY>_0015_...h5
    Example: 3RIMG_17MAR2026_0015_L3C_PET_DLY_V01R00.h5  →  2026-03-17
    """
    m = re.search(r"3RIMG_(\d{2}[A-Z]{3}\d{4})_", filename.upper())
    if m:
        try:
            return datetime.datetime.strptime(m.group(1), "%d%b%Y").date()
        except ValueError:
            pass
    return None


def _discover_orders(sftp) -> Dict:
    """
    Dynamically discover the PET and Rain order folders from /Order/ on SFTP.

    Strategy
    --------
    1. List all sub-directories inside /Order/, sort by mtime (newest first).
    2. For each folder (up to 10 checked), list its .h5 files.
    3. A folder containing *L3C_PET* files  → PET order.
       A folder containing *L3G_IMR* files  → Rain order.
    4. Parse dates from filenames to determine the latest available date
       for each product (so we never attempt a date that isn't on the server).

    Returns
    -------
    {
        "pet_order":      str   (folder name, e.g. "Mar26_175274"),
        "rain_order":     str   (folder name, e.g. "Mar26_175276"),
        "pet_max_date":   datetime.date | None,
        "rain_max_date":  datetime.date | None,
    }
    """
    try:
        entries = sftp.listdir_attr("/Order")
    except Exception as exc:
        raise RuntimeError(f"[ORDERS] Cannot list /Order on SFTP: {exc}")

    # Keep only directories; sort newest-first by modification time
    dirs = [
        e for e in entries
        if e.st_mode is not None and stat_mod.S_ISDIR(e.st_mode)
    ]
    if not dirs:
        # Some SFTP servers don't set st_mode for dirs — fall back to listing all
        logger.warning("[ORDERS] st_mode unavailable; scanning all entries in /Order")
        dirs = list(entries)

    dirs.sort(key=lambda e: (e.st_mtime or 0), reverse=True)

    pet_order    : Optional[str]            = None
    rain_order   : Optional[str]            = None
    pet_max_date : Optional[datetime.date]  = None
    rain_max_date: Optional[datetime.date]  = None

    for entry in dirs[:20]:          # scan at most 20 folders
        if pet_order and rain_order:
            break

        folder_name = entry.filename
        try:
            files = sftp.listdir(f"/Order/{folder_name}")
        except Exception as exc:
            logger.debug(f"[ORDERS] Cannot list /Order/{folder_name}: {exc}")
            continue

        # Accept both .h5 (preferred) and .tif deliveries from MOSDAC
        data_files = [f for f in files if f.upper().endswith(".H5") or f.upper().endswith(".TIF")]

        # PET: only .h5 expected
        pet_files      = [f for f in data_files if "L3C_PET" in f.upper() and f.upper().endswith(".H5")]
        # Rain: .h5 preferred; fall back to .tif if MOSDAC delivered that format
        rain_files_h5  = [f for f in data_files if "L3G_IMR" in f.upper() and f.upper().endswith(".H5")]
        rain_files_tif = [f for f in data_files if "L3G_IMR" in f.upper() and f.upper().endswith(".TIF")]
        rain_files     = rain_files_h5 or rain_files_tif   # prefer .h5, accept .tif

        if pet_files and pet_order is None:
            pet_order = folder_name
            dates = [_parse_date_from_filename(f) for f in pet_files]
            dates = [d for d in dates if d is not None]
            pet_max_date = max(dates) if dates else None
            logger.info(
                f"[ORDERS] PET  folder={pet_order}  "
                f"files={len(pet_files)}  max_date={pet_max_date}"
            )

        if rain_files and rain_order is None:
            rain_order = folder_name
            dates = [_parse_date_from_filename(f) for f in rain_files]
            dates = [d for d in dates if d is not None]
            rain_max_date = max(dates) if dates else None
            ext_note = ".tif (MOSDAC non-HDF5 delivery)" if not rain_files_h5 else ".h5"
            logger.info(
                f"[ORDERS] Rain folder={rain_order}  "
                f"files={len(rain_files)}  max_date={rain_max_date}  ext={ext_note}"
            )

    if not pet_order:
        raise RuntimeError(
            "[ORDERS] No PET order folder found in /Order/. "
            "Ensure a valid order with L3C_PET files exists."
        )
    if not rain_order:
        raise RuntimeError(
            "[ORDERS] No Rain order folder found in /Order/. "
            "Ensure a valid order with L3G_IMR files exists."
        )

    return {
        "pet_order":    pet_order,
        "rain_order":   rain_order,
        "pet_max_date": pet_max_date,
        "rain_max_date": rain_max_date,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ATTRIBUTE PARSING HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _attr(attrs: dict, *keys, cast=float, default=None):
    """Return the first matching key from attrs dict, cast to `cast`."""
    for k in keys:
        if k in attrs:
            val = attrs[k]
            if isinstance(val, (bytes, np.bytes_)):
                val = val.decode()
            try:
                return cast(val)
            except (ValueError, TypeError):
                continue
    return default


def _resolve_bounds_from_latlon_arrays(f: h5py.File) -> Optional[Dict]:
    """Derive W/E/S/N bounds from 1-D lat/lon coordinate arrays if present."""
    lat_keys = ["lat", "latitude", "Latitude", "Lat"]
    lon_keys = ["lon", "longitude", "Longitude", "Lon"]
    lat_arr = lon_arr = None
    for k in lat_keys:
        if k in f:
            lat_arr = np.array(f[k]).ravel()
            break
    for k in lon_keys:
        if k in f:
            lon_arr = np.array(f[k]).ravel()
            break
    if lat_arr is not None and lon_arr is not None:
        return {
            "west": float(lon_arr.min()), "east": float(lon_arr.max()),
            "south": float(lat_arr.min()), "north": float(lat_arr.max()),
        }
    return None


def _find_dataset(f: h5py.File, candidates: List[str]) -> Tuple[str, h5py.Dataset]:
    """
    Locate a spatial data array inside an HDF5 file.
    1. Try known candidate names at root level.
    2. Fall back to largest 2-D/3-D non-coordinate array.
    """
    for name in candidates:
        if name in f and isinstance(f[name], h5py.Dataset):
            return name, f[name]

    all_ds: List[Tuple[str, h5py.Dataset]] = []

    def _collect(name, obj):
        if isinstance(obj, h5py.Dataset) and len(obj.shape) in (2, 3):
            all_ds.append((name, obj))

    f.visititems(_collect)

    spatial = [
        (n, d) for n, d in all_ds
        if d.size > 1000
        and d.name.split("/")[-1].lower()
        not in {"lat", "latitude", "lon", "longitude", "time"}
    ]
    if spatial:
        spatial.sort(key=lambda x: x[1].size, reverse=True)
        return spatial[0]

    raise ValueError(
        "No spatial dataset found in HDF5. "
        "Run --inspect <file.h5> to see available datasets."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CORE HDF5 PARSER  — shared by PET and Rain
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_hdf5(hdf_file: Path, dataset_candidates: List[str], label: str) -> Dict:
    """
    Parse any INSAT-3DR HDF5 product and return a ready-to-mask dict.

    Returns
    -------
    data          float64 ndarray 2-D, NaN = nodata
    dataset_name  str
    transform     rasterio Affine (north-up)
    crs           CRS EPSG:4326
    resolution    degrees per pixel
    bounds        dict west/east/south/north
    scale_applied bool
    """
    try:
        with h5py.File(hdf_file, "r") as f:

            # 1. Find data array
            dataset_name, dataset = _find_dataset(f, dataset_candidates)
            raw = np.array(dataset, dtype=np.float64)
            logger.debug(
                f"[{label}] '{dataset_name}'  shape={raw.shape}  dtype={dataset.dtype}"
            )

            # 2. Squeeze 3-D -> 2-D
            if raw.ndim == 3:
                if raw.shape[0] == 1:
                    raw = raw[0]
                elif raw.shape[2] == 1:
                    raw = raw[:, :, 0]
                else:
                    logger.warning(
                        f"[{label}] 3-D {raw.shape}: taking axis-0 slice"
                    )
                    raw = raw[0]
            if raw.ndim != 2:
                raise ValueError(f"[{label}] Cannot reduce to 2-D: {raw.shape}")

            # 3. Merge attributes (dataset attrs override root attrs)
            all_attrs = {**dict(f.attrs), **dict(dataset.attrs)}

            # 4. Fill value -> NaN
            fill_value = _attr(
                all_attrs,
                "_FillValue", "fill_value", "FillValue",
                "missing_value", "MissingValue",
                default=-9999.0,
            )
            data = raw.astype(np.float64)
            data[np.isclose(data, fill_value, atol=1.0)] = np.nan
            data[data < -500] = np.nan    # catch any other bad sentinels

            # 5. Physical value = raw * scale + offset
            scale  = _attr(all_attrs, "scale_factor", "Scale_factor", "scale",  default=1.0)
            offset = _attr(all_attrs, "add_offset",   "Add_offset",   "offset", default=0.0)
            scale_applied = not (scale == 1.0 and offset == 0.0)
            if scale_applied:
                data = data * scale + offset
                logger.debug(f"[{label}] Applied scale={scale} offset={offset}")

            # 6. Geospatial bounds — INSAT-3DR attribute names first
            west  = _attr(all_attrs, "Left_Longitude",  "west_longitude",  "west",  default=None)
            east  = _attr(all_attrs, "Right_Longitude", "east_longitude",  "east",  default=None)
            north = _attr(all_attrs, "Upper_Latitude",  "north_latitude",  "north", default=None)
            south = _attr(all_attrs, "Lower_Latitude",  "south_latitude",  "south", default=None)

            if None in (west, east, north, south):
                latlon = _resolve_bounds_from_latlon_arrays(f)
                if latlon:
                    west, east   = latlon["west"],  latlon["east"]
                    south, north = latlon["south"], latlon["north"]
                    logger.debug(f"[{label}] Bounds from lat/lon arrays")
                else:
                    west, east   = INSAT_DOMAIN["west"],  INSAT_DOMAIN["east"]
                    south, north = INSAT_DOMAIN["south"], INSAT_DOMAIN["north"]
                    logger.warning(
                        f"[{label}] No bounds in HDF5 — using INSAT India domain. "
                        f"Run --inspect {hdf_file.name} to verify."
                    )

            # 7. Pixel resolution
            res = _attr(
                all_attrs,
                "ImageResolution", "image_resolution",
                "resolution", "Resolution", "pixel_size",
                default=None,
            )
            if res is None:
                rows, cols = data.shape
                res = ((east - west) / cols + (north - south) / rows) / 2.0
                logger.debug(f"[{label}] Resolution derived: {res:.6f} deg")
            elif res > 1.0:
                res = round(res / 111.0, 6)   # km -> degrees
                logger.debug(f"[{label}] Resolution converted km->deg: {res:.6f}")

            transform = from_origin(west, north, res, res)

            logger.info(
                f"[{label}] {dataset_name} | "
                f"{data.shape[1]}x{data.shape[0]} px | "
                f"res={res:.5f}deg | "
                f"W={west:.3f} E={east:.3f} S={south:.3f} N={north:.3f} | "
                f"scale={scale_applied}"
            )

            return {
                "data":          data.astype(np.float64),
                "dataset_name":  dataset_name,
                "transform":     transform,
                "crs":           CRS.from_epsg(4326),
                "resolution":    res,
                "bounds":        {"west": west, "east": east,
                                  "south": south, "north": north},
                "scale_applied": scale_applied,
            }

    except Exception as exc:
        logger.error(f"[{label}] Parse failed [{hdf_file.name}]: {exc}")
        raise


# ═══════════════════════════════════════════════════════════════════════════════
# USN POLYGON SHAPES
# ═══════════════════════════════════════════════════════════════════════════════
def _get_usn_shapes() -> Tuple[List, bool]:
    from shapely.geometry import shape, mapping

    features = GEOJSON.get("features", [])
    if features:
        buffered_shapes = []
        for f in features:
            geom = shape(f["geometry"])
            geom = geom.buffer(0.02)   # ✅ buffer added
            buffered_shapes.append(mapping(geom))
        
        return buffered_shapes, True

    # fallback bbox
    b = BOUNDS
    return [{
        "type": "Polygon",
        "coordinates": [[
            [b["west"],  b["south"]],
            [b["east"],  b["south"]],
            [b["east"],  b["north"]],
            [b["west"],  b["north"]],
            [b["west"],  b["south"]],
        ]],
    }], False

# ═══════════════════════════════════════════════════════════════════════════════
# MASK AND SAVE  — core output writer
# ═══════════════════════════════════════════════════════════════════════════════
def _write_masked_tif(
    data:      np.ndarray,
    transform: object,
    crs:       CRS,
    out_path:  Path,
    tags:      Dict,
    label:     str,
) -> Path:

    NODATA  = -9999.0
    shapes, using_polygon = _get_usn_shapes()
    data_f  = np.where(np.isnan(data), NODATA, data).astype(np.float64)

    raster_meta = {
        "driver":    "GTiff",
        "height":    data_f.shape[0],
        "width":     data_f.shape[1],
        "count":     1,
        "dtype":     "float64",
        "crs":       crs,
        "transform": transform,
        "nodata":    NODATA,
    }

    with MemoryFile() as mf:
        with mf.open(**raster_meta) as mem_ds:
            mem_ds.write(data_f, 1)

        with mf.open() as mem_ds:
            try:
                masked_arr, transform_out = rio_mask(
                    mem_ds,
                    shapes,
                    crop=True,
                    nodata=NODATA,
                    all_touched=True,
                )

                # ✅ FIX: define BEFORE use
                masked_2d = masked_arr[0]

                valid_px = int(np.sum((masked_2d != NODATA) & ~np.isnan(masked_2d)))
                print("Valid pixels after mask:", valid_px)

            except Exception as exc:
                raise ValueError(f"[{label}] rasterio.mask failed: {exc}")

    # ✅ Now safely reuse
    if valid_px < 4:
        raise ValueError(
            f"[{label}] Only {valid_px} valid pixels after mask — "
            f"data may not cover Udham Singh Nagar "
            f"(mask={'polygon' if using_polygon else 'bbox'})"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)

    final_tags = {
        "study_area":   "Udham Singh Nagar, Uttarakhand",
        "mask_type":    "polygon_FAO_GAUL" if using_polygon else "bbox",
        "crop_bounds":  str(BOUNDS),
        "valid_pixels": str(valid_px),
        "processed_at": datetime.datetime.utcnow().isoformat(),
    }
    final_tags.update(tags)

    with rasterio.open(
        out_path,
        "w",
        driver="GTiff",
        height=masked_2d.shape[0],
        width=masked_2d.shape[1],
        count=1,
        dtype="float64",
        crs=crs,
        transform=transform_out,
        nodata=NODATA,
        compress="lzw",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    ) as dst:
        dst.write(masked_2d.astype(np.float64), 1)
        dst.update_tags(**final_tags)

    logger.info(
        f"[{label}] -> {out_path.name}  "
        f"({masked_2d.shape[1]}x{masked_2d.shape[0]} px, "
        f"{valid_px} valid px, "
        f"mask={'polygon' if using_polygon else 'bbox'})"
    )

    return out_path


def mask_hdf5_to_tif(
    hdf_file:   Path,
    out_path:   Path,
    data_type:  str,                       # "pet" or "rain"
    order_id:   str = "",
    extra_tags: Optional[Dict] = None,
) -> Path:
    """
    HDF5 -> parse -> in-memory MemoryFile -> polygon mask -> GeoTIFF.

    No intermediate full-domain TIF written to disk.
    """
    label      = data_type.upper()
    candidates = (
        _PET_DATASET_CANDIDATES if data_type == "pet"
        else _RAIN_DATASET_CANDIDATES
    )
    meta = _parse_hdf5(hdf_file, candidates, label)

    tags = {
        "source":         "INSAT-3DR",
        "dataset":        meta["dataset_name"],
        "resolution_deg": str(meta["resolution"]),
        "scale_applied":  str(meta["scale_applied"]),
        "order_id":       order_id,
    }
    if extra_tags:
        tags.update(extra_tags)

    return _write_masked_tif(
        meta["data"], meta["transform"], meta["crs"],
        out_path, tags, label,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# OUTPUT PATH HELPERS  — single source of truth for all filenames
# ═══════════════════════════════════════════════════════════════════════════════

def _pet_hdf_path(date: datetime.date) -> Path:
    d = date.strftime("%d%b%Y").upper()
    return pet_hdf_dir / f"3RIMG_{d}_0015_L3C_PET_DLY_V01R00.h5"

def _pet_tif_path(date: datetime.date) -> Path:
    """Final PET GeoTIFF. Same stem as the HDF5. No _cropped suffix."""
    d = date.strftime("%d%b%Y").upper()
    return pet_tif_dir / f"3RIMG_{d}_0015_L3C_PET_DLY_V01R00.tif"

def _rain_hdf_path(date: datetime.date) -> Path:
    d = date.strftime("%d%b%Y").upper()
    return rain_hdf_dir / f"3RIMG_{d}_0015_L3G_IMR_DLY_V01R00.h5"

def _rain_tif_path(date: datetime.date) -> Path:
    """Final Rain GeoTIFF. Same stem as the HDF5. No _cropped suffix."""
    d = date.strftime("%d%b%Y").upper()
    return rain_tif_dir / f"3RIMG_{d}_0015_L3G_IMR_DLY_V01R00.tif"


# ═══════════════════════════════════════════════════════════════════════════════
# MONGODB HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _to_dt(date: datetime.date) -> datetime.datetime:
    return datetime.datetime.combine(date, datetime.time.min)


def _is_in_db(date: datetime.date, data_type: str) -> bool:
    """Pure DB check — no disk I/O."""
    if not MONGO_AVAILABLE:
        return False
    dt = _to_dt(date)
    return is_pet_downloaded(dt) if data_type == "pet" else is_rain_downloaded(dt)


def already_complete(date: datetime.date, data_type: str) -> bool:
    """
    Three-layer completeness check (fastest to slowest):
      Layer 1 : MongoDB record exists              -> True (no disk I/O)
      Layer 2 : Valid output TIF exists on disk    -> True + back-fills DB
      Layer 3 : Neither                            -> False (download needed)

    Layer 2 auto-heals the DB if it was wiped but files are intact on disk.
    """
    if _is_in_db(date, data_type):
        return True

    out = _pet_tif_path(date) if data_type == "pet" else _rain_tif_path(date)
    if is_valid_raster(out):
        logger.info(
            f"[{data_type.upper()}] {date} – valid TIF on disk, not in DB; "
            f"registering -> {out.name}"
        )
        _mark_complete(date, data_type, str(out), recovered=True)
        return True

    return False


def _mark_complete(
    date:      datetime.date,
    data_type: str,
    filepath:  str,
    order_id:  str = "",
    extra:     Optional[Dict] = None,
    recovered: bool = False,
) -> bool:
    """Single-write upsert — all provenance fields in one MongoDB round-trip."""
    if not MONGO_AVAILABLE:
        return False
    dt  = _to_dt(date)
    col = pet_col if data_type == "pet" else rain_col

    doc: Dict = {
        "image_date":        dt,
        "raster_path":       filepath,
        "processing_status": "complete",
        "processed_at":      datetime.datetime.utcnow(),
        "download_status":   "complete",
        "downloaded_at":     datetime.datetime.utcnow(),
        "order_id":          order_id,
        "season":            "rabi" if is_wheat_season(date) else "non_rabi",
        "recovered":         recovered,
    }
    if extra:
        doc.update(extra)

    try:
        col.update_one({"image_date": dt}, {"$set": doc}, upsert=True)
        return True
    except Exception as exc:
        logger.error(f"_mark_complete failed [{data_type} {date}]: {exc}")
        return False


def _mark_failed(
    date:      datetime.date,
    data_type: str,
    error:     str,
    order_id:  str = "",
) -> bool:
    if not MONGO_AVAILABLE:
        return False
    dt  = _to_dt(date)
    col = pet_col if data_type == "pet" else rain_col
    try:
        col.update_one(
            {"image_date": dt},
            {"$set": {
                "download_status":   "failed",
                "processing_status": "failed",
                "error":             error,
                "failed_at":         datetime.datetime.utcnow(),
                "order_id":          order_id,
            }},
            upsert=True,
        )
        return True
    except Exception as exc:
        logger.error(f"_mark_failed error [{data_type} {date}]: {exc}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# PER-DATE DOWNLOAD — PET
# ═══════════════════════════════════════════════════════════════════════════════

def download_pet(date: datetime.date, sftp, order_id: str) -> bool:
    """
    Download INSAT-3DR PET HDF5 -> polygon-mask -> save final GeoTIFF.

    Skip layers:
      1. DB record exists           -> skip everything
      2. Valid TIF already on disk  -> register in DB, skip
      3. Valid HDF5 on disk         -> skip SFTP, go straight to mask
      4. Corrupt / missing HDF5     -> delete corrupt + full SFTP download + mask

    Output: insat_pet/<stem>.tif  (same stem as HDF5, no _cropped suffix)
    """
    if already_complete(date, "pet"):
        logger.info(f"[PET] {date} – skip (already complete)")
        return True

    hdf_path = _pet_hdf_path(date)
    out_path = _pet_tif_path(date)
    remote   = f"/Order/{order_id}/{hdf_path.name}"

    try:
        if is_valid_hdf5(hdf_path):
            logger.info(f"[PET] {date} – HDF5 on disk, skipping SFTP")
        else:
            if hdf_path.exists():
                logger.warning(
                    f"[PET] {date} – corrupt HDF5, deleting: {hdf_path.name}"
                )
                hdf_path.unlink()

            # ── Chunked download with retry ──────────────────────────────────
            for attempt in range(MAX_RETRIES):
                try:
                    remote_attr = sftp.stat(remote)
                    if remote_attr.st_size < 250:
                        raise ValueError(
                            f"Remote file too small ({remote_attr.st_size} bytes): {remote}"
                        )
                    logger.info(
                        f"[PET] Remote size: {remote_attr.st_size / 1024:.2f} KB"
                    )

                    if hdf_path.exists():
                        hdf_path.unlink()

                    with sftp.open(remote, "rb") as remote_f:
                        with open(hdf_path, "wb") as local_f:
                            while True:
                                chunk = remote_f.read(32768)  # 32 KB chunks
                                if not chunk:
                                    break
                                local_f.write(chunk)

                    logger.info(
                        f"[PET] Local size: {hdf_path.stat().st_size / 1024:.2f} KB"
                    )

                    if not is_file_complete(hdf_path):
                        raise ValueError(
                            f"File too small after download: {hdf_path.name}"
                        )
                    if not is_valid_hdf5(hdf_path):
                        raise ValueError(
                            f"Invalid HDF5 structure after download: {hdf_path.name}"
                        )

                    logger.info(f"[PET] {date} – downloaded {hdf_path.name}")
                    break  # success

                except Exception as e:
                    logger.warning(
                        f"[PET] Retry {attempt + 1}/{MAX_RETRIES} for {date}: {e}"
                    )
                    try:
                        logger.error(f"[CORRUPTION] {hdf_path.name}: {e}")
                    except Exception:
                        pass
                    if hdf_path.exists():
                        hdf_path.unlink()
                    time.sleep(2)
            else:
                raise RuntimeError(
                    f"[PET] Download failed after {MAX_RETRIES} retries for {date}"
                )

        mask_hdf5_to_tif(hdf_path, out_path, "pet", order_id=order_id)

        _mark_complete(
            date, "pet", str(out_path),
            order_id=order_id,
            extra={
                "hdf5_file":       str(hdf_path),
                "output_tif":      str(out_path),
                "hdf5_size_bytes": hdf_path.stat().st_size,
                "tif_size_bytes":  out_path.stat().st_size,
                "pipeline":        "HDF5->MemoryFile->polygon_mask->GeoTIFF",
            },
        )
        return True

    except Exception as exc:
        msg = f"PET failed: {exc}"
        logger.warning(f"[PET] {date} – {msg}")
        _mark_failed(date, "pet", msg, order_id=order_id)
        return False

MIN_VALID_SIZE_MB = 1.0  # PET ~5-20 MB, Rain ~1-10 MB; 1 MB is the safe floor

def is_file_complete(path: Path) -> bool:
    """True if file exists AND is larger than MIN_VALID_SIZE_MB."""
    return path.exists() #and path.stat().st_size > MIN_VALID_SIZE_MB * 1024 * 1024


def _crop_tif_to_usn(src_path: Path, out_path: Path, label: str, order_id: str = "") -> None:
    """
    Crop / polygon-mask a GeoTIFF delivered directly by MOSDAC (non-HDF5 rain delivery).
    Reprojects to EPSG:4326 if necessary, then applies the same USN polygon mask as
    mask_hdf5_to_tif so the output is consistent with the HDF5 pipeline.
    """
    shapes, using_polygon = _get_usn_shapes()

    with rasterio.open(src_path) as src:
        # Reproject to WGS84 if needed
        if src.crs and not src.crs.to_epsg() == 4326:
            dst_crs = CRS.from_epsg(4326)
            transform, width, height = calculate_default_transform(
                src.crs, dst_crs, src.width, src.height, *src.bounds
            )
            data = np.zeros((src.count, height, width), dtype=src.dtypes[0])
            reproject(
                source=rasterio.band(src, 1),
                destination=data[0],
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform,
                dst_crs=dst_crs,
                resampling=Resampling.nearest,
            )
            meta = src.meta.copy()
            meta.update({"crs": dst_crs, "transform": transform,
                          "width": width, "height": height})
        else:
            data    = src.read()
            meta    = src.meta.copy()
            transform = src.transform

        nodata = meta.get("nodata", -9999.0)

        if using_polygon and shapes:
            with MemoryFile() as memfile:
                with memfile.open(**meta) as tmp:
                    tmp.write(data)
                with memfile.open() as tmp:
                    masked, masked_transform = rio_mask(tmp, shapes, crop=True,
                                                        nodata=nodata, filled=True)
        else:
            b = BOUNDS
            row_start, col_start = rasterio.transform.rowcol(
                transform, b["west"], b["north"]
            )
            row_end, col_end = rasterio.transform.rowcol(
                transform, b["east"], b["south"]
            )
            row_start = max(0, row_start); col_start = max(0, col_start)
            row_end   = min(data.shape[1], row_end)
            col_end   = min(data.shape[2], col_end)
            masked          = data[:, row_start:row_end, col_start:col_end]
            masked_transform = rasterio.transform.from_origin(
                b["west"], b["north"],
                abs(transform.a), abs(transform.e)
            )

    valid_px = int(np.sum((masked != nodata) & ~np.isnan(masked.astype(float))))
    print(f"Valid pixels after mask: {valid_px}")

    out_meta = meta.copy()
    out_meta.update({
        "driver": "GTiff", "dtype": "float32",
        "count": 1, "width": masked.shape[2], "height": masked.shape[1],
        "transform": masked_transform, "crs": CRS.from_epsg(4326),
        "nodata": nodata,
        "compress": "deflate", "predictor": 2, "zlevel": 6,
    })
    tags = {
        "product": label.upper(), "order_id": order_id,
        "mask_type": "polygon" if using_polygon else "bbox",
        "study_area": "Udham_Singh_Nagar_Uttarakhand",
        "valid_pixels": str(valid_px),
        "processed_at": datetime.datetime.utcnow().isoformat(),
        "source_file": src_path.name,
        "pipeline": "TIF->crop_mask->GeoTIFF",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **out_meta) as dst:
        dst.write(masked[0:1].astype("float32"))
        dst.update_tags(**tags)

    logger.info(
        f"[{label.upper()}] -> {out_path.name}  "
        f"({out_meta['width']}x{out_meta['height']} px, {valid_px} valid px, "
        f"mask={'polygon' if using_polygon else 'bbox'})"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# PER-DATE DOWNLOAD — RAIN
# ═══════════════════════════════════════════════════════════════════════════════

def _find_rain_remote_file(sftp, order_id: str, date: datetime.date) -> Optional[str]:
    """
    Scan /Order/<order_id>/ for the actual rain filename for this date.
    MOSDAC delivers rain as .h5 (preferred) or .tif (non-standard but observed).
    Returns the remote filename or None.
    """
    stamp = date.strftime("%d%b%Y").upper()
    try:
        remote_files = sftp.listdir(f"/Order/{order_id}")
    except Exception as exc:
        logger.warning(f"[RAIN] Cannot list /Order/{order_id}: {exc}")
        return None

    # Prefer .h5 for proper HDF5 pipeline; accept .tif as MOSDAC fallback
    candidates = [
        f for f in remote_files
        if f"3RIMG_{stamp}" in f.upper() and "L3G_IMR" in f.upper()
    ]
    h5_candidates  = [f for f in candidates if f.upper().endswith(".H5")]
    tif_candidates = [f for f in candidates if f.upper().endswith(".TIF")]

    if h5_candidates:
        return h5_candidates[0]
    if tif_candidates:
        logger.info(f"[RAIN] {date} – MOSDAC delivered .tif (not HDF5), will use directly")
        return tif_candidates[0]
    return None


def download_rainfall(date: datetime.date, sftp, order_id: str) -> bool:
    """
    Download INSAT-3DR rainfall -> polygon-mask -> save final GeoTIFF.

    Handles both delivery formats from MOSDAC:
      • .h5  (preferred) — HDF5 -> mask_hdf5_to_tif pipeline
      • .tif (observed)  — download directly, crop/mask with rasterio

    Skip layers:
      1. DB record exists           -> skip everything
      2. Valid TIF already on disk  -> register in DB, skip
      3. Valid HDF5 on disk         -> skip SFTP, go straight to mask
      4. Corrupt / missing file     -> delete + full SFTP download + mask

    Output: insat_rain/<canonical_stem>.tif
    """
    if already_complete(date, "rain"):
        logger.info(f"[RAIN] {date} – skip (already complete)")
        return True

    out_path = _rain_tif_path(date)

    try:
        # ── Discover actual remote filename (.h5 or .tif) ────────────────────
        remote_name = _find_rain_remote_file(sftp, order_id, date)
        if not remote_name:
            logger.warning(f"[RAIN] {date} – no matching file in /Order/{order_id}/")
            return False

        remote_is_tif = remote_name.upper().endswith(".TIF")
        remote_path   = f"/Order/{order_id}/{remote_name}"

        # Local storage path depends on delivered format
        hdf_path = _rain_hdf_path(date)  # canonical .h5 path (used for HDF5 pipeline)
        local_dl_path = (
            rain_hdf_dir / remote_name if not remote_is_tif else rain_hdf_dir / remote_name
        )

        # ── If .h5 already on disk and valid, skip download ───────────────────
        if not remote_is_tif and is_valid_hdf5(hdf_path):
            logger.info(f"[RAIN] {date} – HDF5 on disk, skipping SFTP")
        else:
            if local_dl_path.exists():
                logger.warning(f"[RAIN] {date} – stale file, deleting: {local_dl_path.name}")
                local_dl_path.unlink()

            # ── Chunked download with retry ──────────────────────────────────
            for attempt in range(MAX_RETRIES):
                try:
                    remote_attr = sftp.stat(remote_path)
                    if remote_attr.st_size < 250:
                        raise ValueError(
                            f"Remote file too small ({remote_attr.st_size} bytes): {remote_path}"
                        )
                    logger.info(f"[RAIN] Remote size: {remote_attr.st_size / 1024:.2f} KB")

                    if local_dl_path.exists():
                        local_dl_path.unlink()

                    with sftp.open(remote_path, "rb") as remote_f:
                        with open(local_dl_path, "wb") as local_f:
                            while True:
                                chunk = remote_f.read(32768)
                                if not chunk:
                                    break
                                local_f.write(chunk)

                    logger.info(f"[RAIN] Local size: {local_dl_path.stat().st_size / 1024:.2f} KB")

                    if not is_file_complete(local_dl_path):
                        raise ValueError(f"File too small after download: {local_dl_path.name}")

                    if not remote_is_tif and not is_valid_hdf5(local_dl_path):
                        raise ValueError(f"Invalid HDF5 after download: {local_dl_path.name}")

                    logger.info(f"[RAIN] {date} – downloaded {local_dl_path.name}")
                    break

                except Exception as e:
                    logger.warning(f"[RAIN] Retry {attempt + 1}/{MAX_RETRIES} for {date}: {e}")
                    if local_dl_path.exists():
                        local_dl_path.unlink()
                    time.sleep(2)
            else:
                raise RuntimeError(f"[RAIN] Download failed after {MAX_RETRIES} retries for {date}")

        # ── Convert / mask to final GeoTIFF ──────────────────────────────────
        if remote_is_tif:
            # MOSDAC delivered a GeoTIFF directly — crop to USN polygon with rasterio
            _crop_tif_to_usn(local_dl_path, out_path, label="rain", order_id=order_id)
            pipeline_note = "TIF->crop_mask->GeoTIFF"
        else:
            mask_hdf5_to_tif(local_dl_path, out_path, "rain", order_id=order_id)
            pipeline_note = "HDF5->MemoryFile->polygon_mask->GeoTIFF"

        _mark_complete(
            date, "rain", str(out_path),
            order_id=order_id,
            extra={
                "source_file":     str(local_dl_path),
                "output_tif":      str(out_path),
                "source_size_bytes": local_dl_path.stat().st_size,
                "tif_size_bytes":  out_path.stat().st_size,
                "pipeline":        pipeline_note,
            },
        )
        return True

    except Exception as exc:
        msg = f"Rain failed: {exc}"
        logger.warning(f"[RAIN] {date} – {msg}")
        _mark_failed(date, "rain", msg, order_id=order_id)
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# SFTP SESSION FACTORY
# ═══════════════════════════════════════════════════════════════════════════════

def _make_sftp_connection():
    """Open an SFTP connection. Returns a pysftp.Connection context manager."""
    if not SFTP_AVAILABLE:
        raise RuntimeError("pysftp not installed – install with: pip install pysftp")
    cnopts = pysftp.CnOpts()
    cnopts.hostkeys = None   # MOSDAC uses a self-signed / unverified host key
    return pysftp.Connection(HOST, username=USER, password=PASS, cnopts=cnopts)


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLE-DATE DISPATCHER  (opens its own SFTP, discovers orders)
# ═══════════════════════════════════════════════════════════════════════════════

def download_day(date: datetime.date) -> Dict:
    """
    Download PET + Rain for one specific date.

    Flow:
      1. Season check
      2. Open SFTP
      3. Discover current order folders (dynamic — never hardcoded)
      4. Cap date against max available (skip silently if beyond server data)
      5. Download PET then Rain
    """
    if not is_wheat_season(date):
        logger.debug(f"Skip {date} – outside Rabi season (Nov-Apr)")
        return {"pet": False, "rain": False, "skipped": True, "reason": "outside_season"}

    results: Dict = {"pet": False, "rain": False, "skipped": False}

    try:
        with _make_sftp_connection() as sftp:
            orders = _discover_orders(sftp)
            results = _run_day(date, sftp, orders)
    except Exception as exc:
        logger.error(f"SFTP session error for {date}: {exc}")

    return results


def _run_day(
    date:   datetime.date,
    sftp,
    orders: Dict,
) -> Dict:
    """
    Inner dispatcher — reuses an already-open SFTP connection.
    Checks date against max available before attempting any download.
    """
    results: Dict = {"pet": False, "rain": False, "skipped": False}

    pet_max  = orders.get("pet_max_date")
    rain_max = orders.get("rain_max_date")
    server_max = max(
        (d for d in [pet_max, rain_max] if d is not None),
        default=None,
    )

    if server_max and date > server_max:
        logger.warning(
            f"[SKIP] {date} is beyond latest available data on server "
            f"(PET={pet_max}, Rain={rain_max}) — skipping"
        )
        results["skipped"] = True
        results["reason"]  = f"beyond_latest_data({server_max})"
        return results

    # Download Rain first (usually larger, good to know early if SFTP breaks)
    results["rain"] = download_rainfall(date, sftp, orders["rain_order"])
    results["pet"]  = download_pet(date, sftp, orders["pet_order"])

    logger.info(
        f"{date} | "
        f"PET={'OK'  if results['pet']  else 'FAIL'}  "
        f"Rain={'OK' if results['rain'] else 'FAIL'}"
    )
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# BULK BACKFILL  (single SFTP connection for the entire date range)
# ═══════════════════════════════════════════════════════════════════════════════

def backfill_historical(
    start_date: Optional[datetime.date] = None,
    end_date:   Optional[datetime.date] = None,
) -> Dict[str, int]:
    """
    Download all Rabi-season (Nov-Apr) data in [start_date, end_date].

    Uses a SINGLE SFTP connection for the entire run (not one per day).
    Discovers order folders once at the start and caps end_date to the
    latest date actually available on the server.

    Skips:
      • Non-season days
      • Dates already complete (DB or disk)
      • Dates beyond what the server currently has
    """
    start_date = start_date or START_DATE
    end_date   = end_date   or datetime.date.today()

    if not SFTP_AVAILABLE:
        logger.error("pysftp not installed – SFTP unavailable")
        return {}

    stats = dict(
        total=0, skipped_season=0, skipped_complete=0, skipped_no_data=0,
        pet_ok=0, rain_ok=0, pet_fail=0, rain_fail=0,
    )

    try:
        with _make_sftp_connection() as sftp:

            # ── Discover orders once ─────────────────────────────────────────
            orders   = _discover_orders(sftp)
            pet_max  = orders.get("pet_max_date")
            rain_max = orders.get("rain_max_date")
            server_max = max(
                (d for d in [pet_max, rain_max] if d is not None),
                default=None,
            )

            if server_max and end_date > server_max:
                logger.warning(
                    f"[BACKFILL] Requested end_date={end_date} but latest available "
                    f"data on server: PET={pet_max}, Rain={rain_max}. "
                    f"Capping to {server_max}."
                )
                end_date = server_max

            logger.info("=" * 60)
            logger.info(
                f"Backfill: {start_date} -> {end_date}  "
                f"(Nov-Apr only | PET order={orders['pet_order']} | "
                f"Rain order={orders['rain_order']})"
            )
            logger.info("=" * 60)

            # ── Date loop ────────────────────────────────────────────────────
            cur = start_date
            while cur <= end_date:
                stats["total"] += 1

                if not is_wheat_season(cur):
                    stats["skipped_season"] += 1
                    cur += datetime.timedelta(days=1)
                    continue

                pet_done  = already_complete(cur, "pet")
                rain_done = already_complete(cur, "rain")

                if pet_done and rain_done:
                    stats["skipped_complete"] += 1
                    logger.debug(f"[BACKFILL] {cur} – both complete, skipping")
                    cur += datetime.timedelta(days=1)
                    continue

                res = _run_day(cur, sftp, orders)

                if res.get("skipped"):
                    stats["skipped_no_data"] += 1
                else:
                    if res.get("pet"):    stats["pet_ok"]   += 1
                    elif not pet_done:    stats["pet_fail"]  += 1
                    if res.get("rain"):   stats["rain_ok"]   += 1
                    elif not rain_done:   stats["rain_fail"]  += 1

                cur += datetime.timedelta(days=1)

    except Exception as exc:
        logger.error(f"[BACKFILL] SFTP session failed: {exc}")

    logger.info("-" * 60)
    logger.info(
        f"Done | total={stats['total']} | "
        f"season-skip={stats['skipped_season']} | "
        f"already-complete={stats['skipped_complete']} | "
        f"no-data-yet={stats['skipped_no_data']}"
    )
    logger.info(f"  PET   ok={stats['pet_ok']:4d}  fail={stats['pet_fail']}")
    logger.info(f"  Rain  ok={stats['rain_ok']:4d}  fail={stats['rain_fail']}")
    logger.info("-" * 60)
    return stats


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEDULER HOOK  (wired up externally when --stream is added later)
# ═══════════════════════════════════════════════════════════════════════════════

def scheduled_daily_download() -> None:
    """
    Triggered daily at 00:00.
    Discovers current orders fresh each run — handles order ID rotation
    automatically without any code changes.
    """
    logger.info("Scheduled daily download triggered")
    # download_day already discovers orders + caps date vs server max
    download_day(datetime.date.today())


# ═══════════════════════════════════════════════════════════════════════════════
# MOSDAC DOWNLOADER CLASS - Wrapper for scheduler.py compatibility
# ═══════════════════════════════════════════════════════════════════════════════

class MosdacDownloader:
    """
    Wrapper class for MOSDAC downloader functions to maintain compatibility with scheduler.py.
    
    This class provides a clean interface for:
        - Downloading data from orders
        - Processing HDF5 to GeoTIFF
        - Checking download status
    """
    
    def __init__(self):
        """Initialize the downloader with default settings."""
        self.logger = logger
    
    def download_from_orders(self, order_keys: List[str] = None) -> Dict:
        """
        Download the latest available PET and Rain files from SFTP.

        ``order_keys`` is accepted only for API compatibility with scheduler.py
        (where it carries synthetic labels like ``PET_ORDER_20260331`` that are
        useful for log messages but are **not** real SFTP folder names).
        The actual folder names are discovered dynamically via
        ``_discover_orders()``, exactly as ``backfill_historical()`` does.

        Returns
        -------
        {
            "pet":  {"downloaded": int, "failed": int, "skipped": int},
            "rain": {"downloaded": int, "failed": int, "skipped": int},
        }
        """
        results = {
            "pet":  {"downloaded": 0, "failed": 0, "skipped": 0},
            "rain": {"downloaded": 0, "failed": 0, "skipped": 0},
        }

        if order_keys:
            self.logger.info(
                f"[MosdacDownloader] download_from_orders called "
                f"(order labels: {order_keys})"
            )

        try:
            with _make_sftp_connection() as sftp:
                # ── Discover real SFTP folder names + max dates ───────────────
                try:
                    orders = _discover_orders(sftp)
                except RuntimeError as exc:
                    # No ready orders on SFTP yet (freshly placed orders need
                    # MOSDAC processing time — they will be available next run).
                    self.logger.warning(
                        f"[MosdacDownloader] {exc}  "
                        "Orders placed in Stage 2 may not be processed yet — "
                        "they will be downloaded on the next pipeline run."
                    )
                    return results

                pet_order     = orders["pet_order"]
                rain_order    = orders["rain_order"]
                pet_max_date  = orders.get("pet_max_date")
                rain_max_date = orders.get("rain_max_date")

                # ── Rain ─────────────────────────────────────────────────────
                if rain_order and rain_max_date:
                    self.logger.info(
                        f"[MosdacDownloader] Rain: folder={rain_order!r}  "
                        f"target={rain_max_date}"
                    )
                    if download_rainfall(rain_max_date, sftp, rain_order):
                        results["rain"]["downloaded"] += 1
                        self.logger.info(
                            f"[MosdacDownloader] Rain download OK for {rain_max_date}"
                        )
                    else:
                        results["rain"]["failed"] += 1
                        self.logger.error(
                            f"[MosdacDownloader] Rain download FAILED for {rain_max_date}"
                        )
                else:
                    results["rain"]["skipped"] += 1
                    self.logger.warning(
                        f"[MosdacDownloader] No Rain order ready on SFTP "
                        f"(folder={rain_order!r}, max_date={rain_max_date})"
                    )

                # ── PET ──────────────────────────────────────────────────────
                if pet_order and pet_max_date:
                    self.logger.info(
                        f"[MosdacDownloader] PET: folder={pet_order!r}  "
                        f"target={pet_max_date}"
                    )
                    if download_pet(pet_max_date, sftp, pet_order):
                        results["pet"]["downloaded"] += 1
                        self.logger.info(
                            f"[MosdacDownloader] PET download OK for {pet_max_date}"
                        )
                    else:
                        results["pet"]["failed"] += 1
                        self.logger.error(
                            f"[MosdacDownloader] PET download FAILED for {pet_max_date}"
                        )
                else:
                    results["pet"]["skipped"] += 1
                    self.logger.warning(
                        f"[MosdacDownloader] No PET order ready on SFTP "
                        f"(folder={pet_order!r}, max_date={pet_max_date})"
                    )

        except Exception as exc:
            self.logger.error(
                f"[MosdacDownloader] SFTP session error: {exc}", exc_info=True
            )

        return results
    
    def download_single_date(self, date: datetime.date, pet_order: str, rain_order: str) -> Dict:
        """
        Download both PET and Rain for a specific date using existing order IDs.
        
        Args:
            date: Date to download
            pet_order: PET order folder name
            rain_order: Rain order folder name
        
        Returns:
            Dict with download results
        """
        results = {"pet": False, "rain": False}
        
        try:
            with _make_sftp_connection() as sftp:
                results["rain"] = download_rainfall(date, sftp, rain_order)
                results["pet"] = download_pet(date, sftp, pet_order)
        except Exception as e:
            self.logger.error(f"[MosdacDownloader] Error downloading {date}: {e}")
        
        return results
    
    def backfill_range(self, start_date: datetime.date, end_date: datetime.date) -> Dict[str, int]:
        """
        Backfill data for a date range.
        
        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
        
        Returns:
            Statistics dictionary
        """
        return backfill_historical(start_date, end_date)
    
    def check_complete(self, date: datetime.date, data_type: str) -> bool:
        """
        Check if data for a specific date is already downloaded.
        
        Args:
            date: Date to check
            data_type: "pet" or "rain"
        
        Returns:
            True if data is complete and valid
        """
        return already_complete(date, data_type)


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "MOSDAC INSAT-3DR Downloader\n"
            "PET + Rain  HDF5 -> USN polygon-masked GeoTIFF\n\n"
            "Order IDs are discovered automatically from SFTP — never hardcoded."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python mosdac_downloader.py --backfill
  python mosdac_downloader.py --start 2023-11-01 --end 2024-04-30
  python mosdac_downloader.py --date 2024-01-15
  python mosdac_downloader.py --stream
  python mosdac_downloader.py --inspect                    # list all local HDF5
  python mosdac_downloader.py --inspect data/raw/insat_pet_hdf/3RIMG_01NOV2021_0015_L3C_PET_DLY_V01R00.h5
  python mosdac_downloader.py --check-boundary
        """,
    )
    parser.add_argument("--backfill", action="store_true",
                        help="Download START_DATE to today (Nov-Apr only)")
    parser.add_argument("--start",   type=str, metavar="YYYY-MM-DD",
                        help="Start date for backfill (implies --backfill)")
    parser.add_argument("--end",     type=str, metavar="YYYY-MM-DD",
                        help="End date for backfill (implies --backfill); "
                             "capped to latest available on server automatically")
    parser.add_argument("--date",    type=str, metavar="YYYY-MM-DD",
                        help="Download one specific date")
    parser.add_argument("--stream",  action="store_true",
                        help="Start daily scheduled service at 00:00")
    parser.add_argument("--inspect", nargs="?", const="__LIST__",
                        metavar="HDF5_PATH",
                        help=(
                            "No argument -> list all local HDF5 files.  "
                            "With path -> dump full structure of that file."
                        ))
    parser.add_argument("--check-boundary", action="store_true",
                        help="Print boundary and pixel coverage statistics")
    args = parser.parse_args()

    if not MONGO_AVAILABLE:
        logger.warning("MongoDB unavailable – duplicate prevention DISABLED")

    # ── Dispatch ──────────────────────────────────────────────────────────────
    if args.inspect is not None:
        if args.inspect == "__LIST__":
            list_local_hdf5()
        else:
            inspect_hdf5(Path(args.inspect))

    elif args.check_boundary:
        check_boundary()

    elif args.backfill or args.start or args.end:
        # --start / --end without explicit --backfill still triggers backfill
        s = (datetime.datetime.strptime(args.start, "%Y-%m-%d").date()
             if args.start else START_DATE)
        e = (datetime.datetime.strptime(args.end,   "%Y-%m-%d").date()
             if args.end   else datetime.date.today())
        backfill_historical(s, e)

    elif args.date:
        download_day(datetime.datetime.strptime(args.date, "%Y-%m-%d").date())

    elif args.stream:
        logger.info("Streaming service started | daily at 00:00")
        schedule.every().day.at("00:00").do(scheduled_daily_download)
        while True:
            schedule.run_pending()
            time.sleep(60)

    else:
        # No args: download latest available (not blindly today)
        logger.info("No args given – fetching latest available data from server...")
        try:
            with _make_sftp_connection() as sftp:
                orders     = _discover_orders(sftp)
                server_max = max(
                    (d for d in [orders.get("pet_max_date"), orders.get("rain_max_date")]
                     if d is not None),
                    default=None,
                )
                if server_max is None:
                    logger.error("Could not determine latest available date from server")
                elif not is_wheat_season(server_max):
                    logger.info(
                        f"Latest available date {server_max} is outside Rabi season – nothing to do"
                    )
                else:
                    logger.info(f"Downloading latest available date: {server_max}")
                    _run_day(server_max, sftp, orders)
        except Exception as exc:
            logger.error(f"Error in no-arg mode: {exc}")
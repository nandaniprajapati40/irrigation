# import asyncio
# import json
# import logging
# import re
# from datetime import datetime, timedelta
# from pathlib import Path
# from threading import Lock
# from typing import Any, Dict, List, Optional, Tuple

# import numpy as np
# import pandas as pd
# import rasterio
# import rasterio.warp
# import uvicorn
# from fastapi import FastAPI, HTTPException, Query
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import StreamingResponse
# from pydantic import BaseModel
# from rasterio.enums import Resampling
# import os
# from dotenv import load_dotenv
# from config import (
#     STUDY_AREA, DIRECTORIES, GEOSERVER, SARIMAX_CONFIG,
#     WHEAT_PARAMS
# )
# from extract_raster_pixels import (
#     RasterCoordinateError,
#     RasterGridUnavailable,
#     RasterLookupCancelled,
#     RasterOutOfBoundsError,
#     clear_raster_pixel_cache,
#     pixel_from_latlon as raster_pixel_from_latlon,
#     pixel_timeseries_for_pixel,
#     read_history_pixel_value as raster_read_history_pixel_value,
# )
# from logging_config import setup_logging
# import models
# from models import (
#     build_forecast_exog,
#     set_forecast_context,
#     raster_mean,
#     savi_to_kc,
#     get_wheat_stage_info,
#     get_wheat_stage_kc,
#     KC_SLOPE,
#     KC_INTERCEPT,
#     KC_MIN,
#     KC_MAX,
# )

# setup_logging()
# logger = logging.getLogger(__name__)

# CWR_MIN      = 0.0
# CWR_MAX      = 15.0


# # ═══════════════════════════════════════════════════════════════════════════
# # SEASONAL CONSTANTS
# # ═══════════════════════════════════════════════════════════════════════════

# # Rabi wheat season: November (month 11) → April (month 4)
# SEASON_START_MONTH = 11   # November
# SEASON_END_MONTH   = 4    # April
# SEASON_MONTHS      = {11, 12, 1, 2, 3, 4}   # months kept in calendar

# # Cap at 5 complete seasons (Nov 2021–Apr 2022 … Nov 2025–Apr 2026)
# MAX_SEASONS = 5

# # Total slots = 5 seasons × ~6 months × ~3 scenes/month = up to ~90
# # We keep this generous; actual data may be sparser. HISTORY_DATES controls
# # how many slots the pipeline writes; set it to accommodate 5 full seasons.
# HISTORY_DATES  = 191   # upper bound — actual dates may be fewer
# FORECAST_DAYS  = 15
# NODATA         = -9999.0

# # All parameters including ETc
# PARAMS: List[str] = ["savi", "kc", "cwr", "iwr", "etc"]
# FC_PARAMS: List[str] = ["kc", "etc","cwr", "iwr"]   # parameters that get forecast rasters
# POINT_FORECAST_PARAMS: List[str] = ["cwr", "iwr"]    # pixel popup forecast values shown to users

# FORECAST_WINDOWS = ["5day", "10day", "15day"]
# WINDOW_DAYS      = {"5day": 5, "10day": 10, "15day": 15}

# _VALID: Dict[str, Tuple[float, float]] = {
#     "savi": (-1.0, 1.0),
#     "kc":   (KC_MIN, KC_MAX),
#     "cwr":  (CWR_MIN, CWR_MAX),
#     "iwr":  (0.0, CWR_MAX),
#     "etc":  (0.0, 15.0),
# }

# # Cumulative valid ranges for CWR/IWR forecast rasters (mm_total over window).
# # 15-day max = 15 × 15 mm/day = 225 mm; we cap at 200 to clip outliers.
# _VALID_FC: Dict[str, Tuple[float, float]] = {
#     "kc":  (KC_MIN, KC_MAX),
#     "etc": (0.0, 15.0),          # daily average → same as _VALID
#     "cwr": (0.0, 200.0),         # cumulative total mm over window
#     "iwr": (0.0, 200.0),
# }

# _SRC: Dict[str, Tuple[Path, str]] = {
#     "savi": (DIRECTORIES["processed"]["savi"], "savi_*.tif"),
#     "kc":   (DIRECTORIES["processed"]["kc"],   "kc_*.tif"),
#     "cwr":  (DIRECTORIES["processed"]["cwr"],  "cwr_*.tif"),
#     "iwr":  (DIRECTORIES["processed"]["iwr"],  "iwr_*.tif"),
#     "etc":  (DIRECTORIES["processed"]["ETc"],  "etc_*.tif"),
# }

# EXPORT_DIR   = DIRECTORIES["export"]["geoserver"]
# HISTORY_DIR  = EXPORT_DIR / "history"
# FORECAST_DIR = EXPORT_DIR / "forecast"

# for _param in PARAMS:
#     (HISTORY_DIR / _param).mkdir(parents=True, exist_ok=True)
# for _param in FC_PARAMS:
#     (FORECAST_DIR / _param).mkdir(parents=True, exist_ok=True)


# # ═══════════════════════════════════════════════════════════════════════════
# # SEASONAL HELPERS
# # ═══════════════════════════════════════════════════════════════════════════

# def get_season_id(date: datetime) -> str:
#     """
#     Return a canonical season string for a date, e.g. '2024-25'.
#     Season starts November 1; dates May–October fall outside any Rabi season.
#     """
#     m, y = date.month, date.year
#     if m >= SEASON_START_MONTH:          # Nov or Dec → season started this year
#         return f"{y}-{str(y + 1)[-2:]}"
#     elif m <= SEASON_END_MONTH:          # Jan–Apr → season started last year
#         return f"{y - 1}-{str(y)[-2:]}"
#     else:                                # May–Oct → off-season
#         return None


# def is_in_season(date: datetime) -> bool:
#     """Return True if date falls in Nov–Apr (Rabi season)."""
#     return date.month in SEASON_MONTHS


# def get_season_start(season_id: str) -> datetime:
#     """Return Nov 1 of the start year for a season string like '2024-25'."""
#     start_year = int(season_id.split("-")[0])
#     return datetime(start_year, SEASON_START_MONTH, 1)


# def get_allowed_season_ids() -> List[str]:
#     """
#     Return the list of season IDs (newest-first) that fall within the
#     MAX_SEASONS retention window.

#     Logic:
#       • Find the 'current' season (the one containing today or the most
#         recent completed season).
#       • Keep the last MAX_SEASONS seasons counting backwards from there.
#     """
#     today = datetime.utcnow()
#     # Determine the 'anchor' season
#     current = get_season_id(today)
#     if current is None:
#         # We are in the off-season (May–Oct).  Anchor = last completed season.
#         # Last completed season started in November of (this_year - 1).
#         anchor_year = today.year - 1
#         current = f"{anchor_year}-{str(anchor_year + 1)[-2:]}"

#     anchor_start_year = int(current.split("-")[0])
#     seasons = []
#     for i in range(MAX_SEASONS):
#         y = anchor_start_year - i
#         seasons.append(f"{y}-{str(y + 1)[-2:]}")
#     return seasons   # newest first


# def filter_to_allowed_seasons(dates: List[datetime]) -> List[datetime]:
#     """
#     Given a list of datetimes, return only those that:
#       1. Fall in Nov–Apr (Rabi season months)
#       2. Belong to one of the MAX_SEASONS allowed seasons
#     """
#     allowed = set(get_allowed_season_ids())
#     out = []
#     for d in dates:
#         if not is_in_season(d):
#             continue
#         sid = get_season_id(d)
#         if sid and sid in allowed:
#             out.append(d)
#     return out


# # ═══════════════════════════════════════════════════════════════════════════
# # SLOT HELPERS
# # ═══════════════════════════════════════════════════════════════════════════

# def slot_for_index(idx: int) -> str:
#     return "today" if idx == 0 else str(idx)


# def _make_slots(n: int) -> List[str]:
#     return ["today"] + [str(i) for i in range(1, n)]


# # ═══════════════════════════════════════════════════════════════════════════
# # GLOBAL MODEL CACHE
# # ═══════════════════════════════════════════════════════════════════════════

# _MODEL_CACHE: Dict = {}
# _fc_cache: Dict = {"pet_count": -1}


# def _get_model(model_type: str):
#     global _MODEL_CACHE
#     if model_type in _MODEL_CACHE:
#         return _MODEL_CACHE[model_type]
#     try:
#         model, meta = models.load_model(model_type)
#         _MODEL_CACHE[model_type] = (model, meta)
#         logger.info(f"✓ Loaded {model_type.upper()} SARIMAx model "
#                     f"(R²={meta['metrics']['R2']:.4f})")
#         return model, meta
#     except FileNotFoundError:
#         logger.warning(f"Model {model_type} not found — training now...")
#         models.train_all_models()
#         model, meta = models.load_model(model_type)
#         _MODEL_CACHE[model_type] = (model, meta)
#         return model, meta
#     except Exception as e:
#         logger.error(f"Failed to load {model_type} model: {e}")
#         return None, None


# # ═══════════════════════════════════════════════════════════════════════════
# # PATH HELPERS
# # ═══════════════════════════════════════════════════════════════════════════

# def history_path(param: str, slot: str) -> Path:
#     return HISTORY_DIR / param / f"{param}_{slot}.tif"


# def forecast_path(param: str, slot: str, window: str) -> Path:
#     return FORECAST_DIR / param / f"{param}_{slot}_{window}.tif"


# # ═══════════════════════════════════════════════════════════════════════════
# # DATA LOADING HELPERS
# # ═══════════════════════════════════════════════════════════════════════════

# def _parse_date(name: str) -> Optional[datetime]:
#     m = re.search(r"\d{8}", name)
#     if m:
#         try:
#             return datetime.strptime(m.group(), "%Y%m%d")
#         except ValueError:
#             pass
#     return None


# def _dated_files(directory: Path, pattern: str) -> List[Tuple[datetime, Path]]:
#     out = []
#     for p in directory.glob(pattern):
#         d = _parse_date(p.name)
#         if d:
#             out.append((d, p))
#     out.sort(key=lambda x: x[0])
#     return out


# def _latest_n_complete_dates(n: int = HISTORY_DATES) -> List[datetime]:
#     """
#     N most-recent dates where ALL core parameters (savi, kc, cwr, iwr) have
#     processed rasters AND the date falls within the allowed seasonal window
#     (Nov–Apr, last MAX_SEASONS seasons).  Newest-first.

#     ETc is optional — its absence does not exclude a date.
#     """
#     core_params = ["savi", "kc", "etc" , "cwr", "iwr"]
#     date_sets = []
#     for param in core_params:
#         src_dir, pattern = _SRC[param]
#         dates = {d for d, _ in _dated_files(src_dir, pattern)}
#         if not dates:
#             logger.warning(f"No {param} files in {src_dir}")
#             return []
#         date_sets.append(dates)

#     complete = set.intersection(*date_sets)

#     # Apply seasonal filter
#     seasonal = filter_to_allowed_seasons(sorted(complete, reverse=True))

#     return seasonal[:n]


# def _read_mean(path: Path) -> Optional[float]:
#     if not path.exists():
#         return None
#     try:
#         with rasterio.open(path) as src:
#             data = src.read(1).astype(np.float64)
#             nd   = float(src.nodata) if src.nodata else float(NODATA)
#             data[data == np.float64(nd)] = np.nan
#             v = float(np.nanmean(data))
#             return None if np.isnan(v) else round(v, 4)
#     except Exception:
#         return None


# def _processed_mean_for_date(param: str, date: datetime) -> Optional[float]:
#     src = _SRC.get(param)
#     if src is None:
#         return None
#     src_dir, pattern = src
#     date_key = date.replace(hour=0, minute=0, second=0, microsecond=0)
#     for d, path in _dated_files(src_dir, pattern):
#         if d == date_key:
#             return _read_mean(path)
#     return None


# def _reference_mean(param: str, reference_date: datetime, fallback: Optional[float] = None) -> Optional[float]:
#     value = _processed_mean_for_date(param, reference_date)
#     if value is not None:
#         return value
#     for idx, d in enumerate(_latest_n_complete_dates(HISTORY_DATES)):
#         if d.date() == reference_date.date():
#             value = _read_mean(history_path(param, slot_for_index(idx)))
#             if value is not None:
#                 return value
#     return fallback


# def _load_slot_array(param: str, slot: str) -> Optional[np.ndarray]:
#     p = history_path(param, slot)
#     if not p.exists():
#         return None
#     try:
#         with rasterio.open(p) as src:
#             data = src.read(1).astype(np.float64)
#             nd   = float(src.nodata) if src.nodata is not None else float(NODATA)
#             data[data == np.float64(nd)]       = np.nan
#             data[data == np.float64(NODATA)]   = np.nan
#         return data
#     except Exception as e:
#         logger.error(f"[load] {p.name}: {e}")
#         return None


# # ═══════════════════════════════════════════════════════════════════════════
# # WHEAT MASK
# # ═══════════════════════════════════════════════════════════════════════════

# _WHEAT_MASK_CACHE: Optional[Dict] = None


# def _get_wheat_mask() -> Optional[Dict]:
#     global _WHEAT_MASK_CACHE
#     if _WHEAT_MASK_CACHE is not None:
#         return _WHEAT_MASK_CACHE

#     mask_path = DIRECTORIES["processed"]["masks"] / "wheat_mask.tif"
#     if not mask_path.exists():
#         logger.error(f"wheat_mask.tif not found: {mask_path}")
#         return None

#     try:
#         with rasterio.open(mask_path) as src:
#             raw = src.read(1)
#             _WHEAT_MASK_CACHE = {
#                 "crs":       src.crs,
#                 "transform": src.transform,
#                 "width":     src.width,
#                 "height":    src.height,
#                 "mask_bool": (raw > 0),
#             }
#         logger.info(
#             f"Wheat mask: {_WHEAT_MASK_CACHE['width']}×{_WHEAT_MASK_CACHE['height']} | "
#             f"wheat pixels = {_WHEAT_MASK_CACHE['mask_bool'].sum():,}"
#         )
#     except Exception as e:
#         logger.error(f"Failed to load wheat_mask: {e}")
#     return _WHEAT_MASK_CACHE


# # ═══════════════════════════════════════════════════════════════════════════
# # SEASONAL PURGE — delete rasters outside the retention window
# # ═══════════════════════════════════════════════════════════════════════════

# def purge_out_of_season_rasters() -> int:
#     """
#     Delete any history raster whose embedded acquisition_date tag falls
#     outside the allowed MAX_SEASONS window.  Also prunes raw processed files
#     older than the retention window to free disk space.

#     Returns count of deleted files.
#     """
#     allowed_seasons = set(get_allowed_season_ids())
#     deleted = 0

#     for param in PARAMS:
#         param_dir = HISTORY_DIR / param
#         for tif in param_dir.glob("*.tif"):
#             try:
#                 with rasterio.open(tif) as src:
#                     acq = src.tags().get("acquisition_date")
#                 if not acq:
#                     continue
#                 d = datetime.strptime(acq, "%Y-%m-%d")
#                 if not is_in_season(d):
#                     tif.unlink()
#                     deleted += 1
#                     logger.info(f"[purge] off-season: {tif.name}")
#                     continue
#                 sid = get_season_id(d)
#                 if sid and sid not in allowed_seasons:
#                     tif.unlink()
#                     deleted += 1
#                     logger.info(f"[purge] old season {sid}: {tif.name}")
#             except Exception:
#                 pass

#     # Purge forecast rasters whose slot raster was deleted
#     for param in FC_PARAMS:
#         for tif in (FORECAST_DIR / param).glob("*.tif"):
#             try:
#                 with rasterio.open(tif) as src:
#                     acq = src.tags().get("acquisition_date") or src.tags().get("reference_date")
#                 if acq:
#                     d = datetime.strptime(acq, "%Y-%m-%d")
#                     sid = get_season_id(d)
#                     if not is_in_season(d) or (sid and sid not in allowed_seasons):
#                         tif.unlink()
#                         deleted += 1
#             except Exception:
#                 pass

#     if deleted:
#         logger.info(f"[purge] Removed {deleted} out-of-retention rasters")
#     return deleted


# def cleanup_old_rasters():
#     """
#     Remove any slot-named raster files that no longer correspond to a valid
#     slot (i.e. the current set of seasonal dates).  Runs purge first.
#     """
#     purge_out_of_season_rasters()

#     dates = _latest_n_complete_dates(HISTORY_DATES)
#     n = len(dates)
#     valid_slots = _make_slots(n)

#     for param in PARAMS:
#         valid_history = {f"{param}_{s}.tif" for s in valid_slots}
#         for f in (HISTORY_DIR / param).glob("*.tif"):
#             if f.name not in valid_history:
#                 f.unlink()
#                 logger.debug(f"[cleanup] removed stale slot file: {f.name}")

#     for param in FC_PARAMS:
#         valid_forecast = {
#             f"{param}_{s}_{w}.tif"
#             for s in valid_slots
#             for w in FORECAST_WINDOWS
#         }
#         for f in (FORECAST_DIR / param).glob("*.tif"):
#             if f.name not in valid_forecast:
#                 f.unlink()
#                 logger.debug(f"[cleanup] removed stale forecast file: {f.name}")


# # ═══════════════════════════════════════════════════════════════════════════
# # RASTER I/O
# # ═══════════════════════════════════════════════════════════════════════════

# def _reproject_and_write(
#     src_path: Path,
#     dst_path: Path,
#     param: str,
#     date: datetime,
#     extra_tags: Optional[Dict] = None,
# ) -> bool:
#     grid = _get_wheat_mask()
#     if grid is None:
#         return False

#     vmin, vmax = _VALID.get(param, (-1e9, 1e9))

#     try:
#         with rasterio.open(src_path) as src:
#             data       = src.read(1).astype(np.float64)
#             src_nd     = src.nodata
#             src_crs    = src.crs
#             src_trans  = src.transform

#         if src_nd is not None:
#             data[data == np.float64(src_nd)] = np.nan
#         data[data == np.float64(-9999.0)] = np.nan
#         data[data == np.float64(-999.0)]  = np.nan

#         dst = np.full((grid["height"], grid["width"]), np.nan, dtype=np.float64)
#         rasterio.warp.reproject(
#             source=data,
#             destination=dst,
#             src_transform=src_trans,
#             src_crs=src_crs,
#             dst_transform=grid["transform"],
#             dst_crs=grid["crs"],
#             resampling=Resampling.nearest,
#             src_nodata=None,
#             dst_nodata=None,
#         )

#         dst[dst > vmax] = np.nan
#         if param == "cwr":
#             dst[(~np.isnan(dst)) & (dst <= 0.0)] = np.nan
#         dst[dst < vmin] = np.nan
#         dst[~grid["mask_bool"]] = np.nan

#         out     = np.where(np.isnan(dst), float(NODATA), dst).astype(np.float64)
#         profile = {
#             "driver":     "GTiff",
#             "dtype":      rasterio.float64,
#             "count":      1,
#             "crs":        grid["crs"],
#             "transform":  grid["transform"],
#             "width":      grid["width"],
#             "height":     grid["height"],
#             "nodata":     float(NODATA),
#             "compress":   "lzw",
#             "tiled":      True,
#             "blockxsize": 256,
#             "blockysize": 256,
#         }

#         dst_path.parent.mkdir(parents=True, exist_ok=True)
#         with rasterio.open(dst_path, "w", **profile) as f:
#             f.write(out, 1)
#             mean_val = float(np.nanmean(dst)) if np.any(~np.isnan(dst)) else None
#             tags = {
#                 "parameter":        param,
#                 "acquisition_date": date.strftime("%Y-%m-%d"),
#                 "season":           get_season_id(date) or "",
#                 "mean":             str(round(mean_val, 4)) if mean_val is not None else "",
#             }
#             if extra_tags:
#                 tags.update(extra_tags)
#             f.update_tags(**tags)
#         return True
#     except Exception as e:
#         logger.error(f"[raster] {src_path.name}→{dst_path.name}: {e}")
#         return False


# def _write_array_raster(
#     data: np.ndarray,
#     template: Path,
#     dst_path: Path,
#     tags: Dict,
# ) -> bool:
#     try:
#         with rasterio.open(template) as src:
#             profile = src.profile.copy()
#         profile.update(
#             dtype="float64",
#             count=1,
#             nodata=float(NODATA),
#             compress="lzw",
#             tiled=True,
#             blockxsize=256,
#             blockysize=256,
#         )
#         dst_path.parent.mkdir(parents=True, exist_ok=True)
#         with rasterio.open(dst_path, "w", **profile) as f:
#             f.write(data.astype(np.float64), 1)
#             f.update_tags(**tags)
#         return True
#     except Exception as e:
#         logger.error(f"[raster] write {dst_path.name}: {e}")
#         return False


# def _pixel_avg(arrays: List[np.ndarray]) -> np.ndarray:
#     stack = np.stack(arrays, axis=0)
#     valid = (stack != float(NODATA)) & ~np.isnan(stack)
#     total = np.where(valid, stack, 0.0).sum(axis=0)
#     count = valid.sum(axis=0).astype(np.float64)
#     return np.where(count > 0, total / count, float(NODATA)).astype(np.float64)


# # ═══════════════════════════════════════════════════════════════════════════
# # STEP A — HISTORY RASTERS
# # ═══════════════════════════════════════════════════════════════════════════

# def generate_history_rasters() -> int:
#     """
#     Write history/{param}/{param}_{slot}.tif for every param × slot.
#     Slots are assigned newest-first from the seasonal-filtered date list.
#     ETc is optional — missing ETc for a date is silently skipped.
#     """
#     dates = _latest_n_complete_dates(HISTORY_DATES)
#     if not dates:
#         logger.error("[history] No complete Sentinel dates in allowed seasons")
#         return 0

#     logger.info(
#         f"[history] {len(dates)} seasonal dates: "
#         f"{dates[-1].date()} → {dates[0].date()} "
#         f"| seasons={sorted(set(get_season_id(d) for d in dates))}"
#     )
#     total = 0

#     for param, (src_dir, pattern) in _SRC.items():
#         src_by_date = {d: p for d, p in _dated_files(src_dir, pattern)}
#         for idx, date in enumerate(dates):
#             src_path = src_by_date.get(date)
#             if src_path is None:
#                 if param != "etc":
#                     logger.warning(f"[history] {param} missing for {date.date()}")
#                 continue
#             slot     = slot_for_index(idx)
#             dst_path = history_path(param, slot)

#             if dst_path.exists():
#                 try:
#                     with rasterio.open(dst_path) as f:
#                         if f.tags().get("acquisition_date") == date.strftime("%Y-%m-%d"):
#                             total += 1
#                             continue
#                 except Exception:
#                     pass

#             if _reproject_and_write(src_path, dst_path, param, date,
#                                      extra_tags={"slot": slot}):
#                 total += 1
#                 logger.info(f"[history] {dst_path.name} ({date.date()})")

#         logger.info(f"[history] {param} done")

#     logger.info(f"[history] Total: {total} / {len(dates) * len(PARAMS)}")
#     return total


# # ═══════════════════════════════════════════════════════════════════════════
# # STEP B — FORECASTING  (Thesis-compliant)
# # ═══════════════════════════════════════════════════════════════════════════

# def _effective_rainfall_daily(rain_mm: float) -> float:
#     rain_mm = max(float(rain_mm), 0.0)
#     period_factor = 1.0 / 30.0
#     threshold = 75.0 * period_factor
#     if rain_mm > threshold:
#         return max(0.0, 0.8 * rain_mm - 25.0 * period_factor)
#     return max(0.0, 0.6 * rain_mm - 10.0 * period_factor)


# def _rainfall_mean_for_date(date: datetime, rain_by_date: Dict[datetime, Path]) -> float:
#     date_key = date.replace(hour=0, minute=0, second=0, microsecond=0)
#     rain_path = rain_by_date.get(date_key)
#     if rain_path is None:
#         return 0.0
#     rain_val = raster_mean(rain_path, mask_zeros=False)
#     return float(rain_val) if np.isfinite(rain_val) and rain_val >= 0 else 0.0


# def _climatological_peff(future_dates: pd.DatetimeIndex) -> np.ndarray:
#     rain_dir = DIRECTORIES["raw"].get("insat_rain")
#     rain_by_date: Dict[datetime, Path] = {}

#     if rain_dir and Path(rain_dir).exists():
#         for rain_path in Path(rain_dir).glob("*.tif"):
#             try:
#                 rain_date = models.extract_date(rain_path.name)
#                 rain_by_date[rain_date.replace(hour=0, minute=0, second=0, microsecond=0)] = rain_path
#             except Exception:
#                 continue

#     peff_vals = np.array([
#         _effective_rainfall_daily(
#             _rainfall_mean_for_date(
#                 d.to_pydatetime() if hasattr(d, "to_pydatetime") else d,
#                 rain_by_date,
#             )
#         )
#         for d in future_dates
#     ], dtype=float)

#     logger.info(
#         f"[forecast] Peff mean={peff_vals.mean():.3f} mm/day "
#         f"range={peff_vals.min():.3f}–{peff_vals.max():.3f}"
#     )
#     return peff_vals


# def _project_kc_for_dates(
#     future_dates: pd.DatetimeIndex,
#     reference_date: Optional[datetime] = None,
# ) -> Tuple[np.ndarray, np.ndarray]:
#     kc_model, kc_meta = _get_model("kc")

#     anchor_date = reference_date or (future_dates[0].to_pydatetime() - timedelta(days=1))
#     last_kc_obs = _reference_mean("kc", anchor_date, 0.80) or 0.80
#     last_savi_obs = _reference_mean("savi", anchor_date, None) or (
#         (last_kc_obs - KC_INTERCEPT) / KC_SLOPE
#     )
#     set_forecast_context(last_savi=last_savi_obs, last_kc=last_kc_obs)

#     days_ahead = np.arange(1, len(future_dates) + 1, dtype=float)

#     if kc_model is not None:
#         logger.info("Using trained SARIMA Kc model for forecast")
#         exog_cols = kc_meta.get("exog_cols", ["sin_doy", "cos_doy", "sin2_doy", "cos2_doy"])
#         exog_df = build_forecast_exog(future_dates=future_dates, exog_cols=exog_cols)

#         if hasattr(kc_model, "get_forecast"):
#             kc_fc = kc_model.get_forecast(steps=len(future_dates), exog=exog_df)
#             kc_forecast = kc_fc.predicted_mean.values.astype(float)
#         else:
#             kc_forecast = kc_model.forecast(steps=len(future_dates), exog=exog_df).values.astype(float)

#         stage_kc = np.array([
#             get_wheat_stage_kc(d.to_pydatetime())[1]
#             for d in future_dates
#         ], dtype=float)
#         kc_forecast = 0.65 * kc_forecast + 0.35 * stage_kc
#         alpha = np.exp(-days_ahead / 5.0)
#         kc_forecast = alpha * float(last_kc_obs) + (1 - alpha) * kc_forecast

#     else:
#         logger.warning("No Kc SARIMA model — using FAO-56 stage Kc")
#         kc_forecast = np.array([
#             get_wheat_stage_kc(d.to_pydatetime())[1]
#             for d in future_dates
#         ], dtype=float)

#     kc_forecast = np.clip(kc_forecast, KC_MIN, KC_MAX)
#     savi_forecast = np.clip((kc_forecast - KC_INTERCEPT) / KC_SLOPE, -0.1, 0.9)

#     first_stage, first_kc_fao = get_wheat_stage_kc(future_dates[0].to_pydatetime())
#     logger.info(
#         f"Kc forecast: Kc_mean={kc_forecast.mean():.3f}, "
#         f"range={kc_forecast.min():.3f}–{kc_forecast.max():.3f} "
#         f"| crop_stage={first_stage} (FAO-56 Kc={first_kc_fao:.3f})"
#     )
#     return savi_forecast, kc_forecast


# def generate_forecast_for_date(
#     reference_date: datetime,
#     days: int = FORECAST_DAYS,
# ) -> Dict[str, pd.Series]:
#     """
#     THESIS-COMPLIANT forecasting pipeline.
#     Chain: Kc (SARIMA) → PET (SARIMA) → CWR = Kc × PET → IWR = max(CWR−Peff,0)
#     """
#     forecasts: Dict[str, pd.Series] = {}

#     future_dates = pd.date_range(
#         start=reference_date + timedelta(days=1),
#         periods=days,
#         freq="D",
#     )

#     # ── 1. Forecast Kc ──────────────────────────────────────────────────────
#     kc_model, kc_meta = _get_model("kc")
#     if kc_model is None:
#         raise RuntimeError("[forecast] Kc model not available.")

#     last_kc_obs = _reference_mean("kc", reference_date, kc_meta.get("last_kc", 0.80)) or 0.80
#     last_savi_obs = _reference_mean("savi", reference_date, None) or kc_meta.get(
#         "last_savi", (last_kc_obs - KC_INTERCEPT) / KC_SLOPE,
#     )
#     set_forecast_context(last_savi=last_savi_obs, last_kc=last_kc_obs)

#     exog_cols_kc = kc_meta.get("exog_cols", ["sin_doy", "cos_doy", "sin2_doy", "cos2_doy"])
#     exog_kc = build_forecast_exog(future_dates=future_dates, exog_cols=exog_cols_kc)

#     if hasattr(kc_model, "get_forecast"):
#         kc_fc = kc_model.get_forecast(steps=days, exog=exog_kc)
#         kc_values = kc_fc.predicted_mean.values.astype(float)
#     else:
#         kc_values = kc_model.forecast(steps=days, exog=exog_kc).values.astype(float)

#     stage_kc = np.array([
#         get_wheat_stage_kc(d.to_pydatetime())[1]
#         for d in future_dates
#     ], dtype=float)
#     kc_values = 0.65 * kc_values + 0.35 * stage_kc
#     alpha_kc = np.exp(-np.arange(1, days + 1, dtype=float) / 5.0)
#     kc_values = alpha_kc * float(last_kc_obs) + (1 - alpha_kc) * kc_values
#     kc_values = np.clip(kc_values, KC_MIN, KC_MAX)
#     forecasts["kc"] = pd.Series(kc_values, index=future_dates, name="kc")

#     # ── 2. Forecast PET ─────────────────────────────────────────────────────
#     pet_model, pet_meta = _get_model("pet")
#     if pet_model is None:
#         raise RuntimeError("[forecast] PET model not available.")

#     last_cwr_obs = _reference_mean("cwr", reference_date, 3.5) or 3.5
#     last_pet_obs = pet_meta.get("last_pet")
#     if last_pet_obs is None or not np.isfinite(last_pet_obs):
#         last_pet_obs = last_cwr_obs / last_kc_obs if last_kc_obs > 0 else 4.0

#     set_forecast_context(
#         last_savi=last_savi_obs, last_kc=last_kc_obs, last_pet=float(last_pet_obs),
#     )
#     exog_cols_pet = pet_meta.get("exog_cols", ["sin_doy", "cos_doy", "sin2_doy", "cos2_doy", "month"])
#     exog_pet = build_forecast_exog(future_dates=future_dates, exog_cols=exog_cols_pet)

#     if hasattr(pet_model, "get_forecast"):
#         pet_fc = pet_model.get_forecast(steps=days, exog=exog_pet)
#         base_pet = pet_fc.predicted_mean.values.astype(float)
#     else:
#         base_pet = pet_model.forecast(steps=days, exog=exog_pet).values.astype(float)
#     if pet_meta.get("target_transform") == "log1p":
#         base_pet = np.expm1(base_pet)

#     doy = future_dates.dayofyear.values.astype(float)
#     seasonal_pet = 5.5 + 3.2 * np.sin(2 * np.pi * (doy - 45) / 365.25)
#     pet_values = 0.65 * base_pet + 0.35 * seasonal_pet
#     alpha_pet = np.exp(-np.arange(days) / 5.0)
#     pet_values = alpha_pet * float(last_pet_obs) + (1 - alpha_pet) * pet_values
#     pet_values = np.clip(pet_values, 1.5, 12.0)
#     forecasts["pet"] = pd.Series(pet_values, index=future_dates, name="pet")

#     # ── 3. CWR = Kc × PET ───────────────────────────────────────────────────
#     cwr_arr = np.clip(kc_values * pet_values, CWR_MIN, CWR_MAX)
#     forecasts["cwr"] = pd.Series(cwr_arr, index=future_dates, name="cwr")

#     # ── 4. IWR = max(CWR − Peff, 0) ─────────────────────────────────────────
#     peff_arr = _climatological_peff(future_dates)
#     iwr_arr = np.maximum(cwr_arr - peff_arr, 0.0)
#     forecasts["iwr"] = pd.Series(iwr_arr, index=future_dates, name="iwr")
#     forecasts["peff"] = pd.Series(peff_arr, index=future_dates, name="peff")

#     # ── SAVI (derived from Kc) ───────────────────────────────────────────────
#     savi_arr = np.clip((kc_values - KC_INTERCEPT) / KC_SLOPE, -0.1, 0.9)
#     forecasts["savi"] = pd.Series(savi_arr, index=future_dates, name="savi")

#     # ── ETc = Kc × PET = CWR (daily evapotranspiration rate, same physics) ──
#     # ETc forecast uses DAILY VALUES (not cumulative) — aggregated as AVERAGE.
#     forecasts["etc"] = pd.Series(cwr_arr.copy(), index=future_dates, name="etc")

#     stage_info = get_wheat_stage_info(future_dates[0].to_pydatetime())
#     logger.info(
#         f"[forecast] Generated for {reference_date.date()}: "
#         f"stage={stage_info['stage']} "
#         f"Kc_mean={forecasts['kc'].mean():.3f}, "
#         f"PET_mean={forecasts['pet'].mean():.2f}, "
#         f"CWR_mean={forecasts['cwr'].mean():.2f}, "
#         f"IWR_mean={forecasts['iwr'].mean():.2f}"
#     )
#     return forecasts


# def _forecast_raster_is_fresh(param: str, slot: str, window: str, date: datetime) -> bool:
#     """
#     Return True when a forecast raster already exists AND was generated from
#     exactly the same reference date.  This lets us skip the expensive SARIMA
#     re-forecast for slots that have not changed since the last pipeline run.
#     """
#     p = forecast_path(param, slot, window)
#     if not p.exists():
#         return False
#     try:
#         with rasterio.open(p) as src:
#             tags = src.tags()
#             return tags.get("acquisition_date") == date.strftime("%Y-%m-%d")
#     except Exception:
#         return False


# def create_forecast_raster(
#     param: str,
#     slot: str,
#     window: str,
#     forecast_series: pd.Series,
#     template_raster: Path,
#     date: datetime,                     # ← actual acquisition date of this slot
# ) -> bool:
#     """
#     Write a single forecast raster.

#     Aggregation rules
#     -----------------
#     CWR / IWR  →  cumulative SUM  over the window  (units: mm_total)
#     ETc  / Kc  →  spatial AVERAGE over the window  (units: mm/day or dimensionless)
#     """
#     # ── Fast-path: skip if the raster already reflects this date ──────────
#     if _forecast_raster_is_fresh(param, slot, window, date):
#         logger.debug(f"[forecast] skip {param} {slot} {window} — already fresh")
#         return True

#     try:
#         WINDOW_SLICES = {"5day": (0, 5), "10day": (0, 10), "15day": (0, 15)}
#         start_idx, end_idx = WINDOW_SLICES[window]
#         window_days = end_idx - start_idx

#         with rasterio.open(template_raster) as src:
#             template_data = src.read(1).astype(np.float64)
#             nodata        = src.nodata if src.nodata is not None else NODATA
#             template_data = np.where(template_data == nodata, np.nan, template_data)
#             profile       = src.profile.copy()

#             window_forecast = forecast_series.iloc[start_idx:end_idx]

#             # ── CWR & IWR: cumulative total over the window ────────────────
#             if param in ["cwr", "iwr"]:
#                 forecast_val = float(window_forecast.sum())
#                 agg_label    = "total"
#                 unit_label   = "mm"
#                 units_tag    = "mm_total"
#             # ── ETc & Kc: daily average over the window ────────────────────
#             else:
#                 forecast_val = float(window_forecast.mean())
#                 agg_label    = "mean"
#                 unit_label   = "mm/day" if param == "etc" else ""
#                 units_tag    = "mm_per_day" if param == "etc" else ""

#             stage_info = get_wheat_stage_info(window_forecast.index[0].to_pydatetime())

#         valid = ~np.isnan(template_data)
#         if not valid.any():
#             logger.warning(f"No valid pixels in template for {param} {slot}")
#             return False

#         template_mean = float(np.nanmean(template_data[valid]))

#         # Scale the spatial pattern of the template raster to the forecast value.
#         # For CWR/IWR the template is in mm/day; scaling by (sum / daily_mean)
#         # = (mean_daily × window_days / daily_mean) correctly yields mm_total
#         # spatial values while preserving the relative spatial distribution.
#         if template_mean > 0:
#             scale_factor   = forecast_val / template_mean
#             forecast_array = np.where(valid, template_data * scale_factor, np.nan)
#         else:
#             forecast_array = np.where(valid, forecast_val, np.nan)

#         # Clip to the correct valid range (cumulative for CWR/IWR)
#         vmin, vmax     = _VALID_FC.get(param, _VALID.get(param, (-1e9, 1e9)))
#         forecast_array = np.clip(forecast_array, vmin, vmax)

#         dst_path = forecast_path(param, slot, window)
#         profile.update(
#             dtype="float64",
#             nodata=NODATA,
#             compress="lzw",
#             tiled=True,
#             blockxsize=256,
#             blockysize=256,
#         )

#         with rasterio.open(dst_path, "w", **profile) as dst:
#             out_data = np.where(np.isnan(forecast_array), NODATA, forecast_array)
#             dst.write(out_data.astype(np.float64), 1)
#             dst.update_tags(
#                 parameter=param,
#                 slot=slot,
#                 forecast_window=window,
#                 acquisition_date=date.strftime("%Y-%m-%d"),   # ← actual date for freshness check
#                 reference_date=date.strftime("%Y-%m-%d"),
#                 forecast_mean=str(round(forecast_val, 4)),
#                 template_mean=str(round(template_mean, 4)),
#                 crop_stage=stage_info["stage"],
#                 days_after_sowing=str(stage_info["das"]),
#                 kc_fao56=str(round(stage_info["kc_fao56"], 4)),
#                 units=units_tag,
#                 aggregation="sum" if param in ["cwr", "iwr"] else "mean",
#                 window_days=str(window_days),
#                 model="PET-SARIMAX+Physics-CWR/IWR",
#                 generated_by="irrigation_monitoring_v10.1",
#             )

#         logger.info(
#             f"Created {param} forecast for {slot} {window}: "
#             f"{agg_label}={forecast_val:.4f} "
#             f"{unit_label}"
#         )
#         return True

#     except Exception as e:
#         logger.error(f"Failed to create {param} forecast for {slot}_{window}: {e}")
#         return False


# def generate_all_forecast_rasters() -> int:
#     dates = _latest_n_complete_dates(HISTORY_DATES)
#     if not dates:
#         logger.error("[forecast] No Sentinel dates available")
#         return 0

#     total = 0
#     n = len(dates)
#     slots = _make_slots(n)

#     for idx, date in enumerate(dates):
#         slot = slots[idx]

#         # ── Slot-level freshness check ──────────────────────────────────────
#         # If every expected forecast raster for this slot already carries the
#         # correct acquisition_date tag, the SARIMA forecast can be skipped
#         # entirely — saving minutes of compute per slot.
#         params_with_template = [
#             p for p in FC_PARAMS if history_path(p, slot).exists()
#         ]
#         all_fresh = bool(params_with_template) and all(
#             _forecast_raster_is_fresh(p, slot, w, date)
#             for p in params_with_template
#             for w in FORECAST_WINDOWS
#         )
#         if all_fresh:
#             n_skip = len(params_with_template) * len(FORECAST_WINDOWS)
#             total += n_skip
#             logger.debug(
#                 f"[forecast] slot={slot} ({date.date()}): "
#                 f"all {n_skip} rasters fresh — skipping SARIMA"
#             )
#             continue

#         # ── Run SARIMA forecast for this reference date ────────────────────
#         forecasts = generate_forecast_for_date(date, FORECAST_DAYS)
#         if not forecasts:
#             logger.warning(f"[forecast] No forecast for {slot} ({date.date()})")
#             continue

#         n_rasters = 0
#         for param in FC_PARAMS:
#             if param not in forecasts:
#                 continue
#             for window in FORECAST_WINDOWS:
#                 template = history_path(param, slot)
#                 if template.exists():
#                     if create_forecast_raster(
#                         param, slot, window,
#                         forecasts[param], template,
#                         date,           # ← actual date for freshness tag
#                     ):
#                         n_rasters += 1
#                         total += 1

#         logger.info(f"[forecast] slot={slot} ({date.date()}): {n_rasters} files written")

#     expected_total = n * len(FC_PARAMS) * len(FORECAST_WINDOWS)
#     logger.info(f"[forecast] ALL: {total} / {expected_total}")
#     return total


# # ═══════════════════════════════════════════════════════════════════════════
# # STEP C — PUSH TO GEOSERVER
# # ═══════════════════════════════════════════════════════════════════════════

# def push_to_geoserver() -> None:
#     try:
#         from init_geoserver import GeoServerAPI
#         gs = GeoServerAPI()
#     except Exception as e:
#         logger.warning(f"[geoserver] Cannot init GeoServerAPI: {e}")
#         return

#     dates = _latest_n_complete_dates(HISTORY_DATES)
#     n = len(dates)
#     slots = _make_slots(n)

#     for param in PARAMS:
#         for slot in slots:
#             p = history_path(param, slot)
#             if not p.exists():
#                 continue
#             store = f"{param}_{slot}"
#             style = "etc_style" if param == "etc" else f"{param}_style"
#             try:
#                 store_ok     = gs.create_coverage_store_if_not_exists(store, p)
#                 file_ok      = gs.update_coverage_store_file(store, p)
#                 configure_ok = gs.configure_layer(layer_name=store, store_name=store)
#                 style_ok     = gs.assign_style(store, style)
#                 if store_ok and file_ok and configure_ok and style_ok:
#                     logger.info(f"[geoserver] ✅ Layer ready: {store}")
#                 else:
#                     logger.warning(f"[geoserver] ⚠ Partial: {store}")
#             except Exception as e:
#                 logger.warning(f"[geoserver] {store}: {e}")

#     for param in FC_PARAMS:
#         for slot in slots:
#             for window in FORECAST_WINDOWS:
#                 p = forecast_path(param, slot, window)
#                 if not p.exists():
#                     continue
#                 store = f"{param}_{slot}_{window}"
#                 # CWR/IWR forecast rasters are cumulative (mm_total) so they
#                 # need dedicated SLD styles with the wider 0-200 mm colour range.
#                 if param in ("cwr", "iwr"):
#                     fc_style = f"{param}_forecast_style"
#                 else:
#                     fc_style = f"{param}_style"
#                 try:
#                     gs.create_coverage_store_if_not_exists(store, p)
#                     gs.update_coverage_store_file(store, p)
#                     gs.configure_layer(layer_name=store, store_name=store)
#                     gs.assign_style(store, fc_style)
#                     logger.info(f"[geoserver] ✅ Forecast layer ready: {store} (style={fc_style})")
#                 except Exception as e:
#                     logger.warning(f"[geoserver] {store}: {e}")


# # ═══════════════════════════════════════════════════════════════════════════
# # MASTER PIPELINE
# # ═══════════════════════════════════════════════════════════════════════════

# def run_pipeline() -> Dict:
#     logger.info("═" * 65)
#     logger.info("run_pipeline() START — v10.0 (Seasonal Cap + ETc)")
#     logger.info("═" * 65)

#     cleanup_old_rasters()
#     _get_wheat_mask()

#     logger.info("── A: History rasters ──")
#     h_total = generate_history_rasters()

#     logger.info("── B/C: Forecast + rasters ──")
#     _get_model("pet")
#     f_total = generate_all_forecast_rasters()

#     logger.info("── D: GeoServer ──")
#     push_to_geoserver()
#     clear_raster_pixel_cache()

#     dates   = _latest_n_complete_dates()
#     n = len(dates)
#     summary = {
#         "slots":            {slot_for_index(i): str(d.date()) for i, d in enumerate(dates)},
#         "n_dates":          n,
#         "seasons":          sorted(set(get_season_id(d) for d in dates)),
#         "history_rasters":  h_total,
#         "forecast_rasters": f_total,
#         "grand_total":      h_total + f_total,
#         "units":            "mm_per_day",
#         "forecast_model":   "PET-SARIMAX + Physics CWR/IWR",
#     }
#     logger.info(f"DONE: {summary}")
#     return summary


# # ═══════════════════════════════════════════════════════════════════════════
# # SCHEDULER CALLBACKS
# # ═══════════════════════════════════════════════════════════════════════════

# def generate_operational_rasters() -> None:
#     logger.info("[generate_operational_rasters] START")
#     try:
#         cleanup_old_rasters()
#         h = generate_history_rasters()
#         logger.info(f"[generate_operational_rasters] history rasters: {h}")
#     except Exception as e:
#         logger.error(f"[generate_operational_rasters] history step failed: {e}", exc_info=True)
#     try:
#         f = generate_all_forecast_rasters()
#         logger.info(f"[generate_operational_rasters] forecast rasters: {f}")
#     except Exception as e:
#         logger.error(f"[generate_operational_rasters] forecast step failed: {e}", exc_info=True)
#     try:
#         push_to_geoserver()
#         logger.info("[generate_operational_rasters] GeoServer push done")
#     except Exception as e:
#         logger.error(f"[generate_operational_rasters] GeoServer push failed: {e}", exc_info=True)
#     clear_raster_pixel_cache()
#     logger.info("[generate_operational_rasters] DONE")


# def process_single_sentinel_image(tif_path: Path) -> None:
#     logger.info(f"[process_single_sentinel_image] {tif_path.name}")
#     try:
#         from run import run_savi, run_kc, run_etc, run_cwr, run_iwr
#         from processor import DataProcessor
#         p = DataProcessor()
#         run_savi(p)
#         run_kc(p)
#         run_etc(p)
#         run_cwr(p)
#         run_iwr(p)
#         logger.info(f"[process_single_sentinel_image] complete for {tif_path.name}")
#     except Exception as e:
#         logger.error(f"[process_single_sentinel_image] failed for {tif_path.name}: {e}", exc_info=True)


# # ═══════════════════════════════════════════════════════════════════════════
# # FastAPI APP
# # ═══════════════════════════════════════════════════════════════════════════

# from graph import router as graph_router

# app = FastAPI(
#     title="Wheat Irrigation Monitoring System",
#     version="10.0.0",
#     description=(
#         "v10.0 — Seasonal cap (5 seasons Nov–Apr) + ETc layer.\n\n"
#         "  • PET forecasted with SARIMAX\n"
#         "  • CWR = Kc × PET  (FAO-56)\n"
#         "  • IWR = max(CWR − Peff, 0)  (FAO-56)\n"
#         "  • ETc added as map layer\n"
#         "  • Calendar shows Nov–Apr only, last 5 seasons\n"
#     ),
# )

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# app.include_router(graph_router)

# from config import STUDY_AREA, EXACT_BOUNDARY


# class ChatRequest(BaseModel):
#     query: str
#     lat: Optional[float] = None
#     lon: Optional[float] = None
#     history: Optional[List[Dict]] = None
#     session_id: Optional[str] = "default"


# class LiveSensorIngestRequest(BaseModel):
#     sensor_id: Optional[str] = "default"
#     timestamp: Optional[str] = None
#     source: Optional[str] = "api"
#     values: Dict[str, object]


# def _chat_query_needs_live_data(query: str, has_location: bool = False) -> bool:
#     q = (query or "").lower()
#     try:
#         from rag_kb import query_requests_live_metrics

#         requested = query_requests_live_metrics(q)
#     except Exception:
#         requested = False

#     if has_location:
#         return requested
#     if re.search(r"\b(what is|what does|meaning|mean|explain|why|how does|ka matlab|kya hota|kyu|kyon)\b", q):
#         return bool(re.search(r"\b(today|now|current|live|pixel|clicked|map|field value|reading|condition)\b", q))
#     return requested or bool(
#         re.search(
#             r"\b(today|now|current|live|pixel|clicked|map|field|area|condition|reading|"
#             r"value|irrigate|irrigation|sinchai|paani|water now|water today|need water|"
#             r"forecast|predict|next)\b",
#             q,
#         )
#     )

# # ═══════════════════════════════════════════════════════════════════════════
# # PIXEL TIMESERIES FROM HISTORY RASTERS
# # ═══════════════════════════════════════════════════════════════════════════

# _PIXEL_REQUEST_LOCK = Lock()
# _LATEST_PIXEL_REQUEST_IDS: Dict[str, int] = {}


# def _register_pixel_request(request_group: str, request_id: int) -> None:
#     if request_id <= 0:
#         return
#     request_group = request_group or "default"
#     with _PIXEL_REQUEST_LOCK:
#         current = _LATEST_PIXEL_REQUEST_IDS.get(request_group, 0)
#         _LATEST_PIXEL_REQUEST_IDS[request_group] = max(current, request_id)


# def _pixel_request_cancelled(request_group: str, request_id: int) -> bool:
#     if request_id <= 0:
#         return False
#     request_group = request_group or "default"
#     with _PIXEL_REQUEST_LOCK:
#         return request_id < _LATEST_PIXEL_REQUEST_IDS.get(request_group, 0)


# def _pixel_from_latlon(lat: float, lon: float) -> Dict:
#     try:
#         return raster_pixel_from_latlon(lat, lon, params=PARAMS)
#     except RasterGridUnavailable as exc:
#         raise HTTPException(status_code=503, detail=str(exc)) from exc
#     except RasterCoordinateError as exc:
#         logger.warning(f"[pixel-ts] invalid coordinate ({lat}, {lon}): {exc}")
#         raise HTTPException(status_code=400, detail=str(exc)) from exc
#     except RasterOutOfBoundsError as exc:
#         raise HTTPException(status_code=404, detail=str(exc)) from exc


# def _read_history_pixel_value(path: Path, pixel: Dict) -> Optional[float]:
#     return raster_read_history_pixel_value(path, pixel, params=PARAMS)


# def _pixel_timeseries(pixel: Dict, request_group: str = "default", request_id: int = 0) -> Dict[str, List[Dict]]:
#     return pixel_timeseries_for_pixel(
#         pixel,
#         params=PARAMS,
#         allowed_seasons=get_allowed_season_ids(),
#         season_id_fn=get_season_id,
#         in_season_fn=is_in_season,
#         cancelled_fn=lambda: _pixel_request_cancelled(request_group, request_id),
#     )


# def _date_for_slot(slot: Optional[str]) -> Optional[datetime]:
#     dates = _latest_n_complete_dates(HISTORY_DATES)
#     if not dates:
#         return None

#     if not slot or slot == "today":
#         return dates[0]

#     try:
#         idx = int(slot)
#     except (TypeError, ValueError):
#         return None

#     if idx < 0 or idx >= len(dates):
#         return None
#     return dates[idx]


# @app.get("/api/pixel-timeseries")
# def get_pixel_timeseries(
#     lat: float = Query(..., description="Latitude of the clicked point"),
#     lon: float = Query(..., description="Longitude of the clicked point"),
#     request_group: str = Query("default", description="Client request group used to isolate stale-read cancellation"),
#     request_id: int = Query(0, description="Client request id used to supersede stale pixel reads"),
# ):
#     """
#     Return the historical time-series for the clicked raster pixel.

#     The response contains one list per raster type (savi/kc/cwr/iwr/etc).
#     Each list is sorted by date and contains { date, value } objects.

#     This samples the same history rasters used by /api/point and GeoServer,
#     so the chart value for any date matches the selected-point value.
#     """

#     _register_pixel_request(request_group, request_id)
#     pixel = _pixel_from_latlon(lat, lon)
#     pixel_id: str = pixel["pixel_id"]
#     logger.debug(
#         f"[pixel-ts] query=({lat:.5f},{lon:.5f}) "
#         f"→ pixel={pixel_id} "
#         f"center=({pixel['latitude']:.5f},{pixel['longitude']:.5f}) "
#         f"native=({pixel['native_x']:.2f},{pixel['native_y']:.2f})"
#     )

#     # ── 2. Read timeseries for each raster type directly from GeoTIFFs ───
#     try:
#         result = _pixel_timeseries(pixel, request_group=request_group, request_id=request_id)
#     except RasterLookupCancelled as exc:
#         raise HTTPException(status_code=409, detail=str(exc)) from exc

#     # ── 3. Return ─────────────────────────────────────────────────────────
#     return {
#         "pixel_id": pixel_id,
#         "row": pixel["row"],
#         "col": pixel["col"],
#         "latitude": round(float(pixel["latitude"]), 7),
#         "longitude": round(float(pixel["longitude"]), 7),
#         "query_latitude": lat,
#         "query_longitude": lon,
#         "source": "history_rasters",
#         "seasons": get_allowed_season_ids(),
#         "timeseries": result,
#     }


# @app.get("/api/boundary")
# async def get_boundary():
#     bounds = EXACT_BOUNDARY.get("bounds") or STUDY_AREA.get("bounds")
#     if not bounds or not all(k in bounds for k in ("north", "south", "east", "west")):
#         bounds = {"north": 29.4400, "south": 28.8900, "west": 78.8800, "east": 80.1040}

#     north, south, east, west = bounds["north"], bounds["south"], bounds["east"], bounds["west"]
#     if north < south: north, south = south, north
#     if east < west:   east, west   = west, east
#     if (north - south) < 0.01: north += 0.05; south -= 0.05
#     if (east - west) < 0.01:   east  += 0.05; west  -= 0.05

#     return {
#         "name":   STUDY_AREA.get("name", "Udham Singh Nagar"),
#         "state":  STUDY_AREA.get("state", "Uttarakhand"),
#         "crs":    STUDY_AREA.get("crs", "EPSG:4326"),
#         "source": STUDY_AREA.get("boundary_source", "static-fallback"),
#         "bounds": {
#             "north": round(north, 6), "south": round(south, 6),
#             "east":  round(east,  6), "west":  round(west,  6),
#         },
#         "leaflet_bounds": [
#             [round(south, 6), round(west, 6)],
#             [round(north, 6), round(east, 6)],
#         ],
#         "center": EXACT_BOUNDARY.get("center") or [
#             round((east + west) / 2, 6),
#             round((north + south) / 2, 6),
#         ],
#         "geojson": EXACT_BOUNDARY.get("geojson", {"type": "FeatureCollection", "features": []}),
#     }


# @app.get("/api/history")
# async def get_history():
#     """
#     Return observed and forecast means for all history slots.

#     Calendar-aware response:
#       • Only Nov–Apr dates from the last MAX_SEASONS seasons
#       • Each slot carries: date, season_id, slot, obs_means, forecast_means
#       • Extra metadata for the frontend calendar (season list, filter helpers)
#     """
#     dates = _latest_n_complete_dates()
#     if not dates:
#         raise HTTPException(status_code=404, detail="No processed Sentinel scenes found")

#     result = []
#     n = len(dates)

#     for idx, d in enumerate(dates):
#         slot      = slot_for_index(idx)
#         obs_means = {}
#         fc_means  = {}

#         for param in PARAMS:
#             path = history_path(param, slot)
#             if path.exists():
#                 with rasterio.open(path) as src:
#                     tags = src.tags()
#                 mean_str         = tags.get("mean")
#                 obs_means[param] = (
#                     float(mean_str)
#                     if mean_str and mean_str not in ("None", "nan", "")
#                     else None
#                 )
#             else:
#                 obs_means[param] = None

#             fc_means[param] = {}
#             if param in FC_PARAMS:
#                 for w in FORECAST_WINDOWS:
#                     fpath = forecast_path(param, slot, w)
#                     if fpath.exists():
#                         with rasterio.open(fpath) as src:
#                             tags = src.tags()
#                         fc_str              = tags.get("forecast_mean")
#                         fc_means[param][w]  = (
#                             float(fc_str)
#                             if fc_str and fc_str not in ("None", "nan", "")
#                             else None
#                         )
#                     else:
#                         fc_means[param][w] = None

#         season_id = get_season_id(d) or ""

#         result.append({
#             "slot":           slot,
#             "date":           str(d.date()),
#             "season":         season_id,
#             "month":          d.month,
#             "year":           d.year,
#             "is_latest":      idx == 0,
#             "obs_means":      obs_means,
#             "forecast_means": fc_means,
#         })

#     # Build season summary for frontend filter UI
#     seasons_present = {}
#     for item in result:
#         sid = item["season"]
#         if sid not in seasons_present:
#             seasons_present[sid] = {"season": sid, "count": 0, "months": set()}
#         seasons_present[sid]["count"] += 1
#         seasons_present[sid]["months"].add(item["month"])

#     seasons_list = [
#         {
#             "season": v["season"],
#             "count":  v["count"],
#             "months": sorted(v["months"]),
#         }
#         for v in sorted(seasons_present.values(), key=lambda x: x["season"], reverse=True)
#     ]

#     return {
#         "n_slots":        n,
#         "max_seasons":    MAX_SEASONS,
#         "season_months":  sorted(SEASON_MONTHS),   # [1,2,3,4,11,12]
#         "allowed_seasons": get_allowed_season_ids(),
#         "seasons":        seasons_list,
#         "units":          "mm_per_day",
#         "model":          "PET-SARIMAX + Physics CWR/IWR",
#         "params":         PARAMS,
#         "slots":          result,
#     }


# @app.get("/api/seasons")
# async def get_seasons():
#     """
#     Lightweight endpoint: returns allowed season IDs and which are present in data.
#     Used by the frontend calendar filter.
#     """
#     allowed = get_allowed_season_ids()
#     dates   = _latest_n_complete_dates()
#     present = set(get_season_id(d) for d in dates if get_season_id(d))

#     return {
#         "allowed_seasons": allowed,
#         "present_seasons": sorted(present, reverse=True),
#         "max_seasons":     MAX_SEASONS,
#         "season_months":   sorted(SEASON_MONTHS),
#     }


# @app.get("/api/forecast")
# async def get_forecast(
#     date: str = Query(..., description="Reference date YYYY-MM-DD"),
#     days: int  = Query(15,  ge=1, le=30, description="Forecast horizon (days)"),
# ):
#     try:
#         ref_date = datetime.strptime(date, "%Y-%m-%d")
#     except ValueError:
#         raise HTTPException(status_code=400, detail="Invalid date — use YYYY-MM-DD")

#     forecasts = generate_forecast_for_date(ref_date, days)
#     if not forecasts:
#         raise HTTPException(status_code=500, detail="Failed to generate forecast")

#     result: dict = {
#         "reference_date": date,
#         "forecast_days":  days,
#         "model":          "PET-SARIMAX + Physics CWR/IWR (v10.0)",
#         "forecasts":      {},
#     }

#     units_by_param = {
#         "savi": "unitless", "kc": "unitless",
#         "pet": "mm_per_day", "cwr": "mm_per_day",
#         "iwr": "mm_per_day", "peff": "mm_per_day",
#     }

#     for param in ("savi", "pet", "kc", "cwr", "iwr", "peff"):
#         if param in forecasts:
#             series = forecasts[param]
#             result["forecasts"][param] = {
#                 "dates":  [d.strftime("%Y-%m-%d") for d in series.index],
#                 "values": [round(float(v), 4) for v in series.values],
#                 "units":  units_by_param[param],
#                 "mean":   round(float(series.mean()), 4),
#                 "min":    round(float(series.min()),  4),
#                 "max":    round(float(series.max()),  4),
#             }

#     result["crop_stages"] = [
#         {"date": d.strftime("%Y-%m-%d"), **get_wheat_stage_info(d.to_pydatetime())}
#         for d in forecasts["kc"].index
#     ]

#     WINDOW_SLICES = {"5day": (0, 5), "10day": (0, 10), "15day": (0, 15)}
#     result["window_summaries"] = {}
#     for window, (start_idx, end_idx) in WINDOW_SLICES.items():
#         result["window_summaries"][window] = {}
#         for param in ("kc", "cwr", "iwr", "peff"):
#             if param in forecasts:
#                 vals = forecasts[param].iloc[start_idx:end_idx].values
#                 result["window_summaries"][window][param] = {
#                     "mean":  round(float(np.mean(vals)), 4),
#                     "total": round(float(np.sum(vals)), 4),
#                 }
#         window_date = forecasts["kc"].index[start_idx].to_pydatetime()
#         result["window_summaries"][window]["crop_stage"] = get_wheat_stage_info(window_date)

#     return result


# @app.get("/api/point")
# def get_point(
#     lat:  float,
#     lon:  float,
#     slot: Optional[str] = None,
# ):
#     slot = slot or "today"
#     pixel = _pixel_from_latlon(lat, lon)
#     selected_date = _date_for_slot(slot)
#     if selected_date is None:
#         raise HTTPException(status_code=404, detail=f"No acquisition date found for slot '{slot}'")

#     result: Dict[str, Optional[float]] = {}
#     forecast = {}

#     for param in PARAMS:
#         result[param] = _read_history_pixel_value(history_path(param, slot), pixel)

#     for param in POINT_FORECAST_PARAMS:
#         forecast[param] = {}
#         for w in FORECAST_WINDOWS:
#             fpath = forecast_path(param, slot, w)
#             forecast[param][w] = _read_history_pixel_value(fpath, pixel)

#     return {
#         "lat":              round(float(pixel["latitude"]), 7),
#         "lon":              round(float(pixel["longitude"]), 7),
#         "query_lat":        lat,
#         "query_lon":        lon,
#         "pixel_id":         pixel["pixel_id"],
#         "row":              pixel["row"],
#         "col":              pixel["col"],
#         "acquisition_date": selected_date.strftime("%Y-%m-%d"),
#         "slot":             slot,
#         "values":           result,
#         "forecast":         forecast,
#     }


# def _collect_chat_live_data(req: ChatRequest) -> Dict[str, object]:
#     live_data: Dict[str, object] = {}
#     try:
#         dates = _latest_n_complete_dates(1)
#         if not dates:
#             return live_data

#         for param in PARAMS:
#             val = _read_mean(history_path(param, "today"))
#             if val is not None:
#                 live_data[param] = round(val, 3)

#         if req.lat is not None and req.lon is not None:
#             live_data["query_location"] = f"lat={req.lat:.4f}, lon={req.lon:.4f}"
#             try:
#                 pixel = _pixel_from_latlon(req.lat, req.lon)
#                 for param in PARAMS:
#                     value = _read_history_pixel_value(history_path(param, "today"), pixel)
#                     if value is not None:
#                         live_data[f"point_{param}"] = round(float(value), 3)
#             except HTTPException as exc:
#                 live_data["point_lookup_status"] = str(exc.detail)
#             except Exception as exc:
#                 logger.debug("[chat] point lookup skipped: %s", exc)
#     except Exception as exc:
#         logger.warning("[chat] live data fetch failed: %s", exc)
#     return live_data


# def _prepare_chat_context(req: ChatRequest) -> Dict[str, Any]:
#     query = (req.query or "").strip()
#     needs_live_data = _chat_query_needs_live_data(query, req.lat is not None and req.lon is not None)
#     live_data = _collect_chat_live_data(req) if needs_live_data else {}
#     tool_answer = None
#     tool_sources: List[str] = []
#     query_type = "knowledge_based"
#     structured_context = None

#     try:
#         from chat_data_tools import get_data_tools, safe_llm_context

#         tool_result = get_data_tools().answer(query, live_data=live_data or None)
#         query_type = tool_result.query_type
#         tool_answer = tool_result.answer
#         tool_sources = tool_result.sources or []
#         structured_context = safe_llm_context(tool_result)
#     except Exception as exc:
#         logger.warning("[chat] structured query tools failed: %s", exc, exc_info=True)

#     return {
#         "query": query,
#         "live_data": live_data,
#         "tool_answer": tool_answer,
#         "tool_sources": tool_sources,
#         "query_type": query_type,
#         "structured_context": structured_context,
#         "needs_live_data": needs_live_data,
#     }


# def _sse(event: str, payload: Dict[str, Any]) -> str:
#     return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


# @app.post("/api/chat")
# async def chat(req: ChatRequest):
#     query = (req.query or "").strip()
#     if not query:
#         return {
#             "answer": "Please ask a question about irrigation, crop water requirements, or the study region.",
#             "sources": [],
#             "live_data": {},
#         }

#     context = await asyncio.to_thread(_prepare_chat_context, req)
#     live_data = context["live_data"]
#     tool_answer = context["tool_answer"]
#     tool_sources = context["tool_sources"]
#     query_type = context["query_type"]
#     structured_context = context["structured_context"]

#     try:
#         from rag_kb import get_chat_answer

#         rag_response = await asyncio.to_thread(
#             get_chat_answer,
#             query,
#             live_data or None,
#             req.history or [],
#             req.session_id or "default",
#             structured_context,
#         )
#         answer = rag_response.get("answer") or "I am having trouble checking the data right now. Please try again in a moment."
#         source_ids = list(dict.fromkeys(tool_sources + (rag_response.get("sources", []) or [])))
#     except Exception as exc:
#         logger.error("[chat] LangChain RAG failed: %s", exc, exc_info=True)
#         try:
#             from rag_kb import llm_unavailable_answer

#             answer = llm_unavailable_answer()
#         except Exception:
#             answer = "I could not generate a knowledge-base answer right now because the LLM is unavailable."
#         source_ids = tool_sources
#         rag_response = {"model_used": "llm_unavailable"}

#     include_live_metrics = bool(context.get("needs_live_data") and rag_response.get("include_live_metrics"))

#     return {
#         "answer": answer,
#         "sources": source_ids,
#         "live_data": live_data if include_live_metrics else {},
#         "include_live_metrics": include_live_metrics,
#         "query_type": query_type,
#         "model_used": rag_response.get("model_used"),
#         "rag_chunks": rag_response.get("rag_chunks", []),
#         "retrieved_context": rag_response.get("retrieved_context", []),
#         "attempts": rag_response.get("attempts", []),
#         "latency_ms": rag_response.get("latency_ms"),
#         "retrieval_ms": rag_response.get("retrieval_ms"),
#         "rag_backend": rag_response.get("rag_backend"),
#     }


# @app.post("/api/chat/stream")
# async def chat_stream(req: ChatRequest):
#     query = (req.query or "").strip()
#     if not query:
#         def empty_stream():
#             answer = "Please ask a question about irrigation, crop water requirements, or the study region."
#             yield _sse("token", {"content": answer})
#             yield _sse("done", {"answer": answer, "sources": [], "live_data": {}, "query_type": "empty"})

#         return StreamingResponse(empty_stream(), media_type="text/event-stream")

#     def event_stream():
#         context: Dict[str, Any] = {
#             "live_data": {},
#             "tool_sources": [],
#             "structured_context": None,
#             "query_type": "knowledge_based",
#         }
#         live_data: Dict[str, object] = {}
#         tool_sources: List[str] = []
#         structured_context = None
#         try:
#             context = _prepare_chat_context(req)
#             live_data = context["live_data"]
#             tool_sources = context["tool_sources"]
#             structured_context = context["structured_context"]

#             from rag_kb import stream_chat_answer

#             for event in stream_chat_answer(
#                 query,
#                 live_data=live_data or None,
#                 history=req.history or [],
#                 session_id=req.session_id or "default",
#                 structured_context=structured_context,
#             ):
#                 event_type = event.get("type", "message")
#                 if event_type == "token":
#                     yield _sse("token", {"content": event.get("content", "")})
#                 elif event_type == "status":
#                     yield _sse("status", {"model": event.get("model"), "status": event.get("status")})
#                 elif event_type == "meta":
#                     sources = list(dict.fromkeys(tool_sources + (event.get("sources", []) or [])))
#                     include_live_metrics = bool(context.get("needs_live_data") and event.get("include_live_metrics"))
#                     yield _sse(
#                         "meta",
#                         {
#                             "sources": sources,
#                             "rag_chunks": event.get("rag_chunks", []),
#                             "retrieved_context": event.get("retrieved_context", []),
#                             "retrieval_ms": event.get("retrieval_ms"),
#                             "rag_backend": event.get("rag_backend"),
#                             "live_data": live_data if include_live_metrics else {},
#                             "include_live_metrics": include_live_metrics,
#                             "query_type": context["query_type"],
#                         },
#                     )
#                 elif event_type == "done":
#                     sources = list(dict.fromkeys(tool_sources + (event.get("sources", []) or [])))
#                     include_live_metrics = bool(context.get("needs_live_data") and event.get("include_live_metrics"))
#                     yield _sse(
#                         "done",
#                         {
#                             **event,
#                             "sources": sources,
#                             "live_data": live_data if include_live_metrics else {},
#                             "include_live_metrics": include_live_metrics,
#                             "query_type": context["query_type"],
#                         },
#                     )
#         except Exception as exc:
#             logger.error("[chat] streaming RAG failed: %s", exc, exc_info=True)
#             try:
#                 from rag_kb import llm_unavailable_answer

#                 answer = llm_unavailable_answer()
#             except Exception:
#                 answer = "I could not generate a knowledge-base answer right now because the LLM is unavailable."
#             yield _sse("token", {"content": answer})
#             yield _sse(
#                 "done",
#                 {
#                     "answer": answer,
#                     "sources": tool_sources,
#                     "live_data": {},
#                     "include_live_metrics": False,
#                     "query_type": context["query_type"],
#                     "model_used": "llm_unavailable",
#                 },
#             )

#     return StreamingResponse(
#         event_stream(),
#         media_type="text/event-stream",
#         headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
#     )


# @app.get("/api/chat/health")
# async def chat_health():
#     try:
#         from rag_kb import rag_health

#         return await asyncio.to_thread(rag_health)
#     except Exception as exc:
#         logger.exception("[chat] health failed")
#         raise HTTPException(status_code=503, detail=str(exc))


# @app.post("/api/live-data")
# async def ingest_live_data(req: LiveSensorIngestRequest):
#     """
#     Store live sensor/API readings for real-time chatbot queries.

#     Example payload:
#       {"sensor_id": "field-01", "values": {"iwr": 42.6, "cwr": 5.1}}
#     """
#     try:
#         from chat_data_tools import get_data_tools
#         payload = req.dict()
#         return {"status": "ok", **get_data_tools().ingest_live(payload)}
#     except Exception as e:
#         logger.exception("[live-data] ingest failed")
#         raise HTTPException(status_code=500, detail=str(e))


# @app.get("/api/live-data/latest")
# async def latest_live_data(metric: Optional[str] = None):
#     try:
#         from chat_data_tools import get_data_tools, PARAM_ALIASES
#         normalized_metric = PARAM_ALIASES.get(metric.lower(), metric.lower()) if metric else None
#         latest = get_data_tools().live_store.latest(normalized_metric)
#         if not latest:
#             return {"status": "unavailable", "message": "Real-time data is currently unavailable.", "latest": {}}
#         return {"status": "ok", "latest": latest}
#     except Exception as e:
#         logger.exception("[live-data] latest failed")
#         raise HTTPException(status_code=500, detail=str(e))


# @app.get("/health")
# async def health():
#     return {"status": "ok", "version": "10.0.0", "model": "PET-SARIMAX + Physics CWR/IWR"}


# @app.post("/api/refresh")
# async def manual_refresh():
#     try:
#         return {"status": "ok", "result": run_pipeline()}
#     except Exception as e:
#         logger.exception("Pipeline failed")
#         raise HTTPException(status_code=500, detail=str(e))


# @app.get("/api/model/info")
# async def model_info():
#     pet_model, pet_meta = _get_model("pet")
#     kc_model, kc_meta   = _get_model("kc")

#     def _meta_dict(model, meta):
#         if meta is None:
#             return {"available": False}
#         return {
#             "available": model is not None,
#             "note":     meta.get("note", ""),
#             "test_r2":  meta["metrics"].get("R2"),
#             "test_rmse":meta["metrics"].get("RMSE"),
#             "test_mae": meta["metrics"].get("MAE"),
#             "order":    meta.get("order"),
#             "exog_cols":meta.get("exog_cols"),
#             "last_training_date": (
#                 meta["last_date"].strftime("%Y-%m-%d")
#                 if meta.get("last_date") else None
#             ),
#         }

#     return {
#         "models": {
#             "kc":  _meta_dict(kc_model,  kc_meta),
#             "pet": _meta_dict(pet_model, pet_meta),
#         },
#         "history_slots":       HISTORY_DATES,
#         "max_seasons":         MAX_SEASONS,
#         "season_months":       sorted(SEASON_MONTHS),
#         "allowed_seasons":     get_allowed_season_ids(),
#         "thesis_reference":    "Satabdi Mandal, 2025, IIRS-ISRO, §4.6, §5.6",
#         "physical_relationships": {
#             "savi_to_kc": f"Kc = {KC_SLOPE:.4f} × SAVI + {KC_INTERCEPT:.4f}  (thesis Table 9)",
#             "cwr":        "CWR = Kc × PET  (FAO-56)",
#             "iwr":        "IWR = max(CWR − Peff, 0)  (FAO-56)",
#         },
#         "crop_stage_today": get_wheat_stage_info(datetime.utcnow()),
#     }


# # ═══════════════════════════════════════════════════════════════════════════
# # MAIN ENTRY POINT
# # ═══════════════════════════════════════════════════════════════════════════

# def main():
#     setup_logging()
#     logger.info("=" * 65)
#     logger.info("Irrigation Monitoring System v10.0 starting …")
#     logger.info(f"Seasonal cap: {MAX_SEASONS} seasons | Months: Nov–Apr")
#     logger.info(f"Allowed seasons: {get_allowed_season_ids()}")
#     logger.info("=" * 65)

#     _get_wheat_mask()

#     pet_model, pet_meta = _get_model("pet")
#     if pet_model:
#         logger.info(f"✓ PET model ready (R²={pet_meta['metrics']['R2']:.4f})")
#     else:
#         logger.error("✗ Failed to initialise PET model")

#     run_pipeline()

#     try:
#         from scheduler import start_scheduler
#         _scheduler, _observer = start_scheduler(
#             delete_callback=cleanup_old_rasters,
#             generate_callback=generate_operational_rasters,
#             download_and_process_callback=None,
#             single_image_pipeline_callback=process_single_sentinel_image,
#         )
#         logger.info("✓ Scheduler + Watchdog started")
#     except Exception as e:
#         logger.error(f"✗ Scheduler failed to start: {e}", exc_info=True)
#         logger.warning("Continuing without scheduler — pipeline will NOT run automatically.")

#     uvicorn.run(
#         app, host="0.0.0.0", port=8000,
#         log_level="info", access_log=True,
#     )


# if __name__ == "__main__":
#     main()




import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import rasterio
import rasterio.warp
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from rasterio.enums import Resampling
import os
from dotenv import load_dotenv
from config import (
    STUDY_AREA, DIRECTORIES, GEOSERVER, SARIMAX_CONFIG,
    WHEAT_PARAMS
)
from extract_raster_pixels import (
    RasterCoordinateError,
    RasterGridUnavailable,
    RasterLookupCancelled,
    RasterOutOfBoundsError,
    clear_raster_pixel_cache,
    pixel_from_latlon as raster_pixel_from_latlon,
    pixel_timeseries_for_pixel,
    read_history_pixel_value as raster_read_history_pixel_value,
)
from logging_config import setup_logging
import models
from models import (
    build_forecast_exog,
    set_forecast_context,
    raster_mean,
    savi_to_kc,
    get_wheat_stage_info,
    get_wheat_stage_kc,
    KC_SLOPE,
    KC_INTERCEPT,
    KC_MIN,
    KC_MAX,
)

setup_logging()
logger = logging.getLogger(__name__)

CWR_MIN      = 0.0
CWR_MAX      = 15.0


# ═══════════════════════════════════════════════════════════════════════════
# SEASONAL CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

# Rabi wheat season: November (month 11) → April (month 4)
SEASON_START_MONTH = 11   # November
SEASON_END_MONTH   = 4    # April
SEASON_MONTHS      = {11, 12, 1, 2, 3, 4}   # months kept in calendar

# Cap at 5 complete seasons (Nov 2021–Apr 2022 … Nov 2025–Apr 2026)
MAX_SEASONS = 5

# Total slots = 5 seasons × ~6 months × ~3 scenes/month = up to ~90
# We keep this generous; actual data may be sparser. HISTORY_DATES controls
# how many slots the pipeline writes; set it to accommodate 5 full seasons.
HISTORY_DATES  = 191   # upper bound — actual dates may be fewer
FORECAST_DAYS  = 15
NODATA         = -9999.0

# All parameters including ETc
PARAMS: List[str] = ["savi", "kc", "cwr", "iwr", "etc"]
FC_PARAMS: List[str] = ["kc", "etc","cwr", "iwr"]   # parameters that get forecast rasters
POINT_FORECAST_PARAMS: List[str] = ["cwr", "iwr"]    # pixel popup forecast values shown to users

FORECAST_WINDOWS = ["5day", "10day", "15day"]
WINDOW_DAYS      = {"5day": 5, "10day": 10, "15day": 15}

_VALID: Dict[str, Tuple[float, float]] = {
    "savi": (-1.0, 1.0),
    "kc":   (KC_MIN, KC_MAX),
    "cwr":  (CWR_MIN, CWR_MAX),
    "iwr":  (0.0, CWR_MAX),
    "etc":  (0.0, 15.0),
}

# Cumulative valid ranges for CWR/IWR forecast rasters (mm_total over window).
# 15-day max = 15 × 15 mm/day = 225 mm; we cap at 200 to clip outliers.
_VALID_FC: Dict[str, Tuple[float, float]] = {
    "kc":  (KC_MIN, KC_MAX),
    "etc": (0.0, 15.0),          # daily average → same as _VALID
    "cwr": (0.0, 200.0),         # cumulative total mm over window
    "iwr": (0.0, 200.0),
}

_SRC: Dict[str, Tuple[Path, str]] = {
    "savi": (DIRECTORIES["processed"]["savi"], "savi_*.tif"),
    "kc":   (DIRECTORIES["processed"]["kc"],   "kc_*.tif"),
    "cwr":  (DIRECTORIES["processed"]["cwr"],  "cwr_*.tif"),
    "iwr":  (DIRECTORIES["processed"]["iwr"],  "iwr_*.tif"),
    "etc":  (DIRECTORIES["processed"]["ETc"],  "etc_*.tif"),
}

EXPORT_DIR   = DIRECTORIES["export"]["geoserver"]
HISTORY_DIR  = EXPORT_DIR / "history"
FORECAST_DIR = EXPORT_DIR / "forecast"

for _param in PARAMS:
    (HISTORY_DIR / _param).mkdir(parents=True, exist_ok=True)
for _param in FC_PARAMS:
    (FORECAST_DIR / _param).mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════
# SEASONAL HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def get_season_id(date: datetime) -> str:
    """
    Return a canonical season string for a date, e.g. '2024-25'.
    Season starts November 1; dates May–October fall outside any Rabi season.
    """
    m, y = date.month, date.year
    if m >= SEASON_START_MONTH:          # Nov or Dec → season started this year
        return f"{y}-{str(y + 1)[-2:]}"
    elif m <= SEASON_END_MONTH:          # Jan–Apr → season started last year
        return f"{y - 1}-{str(y)[-2:]}"
    else:                                # May–Oct → off-season
        return None


def is_in_season(date: datetime) -> bool:
    """Return True if date falls in Nov–Apr (Rabi season)."""
    return date.month in SEASON_MONTHS


def get_season_start(season_id: str) -> datetime:
    """Return Nov 1 of the start year for a season string like '2024-25'."""
    start_year = int(season_id.split("-")[0])
    return datetime(start_year, SEASON_START_MONTH, 1)


def get_allowed_season_ids() -> List[str]:
    """
    Return the list of season IDs (newest-first) that fall within the
    MAX_SEASONS retention window.

    Logic:
      • Find the 'current' season (the one containing today or the most
        recent completed season).
      • Keep the last MAX_SEASONS seasons counting backwards from there.
    """
    today = datetime.utcnow()
    # Determine the 'anchor' season
    current = get_season_id(today)
    if current is None:
        # We are in the off-season (May–Oct).  Anchor = last completed season.
        # Last completed season started in November of (this_year - 1).
        anchor_year = today.year - 1
        current = f"{anchor_year}-{str(anchor_year + 1)[-2:]}"

    anchor_start_year = int(current.split("-")[0])
    seasons = []
    for i in range(MAX_SEASONS):
        y = anchor_start_year - i
        seasons.append(f"{y}-{str(y + 1)[-2:]}")
    return seasons   # newest first


def filter_to_allowed_seasons(dates: List[datetime]) -> List[datetime]:
    """
    Given a list of datetimes, return only those that:
      1. Fall in Nov–Apr (Rabi season months)
      2. Belong to one of the MAX_SEASONS allowed seasons
    """
    allowed = set(get_allowed_season_ids())
    out = []
    for d in dates:
        if not is_in_season(d):
            continue
        sid = get_season_id(d)
        if sid and sid in allowed:
            out.append(d)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# SLOT HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def slot_for_index(idx: int) -> str:
    return "today" if idx == 0 else str(idx)


def _make_slots(n: int) -> List[str]:
    return ["today"] + [str(i) for i in range(1, n)]


# ═══════════════════════════════════════════════════════════════════════════
# GLOBAL MODEL CACHE
# ═══════════════════════════════════════════════════════════════════════════

_MODEL_CACHE: Dict = {}
_fc_cache: Dict = {"pet_count": -1}


def _get_model(model_type: str):
    global _MODEL_CACHE
    if model_type in _MODEL_CACHE:
        return _MODEL_CACHE[model_type]
    try:
        model, meta = models.load_model(model_type)
        _MODEL_CACHE[model_type] = (model, meta)
        logger.info(f"✓ Loaded {model_type.upper()} SARIMAx model "
                    f"(R²={meta['metrics']['R2']:.4f})")
        return model, meta
    except FileNotFoundError:
        logger.warning(f"Model {model_type} not found — training now...")
        models.train_all_models()
        model, meta = models.load_model(model_type)
        _MODEL_CACHE[model_type] = (model, meta)
        return model, meta
    except Exception as e:
        logger.error(f"Failed to load {model_type} model: {e}")
        return None, None


# ═══════════════════════════════════════════════════════════════════════════
# PATH HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def history_path(param: str, slot: str) -> Path:
    return HISTORY_DIR / param / f"{param}_{slot}.tif"


def forecast_path(param: str, slot: str, window: str) -> Path:
    return FORECAST_DIR / param / f"{param}_{slot}_{window}.tif"


# ═══════════════════════════════════════════════════════════════════════════
# DATA LOADING HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _parse_date(name: str) -> Optional[datetime]:
    m = re.search(r"\d{8}", name)
    if m:
        try:
            return datetime.strptime(m.group(), "%Y%m%d")
        except ValueError:
            pass
    return None


def _dated_files(directory: Path, pattern: str) -> List[Tuple[datetime, Path]]:
    out = []
    for p in directory.glob(pattern):
        d = _parse_date(p.name)
        if d:
            out.append((d, p))
    out.sort(key=lambda x: x[0])
    return out


def _latest_n_complete_dates(n: int = HISTORY_DATES) -> List[datetime]:
    """
    N most-recent dates where ALL core parameters (savi, kc, cwr, iwr) have
    processed rasters AND the date falls within the allowed seasonal window
    (Nov–Apr, last MAX_SEASONS seasons).  Newest-first.

    ETc is optional — its absence does not exclude a date.
    """
    core_params = ["savi", "kc", "etc" , "cwr", "iwr"]
    date_sets = []
    for param in core_params:
        src_dir, pattern = _SRC[param]
        dates = {d for d, _ in _dated_files(src_dir, pattern)}
        if not dates:
            logger.warning(f"No {param} files in {src_dir}")
            return []
        date_sets.append(dates)

    complete = set.intersection(*date_sets)

    # Apply seasonal filter
    seasonal = filter_to_allowed_seasons(sorted(complete, reverse=True))

    return seasonal[:n]


def _read_mean(path: Path) -> Optional[float]:
    if not path.exists():
        return None
    try:
        with rasterio.open(path) as src:
            data = src.read(1).astype(np.float64)
            nd   = float(src.nodata) if src.nodata else float(NODATA)
            data[data == np.float64(nd)] = np.nan
            v = float(np.nanmean(data))
            return None if np.isnan(v) else round(v, 4)
    except Exception:
        return None


def _processed_mean_for_date(param: str, date: datetime) -> Optional[float]:
    src = _SRC.get(param)
    if src is None:
        return None
    src_dir, pattern = src
    date_key = date.replace(hour=0, minute=0, second=0, microsecond=0)
    for d, path in _dated_files(src_dir, pattern):
        if d == date_key:
            return _read_mean(path)
    return None


def _reference_mean(param: str, reference_date: datetime, fallback: Optional[float] = None) -> Optional[float]:
    value = _processed_mean_for_date(param, reference_date)
    if value is not None:
        return value
    for idx, d in enumerate(_latest_n_complete_dates(HISTORY_DATES)):
        if d.date() == reference_date.date():
            value = _read_mean(history_path(param, slot_for_index(idx)))
            if value is not None:
                return value
    return fallback


def _load_slot_array(param: str, slot: str) -> Optional[np.ndarray]:
    p = history_path(param, slot)
    if not p.exists():
        return None
    try:
        with rasterio.open(p) as src:
            data = src.read(1).astype(np.float64)
            nd   = float(src.nodata) if src.nodata is not None else float(NODATA)
            data[data == np.float64(nd)]       = np.nan
            data[data == np.float64(NODATA)]   = np.nan
        return data
    except Exception as e:
        logger.error(f"[load] {p.name}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# WHEAT MASK
# ═══════════════════════════════════════════════════════════════════════════

_WHEAT_MASK_CACHE: Optional[Dict] = None


def _get_wheat_mask() -> Optional[Dict]:
    global _WHEAT_MASK_CACHE
    if _WHEAT_MASK_CACHE is not None:
        return _WHEAT_MASK_CACHE

    mask_path = DIRECTORIES["processed"]["masks"] / "wheat_mask.tif"
    if not mask_path.exists():
        logger.error(f"wheat_mask.tif not found: {mask_path}")
        return None

    try:
        with rasterio.open(mask_path) as src:
            raw = src.read(1)
            _WHEAT_MASK_CACHE = {
                "crs":       src.crs,
                "transform": src.transform,
                "width":     src.width,
                "height":    src.height,
                "mask_bool": (raw > 0),
            }
        logger.info(
            f"Wheat mask: {_WHEAT_MASK_CACHE['width']}×{_WHEAT_MASK_CACHE['height']} | "
            f"wheat pixels = {_WHEAT_MASK_CACHE['mask_bool'].sum():,}"
        )
    except Exception as e:
        logger.error(f"Failed to load wheat_mask: {e}")
    return _WHEAT_MASK_CACHE


# ═══════════════════════════════════════════════════════════════════════════
# SEASONAL PURGE — delete rasters outside the retention window
# ═══════════════════════════════════════════════════════════════════════════

def purge_out_of_season_rasters() -> int:
    """
    Delete any history raster whose embedded acquisition_date tag falls
    outside the allowed MAX_SEASONS window.  Also prunes raw processed files
    older than the retention window to free disk space.

    Returns count of deleted files.
    """
    allowed_seasons = set(get_allowed_season_ids())
    deleted = 0

    for param in PARAMS:
        param_dir = HISTORY_DIR / param
        for tif in param_dir.glob("*.tif"):
            try:
                with rasterio.open(tif) as src:
                    acq = src.tags().get("acquisition_date")
                if not acq:
                    continue
                d = datetime.strptime(acq, "%Y-%m-%d")
                if not is_in_season(d):
                    tif.unlink()
                    deleted += 1
                    logger.info(f"[purge] off-season: {tif.name}")
                    continue
                sid = get_season_id(d)
                if sid and sid not in allowed_seasons:
                    tif.unlink()
                    deleted += 1
                    logger.info(f"[purge] old season {sid}: {tif.name}")
            except Exception:
                pass

    # Purge forecast rasters whose slot raster was deleted
    for param in FC_PARAMS:
        for tif in (FORECAST_DIR / param).glob("*.tif"):
            try:
                with rasterio.open(tif) as src:
                    acq = src.tags().get("acquisition_date") or src.tags().get("reference_date")
                if acq:
                    d = datetime.strptime(acq, "%Y-%m-%d")
                    sid = get_season_id(d)
                    if not is_in_season(d) or (sid and sid not in allowed_seasons):
                        tif.unlink()
                        deleted += 1
            except Exception:
                pass

    if deleted:
        logger.info(f"[purge] Removed {deleted} out-of-retention rasters")
    return deleted


def cleanup_old_rasters():
    """
    Remove any slot-named raster files that no longer correspond to a valid
    slot (i.e. the current set of seasonal dates).  Runs purge first.
    """
    purge_out_of_season_rasters()

    dates = _latest_n_complete_dates(HISTORY_DATES)
    n = len(dates)
    valid_slots = _make_slots(n)

    for param in PARAMS:
        valid_history = {f"{param}_{s}.tif" for s in valid_slots}
        for f in (HISTORY_DIR / param).glob("*.tif"):
            if f.name not in valid_history:
                f.unlink()
                logger.debug(f"[cleanup] removed stale slot file: {f.name}")

    for param in FC_PARAMS:
        valid_forecast = {
            f"{param}_{s}_{w}.tif"
            for s in valid_slots
            for w in FORECAST_WINDOWS
        }
        for f in (FORECAST_DIR / param).glob("*.tif"):
            if f.name not in valid_forecast:
                f.unlink()
                logger.debug(f"[cleanup] removed stale forecast file: {f.name}")


# ═══════════════════════════════════════════════════════════════════════════
# RASTER I/O
# ═══════════════════════════════════════════════════════════════════════════

def _reproject_and_write(
    src_path: Path,
    dst_path: Path,
    param: str,
    date: datetime,
    extra_tags: Optional[Dict] = None,
) -> bool:
    grid = _get_wheat_mask()
    if grid is None:
        return False

    vmin, vmax = _VALID.get(param, (-1e9, 1e9))

    try:
        with rasterio.open(src_path) as src:
            data       = src.read(1).astype(np.float64)
            src_nd     = src.nodata
            src_crs    = src.crs
            src_trans  = src.transform

        if src_nd is not None:
            data[data == np.float64(src_nd)] = np.nan
        data[data == np.float64(-9999.0)] = np.nan
        data[data == np.float64(-999.0)]  = np.nan

        dst = np.full((grid["height"], grid["width"]), np.nan, dtype=np.float64)
        rasterio.warp.reproject(
            source=data,
            destination=dst,
            src_transform=src_trans,
            src_crs=src_crs,
            dst_transform=grid["transform"],
            dst_crs=grid["crs"],
            resampling=Resampling.nearest,
            src_nodata=None,
            dst_nodata=None,
        )

        dst[dst > vmax] = np.nan
        if param == "cwr":
            dst[(~np.isnan(dst)) & (dst <= 0.0)] = np.nan
        dst[dst < vmin] = np.nan
        dst[~grid["mask_bool"]] = np.nan

        out     = np.where(np.isnan(dst), float(NODATA), dst).astype(np.float64)
        profile = {
            "driver":     "GTiff",
            "dtype":      rasterio.float64,
            "count":      1,
            "crs":        grid["crs"],
            "transform":  grid["transform"],
            "width":      grid["width"],
            "height":     grid["height"],
            "nodata":     float(NODATA),
            "compress":   "lzw",
            "tiled":      True,
            "blockxsize": 256,
            "blockysize": 256,
        }

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dst_path, "w", **profile) as f:
            f.write(out, 1)
            mean_val = float(np.nanmean(dst)) if np.any(~np.isnan(dst)) else None
            tags = {
                "parameter":        param,
                "acquisition_date": date.strftime("%Y-%m-%d"),
                "season":           get_season_id(date) or "",
                "mean":             str(round(mean_val, 4)) if mean_val is not None else "",
            }
            if extra_tags:
                tags.update(extra_tags)
            f.update_tags(**tags)
        return True
    except Exception as e:
        logger.error(f"[raster] {src_path.name}→{dst_path.name}: {e}")
        return False


def _write_array_raster(
    data: np.ndarray,
    template: Path,
    dst_path: Path,
    tags: Dict,
) -> bool:
    try:
        with rasterio.open(template) as src:
            profile = src.profile.copy()
        profile.update(
            dtype="float64",
            count=1,
            nodata=float(NODATA),
            compress="lzw",
            tiled=True,
            blockxsize=256,
            blockysize=256,
        )
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dst_path, "w", **profile) as f:
            f.write(data.astype(np.float64), 1)
            f.update_tags(**tags)
        return True
    except Exception as e:
        logger.error(f"[raster] write {dst_path.name}: {e}")
        return False


def _pixel_avg(arrays: List[np.ndarray]) -> np.ndarray:
    stack = np.stack(arrays, axis=0)
    valid = (stack != float(NODATA)) & ~np.isnan(stack)
    total = np.where(valid, stack, 0.0).sum(axis=0)
    count = valid.sum(axis=0).astype(np.float64)
    return np.where(count > 0, total / count, float(NODATA)).astype(np.float64)


# ═══════════════════════════════════════════════════════════════════════════
# STEP A — HISTORY RASTERS
# ═══════════════════════════════════════════════════════════════════════════

def generate_history_rasters() -> int:
    """
    Write history/{param}/{param}_{slot}.tif for every param × slot.
    Slots are assigned newest-first from the seasonal-filtered date list.
    ETc is optional — missing ETc for a date is silently skipped.
    """
    dates = _latest_n_complete_dates(HISTORY_DATES)
    if not dates:
        logger.error("[history] No complete Sentinel dates in allowed seasons")
        return 0

    logger.info(
        f"[history] {len(dates)} seasonal dates: "
        f"{dates[-1].date()} → {dates[0].date()} "
        f"| seasons={sorted(set(get_season_id(d) for d in dates))}"
    )
    total = 0

    for param, (src_dir, pattern) in _SRC.items():
        src_by_date = {d: p for d, p in _dated_files(src_dir, pattern)}
        for idx, date in enumerate(dates):
            src_path = src_by_date.get(date)
            if src_path is None:
                if param != "etc":
                    logger.warning(f"[history] {param} missing for {date.date()}")
                continue
            slot     = slot_for_index(idx)
            dst_path = history_path(param, slot)

            if dst_path.exists():
                try:
                    with rasterio.open(dst_path) as f:
                        if f.tags().get("acquisition_date") == date.strftime("%Y-%m-%d"):
                            total += 1
                            continue
                except Exception:
                    pass

            if _reproject_and_write(src_path, dst_path, param, date,
                                     extra_tags={"slot": slot}):
                total += 1
                logger.info(f"[history] {dst_path.name} ({date.date()})")

        logger.info(f"[history] {param} done")

    logger.info(f"[history] Total: {total} / {len(dates) * len(PARAMS)}")
    return total


# ═══════════════════════════════════════════════════════════════════════════
# STEP B — FORECASTING  (Thesis-compliant)
# ═══════════════════════════════════════════════════════════════════════════

def _effective_rainfall_daily(rain_mm: float) -> float:
    rain_mm = max(float(rain_mm), 0.0)
    period_factor = 1.0 / 30.0
    threshold = 75.0 * period_factor
    if rain_mm > threshold:
        return max(0.0, 0.8 * rain_mm - 25.0 * period_factor)
    return max(0.0, 0.6 * rain_mm - 10.0 * period_factor)


def _rainfall_mean_for_date(date: datetime, rain_by_date: Dict[datetime, Path]) -> float:
    date_key = date.replace(hour=0, minute=0, second=0, microsecond=0)
    rain_path = rain_by_date.get(date_key)
    if rain_path is None:
        return 0.0
    rain_val = raster_mean(rain_path, mask_zeros=False)
    return float(rain_val) if np.isfinite(rain_val) and rain_val >= 0 else 0.0


def _climatological_peff(future_dates: pd.DatetimeIndex) -> np.ndarray:
    rain_dir = DIRECTORIES["raw"].get("insat_rain")
    rain_by_date: Dict[datetime, Path] = {}

    if rain_dir and Path(rain_dir).exists():
        for rain_path in Path(rain_dir).glob("*.tif"):
            try:
                rain_date = models.extract_date(rain_path.name)
                rain_by_date[rain_date.replace(hour=0, minute=0, second=0, microsecond=0)] = rain_path
            except Exception:
                continue

    peff_vals = np.array([
        _effective_rainfall_daily(
            _rainfall_mean_for_date(
                d.to_pydatetime() if hasattr(d, "to_pydatetime") else d,
                rain_by_date,
            )
        )
        for d in future_dates
    ], dtype=float)

    logger.info(
        f"[forecast] Peff mean={peff_vals.mean():.3f} mm/day "
        f"range={peff_vals.min():.3f}–{peff_vals.max():.3f}"
    )
    return peff_vals


def _project_kc_for_dates(
    future_dates: pd.DatetimeIndex,
    reference_date: Optional[datetime] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    kc_model, kc_meta = _get_model("kc")

    anchor_date = reference_date or (future_dates[0].to_pydatetime() - timedelta(days=1))
    last_kc_obs = _reference_mean("kc", anchor_date, 0.80) or 0.80
    last_savi_obs = _reference_mean("savi", anchor_date, None) or (
        (last_kc_obs - KC_INTERCEPT) / KC_SLOPE
    )
    set_forecast_context(last_savi=last_savi_obs, last_kc=last_kc_obs)

    days_ahead = np.arange(1, len(future_dates) + 1, dtype=float)

    if kc_model is not None:
        logger.info("Using trained SARIMA Kc model for forecast")
        exog_cols = kc_meta.get("exog_cols", ["sin_doy", "cos_doy", "sin2_doy", "cos2_doy"])
        exog_df = build_forecast_exog(future_dates=future_dates, exog_cols=exog_cols)

        if hasattr(kc_model, "get_forecast"):
            kc_fc = kc_model.get_forecast(steps=len(future_dates), exog=exog_df)
            kc_forecast = kc_fc.predicted_mean.values.astype(float)
        else:
            kc_forecast = kc_model.forecast(steps=len(future_dates), exog=exog_df).values.astype(float)

        stage_kc = np.array([
            get_wheat_stage_kc(d.to_pydatetime())[1]
            for d in future_dates
        ], dtype=float)
        kc_forecast = 0.65 * kc_forecast + 0.35 * stage_kc
        alpha = np.exp(-days_ahead / 5.0)
        kc_forecast = alpha * float(last_kc_obs) + (1 - alpha) * kc_forecast

    else:
        logger.warning("No Kc SARIMA model — using FAO-56 stage Kc")
        kc_forecast = np.array([
            get_wheat_stage_kc(d.to_pydatetime())[1]
            for d in future_dates
        ], dtype=float)

    kc_forecast = np.clip(kc_forecast, KC_MIN, KC_MAX)
    savi_forecast = np.clip((kc_forecast - KC_INTERCEPT) / KC_SLOPE, -0.1, 0.9)

    first_stage, first_kc_fao = get_wheat_stage_kc(future_dates[0].to_pydatetime())
    logger.info(
        f"Kc forecast: Kc_mean={kc_forecast.mean():.3f}, "
        f"range={kc_forecast.min():.3f}–{kc_forecast.max():.3f} "
        f"| crop_stage={first_stage} (FAO-56 Kc={first_kc_fao:.3f})"
    )
    return savi_forecast, kc_forecast


def generate_forecast_for_date(
    reference_date: datetime,
    days: int = FORECAST_DAYS,
) -> Dict[str, pd.Series]:
    """
    THESIS-COMPLIANT forecasting pipeline.
    Chain: Kc (SARIMA) → PET (SARIMA) → CWR = Kc × PET → IWR = max(CWR−Peff,0)
    """
    forecasts: Dict[str, pd.Series] = {}

    future_dates = pd.date_range(
        start=reference_date + timedelta(days=1),
        periods=days,
        freq="D",
    )

    # ── 1. Forecast Kc ──────────────────────────────────────────────────────
    kc_model, kc_meta = _get_model("kc")
    if kc_model is None:
        raise RuntimeError("[forecast] Kc model not available.")

    last_kc_obs = _reference_mean("kc", reference_date, kc_meta.get("last_kc", 0.80)) or 0.80
    last_savi_obs = _reference_mean("savi", reference_date, None) or kc_meta.get(
        "last_savi", (last_kc_obs - KC_INTERCEPT) / KC_SLOPE,
    )
    set_forecast_context(last_savi=last_savi_obs, last_kc=last_kc_obs)

    exog_cols_kc = kc_meta.get("exog_cols", ["sin_doy", "cos_doy", "sin2_doy", "cos2_doy"])
    exog_kc = build_forecast_exog(future_dates=future_dates, exog_cols=exog_cols_kc)

    if hasattr(kc_model, "get_forecast"):
        kc_fc = kc_model.get_forecast(steps=days, exog=exog_kc)
        kc_values = kc_fc.predicted_mean.values.astype(float)
    else:
        kc_values = kc_model.forecast(steps=days, exog=exog_kc).values.astype(float)

    stage_kc = np.array([
        get_wheat_stage_kc(d.to_pydatetime())[1]
        for d in future_dates
    ], dtype=float)
    kc_values = 0.65 * kc_values + 0.35 * stage_kc
    alpha_kc = np.exp(-np.arange(1, days + 1, dtype=float) / 5.0)
    kc_values = alpha_kc * float(last_kc_obs) + (1 - alpha_kc) * kc_values
    kc_values = np.clip(kc_values, KC_MIN, KC_MAX)
    forecasts["kc"] = pd.Series(kc_values, index=future_dates, name="kc")

    # ── 2. Forecast PET ─────────────────────────────────────────────────────
    pet_model, pet_meta = _get_model("pet")
    if pet_model is None:
        raise RuntimeError("[forecast] PET model not available.")

    last_cwr_obs = _reference_mean("cwr", reference_date, 3.5) or 3.5
    last_pet_obs = pet_meta.get("last_pet")
    if last_pet_obs is None or not np.isfinite(last_pet_obs):
        last_pet_obs = last_cwr_obs / last_kc_obs if last_kc_obs > 0 else 4.0

    set_forecast_context(
        last_savi=last_savi_obs, last_kc=last_kc_obs, last_pet=float(last_pet_obs),
    )
    exog_cols_pet = pet_meta.get("exog_cols", ["sin_doy", "cos_doy", "sin2_doy", "cos2_doy", "month"])
    exog_pet = build_forecast_exog(future_dates=future_dates, exog_cols=exog_cols_pet)

    if hasattr(pet_model, "get_forecast"):
        pet_fc = pet_model.get_forecast(steps=days, exog=exog_pet)
        base_pet = pet_fc.predicted_mean.values.astype(float)
    else:
        base_pet = pet_model.forecast(steps=days, exog=exog_pet).values.astype(float)
    if pet_meta.get("target_transform") == "log1p":
        base_pet = np.expm1(base_pet)

    doy = future_dates.dayofyear.values.astype(float)
    seasonal_pet = 5.5 + 3.2 * np.sin(2 * np.pi * (doy - 45) / 365.25)
    pet_values = 0.65 * base_pet + 0.35 * seasonal_pet
    alpha_pet = np.exp(-np.arange(days) / 5.0)
    pet_values = alpha_pet * float(last_pet_obs) + (1 - alpha_pet) * pet_values
    pet_values = np.clip(pet_values, 1.5, 12.0)
    forecasts["pet"] = pd.Series(pet_values, index=future_dates, name="pet")

    # ── 3. CWR = Kc × PET ───────────────────────────────────────────────────
    cwr_arr = np.clip(kc_values * pet_values, CWR_MIN, CWR_MAX)
    forecasts["cwr"] = pd.Series(cwr_arr, index=future_dates, name="cwr")

    # ── 4. IWR = max(CWR − Peff, 0) ─────────────────────────────────────────
    peff_arr = _climatological_peff(future_dates)
    iwr_arr = np.maximum(cwr_arr - peff_arr, 0.0)
    forecasts["iwr"] = pd.Series(iwr_arr, index=future_dates, name="iwr")
    forecasts["peff"] = pd.Series(peff_arr, index=future_dates, name="peff")

    # ── SAVI (derived from Kc) ───────────────────────────────────────────────
    savi_arr = np.clip((kc_values - KC_INTERCEPT) / KC_SLOPE, -0.1, 0.9)
    forecasts["savi"] = pd.Series(savi_arr, index=future_dates, name="savi")

    # ── ETc = Kc × PET = CWR (daily evapotranspiration rate, same physics) ──
    # ETc forecast uses DAILY VALUES (not cumulative) — aggregated as AVERAGE.
    forecasts["etc"] = pd.Series(cwr_arr.copy(), index=future_dates, name="etc")

    stage_info = get_wheat_stage_info(future_dates[0].to_pydatetime())
    logger.info(
        f"[forecast] Generated for {reference_date.date()}: "
        f"stage={stage_info['stage']} "
        f"Kc_mean={forecasts['kc'].mean():.3f}, "
        f"PET_mean={forecasts['pet'].mean():.2f}, "
        f"CWR_mean={forecasts['cwr'].mean():.2f}, "
        f"IWR_mean={forecasts['iwr'].mean():.2f}"
    )
    return forecasts


def _forecast_raster_is_fresh(param: str, slot: str, window: str, date: datetime) -> bool:
    """
    Return True when a forecast raster already exists AND was generated from
    exactly the same reference date.  This lets us skip the expensive SARIMA
    re-forecast for slots that have not changed since the last pipeline run.
    """
    p = forecast_path(param, slot, window)
    if not p.exists():
        return False
    try:
        with rasterio.open(p) as src:
            tags = src.tags()
            return tags.get("acquisition_date") == date.strftime("%Y-%m-%d")
    except Exception:
        return False


def create_forecast_raster(
    param: str,
    slot: str,
    window: str,
    forecast_series: pd.Series,
    template_raster: Path,
    date: datetime,                     # ← actual acquisition date of this slot
) -> bool:
    """
    Write a single forecast raster.

    Aggregation rules
    -----------------
    CWR / IWR  →  cumulative SUM  over the window  (units: mm_total)
    ETc  / Kc  →  spatial AVERAGE over the window  (units: mm/day or dimensionless)
    """
    # ── Fast-path: skip if the raster already reflects this date ──────────
    if _forecast_raster_is_fresh(param, slot, window, date):
        logger.debug(f"[forecast] skip {param} {slot} {window} — already fresh")
        return True

    try:
        WINDOW_SLICES = {"5day": (0, 5), "10day": (0, 10), "15day": (0, 15)}
        start_idx, end_idx = WINDOW_SLICES[window]
        window_days = end_idx - start_idx

        with rasterio.open(template_raster) as src:
            template_data = src.read(1).astype(np.float64)
            nodata        = src.nodata if src.nodata is not None else NODATA
            template_data = np.where(template_data == nodata, np.nan, template_data)
            profile       = src.profile.copy()

            window_forecast = forecast_series.iloc[start_idx:end_idx]

            # ── CWR & IWR: cumulative total over the window ────────────────
            if param in ["cwr", "iwr"]:
                forecast_val = float(window_forecast.sum())
                agg_label    = "total"
                unit_label   = "mm"
                units_tag    = "mm_total"
            # ── ETc & Kc: daily average over the window ────────────────────
            else:
                forecast_val = float(window_forecast.mean())
                agg_label    = "mean"
                unit_label   = "mm/day" if param == "etc" else ""
                units_tag    = "mm_per_day" if param == "etc" else ""

            stage_info = get_wheat_stage_info(window_forecast.index[0].to_pydatetime())

        valid = ~np.isnan(template_data)
        if not valid.any():
            logger.warning(f"No valid pixels in template for {param} {slot}")
            return False

        template_mean = float(np.nanmean(template_data[valid]))

        # Scale the spatial pattern of the template raster to the forecast value.
        # For CWR/IWR the template is in mm/day; scaling by (sum / daily_mean)
        # = (mean_daily × window_days / daily_mean) correctly yields mm_total
        # spatial values while preserving the relative spatial distribution.
        if template_mean > 0:
            scale_factor   = forecast_val / template_mean
            forecast_array = np.where(valid, template_data * scale_factor, np.nan)
        else:
            forecast_array = np.where(valid, forecast_val, np.nan)

        # Clip to the correct valid range (cumulative for CWR/IWR)
        vmin, vmax     = _VALID_FC.get(param, _VALID.get(param, (-1e9, 1e9)))
        forecast_array = np.clip(forecast_array, vmin, vmax)

        dst_path = forecast_path(param, slot, window)
        profile.update(
            dtype="float64",
            nodata=NODATA,
            compress="lzw",
            tiled=True,
            blockxsize=256,
            blockysize=256,
        )

        with rasterio.open(dst_path, "w", **profile) as dst:
            out_data = np.where(np.isnan(forecast_array), NODATA, forecast_array)
            dst.write(out_data.astype(np.float64), 1)
            dst.update_tags(
                parameter=param,
                slot=slot,
                forecast_window=window,
                acquisition_date=date.strftime("%Y-%m-%d"),   # ← actual date for freshness check
                reference_date=date.strftime("%Y-%m-%d"),
                forecast_mean=str(round(forecast_val, 4)),
                template_mean=str(round(template_mean, 4)),
                crop_stage=stage_info["stage"],
                days_after_sowing=str(stage_info["das"]),
                kc_fao56=str(round(stage_info["kc_fao56"], 4)),
                units=units_tag,
                aggregation="sum" if param in ["cwr", "iwr"] else "mean",
                window_days=str(window_days),
                model="PET-SARIMAX+Physics-CWR/IWR",
                generated_by="irrigation_monitoring_v10.1",
            )

        logger.info(
            f"Created {param} forecast for {slot} {window}: "
            f"{agg_label}={forecast_val:.4f} "
            f"{unit_label}"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to create {param} forecast for {slot}_{window}: {e}")
        return False


def generate_all_forecast_rasters() -> int:
    dates = _latest_n_complete_dates(HISTORY_DATES)
    if not dates:
        logger.error("[forecast] No Sentinel dates available")
        return 0

    total = 0
    n = len(dates)
    slots = _make_slots(n)

    for idx, date in enumerate(dates):
        slot = slots[idx]

        # ── Slot-level freshness check ──────────────────────────────────────
        # If every expected forecast raster for this slot already carries the
        # correct acquisition_date tag, the SARIMA forecast can be skipped
        # entirely — saving minutes of compute per slot.
        params_with_template = [
            p for p in FC_PARAMS if history_path(p, slot).exists()
        ]
        all_fresh = bool(params_with_template) and all(
            _forecast_raster_is_fresh(p, slot, w, date)
            for p in params_with_template
            for w in FORECAST_WINDOWS
        )
        if all_fresh:
            n_skip = len(params_with_template) * len(FORECAST_WINDOWS)
            total += n_skip
            logger.debug(
                f"[forecast] slot={slot} ({date.date()}): "
                f"all {n_skip} rasters fresh — skipping SARIMA"
            )
            continue

        # ── Run SARIMA forecast for this reference date ────────────────────
        forecasts = generate_forecast_for_date(date, FORECAST_DAYS)
        if not forecasts:
            logger.warning(f"[forecast] No forecast for {slot} ({date.date()})")
            continue

        n_rasters = 0
        for param in FC_PARAMS:
            if param not in forecasts:
                continue
            for window in FORECAST_WINDOWS:
                template = history_path(param, slot)
                if template.exists():
                    if create_forecast_raster(
                        param, slot, window,
                        forecasts[param], template,
                        date,           # ← actual date for freshness tag
                    ):
                        n_rasters += 1
                        total += 1

        logger.info(f"[forecast] slot={slot} ({date.date()}): {n_rasters} files written")

    expected_total = n * len(FC_PARAMS) * len(FORECAST_WINDOWS)
    logger.info(f"[forecast] ALL: {total} / {expected_total}")
    return total


# ═══════════════════════════════════════════════════════════════════════════
# STEP C — PUSH TO GEOSERVER
# ═══════════════════════════════════════════════════════════════════════════

def push_to_geoserver() -> None:
    try:
        from init_geoserver import GeoServerAPI
        gs = GeoServerAPI()
    except Exception as e:
        logger.warning(f"[geoserver] Cannot init GeoServerAPI: {e}")
        return

    dates = _latest_n_complete_dates(HISTORY_DATES)
    n = len(dates)
    slots = _make_slots(n)

    for param in PARAMS:
        for slot in slots:
            p = history_path(param, slot)
            if not p.exists():
                continue
            store = f"{param}_{slot}"
            style = "etc_style" if param == "etc" else f"{param}_style"
            try:
                store_ok     = gs.create_coverage_store_if_not_exists(store, p)
                file_ok      = gs.update_coverage_store_file(store, p)
                configure_ok = gs.configure_layer(layer_name=store, store_name=store)
                style_ok     = gs.assign_style(store, style)
                if store_ok and file_ok and configure_ok and style_ok:
                    logger.info(f"[geoserver] ✅ Layer ready: {store}")
                else:
                    logger.warning(f"[geoserver] ⚠ Partial: {store}")
            except Exception as e:
                logger.warning(f"[geoserver] {store}: {e}")

    for param in FC_PARAMS:
        for slot in slots:
            for window in FORECAST_WINDOWS:
                p = forecast_path(param, slot, window)
                if not p.exists():
                    continue
                store = f"{param}_{slot}_{window}"
                # CWR/IWR forecast rasters are cumulative (mm_total) so they
                # need dedicated SLD styles with the wider 0-200 mm colour range.
                if param in ("cwr", "iwr"):
                    fc_style = f"{param}_forecast_style"
                else:
                    fc_style = f"{param}_style"
                try:
                    gs.create_coverage_store_if_not_exists(store, p)
                    gs.update_coverage_store_file(store, p)
                    gs.configure_layer(layer_name=store, store_name=store)
                    gs.assign_style(store, fc_style)
                    logger.info(f"[geoserver] ✅ Forecast layer ready: {store} (style={fc_style})")
                except Exception as e:
                    logger.warning(f"[geoserver] {store}: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# MASTER PIPELINE
# ═══════════════════════════════════════════════════════════════════════════

def run_pipeline() -> Dict:
    logger.info("═" * 65)
    logger.info("run_pipeline() START — v10.0 (Seasonal Cap + ETc)")
    logger.info("═" * 65)

    cleanup_old_rasters()
    _get_wheat_mask()

    logger.info("── A: History rasters ──")
    h_total = generate_history_rasters()

    logger.info("── B/C: Forecast + rasters ──")
    _get_model("pet")
    f_total = generate_all_forecast_rasters()

    logger.info("── D: GeoServer ──")
    push_to_geoserver()
    clear_raster_pixel_cache()

    dates   = _latest_n_complete_dates()
    n = len(dates)
    summary = {
        "slots":            {slot_for_index(i): str(d.date()) for i, d in enumerate(dates)},
        "n_dates":          n,
        "seasons":          sorted(set(get_season_id(d) for d in dates)),
        "history_rasters":  h_total,
        "forecast_rasters": f_total,
        "grand_total":      h_total + f_total,
        "units":            "mm_per_day",
        "forecast_model":   "PET-SARIMAX + Physics CWR/IWR",
    }
    logger.info(f"DONE: {summary}")
    return summary


# ═══════════════════════════════════════════════════════════════════════════
# SCHEDULER CALLBACKS
# ═══════════════════════════════════════════════════════════════════════════

def generate_operational_rasters() -> None:
    logger.info("[generate_operational_rasters] START")
    try:
        cleanup_old_rasters()
        h = generate_history_rasters()
        logger.info(f"[generate_operational_rasters] history rasters: {h}")
    except Exception as e:
        logger.error(f"[generate_operational_rasters] history step failed: {e}", exc_info=True)
    try:
        f = generate_all_forecast_rasters()
        logger.info(f"[generate_operational_rasters] forecast rasters: {f}")
    except Exception as e:
        logger.error(f"[generate_operational_rasters] forecast step failed: {e}", exc_info=True)
    try:
        push_to_geoserver()
        logger.info("[generate_operational_rasters] GeoServer push done")
    except Exception as e:
        logger.error(f"[generate_operational_rasters] GeoServer push failed: {e}", exc_info=True)
    clear_raster_pixel_cache()
    logger.info("[generate_operational_rasters] DONE")


def process_single_sentinel_image(tif_path: Path) -> None:
    logger.info(f"[process_single_sentinel_image] {tif_path.name}")
    try:
        from run import run_savi, run_kc, run_etc, run_cwr, run_iwr
        from processor import DataProcessor
        p = DataProcessor()
        run_savi(p)
        run_kc(p)
        run_etc(p)
        run_cwr(p)
        run_iwr(p)
        logger.info(f"[process_single_sentinel_image] complete for {tif_path.name}")
    except Exception as e:
        logger.error(f"[process_single_sentinel_image] failed for {tif_path.name}: {e}", exc_info=True)


# ═══════════════════════════════════════════════════════════════════════════
# FastAPI APP
# ═══════════════════════════════════════════════════════════════════════════

from graph import router as graph_router

app = FastAPI(
    title="Wheat Irrigation Monitoring System",
    version="10.0.0",
    description=(
        "v10.0 — Seasonal cap (5 seasons Nov–Apr) + ETc layer.\n\n"
        "  • PET forecasted with SARIMAX\n"
        "  • CWR = Kc × PET  (FAO-56)\n"
        "  • IWR = max(CWR − Peff, 0)  (FAO-56)\n"
        "  • ETc added as map layer\n"
        "  • Calendar shows Nov–Apr only, last 5 seasons\n"
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(graph_router)

from config import STUDY_AREA, EXACT_BOUNDARY


class ChatRequest(BaseModel):
    query: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    history: Optional[List[Dict]] = None
    session_id: Optional[str] = "default"


class LiveSensorIngestRequest(BaseModel):
    sensor_id: Optional[str] = "default"
    timestamp: Optional[str] = None
    source: Optional[str] = "api"
    values: Dict[str, object]


def _chat_query_needs_live_data(query: str, has_location: bool = False) -> bool:
    q = (query or "").lower()
    try:
        from rag_kb import query_requests_live_metrics

        requested = query_requests_live_metrics(q)
    except Exception:
        requested = False

    if has_location:
        return requested
    if re.search(r"\b(what is|what does|meaning|mean|explain|why|how does|ka matlab|kya hota|kyu|kyon)\b", q):
        return bool(re.search(r"\b(today|now|current|live|pixel|clicked|map|field value|reading|condition)\b", q))
    return requested or bool(
        re.search(
            r"\b(today|now|current|live|pixel|clicked|map|field|area|condition|reading|"
            r"value|irrigate|irrigation|sinchai|paani|water now|water today|need water|"
            r"forecast|predict|next)\b",
            q,
        )
    )

# ═══════════════════════════════════════════════════════════════════════════
# PIXEL TIMESERIES FROM HISTORY RASTERS
# ═══════════════════════════════════════════════════════════════════════════

_PIXEL_REQUEST_LOCK = Lock()
_LATEST_PIXEL_REQUEST_IDS: Dict[str, int] = {}


def _register_pixel_request(request_group: str, request_id: int) -> None:
    if request_id <= 0:
        return
    request_group = request_group or "default"
    with _PIXEL_REQUEST_LOCK:
        current = _LATEST_PIXEL_REQUEST_IDS.get(request_group, 0)
        _LATEST_PIXEL_REQUEST_IDS[request_group] = max(current, request_id)


def _pixel_request_cancelled(request_group: str, request_id: int) -> bool:
    if request_id <= 0:
        return False
    request_group = request_group or "default"
    with _PIXEL_REQUEST_LOCK:
        return request_id < _LATEST_PIXEL_REQUEST_IDS.get(request_group, 0)


def _pixel_from_latlon(lat: float, lon: float) -> Dict:
    try:
        return raster_pixel_from_latlon(lat, lon, params=PARAMS)
    except RasterGridUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RasterCoordinateError as exc:
        logger.warning(f"[pixel-ts] invalid coordinate ({lat}, {lon}): {exc}")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RasterOutOfBoundsError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _read_history_pixel_value(path: Path, pixel: Dict) -> Optional[float]:
    return raster_read_history_pixel_value(path, pixel, params=PARAMS)


def _pixel_timeseries(pixel: Dict, request_group: str = "default", request_id: int = 0) -> Dict[str, List[Dict]]:
    return pixel_timeseries_for_pixel(
        pixel,
        params=PARAMS,
        allowed_seasons=get_allowed_season_ids(),
        season_id_fn=get_season_id,
        in_season_fn=is_in_season,
        cancelled_fn=lambda: _pixel_request_cancelled(request_group, request_id),
    )


def _date_for_slot(slot: Optional[str]) -> Optional[datetime]:
    dates = _latest_n_complete_dates(HISTORY_DATES)
    if not dates:
        return None

    if not slot or slot == "today":
        return dates[0]

    try:
        idx = int(slot)
    except (TypeError, ValueError):
        return None

    if idx < 0 or idx >= len(dates):
        return None
    return dates[idx]


@app.get("/api/pixel-timeseries")
def get_pixel_timeseries(
    lat: float = Query(..., description="Latitude of the clicked point"),
    lon: float = Query(..., description="Longitude of the clicked point"),
    request_group: str = Query("default", description="Client request group used to isolate stale-read cancellation"),
    request_id: int = Query(0, description="Client request id used to supersede stale pixel reads"),
):
    """
    Return the historical time-series for the clicked raster pixel.

    The response contains one list per raster type (savi/kc/cwr/iwr/etc).
    Each list is sorted by date and contains { date, value } objects.

    This samples the same history rasters used by /api/point and GeoServer,
    so the chart value for any date matches the selected-point value.
    """

    _register_pixel_request(request_group, request_id)
    pixel = _pixel_from_latlon(lat, lon)
    pixel_id: str = pixel["pixel_id"]
    logger.debug(
        f"[pixel-ts] query=({lat:.5f},{lon:.5f}) "
        f"→ pixel={pixel_id} "
        f"center=({pixel['latitude']:.5f},{pixel['longitude']:.5f}) "
        f"native=({pixel['native_x']:.2f},{pixel['native_y']:.2f})"
    )

    # ── 2. Read timeseries for each raster type directly from GeoTIFFs ───
    try:
        result = _pixel_timeseries(pixel, request_group=request_group, request_id=request_id)
    except RasterLookupCancelled as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # ── 3. Return ─────────────────────────────────────────────────────────
    return {
        "pixel_id": pixel_id,
        "row": pixel["row"],
        "col": pixel["col"],
        "latitude": round(float(pixel["latitude"]), 7),
        "longitude": round(float(pixel["longitude"]), 7),
        "query_latitude": lat,
        "query_longitude": lon,
        "source": "history_rasters",
        "seasons": get_allowed_season_ids(),
        "timeseries": result,
    }


@app.get("/api/boundary")
async def get_boundary():
    bounds = EXACT_BOUNDARY.get("bounds") or STUDY_AREA.get("bounds")
    if not bounds or not all(k in bounds for k in ("north", "south", "east", "west")):
        bounds = {"north": 29.4400, "south": 28.8900, "west": 78.8800, "east": 80.1040}

    north, south, east, west = bounds["north"], bounds["south"], bounds["east"], bounds["west"]
    if north < south: north, south = south, north
    if east < west:   east, west   = west, east
    if (north - south) < 0.01: north += 0.05; south -= 0.05
    if (east - west) < 0.01:   east  += 0.05; west  -= 0.05

    return {
        "name":   STUDY_AREA.get("name", "Udham Singh Nagar"),
        "state":  STUDY_AREA.get("state", "Uttarakhand"),
        "crs":    STUDY_AREA.get("crs", "EPSG:4326"),
        "source": STUDY_AREA.get("boundary_source", "static-fallback"),
        "bounds": {
            "north": round(north, 6), "south": round(south, 6),
            "east":  round(east,  6), "west":  round(west,  6),
        },
        "leaflet_bounds": [
            [round(south, 6), round(west, 6)],
            [round(north, 6), round(east, 6)],
        ],
        "center": EXACT_BOUNDARY.get("center") or [
            round((east + west) / 2, 6),
            round((north + south) / 2, 6),
        ],
        "geojson": EXACT_BOUNDARY.get("geojson", {"type": "FeatureCollection", "features": []}),
    }


@app.get("/api/history")
async def get_history():
    """
    Return observed and forecast means for all history slots.

    Calendar-aware response:
      • Only Nov–Apr dates from the last MAX_SEASONS seasons
      • Each slot carries: date, season_id, slot, obs_means, forecast_means
      • Extra metadata for the frontend calendar (season list, filter helpers)
    """
    dates = _latest_n_complete_dates()
    if not dates:
        raise HTTPException(status_code=404, detail="No processed Sentinel scenes found")

    result = []
    n = len(dates)

    for idx, d in enumerate(dates):
        slot      = slot_for_index(idx)
        obs_means = {}
        fc_means  = {}

        for param in PARAMS:
            path = history_path(param, slot)
            if path.exists():
                with rasterio.open(path) as src:
                    tags = src.tags()
                mean_str         = tags.get("mean")
                obs_means[param] = (
                    float(mean_str)
                    if mean_str and mean_str not in ("None", "nan", "")
                    else None
                )
            else:
                obs_means[param] = None

            fc_means[param] = {}
            if param in FC_PARAMS:
                for w in FORECAST_WINDOWS:
                    fpath = forecast_path(param, slot, w)
                    if fpath.exists():
                        with rasterio.open(fpath) as src:
                            tags = src.tags()
                        fc_str              = tags.get("forecast_mean")
                        fc_means[param][w]  = (
                            float(fc_str)
                            if fc_str and fc_str not in ("None", "nan", "")
                            else None
                        )
                    else:
                        fc_means[param][w] = None

        season_id = get_season_id(d) or ""

        result.append({
            "slot":           slot,
            "date":           str(d.date()),
            "season":         season_id,
            "month":          d.month,
            "year":           d.year,
            "is_latest":      idx == 0,
            "obs_means":      obs_means,
            "forecast_means": fc_means,
        })

    # Build season summary for frontend filter UI
    seasons_present = {}
    for item in result:
        sid = item["season"]
        if sid not in seasons_present:
            seasons_present[sid] = {"season": sid, "count": 0, "months": set()}
        seasons_present[sid]["count"] += 1
        seasons_present[sid]["months"].add(item["month"])

    seasons_list = [
        {
            "season": v["season"],
            "count":  v["count"],
            "months": sorted(v["months"]),
        }
        for v in sorted(seasons_present.values(), key=lambda x: x["season"], reverse=True)
    ]

    return {
        "n_slots":        n,
        "max_seasons":    MAX_SEASONS,
        "season_months":  sorted(SEASON_MONTHS),   # [1,2,3,4,11,12]
        "allowed_seasons": get_allowed_season_ids(),
        "seasons":        seasons_list,
        "units":          "mm_per_day",
        "model":          "PET-SARIMAX + Physics CWR/IWR",
        "params":         PARAMS,
        "slots":          result,
    }


@app.get("/api/seasons")
async def get_seasons():
    """
    Lightweight endpoint: returns allowed season IDs and which are present in data.
    Used by the frontend calendar filter.
    """
    allowed = get_allowed_season_ids()
    dates   = _latest_n_complete_dates()
    present = set(get_season_id(d) for d in dates if get_season_id(d))

    return {
        "allowed_seasons": allowed,
        "present_seasons": sorted(present, reverse=True),
        "max_seasons":     MAX_SEASONS,
        "season_months":   sorted(SEASON_MONTHS),
    }


@app.get("/api/forecast")
async def get_forecast(
    date: str = Query(..., description="Reference date YYYY-MM-DD"),
    days: int  = Query(15,  ge=1, le=30, description="Forecast horizon (days)"),
):
    try:
        ref_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date — use YYYY-MM-DD")

    forecasts = generate_forecast_for_date(ref_date, days)
    if not forecasts:
        raise HTTPException(status_code=500, detail="Failed to generate forecast")

    result: dict = {
        "reference_date": date,
        "forecast_days":  days,
        "model":          "PET-SARIMAX + Physics CWR/IWR (v10.0)",
        "forecasts":      {},
    }

    units_by_param = {
        "savi": "unitless", "kc": "unitless",
        "pet": "mm_per_day", "cwr": "mm_per_day",
        "iwr": "mm_per_day", "peff": "mm_per_day",
    }

    for param in ("savi", "pet", "kc", "cwr", "iwr", "peff"):
        if param in forecasts:
            series = forecasts[param]
            result["forecasts"][param] = {
                "dates":  [d.strftime("%Y-%m-%d") for d in series.index],
                "values": [round(float(v), 4) for v in series.values],
                "units":  units_by_param[param],
                "mean":   round(float(series.mean()), 4),
                "min":    round(float(series.min()),  4),
                "max":    round(float(series.max()),  4),
            }

    result["crop_stages"] = [
        {"date": d.strftime("%Y-%m-%d"), **get_wheat_stage_info(d.to_pydatetime())}
        for d in forecasts["kc"].index
    ]

    WINDOW_SLICES = {"5day": (0, 5), "10day": (0, 10), "15day": (0, 15)}
    result["window_summaries"] = {}
    for window, (start_idx, end_idx) in WINDOW_SLICES.items():
        result["window_summaries"][window] = {}
        for param in ("kc", "cwr", "iwr", "peff"):
            if param in forecasts:
                vals = forecasts[param].iloc[start_idx:end_idx].values
                result["window_summaries"][window][param] = {
                    "mean":  round(float(np.mean(vals)), 4),
                    "total": round(float(np.sum(vals)), 4),
                }
        window_date = forecasts["kc"].index[start_idx].to_pydatetime()
        result["window_summaries"][window]["crop_stage"] = get_wheat_stage_info(window_date)

    return result


@app.get("/api/point")
def get_point(
    lat:  float,
    lon:  float,
    slot: Optional[str] = None,
):
    slot = slot or "today"
    pixel = _pixel_from_latlon(lat, lon)
    selected_date = _date_for_slot(slot)
    if selected_date is None:
        raise HTTPException(status_code=404, detail=f"No acquisition date found for slot '{slot}'")

    result: Dict[str, Optional[float]] = {}
    forecast = {}

    for param in PARAMS:
        result[param] = _read_history_pixel_value(history_path(param, slot), pixel)

    for param in POINT_FORECAST_PARAMS:
        forecast[param] = {}
        for w in FORECAST_WINDOWS:
            fpath = forecast_path(param, slot, w)
            forecast[param][w] = _read_history_pixel_value(fpath, pixel)

    return {
        "lat":              round(float(pixel["latitude"]), 7),
        "lon":              round(float(pixel["longitude"]), 7),
        "query_lat":        lat,
        "query_lon":        lon,
        "pixel_id":         pixel["pixel_id"],
        "row":              pixel["row"],
        "col":              pixel["col"],
        "acquisition_date": selected_date.strftime("%Y-%m-%d"),
        "slot":             slot,
        "values":           result,
        "forecast":         forecast,
    }


def _collect_chat_live_data(req: ChatRequest) -> Dict[str, object]:
    live_data: Dict[str, object] = {}
    try:
        dates = _latest_n_complete_dates(1)
        if not dates:
            return live_data

        for param in PARAMS:
            val = _read_mean(history_path(param, "today"))
            if val is not None:
                live_data[param] = round(val, 3)

        if req.lat is not None and req.lon is not None:
            live_data["query_location"] = f"lat={req.lat:.4f}, lon={req.lon:.4f}"
            try:
                pixel = _pixel_from_latlon(req.lat, req.lon)
                for param in PARAMS:
                    value = _read_history_pixel_value(history_path(param, "today"), pixel)
                    if value is not None:
                        live_data[f"point_{param}"] = round(float(value), 3)
            except HTTPException as exc:
                live_data["point_lookup_status"] = str(exc.detail)
            except Exception as exc:
                logger.debug("[chat] point lookup skipped: %s", exc)
    except Exception as exc:
        logger.warning("[chat] live data fetch failed: %s", exc)
    return live_data


def _prepare_chat_context(req: ChatRequest) -> Dict[str, Any]:
    query = (req.query or "").strip()
    needs_live_data = _chat_query_needs_live_data(query, req.lat is not None and req.lon is not None)
    live_data = _collect_chat_live_data(req) if needs_live_data else {}
    tool_answer = None
    tool_sources: List[str] = []
    query_type = "knowledge_based"
    structured_context = None

    try:
        from chat_data_tools import get_data_tools, safe_llm_context

        tool_result = get_data_tools().answer(query, live_data=live_data or None)
        query_type = tool_result.query_type
        tool_answer = tool_result.answer
        tool_sources = tool_result.sources or []
        structured_context = safe_llm_context(tool_result)
    except Exception as exc:
        logger.warning("[chat] structured query tools failed: %s", exc, exc_info=True)

    return {
        "query": query,
        "live_data": live_data,
        "tool_answer": tool_answer,
        "tool_sources": tool_sources,
        "query_type": query_type,
        "structured_context": structured_context,
        "needs_live_data": needs_live_data,
    }


def _sse(event: str, payload: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.post("/api/chat")
async def chat(req: ChatRequest):
    query = (req.query or "").strip()
    if not query:
        return {
            "answer": "Please ask a question about irrigation, crop water requirements, or the study region.",
            "sources": [],
            "live_data": {},
        }

    context = await asyncio.to_thread(_prepare_chat_context, req)
    live_data = context["live_data"]
    tool_answer = context["tool_answer"]
    tool_sources = context["tool_sources"]
    query_type = context["query_type"]
    structured_context = context["structured_context"]

    # Prepend any direct tool answer into structured_context so the LLM can
    # reference it.  A tool answer that exists but is never forwarded would be
    # silently dropped, causing the RAG model to ignore pre-computed field data.
    if tool_answer:
        tool_block = f"## Structured Tool Answer\n{tool_answer}"
        structured_context = (
            tool_block + "\n\n" + structured_context if structured_context else tool_block
        )

    try:
        from rag_kb import get_chat_answer

        rag_response = await asyncio.to_thread(
            get_chat_answer,
            query,
            live_data or None,
            req.history or [],
            req.session_id or "default",
            structured_context,
        )
        answer = rag_response.get("answer") or "I am having trouble checking the data right now. Please try again in a moment."
        source_ids = list(dict.fromkeys(tool_sources + (rag_response.get("sources", []) or [])))
    except Exception as exc:
        logger.error("[chat] LangChain RAG failed: %s", exc, exc_info=True)
        try:
            from rag_kb import llm_unavailable_answer

            answer = llm_unavailable_answer()
        except Exception:
            answer = "I could not generate a knowledge-base answer right now because the LLM is unavailable."
        source_ids = tool_sources
        rag_response = {"model_used": "llm_unavailable"}

    include_live_metrics = bool(context.get("needs_live_data") and rag_response.get("include_live_metrics"))

    return {
        "answer": answer,
        "sources": source_ids,
        "live_data": live_data if include_live_metrics else {},
        "include_live_metrics": include_live_metrics,
        "query_type": query_type,
        "model_used": rag_response.get("model_used"),
        "rag_chunks": rag_response.get("rag_chunks", []),
        "retrieved_context": rag_response.get("retrieved_context", []),
        "attempts": rag_response.get("attempts", []),
        "latency_ms": rag_response.get("latency_ms"),
        "retrieval_ms": rag_response.get("retrieval_ms"),
        "rag_backend": rag_response.get("rag_backend"),
    }


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    query = (req.query or "").strip()
    if not query:
        def empty_stream():
            answer = "Please ask a question about irrigation, crop water requirements, or the study region."
            yield _sse("token", {"content": answer})
            yield _sse("done", {"answer": answer, "sources": [], "live_data": {}, "query_type": "empty"})

        return StreamingResponse(empty_stream(), media_type="text/event-stream")

    def event_stream():
        context: Dict[str, Any] = {
            "live_data": {},
            "tool_sources": [],
            "structured_context": None,
            "query_type": "knowledge_based",
        }
        live_data: Dict[str, object] = {}
        tool_sources: List[str] = []
        structured_context = None
        try:
            context = _prepare_chat_context(req)
            live_data = context["live_data"]
            tool_sources = context["tool_sources"]
            structured_context = context["structured_context"]

            # Merge pre-computed tool answer into structured_context.
            tool_answer_text = context.get("tool_answer")
            if tool_answer_text:
                tool_block = f"## Structured Tool Answer\n{tool_answer_text}"
                structured_context = (
                    tool_block + "\n\n" + structured_context if structured_context else tool_block
                )

            from rag_kb import stream_chat_answer

            for event in stream_chat_answer(
                query,
                live_data=live_data or None,
                history=req.history or [],
                session_id=req.session_id or "default",
                structured_context=structured_context,
            ):
                event_type = event.get("type", "message")
                if event_type == "token":
                    yield _sse("token", {"content": event.get("content", "")})
                elif event_type == "status":
                    yield _sse("status", {"model": event.get("model"), "status": event.get("status")})
                elif event_type == "meta":
                    sources = list(dict.fromkeys(tool_sources + (event.get("sources", []) or [])))
                    include_live_metrics = bool(context.get("needs_live_data") and event.get("include_live_metrics"))
                    yield _sse(
                        "meta",
                        {
                            "sources": sources,
                            "rag_chunks": event.get("rag_chunks", []),
                            "retrieved_context": event.get("retrieved_context", []),
                            "retrieval_ms": event.get("retrieval_ms"),
                            "rag_backend": event.get("rag_backend"),
                            "live_data": live_data if include_live_metrics else {},
                            "include_live_metrics": include_live_metrics,
                            "query_type": context["query_type"],
                        },
                    )
                elif event_type == "done":
                    sources = list(dict.fromkeys(tool_sources + (event.get("sources", []) or [])))
                    include_live_metrics = bool(context.get("needs_live_data") and event.get("include_live_metrics"))
                    yield _sse(
                        "done",
                        {
                            **event,
                            "sources": sources,
                            "live_data": live_data if include_live_metrics else {},
                            "include_live_metrics": include_live_metrics,
                            "query_type": context["query_type"],
                        },
                    )
        except Exception as exc:
            logger.error("[chat] streaming RAG failed: %s", exc, exc_info=True)
            try:
                from rag_kb import llm_unavailable_answer

                answer = llm_unavailable_answer()
            except Exception:
                answer = "I could not generate a knowledge-base answer right now because the LLM is unavailable."
            yield _sse("token", {"content": answer})
            yield _sse(
                "done",
                {
                    "answer": answer,
                    "sources": tool_sources,
                    "live_data": {},
                    "include_live_metrics": False,
                    "query_type": context["query_type"],
                    "model_used": "llm_unavailable",
                },
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/chat/health")
async def chat_health():
    try:
        from rag_kb import rag_health

        return await asyncio.to_thread(rag_health)
    except Exception as exc:
        logger.exception("[chat] health failed")
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/api/live-data")
async def ingest_live_data(req: LiveSensorIngestRequest):
    """
    Store live sensor/API readings for real-time chatbot queries.

    Example payload:
      {"sensor_id": "field-01", "values": {"iwr": 42.6, "cwr": 5.1}}
    """
    try:
        from chat_data_tools import get_data_tools
        payload = req.dict()
        return {"status": "ok", **get_data_tools().ingest_live(payload)}
    except Exception as e:
        logger.exception("[live-data] ingest failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/live-data/latest")
async def latest_live_data(metric: Optional[str] = None):
    try:
        from chat_data_tools import get_data_tools, PARAM_ALIASES
        normalized_metric = PARAM_ALIASES.get(metric.lower(), metric.lower()) if metric else None
        latest = get_data_tools().live_store.latest(normalized_metric)
        if not latest:
            return {"status": "unavailable", "message": "Real-time data is currently unavailable.", "latest": {}}
        return {"status": "ok", "latest": latest}
    except Exception as e:
        logger.exception("[live-data] latest failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health():
    return {"status": "ok", "version": "10.0.0", "model": "PET-SARIMAX + Physics CWR/IWR"}


@app.post("/api/refresh")
async def manual_refresh():
    try:
        return {"status": "ok", "result": run_pipeline()}
    except Exception as e:
        logger.exception("Pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/model/info")
async def model_info():
    pet_model, pet_meta = _get_model("pet")
    kc_model, kc_meta   = _get_model("kc")

    def _meta_dict(model, meta):
        if meta is None:
            return {"available": False}
        return {
            "available": model is not None,
            "note":     meta.get("note", ""),
            "test_r2":  meta["metrics"].get("R2"),
            "test_rmse":meta["metrics"].get("RMSE"),
            "test_mae": meta["metrics"].get("MAE"),
            "order":    meta.get("order"),
            "exog_cols":meta.get("exog_cols"),
            "last_training_date": (
                meta["last_date"].strftime("%Y-%m-%d")
                if meta.get("last_date") else None
            ),
        }

    return {
        "models": {
            "kc":  _meta_dict(kc_model,  kc_meta),
            "pet": _meta_dict(pet_model, pet_meta),
        },
        "history_slots":       HISTORY_DATES,
        "max_seasons":         MAX_SEASONS,
        "season_months":       sorted(SEASON_MONTHS),
        "allowed_seasons":     get_allowed_season_ids(),
        "thesis_reference":    "Satabdi Mandal, 2025, IIRS-ISRO, §4.6, §5.6",
        "physical_relationships": {
            "savi_to_kc": f"Kc = {KC_SLOPE:.4f} × SAVI + {KC_INTERCEPT:.4f}  (thesis Table 9)",
            "cwr":        "CWR = Kc × PET  (FAO-56)",
            "iwr":        "IWR = max(CWR − Peff, 0)  (FAO-56)",
        },
        "crop_stage_today": get_wheat_stage_info(datetime.utcnow()),
    }


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def main():
    setup_logging()
    logger.info("=" * 65)
    logger.info("Irrigation Monitoring System v10.0 starting …")
    logger.info(f"Seasonal cap: {MAX_SEASONS} seasons | Months: Nov–Apr")
    logger.info(f"Allowed seasons: {get_allowed_season_ids()}")
    logger.info("=" * 65)

    _get_wheat_mask()

    pet_model, pet_meta = _get_model("pet")
    if pet_model:
        logger.info(f"✓ PET model ready (R²={pet_meta['metrics']['R2']:.4f})")
    else:
        logger.error("✗ Failed to initialise PET model")

    run_pipeline()

    try:
        from scheduler import start_scheduler
        _scheduler, _observer = start_scheduler(
            delete_callback=cleanup_old_rasters,
            generate_callback=generate_operational_rasters,
            download_and_process_callback=None,
            single_image_pipeline_callback=process_single_sentinel_image,
        )
        logger.info("✓ Scheduler + Watchdog started")
    except Exception as e:
        logger.error(f"✗ Scheduler failed to start: {e}", exc_info=True)
        logger.warning("Continuing without scheduler — pipeline will NOT run automatically.")

    uvicorn.run(
        app, host="0.0.0.0", port=8000,
        log_level="info", access_log=True,
    )


if __name__ == "__main__":
    main()
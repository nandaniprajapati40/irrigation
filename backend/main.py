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
import pickle
import lightgbm as lgb
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

CWR_MIN = 0.0
CWR_MAX = 15.0

# ═══════════════════════════════════════════════════════════════════════════
# NEW: LightGBM Model Configuration
# ═══════════════════════════════════════════════════════════════════════════

# Resolve MODEL_DIR relative to this file so it works regardless of the
# working directory the server is launched from.
# Trained models live at:  backend/data/models/
MODEL_DIR = Path(__file__).parent / "data" / "models"

# Load feature lists from v5.0 model metadata
def _load_feature_lists():
    """Load feature lists from model metadata or define them."""
    # These should match the features used in model.ipynb
    # For now, we define them here - in production, load from metadata
    BANDS = ["savi", "kc", "cwr", "iwr", "pet", "rain"]
    
    META_COLS = [f"{b}_{s}" for b in BANDS for s in ("mean", "min", "max", "std", "range", "cv")]
    TEMPORAL_COLS = ["rabi_doy", "month", "season_id", "sin1_doy", "cos1_doy", "sin2_doy", "cos2_doy"]
    LAG_DAYS = (1, 3, 5, 7)
    ROLL_WINDOWS = (3, 7)
    
    LAG_ROLL_COLS_CWR = (
        [f"cwr_lag{n}" for n in LAG_DAYS]
        + [f"pet_lag{n}" for n in (1, 3, 7)]
        + [f"rain_lag{n}" for n in (1, 3, 7)]
        + [f"savi_lag{n}" for n in (1, 3, 7)]
        + ["cwr_rmean3", "cwr_rmean7", "cwr_rstd7"]
        + ["pet_rmean3", "pet_rmean7", "pet_rstd7"]
        + ["savi_rmean3", "savi_rmean7", "savi_rstd7"]
        + ["rain_cumsum3", "rain_cumsum7"]
        + ["savi_std_lag1", "savi_std_lag3", "cwr_std_lag1", "cwr_std_lag3",
           "rain_std_lag1", "rain_std_lag3"]
    )
    
    LAG_ROLL_COLS_IWR = (
        [f"iwr_lag{n}" for n in LAG_DAYS]
        + [f"cwr_lag{n}" for n in (1, 3, 7)]
        + [f"rain_lag{n}" for n in (1, 3, 7)]
        + [f"savi_lag{n}" for n in (1, 3, 7)]
        + ["iwr_rmean3", "iwr_rmean7", "iwr_rstd7"]
        + ["cwr_rmean3", "cwr_rmean7"]
        + ["rain_cumsum3", "rain_cumsum7"]
        + ["savi_std_lag1", "savi_std_lag3", "cwr_std_lag1", "cwr_std_lag3",
           "rain_std_lag1", "rain_std_lag3"]
    )
    
    INTERACTION_COLS = ["pet_x_savi", "kc_x_pet", "rain_deficit"]
    
    FEATURES_CWR = list(dict.fromkeys(META_COLS + TEMPORAL_COLS + LAG_ROLL_COLS_CWR + INTERACTION_COLS))
    FEATURES_IWR = list(dict.fromkeys(META_COLS + TEMPORAL_COLS + LAG_ROLL_COLS_IWR + INTERACTION_COLS))
    
    return FEATURES_CWR, FEATURES_IWR

FEATURES_CWR, FEATURES_IWR = _load_feature_lists()

# ── Deserialisation stub for pickled LGBMWrapper objects from model.ipynb ──
# pickle.load() resolves class names against __main__ at load time.  The pkl
# files were produced in model.ipynb where LGBMWrapper was the top-level class,
# so when this server is __main__ Python searches HERE for it.  We only need
# the attributes that pickle actually restores (those set in __init__ and fit);
# predict() delegates to the fitted inner LGBMRegressor so inference works
# identically to the notebook.
from sklearn.base import BaseEstimator, RegressorMixin  # noqa: E402

class LGBMWrapper(BaseEstimator, RegressorMixin):
    """Deserialisation-compatible stub for pickled v5.0 model objects.

    The full training class lives in model.ipynb.  This stub only needs to
    support pickle round-tripping and inference — it is never re-trained here.
    """
    def __init__(self, num_leaves=31, max_depth=6, learning_rate=0.05,
                 n_estimators=500, min_data_in_leaf=5, subsample=0.8,
                 colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=1.0,
                 random_state=42):
        self.num_leaves       = num_leaves
        self.max_depth        = max_depth
        self.learning_rate    = learning_rate
        self.n_estimators     = n_estimators
        self.min_data_in_leaf = min_data_in_leaf
        self.subsample        = subsample
        self.colsample_bytree = colsample_bytree
        self.reg_alpha        = reg_alpha
        self.reg_lambda       = reg_lambda
        self.random_state     = random_state

    def fit(self, X, y, **fit_params):  # pragma: no cover – not called at serve-time
        self.model_ = lgb.LGBMRegressor(
            objective="regression", metric="rmse",
            num_leaves=self.num_leaves, max_depth=self.max_depth,
            learning_rate=self.learning_rate, n_estimators=self.n_estimators,
            min_data_in_leaf=self.min_data_in_leaf,
            subsample=self.subsample, colsample_bytree=self.colsample_bytree,
            reg_alpha=self.reg_alpha, reg_lambda=self.reg_lambda,
            random_state=self.random_state, verbose=-1,
        )
        self.model_.fit(X, y, **fit_params)
        return self

    def predict(self, X) -> np.ndarray:
        # Pass DataFrame directly so LGBMRegressor receives the feature names
        # it was fitted with, avoiding the sklearn "no valid feature names" warning.
        # Only fall back to ndarray for non-DataFrame inputs.
        if not isinstance(X, pd.DataFrame):
            X = pd.DataFrame(np.asarray(X), columns=getattr(self.model_, "feature_name_", None))
        return self.model_.predict(X)


# ── Thin wrapper so raw lgb.Booster (txt format) exposes the same
#    .predict(DataFrame) → np.ndarray interface as LGBMWrapper. ────────────
class _BoosterWrapper:
    """Wraps a raw lgb.Booster so it accepts a pandas DataFrame and returns
    predictions the same way LGBMWrapper does."""
    def __init__(self, booster: lgb.Booster):
        self._booster = booster

    def predict(self, X) -> np.ndarray:
        # lgb.Booster.predict expects a 2-D numeric array; convert DataFrame
        arr = X.values if hasattr(X, "values") else np.asarray(X)
        return self._booster.predict(arr)


def _load_lgb_models():
    """Load the v5.0 LightGBM models.

    Load order:
      1. pkl  — LGBMWrapper objects serialised by model.ipynb (fastest, preferred)
      2. txt  — native lgb.Booster text format (fallback; wrapped in _BoosterWrapper)
    """
    result = {"cwr": None, "iwr": None}

    # ── Primary path: pickled LGBMWrapper objects ─────────────────────────
    pkl_cwr = MODEL_DIR / "lgb_cwr_v5.pkl"
    pkl_iwr = MODEL_DIR / "lgb_iwr_v5.pkl"
    if pkl_cwr.exists() and pkl_iwr.exists():
        try:
            with open(pkl_cwr, "rb") as f:
                result["cwr"] = pickle.load(f)
            with open(pkl_iwr, "rb") as f:
                result["iwr"] = pickle.load(f)
            logger.info("✓ Loaded LightGBM v5.0 models (pkl format)")
            return result
        except Exception as e:
            logger.warning(f"pkl load failed ({e}), trying txt format …")
            result = {"cwr": None, "iwr": None}  # reset before txt attempt

    

    return result

_LGB_MODELS = _load_lgb_models()

# ═══════════════════════════════════════════════════════════════════════════
# SEASONAL CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════

SEASON_START_MONTH = 11
SEASON_END_MONTH = 4
SEASON_MONTHS = {11, 12, 1, 2, 3, 4}
MAX_SEASONS = 5
HISTORY_DATES = 191
FORECAST_DAYS = 15
NODATA = -9999.0

PARAMS = ["savi", "kc", "cwr", "iwr", "etc"]
FC_PARAMS = ["cwr", "iwr"]
POINT_FORECAST_PARAMS = ["cwr", "iwr"]
FORECAST_WINDOWS = ["5day", "10day", "15day"]
WINDOW_DAYS = {"5day": 5, "10day": 10, "15day": 15}

_VALID = {
    "savi": (-1.0, 1.0),
    "kc": (KC_MIN, KC_MAX),
    "cwr": (CWR_MIN, CWR_MAX),
    "iwr": (0.0, CWR_MAX),
    "etc": (0.0, 15.0),
}

_VALID_FC = {
    "kc": (KC_MIN, KC_MAX),
    "etc": (0.0, 15.0),
    "cwr": (0.0, 200.0),
    "iwr": (0.0, 200.0),
}

_SRC = {
    "savi": (DIRECTORIES["processed"]["savi"], "savi_*.tif"),
    "kc": (DIRECTORIES["processed"]["kc"], "kc_*.tif"),
    "cwr": (DIRECTORIES["processed"]["cwr"], "cwr_*.tif"),
    "iwr": (DIRECTORIES["processed"]["iwr"], "iwr_*.tif"),
    "etc": (DIRECTORIES["processed"]["ETc"], "etc_*.tif"),
}

EXPORT_DIR = DIRECTORIES["export"]["geoserver"]
HISTORY_DIR = EXPORT_DIR / "history"
FORECAST_DIR = EXPORT_DIR / "forecast"

for _param in PARAMS:
    (HISTORY_DIR / _param).mkdir(parents=True, exist_ok=True)
for _param in FC_PARAMS:
    (FORECAST_DIR / _param).mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════
# SEASONAL HELPERS (unchanged)
# ═══════════════════════════════════════════════════════════════════════════

def get_season_id(date: datetime) -> str:
    m, y = date.month, date.year
    if m >= SEASON_START_MONTH:
        return f"{y}-{str(y + 1)[-2:]}"
    elif m <= SEASON_END_MONTH:
        return f"{y - 1}-{str(y)[-2:]}"
    else:
        return None

def is_in_season(date: datetime) -> bool:
    return date.month in SEASON_MONTHS

def get_season_start(season_id: str) -> datetime:
    start_year = int(season_id.split("-")[0])
    return datetime(start_year, SEASON_START_MONTH, 1)

def get_allowed_season_ids() -> List[str]:
    today = datetime.utcnow()
    current = get_season_id(today)
    if current is None:
        anchor_year = today.year - 1
        current = f"{anchor_year}-{str(anchor_year + 1)[-2:]}"
    anchor_start_year = int(current.split("-")[0])
    seasons = []
    for i in range(MAX_SEASONS):
        y = anchor_start_year - i
        seasons.append(f"{y}-{str(y + 1)[-2:]}")
    return seasons

def filter_to_allowed_seasons(dates: List[datetime]) -> List[datetime]:
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
# SLOT HELPERS (unchanged)
# ═══════════════════════════════════════════════════════════════════════════

def slot_for_index(idx: int) -> str:
    return "today" if idx == 0 else str(idx)

def _make_slots(n: int) -> List[str]:
    return ["today"] + [str(i) for i in range(1, n)]


# ═══════════════════════════════════════════════════════════════════════════
# PATH HELPERS (unchanged)
# ═══════════════════════════════════════════════════════════════════════════

def history_path(param: str, slot: str) -> Path:
    return HISTORY_DIR / param / f"{param}_{slot}.tif"

def forecast_path(param: str, slot: str, window: str) -> Path:
    return FORECAST_DIR / param / f"{param}_{slot}_{window}.tif"


# ═══════════════════════════════════════════════════════════════════════════
# DATA LOADING HELPERS (unchanged)
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
    core_params = ["savi", "kc", "etc", "cwr", "iwr"]
    date_sets = []
    for param in core_params:
        src_dir, pattern = _SRC[param]
        dates = {d for d, _ in _dated_files(src_dir, pattern)}
        if not dates:
            logger.warning(f"No {param} files in {src_dir}")
            return []
        date_sets.append(dates)
    complete = set.intersection(*date_sets)
    seasonal = filter_to_allowed_seasons(sorted(complete, reverse=True))
    return seasonal[:n]

def _read_mean(path: Path) -> Optional[float]:
    if not path.exists():
        return None
    try:
        with rasterio.open(path) as src:
            data = src.read(1).astype(np.float64)
            nd = float(src.nodata) if src.nodata else float(NODATA)
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
            nd = float(src.nodata) if src.nodata is not None else float(NODATA)
            data[data == np.float64(nd)] = np.nan
            data[data == np.float64(NODATA)] = np.nan
        return data
    except Exception as e:
        logger.error(f"[load] {p.name}: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# WHEAT MASK (unchanged)
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
                "crs": src.crs,
                "transform": src.transform,
                "width": src.width,
                "height": src.height,
                "mask_bool": (raw > 0),
            }
        logger.info(f"Wheat mask: {_WHEAT_MASK_CACHE['width']}×{_WHEAT_MASK_CACHE['height']} | "
                   f"wheat pixels = {_WHEAT_MASK_CACHE['mask_bool'].sum():,}")
    except Exception as e:
        logger.error(f"Failed to load wheat_mask: {e}")
    return _WHEAT_MASK_CACHE


# ═══════════════════════════════════════════════════════════════════════════
# SEASONAL PURGE (unchanged)
# ═══════════════════════════════════════════════════════════════════════════

def purge_out_of_season_rasters() -> int:
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
        valid_forecast = {f"{param}_{s}_{w}.tif" for s in valid_slots for w in FORECAST_WINDOWS}
        for f in (FORECAST_DIR / param).glob("*.tif"):
            if f.name not in valid_forecast:
                f.unlink()
                logger.debug(f"[cleanup] removed stale forecast file: {f.name}")


# ═══════════════════════════════════════════════════════════════════════════
# RASTER I/O (unchanged)
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
            data = src.read(1).astype(np.float64)
            src_nd = src.nodata
            src_crs = src.crs
            src_trans = src.transform
        if src_nd is not None:
            data[data == np.float64(src_nd)] = np.nan
        data[data == np.float64(-9999.0)] = np.nan
        data[data == np.float64(-999.0)] = np.nan
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
        out = np.where(np.isnan(dst), float(NODATA), dst).astype(np.float64)
        profile = {
            "driver": "GTiff",
            "dtype": rasterio.float64,
            "count": 1,
            "crs": grid["crs"],
            "transform": grid["transform"],
            "width": grid["width"],
            "height": grid["height"],
            "nodata": float(NODATA),
            "compress": "lzw",
            "tiled": True,
            "blockxsize": 256,
            "blockysize": 256,
        }
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dst_path, "w", **profile) as f:
            f.write(out, 1)
            mean_val = float(np.nanmean(dst)) if np.any(~np.isnan(dst)) else None
            tags = {
                "parameter": param,
                "acquisition_date": date.strftime("%Y-%m-%d"),
                "season": get_season_id(date) or "",
                "mean": str(round(mean_val, 4)) if mean_val is not None else "",
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
# STEP A — HISTORY RASTERS (unchanged)
# ═══════════════════════════════════════════════════════════════════════════

def generate_history_rasters() -> int:
    dates = _latest_n_complete_dates(HISTORY_DATES)
    if not dates:
        logger.error("[history] No complete Sentinel dates in allowed seasons")
        return 0
    logger.info(f"[history] {len(dates)} seasonal dates: "
               f"{dates[-1].date()} → {dates[0].date()} "
               f"| seasons={sorted(set(get_season_id(d) for d in dates))}")
    total = 0
    for param, (src_dir, pattern) in _SRC.items():
        src_by_date = {d: p for d, p in _dated_files(src_dir, pattern)}
        for idx, date in enumerate(dates):
            src_path = src_by_date.get(date)
            if src_path is None:
                if param != "etc":
                    logger.warning(f"[history] {param} missing for {date.date()}")
                continue
            slot = slot_for_index(idx)
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
# STEP B — FORECASTING USING LIGHTGBM v5.0
# ═══════════════════════════════════════════════════════════════════════════

# Climatology for forecast features
_clim_cache = {}

def _get_clim_series():
    """Load climatology series from the training data."""
    global _clim_cache
    if _clim_cache:
        return _clim_cache
    
    # Load the enriched series from the model notebook
    enriched_path = Path("enriched_series.parquet")
    if enriched_path.exists():
        df = pd.read_parquet(enriched_path)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        
        # Build calendar features
        df["doy"] = df["date"].dt.dayofyear
        df["rabi_doy"] = df["date"].apply(lambda d: (
            (d - pd.Timestamp(d.year if d.month >= 11 else d.year - 1, 11, 1)).days + 1
            if d.month >= 11 or d.month <= 4 else None
        ))
        
        _clim_cache["pet"]  = df.groupby("doy")["pet_mean"].mean()
        _clim_cache["rain"] = df.groupby("doy")["rain_mean"].mean()
        _clim_cache["kc"]   = df.groupby("doy")["kc_mean"].mean()
        _clim_cache["cwr"]  = df.groupby("doy")["cwr_mean"].mean()
        _clim_cache["iwr"]  = df.groupby("doy")["iwr_mean"].mean()
        _clim_cache["savi"] = (
            df.groupby("rabi_doy")["savi_mean"].mean()
            .reindex(range(1, 181)).interpolate().bfill().ffill()
        )
        logger.info("✓ Climatology loaded for LightGBM forecasting")
    else:
        logger.warning("enriched_series.parquet not found. Using fallback climatology.")
        _clim_cache["pet"]  = pd.Series()
        _clim_cache["rain"] = pd.Series()
        _clim_cache["kc"]   = pd.Series()
        _clim_cache["cwr"]  = pd.Series()
        _clim_cache["iwr"]  = pd.Series()
        _clim_cache["savi"] = pd.Series()
    
    return _clim_cache

def _effective_rainfall_daily(rain_mm: float) -> float:
    """Exponential effective-rainfall cap — must match model.ipynb exactly.
    effective_rain = cap * (1 - exp(-rain / cap)),  cap = 25 mm."""
    cap = 25.0
    rain_mm = max(float(rain_mm), 0.0)
    return cap * (1.0 - np.exp(-rain_mm / cap))

def _get_clim_value(series: pd.Series, key: int, default: float = 0.0) -> float:
    """Get climatology value for a given key (doy or rabi_doy)."""
    if series is None or len(series) == 0:
        return default
    try:
        val = series.get(key, default)
        return float(val) if not pd.isna(val) else default
    except:
        return default

def _project_savi(last_savi: float, rabi_doy_now: int, step: int) -> float:
    """Project SAVI using climatology."""
    clim = _get_clim_series()
    savi_clim = clim.get("savi", pd.Series())
    if len(savi_clim) == 0:
        return last_savi
    
    doy_now = min(max(rabi_doy_now, 1), 180)
    doy_future = min(max(rabi_doy_now + step, 1), 180)
    delta = _get_clim_value(savi_clim, doy_future, last_savi) - _get_clim_value(savi_clim, doy_now, last_savi)
    return last_savi + delta

def _build_forecast_row(
    step: int,
    anchor_row: Dict,
    lag_buf_cwr: List[float],
    lag_buf_iwr: List[float],
    lag_buf_pet: List[float],
    lag_buf_rain: List[float],
    lag_buf_savi: List[float],
    anchor_stats: Dict,
) -> Dict:
    """Build feature row for LightGBM forecast step."""
    clim = _get_clim_series()
    
    future_date = pd.Timestamp(anchor_row["date"]) + pd.Timedelta(days=step)
    doy = future_date.dayofyear
    rabi_doy_step = int(anchor_row["rabi_doy"]) + step
    
    savi_f = _project_savi(float(anchor_row["savi_mean"]), int(anchor_row["rabi_doy"]), step)
    pet_f = _get_clim_value(clim.get("pet", pd.Series()), doy, float(anchor_row.get("pet_mean", 4.0)))
    rain_f = _get_clim_value(clim.get("rain", pd.Series()), doy, 0.0)
    kc_f = _get_clim_value(clim.get("kc", pd.Series()), doy, 0.8)
    rain_eff_f = _effective_rainfall_daily(rain_f)
    
    # Get metadata stats
    def _get_meta(band: str, stat: str, default: float = 0.0) -> float:
        return float(anchor_stats.get(band, {}).get(stat, default))
    
    row = {
        "savi_mean": savi_f,
        "kc_mean": kc_f,
        "pet_mean": pet_f,
        "rain_mean": rain_f,
        "cwr_mean": lag_buf_cwr[-1] if lag_buf_cwr else 0.0,
        "iwr_mean": lag_buf_iwr[-1] if lag_buf_iwr else 0.0,
        "rain_eff": rain_eff_f,
    }
    
    # Add metadata stats
    for band in ["savi", "kc", "cwr", "iwr", "pet", "rain"]:
        for stat in ["min", "max", "std", "range", "cv"]:
            row[f"{band}_{stat}"] = _get_meta(band, stat, 0.0)
    
    # Temporal features
    row["rabi_doy"] = rabi_doy_step
    row["month"] = future_date.month
    row["season_id"] = int(anchor_row.get("season_id", 0))
    row["sin1_doy"] = np.sin(2 * np.pi * doy / 365.25)
    row["cos1_doy"] = np.cos(2 * np.pi * doy / 365.25)
    row["sin2_doy"] = np.sin(4 * np.pi * doy / 365.25)
    row["cos2_doy"] = np.cos(4 * np.pi * doy / 365.25)
    
    # Lag features
    def _safe_lag(buf: List[float], n: int, default: float = 0.0) -> float:
        return buf[-n] if len(buf) >= n else default
    
    row["cwr_lag1"] = _safe_lag(lag_buf_cwr, 1)
    row["cwr_lag3"] = _safe_lag(lag_buf_cwr, 3)
    row["cwr_lag5"] = _safe_lag(lag_buf_cwr, 5)
    row["cwr_lag7"] = _safe_lag(lag_buf_cwr, 7)
    row["iwr_lag1"] = _safe_lag(lag_buf_iwr, 1)
    row["iwr_lag3"] = _safe_lag(lag_buf_iwr, 3)
    row["iwr_lag5"] = _safe_lag(lag_buf_iwr, 5)
    row["iwr_lag7"] = _safe_lag(lag_buf_iwr, 7)
    row["pet_lag1"] = _safe_lag(lag_buf_pet, 1)
    row["pet_lag3"] = _safe_lag(lag_buf_pet, 3)
    row["pet_lag7"] = _safe_lag(lag_buf_pet, 7)
    row["rain_lag1"] = _safe_lag(lag_buf_rain, 1)
    row["rain_lag3"] = _safe_lag(lag_buf_rain, 3)
    row["rain_lag7"] = _safe_lag(lag_buf_rain, 7)
    row["savi_lag1"] = _safe_lag(lag_buf_savi, 1)
    row["savi_lag3"] = _safe_lag(lag_buf_savi, 3)
    row["savi_lag7"] = _safe_lag(lag_buf_savi, 7)
    
    # Rolling features
    def _safe_mean(buf: List[float], n: int, default: float = 0.0) -> float:
        return np.mean(buf[-n:]) if len(buf) >= n else default
    
    def _safe_std(buf: List[float], n: int, default: float = 0.0) -> float:
        return np.std(buf[-n:], ddof=1) if len(buf) >= n else default
    
    row["cwr_rmean3"] = _safe_mean(lag_buf_cwr, 3)
    row["cwr_rmean7"] = _safe_mean(lag_buf_cwr, 7)
    row["cwr_rstd7"] = _safe_std(lag_buf_cwr, 7)
    row["iwr_rmean3"] = _safe_mean(lag_buf_iwr, 3)
    row["iwr_rmean7"] = _safe_mean(lag_buf_iwr, 7)
    row["iwr_rstd7"] = _safe_std(lag_buf_iwr, 7)
    row["pet_rmean3"] = _safe_mean(lag_buf_pet, 3)
    row["pet_rmean7"] = _safe_mean(lag_buf_pet, 7)
    row["pet_rstd7"] = _safe_std(lag_buf_pet, 7)
    row["savi_rmean3"] = _safe_mean(lag_buf_savi, 3)
    row["savi_rmean7"] = _safe_mean(lag_buf_savi, 7)
    row["savi_rstd7"] = _safe_std(lag_buf_savi, 7)
    
    # Cumulative rainfall
    def _eff_rain(vals: List[float]) -> float:
        return sum(_effective_rainfall_daily(v) for v in vals)
    
    row["rain_cumsum3"] = _eff_rain(lag_buf_rain[-3:]) if len(lag_buf_rain) >= 3 else 0.0
    row["rain_cumsum7"] = _eff_rain(lag_buf_rain[-7:]) if len(lag_buf_rain) >= 7 else 0.0
    
    # Metadata lags
    row["savi_std_lag1"] = _get_meta("savi", "std", 0.0)
    row["savi_std_lag3"] = _get_meta("savi", "std", 0.0)
    row["cwr_std_lag1"] = _get_meta("cwr", "std", 0.0)
    row["cwr_std_lag3"] = _get_meta("cwr", "std", 0.0)
    row["rain_std_lag1"] = _get_meta("rain", "std", 0.0)
    row["rain_std_lag3"] = _get_meta("rain", "std", 0.0)
    
    # Interactions
    row["pet_x_savi"] = pet_f * savi_f
    row["kc_x_pet"] = kc_f * pet_f
    row["rain_deficit"] = max(pet_f - rain_f, 0.0)
    
    return row

def generate_lgb_forecast_for_date(
    reference_date: datetime,
    days: int = FORECAST_DAYS,
) -> Dict[str, pd.Series]:
    """
    Generate forecast using LightGBM v5.0 model.
    
    Returns:
        Dict with forecast series for cwr and iwr
    """
    if _LGB_MODELS["cwr"] is None or _LGB_MODELS["iwr"] is None:
        logger.error("LightGBM models not loaded. Falling back to SARIMAX.")
        return generate_forecast_for_date(reference_date, days)
    
    # Get historical data for feature engineering
    dates = _latest_n_complete_dates(HISTORY_DATES)
    if not dates or len(dates) < 7:
        logger.error("Not enough historical dates for forecasting")
        return {}
    
    # Locate reference_date's own position in the (most-recent-first) `dates`
    # list, so each slot anchors on its own date/raster instead of always
    # collapsing onto the most recent one (dates[0] / slot "today").
    ref_idx = None
    for i, d in enumerate(dates):
        if d.date() == reference_date.date():
            ref_idx = i
            break
    if ref_idx is None:
        logger.warning(
            f"[LGB forecast] reference_date {reference_date.date()} not found in "
            f"history window ({dates[-1].date()}..{dates[0].date()}); "
            f"falling back to most recent slot for anchoring"
        )
        ref_idx = 0
    anchor_slot = slot_for_index(ref_idx)
    
    # Build anchor row from the slot's own date
    anchor_date = dates[ref_idx]
    anchor_row = {"date": pd.Timestamp(anchor_date)}
    
    # Gather all needed values from history rasters
    for param in ["savi", "kc", "cwr", "iwr", "pet", "rain"]:
        val = _reference_mean(param, anchor_date, 0.0)
        anchor_row[f"{param}_mean"] = val if val is not None else 0.0
    
    # Get metadata stats from the raster for THIS slot (was hardcoded "today",
    # which made every slot read the same raster).
    anchor_stats = {}
    for band in ["savi", "kc", "cwr", "iwr", "pet", "rain"]:
        path = history_path(band, anchor_slot)
        if path.exists():
            try:
                with rasterio.open(path) as src:
                    data = src.read(1).astype(np.float64)
                    nd = float(src.nodata) if src.nodata else float(NODATA)
                    data[data == np.float64(nd)] = np.nan
                    valid = data[~np.isnan(data)]
                    anchor_stats[band] = {
                        "mean": float(np.mean(valid)) if len(valid) > 0 else 0.0,
                        "min": float(np.min(valid)) if len(valid) > 0 else 0.0,
                        "max": float(np.max(valid)) if len(valid) > 0 else 0.0,
                        "std": float(np.std(valid, ddof=1)) if len(valid) > 1 else 0.0,
                        "range": float(np.max(valid) - np.min(valid)) if len(valid) > 0 else 0.0,
                        "cv": float(np.std(valid, ddof=1) / (np.mean(valid) + 1e-9)) if len(valid) > 1 else 0.0,
                    }
            except Exception as e:
                logger.warning(f"Failed to read metadata for {band}: {e}")
                anchor_stats[band] = {"mean": 0.0, "min": 0.0, "max": 0.0, "std": 0.0, "range": 0.0, "cv": 0.0}
        else:
            anchor_stats[band] = {"mean": 0.0, "min": 0.0, "max": 0.0, "std": 0.0, "range": 0.0, "cv": 0.0}
    
    # Get season info
    season_start_y = anchor_date.year if anchor_date.month >= SEASON_START_MONTH else anchor_date.year - 1
    anchor_row["rabi_doy"] = (
        anchor_date - datetime(season_start_y, SEASON_START_MONTH, 1)
    ).days + 1
    # season_id: 0=oldest allowed season, MAX_SEASONS-1=newest (matches training)
    allowed_seasons = get_allowed_season_ids()  # newest first
    anchor_season = get_season_id(anchor_date)
    try:
        anchor_row["season_id"] = list(reversed(allowed_seasons)).index(anchor_season)
    except ValueError:
        anchor_row["season_id"] = len(allowed_seasons) - 1

    # Initialize lag buffers from history.
    # pet and rain are raw INSAT rasters not registered in _SRC, so
    # _reference_mean() returns None for them. Fall back to climatology
    # in that case so the buffers are never all-zero.
    clim_for_buf = _get_clim_series()

    def _get_historical_series(param: str, n: int = 7) -> List[float]:
        vals = []
        for i in range(ref_idx, min(ref_idx + n, len(dates))):
            val = _reference_mean(param, dates[i], None)
            if val is None:
                # pet / rain not in _SRC — use climatology for that doy
                doy = dates[i].timetuple().tm_yday
                val = _get_clim_value(clim_for_buf.get(param, pd.Series()), doy, 0.0)
            vals.append(float(val))
        # Pad to n if history is short (oldest first, newest last)
        while len(vals) < n:
            vals.insert(0, vals[0] if vals else 0.0)
        return vals[-n:]
    
    lag_buf_cwr = _get_historical_series("cwr", 7)
    lag_buf_iwr = _get_historical_series("iwr", 7)
    lag_buf_pet = _get_historical_series("pet", 7)
    lag_buf_rain = _get_historical_series("rain", 7)
    lag_buf_savi = _get_historical_series("savi", 7)
    
    # Generate forecast iteratively
    future_dates = pd.date_range(start=reference_date + timedelta(days=1), periods=days, freq="D")
    cwr_forecast = []
    iwr_forecast = []
    
    for step in range(1, days + 1):
        row_dict = _build_forecast_row(
            step, anchor_row, lag_buf_cwr, lag_buf_iwr,
            lag_buf_pet, lag_buf_rain, lag_buf_savi, anchor_stats
        )
        row_df = pd.DataFrame([row_dict])
        
        # Predict using LightGBM
        # Ensure all expected feature columns exist (fill missing with 0).
        for col in FEATURES_CWR + FEATURES_IWR:
            if col not in row_df.columns:
                row_df[col] = 0.0
        try:
            pred_cwr = float(_LGB_MODELS["cwr"].predict(row_df[FEATURES_CWR].fillna(0))[0])
            pred_cwr = max(0.0, pred_cwr)

            pred_iwr = float(_LGB_MODELS["iwr"].predict(row_df[FEATURES_IWR].fillna(0))[0])
            pred_iwr = max(0.0, pred_iwr)
        except Exception as e:
            logger.error(f"LightGBM prediction failed at step {step}: {e}")
            clim = _get_clim_series()
            pred_cwr = _get_clim_value(clim.get("cwr", pd.Series()), future_dates[step-1].dayofyear, 2.0)
            pred_iwr = _get_clim_value(clim.get("iwr", pd.Series()), future_dates[step-1].dayofyear, 1.0)
        
        cwr_forecast.append(pred_cwr)
        iwr_forecast.append(pred_iwr)
        
        # Update lag buffers
        lag_buf_cwr = lag_buf_cwr[1:] + [pred_cwr]
        lag_buf_iwr = lag_buf_iwr[1:] + [pred_iwr]
        lag_buf_pet = lag_buf_pet[1:] + [_get_clim_value(_get_clim_series().get("pet", pd.Series()), future_dates[step-1].dayofyear, lag_buf_pet[-1])]
        lag_buf_rain = lag_buf_rain[1:] + [_get_clim_value(_get_clim_series().get("rain", pd.Series()), future_dates[step-1].dayofyear, 0.0)]
        lag_buf_savi = lag_buf_savi[1:] + [_project_savi(float(anchor_row["savi_mean"]), int(anchor_row["rabi_doy"]), step)]
    
    forecasts = {
        "cwr": pd.Series(cwr_forecast, index=future_dates, name="cwr"),
        "iwr": pd.Series(iwr_forecast, index=future_dates, name="iwr"),
    }
    
    logger.info(f"[LGB forecast] Generated for {reference_date.date()}: "
               f"CWR_mean={forecasts['cwr'].mean():.2f}, "
               f"IWR_mean={forecasts['iwr'].mean():.2f}")
    
    return forecasts

# Keep the original function for backward compatibility
def generate_forecast_for_date(
    reference_date: datetime,
    days: int = FORECAST_DAYS,
) -> Dict[str, pd.Series]:
    """
    Generate forecast using either LightGBM or SARIMAX.
    """
    # Use LightGBM if available
    if _LGB_MODELS["cwr"] is not None and _LGB_MODELS["iwr"] is not None:
        return generate_lgb_forecast_for_date(reference_date, days)
    
    # Fallback to original SARIMAX method
    logger.warning("LightGBM models not available. Using SARIMAX fallback.")
    forecasts = {}
    future_dates = pd.date_range(start=reference_date + timedelta(days=1), periods=days, freq="D")
    
   
    
    return {}


# ═══════════════════════════════════════════════════════════════════════════
# FORECAST RASTER CREATION (unchanged)
# ═══════════════════════════════════════════════════════════════════════════

def _forecast_raster_is_fresh(param: str, slot: str, window: str, date: datetime) -> bool:
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
    date: datetime,
) -> bool:
    if _forecast_raster_is_fresh(param, slot, window, date):
        logger.debug(f"[forecast] skip {param} {slot} {window} — already fresh")
        return True
    
    try:
        WINDOW_SLICES = {"5day": (0, 5), "10day": (0, 10), "15day": (0, 15)}
        start_idx, end_idx = WINDOW_SLICES[window]
        window_days = end_idx - start_idx

        # ── Derive forecast scalar and labels BEFORE opening raster so that
        #    any error here produces a clear message rather than a NameError
        #    when variables are referenced later in dst.update_tags(). ──────
        window_forecast = forecast_series.iloc[start_idx:end_idx]

        if param in ["cwr", "iwr"]:
            forecast_val = float(window_forecast.sum())
            agg_label = "total"
            unit_label = "mm"
            units_tag = "mm_total"
        else:
            forecast_val = float(window_forecast.mean()) if len(window_forecast) > 0 else 0.0
            agg_label = "mean"
            if param == "etc":
                unit_label = "mm/day"
                units_tag = "mm_per_day"
            elif param == "kc":
                unit_label = ""
                units_tag = "dimensionless"
            else:
                unit_label = ""
                units_tag = ""

        # Guard: empty window means the anchor date has no forecast horizon
        # (e.g. end-of-season slot where all future dates are off-season).
        if len(window_forecast) == 0:
            logger.warning(
                f"[forecast] empty window_forecast for {param} {slot} {window} "
                f"(forecast_series has {len(forecast_series)} rows, "
                f"slice [{start_idx}:{end_idx}]); skipping raster write"
            )
            return False

        stage_info = get_wheat_stage_info(window_forecast.index[0].to_pydatetime())

        with rasterio.open(template_raster) as src:
            template_data = src.read(1).astype(np.float64)
            nodata = src.nodata if src.nodata is not None else NODATA
            template_data = np.where(template_data == nodata, np.nan, template_data)
            profile = src.profile.copy()

        valid = ~np.isnan(template_data)
        if not valid.any():
            logger.warning(f"No valid pixels in template for {param} {slot}")
            return False
        
        template_mean = float(np.nanmean(template_data[valid]))
        if template_mean > 0:
            scale_factor = forecast_val / template_mean
            forecast_array = np.where(valid, template_data * scale_factor, np.nan)
        else:
            forecast_array = np.where(valid, forecast_val, np.nan)
        
        vmin, vmax = _VALID_FC.get(param, _VALID.get(param, (-1e9, 1e9)))
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
                acquisition_date=date.strftime("%Y-%m-%d"),
                reference_date=date.strftime("%Y-%m-%d"),
                forecast_mean=str(round(forecast_val, 4)),
                template_mean=str(round(template_mean, 4)),
                crop_stage=stage_info["stage"],
                das=str(stage_info["das"]),
                kc_fao56=str(round(stage_info["kc_fao56"], 4)),
                units=units_tag,
                aggregation="sum" if param in ["cwr", "iwr"] else "mean",
                window_days=str(window_days),
                model="LightGBM-v5.0",
                generated_by="irrigation_monitoring_v11.0",
            )
        
        logger.info(f"Created {param} forecast for {slot} {window}: "
                   f"{agg_label}={forecast_val:.4f} {unit_label}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create {param} forecast for {slot}_{window}: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
# MASTER PIPELINE (updated for LightGBM)
# ═══════════════════════════════════════════════════════════════════════════

def generate_all_forecast_rasters() -> int:
    dates = _latest_n_complete_dates(HISTORY_DATES)
    if not dates:
        logger.error("[forecast] No Sentinel dates available")
        return 0
    
    total = 0
    n = len(dates)
    slots = _make_slots(n)
    
    # Load climatology
    _get_clim_series()
    
    for idx, date in enumerate(dates):
        slot = slots[idx]
        
        # Check if all forecasts are fresh
        params_with_template = [p for p in FC_PARAMS if history_path(p, slot).exists()]
        all_fresh = bool(params_with_template) and all(
            _forecast_raster_is_fresh(p, slot, w, date)
            for p in params_with_template
            for w in FORECAST_WINDOWS
        )
        if all_fresh:
            n_skip = len(params_with_template) * len(FORECAST_WINDOWS)
            total += n_skip
            logger.debug(f"[forecast] slot={slot} ({date.date()}): "
                        f"all {n_skip} rasters fresh — skipping")
            continue
        
        # Generate forecast using LightGBM or fallback
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
                        date,
                    ):
                        n_rasters += 1
                        total += 1
        
        logger.info(f"[forecast] slot={slot} ({date.date()}): {n_rasters} files written")
    
    expected_total = n * len(FC_PARAMS) * len(FORECAST_WINDOWS)
    logger.info(f"[forecast] ALL: {total} / {expected_total}")
    return total


# ═══════════════════════════════════════════════════════════════════════════
# STEP C — PUSH TO GEOSERVER (unchanged)
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
                store_ok = gs.create_coverage_store_if_not_exists(store, p)
                file_ok = gs.update_coverage_store_file(store, p)
                configure_ok = gs.configure_layer(layer_name=store, store_name=store)
                style_ok = gs.assign_style(store, style)
                if store_ok and file_ok and configure_ok and style_ok:
                    logger.info(f"[geoserver] ✅ Layer ready: {store}")
                else:
                    logger.warning(f"[geoserver] ⚠ Partial: {store}")
            except Exception as e:
                logger.warning(f"[geoserver] {store}: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# MASTER RUN FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

def run_pipeline() -> Dict:
    logger.info("═" * 65)
    logger.info("run_pipeline() START — v11.0 (LightGBM v5.0)")
    logger.info("═" * 65)
    
    cleanup_old_rasters()
    _get_wheat_mask()
    
    logger.info("── A: History rasters ──")
    h_total = generate_history_rasters()
    
    logger.info("── B/C: Forecast + rasters (LightGBM v5.0) ──")
    f_total = generate_all_forecast_rasters()
    
    logger.info("── D: GeoServer ──")
    push_to_geoserver()
    clear_raster_pixel_cache()
    
    dates = _latest_n_complete_dates()
    n = len(dates)
    summary = {
        "slots": {slot_for_index(i): str(d.date()) for i, d in enumerate(dates)},
        "n_dates": n,
        "seasons": sorted(set(get_season_id(d) for d in dates)),
        "history_rasters": h_total,
        "forecast_rasters": f_total,
        "grand_total": h_total + f_total,
        "units": "mm_per_day",
        "forecast_model": "LightGBM-v5.0 (raster-metadata + TimeSeriesSplit CV)",
        "model_version": "v11.0",
    }
    logger.info(f"DONE: {summary}")
    return summary


# ═══════════════════════════════════════════════════════════════════════════
# SCHEDULER CALLBACKS (unchanged)
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
# FastAPI APP (unchanged except version)
# ═══════════════════════════════════════════════════════════════════════════

from graph import router as graph_router

app = FastAPI(
    title="Wheat Irrigation Monitoring System",
    version="11.0.0",
    description=(
        "v11.0 — LightGBM v5.0 forecasting with raster-metadata features.\n\n"
        "  • CWR and IWR forecasted using LightGBM with TimeSeriesSplit CV\n"
        "  • Raster metadata (min, max, std, range, cv) used as features\n"
        "  • PET and Kc climatology for feature engineering\n"
        "  • Seasonal cap (5 seasons Nov–Apr)\n"
        "  • ETc layer included"
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


# ═══════════════════════════════════════════════════════════════════════════
# PIXEL TIMESERIES (unchanged)
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


# ═══════════════════════════════════════════════════════════════════════════
# API ENDPOINTS (most unchanged)
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/pixel-timeseries")
def get_pixel_timeseries(
    lat: float = Query(..., description="Latitude of the clicked point"),
    lon: float = Query(..., description="Longitude of the clicked point"),
    request_group: str = Query("default", description="Client request group used to isolate stale-read cancellation"),
    request_id: int = Query(0, description="Client request id used to supersede stale pixel reads"),
):
    _register_pixel_request(request_group, request_id)
    pixel = _pixel_from_latlon(lat, lon)
    pixel_id: str = pixel["pixel_id"]
    logger.debug(f"[pixel-ts] query=({lat:.5f},{lon:.5f}) → pixel={pixel_id} "
                f"center=({pixel['latitude']:.5f},{pixel['longitude']:.5f}) "
                f"native=({pixel['native_x']:.2f},{pixel['native_y']:.2f})")
    
    try:
        result = _pixel_timeseries(pixel, request_group=request_group, request_id=request_id)
    except RasterLookupCancelled as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    
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
    if east < west: east, west = west, east
    if (north - south) < 0.01: north += 0.05; south -= 0.05
    if (east - west) < 0.01: east += 0.05; west -= 0.05
    return {
        "name": STUDY_AREA.get("name", "Udham Singh Nagar"),
        "state": STUDY_AREA.get("state", "Uttarakhand"),
        "crs": STUDY_AREA.get("crs", "EPSG:4326"),
        "source": STUDY_AREA.get("boundary_source", "static-fallback"),
        "bounds": {
            "north": round(north, 6), "south": round(south, 6),
            "east": round(east, 6), "west": round(west, 6),
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
    dates = _latest_n_complete_dates()
    if not dates:
        raise HTTPException(status_code=404, detail="No processed Sentinel scenes found")
    
    result = []
    n = len(dates)
    
    for idx, d in enumerate(dates):
        slot = slot_for_index(idx)
        obs_means = {}
        fc_means = {}
        
        for param in PARAMS:
            path = history_path(param, slot)
            if path.exists():
                with rasterio.open(path) as src:
                    tags = src.tags()
                mean_str = tags.get("mean")
                obs_means[param] = float(mean_str) if mean_str and mean_str not in ("None", "nan", "") else None
            else:
                obs_means[param] = None
            
            fc_means[param] = {}
            if param in FC_PARAMS:
                for w in FORECAST_WINDOWS:
                    fpath = forecast_path(param, slot, w)
                    if fpath.exists():
                        with rasterio.open(fpath) as src:
                            tags = src.tags()
                        fc_str = tags.get("forecast_mean")
                        fc_means[param][w] = float(fc_str) if fc_str and fc_str not in ("None", "nan", "") else None
                    else:
                        fc_means[param][w] = None
        
        season_id = get_season_id(d) or ""
        result.append({
            "slot": slot,
            "date": str(d.date()),
            "season": season_id,
            "month": d.month,
            "year": d.year,
            "is_latest": idx == 0,
            "obs_means": obs_means,
            "forecast_means": fc_means,
        })
    
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
            "count": v["count"],
            "months": sorted(v["months"]),
        }
        for v in sorted(seasons_present.values(), key=lambda x: x["season"], reverse=True)
    ]
    
    return {
        "n_slots": n,
        "max_seasons": MAX_SEASONS,
        "season_months": sorted(SEASON_MONTHS),
        "allowed_seasons": get_allowed_season_ids(),
        "seasons": seasons_list,
        "units": "mm_per_day",
        "model": "LightGBM-v5.0 + Physics CWR/IWR",
        "params": PARAMS,
        "slots": result,
    }


@app.get("/api/seasons")
async def get_seasons():
    allowed = get_allowed_season_ids()
    dates = _latest_n_complete_dates()
    present = set(get_season_id(d) for d in dates if get_season_id(d))
    return {
        "allowed_seasons": allowed,
        "present_seasons": sorted(present, reverse=True),
        "max_seasons": MAX_SEASONS,
        "season_months": sorted(SEASON_MONTHS),
    }


@app.get("/api/forecast")
async def get_forecast(
    date: str = Query(..., description="Reference date YYYY-MM-DD"),
    days: int = Query(15, ge=1, le=30, description="Forecast horizon (days)"),
):
    try:
        ref_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date — use YYYY-MM-DD")
    
    forecasts = generate_forecast_for_date(ref_date, days)
    if not forecasts:
        raise HTTPException(status_code=500, detail="Failed to generate forecast")
    
    result = {
        "reference_date": date,
        "forecast_days": days,
        "model": "LightGBM-v5.0 + Physics CWR/IWR (v11.0)",
        "forecasts": {},
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
                "dates": [d.strftime("%Y-%m-%d") for d in series.index],
                "values": [round(float(v), 4) for v in series.values],
                "units": units_by_param[param],
                "mean": round(float(series.mean()), 4),
                "min": round(float(series.min()), 4),
                "max": round(float(series.max()), 4),
            }
    
    result["crop_stages"] = [
        {"date": d.strftime("%Y-%m-%d"), **get_wheat_stage_info(d.to_pydatetime())}
        for d in forecasts["cwr"].index
    ]
    
    WINDOW_SLICES = {"5day": (0, 5), "10day": (0, 10), "15day": (0, 15)}
    result["window_summaries"] = {}
    for window, (start_idx, end_idx) in WINDOW_SLICES.items():
        result["window_summaries"][window] = {}
        for param in ("kc", "cwr", "iwr", "peff"):
            if param in forecasts:
                vals = forecasts[param].iloc[start_idx:end_idx].values
                result["window_summaries"][window][param] = {
                    "mean": round(float(np.mean(vals)), 4),
                    "total": round(float(np.sum(vals)), 4),
                }
        window_date = forecasts["cwr"].index[start_idx].to_pydatetime()
        result["window_summaries"][window]["crop_stage"] = get_wheat_stage_info(window_date)
    
    return result


@app.get("/api/point")
def get_point(
    lat: float,
    lon: float,
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
        "lat": round(float(pixel["latitude"]), 7),
        "lon": round(float(pixel["longitude"]), 7),
        "query_lat": lat,
        "query_lon": lon,
        "pixel_id": pixel["pixel_id"],
        "row": pixel["row"],
        "col": pixel["col"],
        "acquisition_date": selected_date.strftime("%Y-%m-%d"),
        "slot": slot,
        "values": result,
        "forecast": forecast,
    }


@app.get("/api/point1")
def get_point_forecast_details(
    lat: float,
    lon: float,
    slot: Optional[str] = "today",
):
    pixel = _pixel_from_latlon(lat, lon)

    reference_date = _date_for_slot(slot)
    if reference_date is None:
        raise HTTPException(
            status_code=404,
            detail=f"No acquisition date found for slot '{slot}'"
        )

    # Generate the same forecast used while creating rasters
    forecasts = generate_forecast_for_date(reference_date, FORECAST_DAYS)

    if not forecasts:
        raise HTTPException(
            status_code=500,
            detail="Forecast generation failed"
        )

    response = {
        "pixel_id": pixel["pixel_id"],
        "row": pixel["row"],
        "col": pixel["col"],
        "lat": round(float(pixel["latitude"]), 7),
        "lon": round(float(pixel["longitude"]), 7),
        "acquisition_date": reference_date.strftime("%Y-%m-%d"),
        "today": {},
        "cwr": {
            "daily": [],
            "summary": {}
        },
        "iwr": {
            "daily": [],
            "summary": {}
        }
    }

    # Today's observed value
    response["today"]["cwr"] = _read_history_pixel_value(
        history_path("cwr", slot),
        pixel
    )

    response["today"]["iwr"] = _read_history_pixel_value(
        history_path("iwr", slot),
        pixel
    )

    cwr_series = forecasts["cwr"]
    iwr_series = forecasts["iwr"]

    cwr_running = 0.0
    iwr_running = 0.0

    for i in range(len(cwr_series)):

        cwr = float(cwr_series.iloc[i])
        iwr = float(iwr_series.iloc[i])

        cwr_running += cwr
        iwr_running += iwr

        response["cwr"]["daily"].append({
            "date": cwr_series.index[i].strftime("%Y-%m-%d"),
            "day": i + 1,
            "value": round(cwr, 4),
            "cumulative": round(cwr_running, 4)
        })

        response["iwr"]["daily"].append({
            "date": iwr_series.index[i].strftime("%Y-%m-%d"),
            "day": i + 1,
            "value": round(iwr, 4),
            "cumulative": round(iwr_running, 4)
        })

    response["cwr"]["summary"] = {
        "5day": round(sum(cwr_series.iloc[:5]), 4),
        "10day": round(sum(cwr_series.iloc[:10]), 4),
        "15day": round(sum(cwr_series.iloc[:15]), 4),
    }

    response["iwr"]["summary"] = {
        "5day": round(sum(iwr_series.iloc[:5]), 4),
        "10day": round(sum(iwr_series.iloc[:10]), 4),
        "15day": round(sum(iwr_series.iloc[:15]), 4),
    }

    return response


@app.get("/api/point/verify")
def verify_point_forecast(
    lat: float,
    lon: float,
    slot: Optional[str] = "today",
):
    """
    Diagnostic endpoint to reconcile /api/point (raster-read forecast) against
    /api/point1 (live area-aggregate forecast).

    generate_lgb_forecast_for_date() builds features from the *spatial mean*
    of each history raster, so its output curve is identical for every pixel
    on a given date — /api/point1 just returns that curve as-is.

    /api/point instead reads forecast_*.tif rasters, which create_forecast_raster()
    builds by taking that SAME area-wide curve and rescaling it per pixel:
        scale_factor   = window_forecast_sum / template_mean
        pixel_forecast = template_pixel_value * scale_factor

    This endpoint recomputes the pixel-scaled value live (so you can sanity
    check the math) AND reads what's literally stored in the forecast raster
    right now (so you can catch staleness, not just scaling differences).
    """
    pixel = _pixel_from_latlon(lat, lon)
    reference_date = _date_for_slot(slot)
    if reference_date is None:
        raise HTTPException(
            status_code=404, detail=f"No acquisition date found for slot '{slot}'"
        )

    # Same area-aggregate model curve used by /api/point1 AND by the raster pipeline
    forecasts = generate_forecast_for_date(reference_date, FORECAST_DAYS)
    if not forecasts:
        raise HTTPException(status_code=500, detail="Forecast generation failed")

    out: Dict[str, Any] = {
        "pixel_id": pixel["pixel_id"],
        "row": pixel["row"],
        "col": pixel["col"],
        "lat": round(float(pixel["latitude"]), 7),
        "lon": round(float(pixel["longitude"]), 7),
        "acquisition_date": reference_date.strftime("%Y-%m-%d"),
        "slot": slot,
    }

    for param in FC_PARAMS:  # ["cwr", "iwr"]
        series = forecasts[param]

        # --- replicate create_forecast_raster()'s scale factor for THIS pixel ---
        template_path = history_path(param, slot)
        pixel_today_value = _read_history_pixel_value(template_path, pixel)
        template_mean = _read_mean(template_path)

        if pixel_today_value is not None and template_mean and template_mean > 0:
            scale_factor = pixel_today_value / template_mean
        else:
            scale_factor = 1.0

        vmin, vmax = _VALID_FC.get(param, (-1e9, 1e9))

        raw_vals = [float(v) for v in series.values]
        scaled_vals = [float(np.clip(v * scale_factor, vmin, vmax)) for v in raw_vals]

        daily = []
        running_raw = 0.0
        running_scaled = 0.0
        for i in range(len(series)):
            running_raw += raw_vals[i]
            running_scaled += scaled_vals[i]
            daily.append({
                "date": series.index[i].strftime("%Y-%m-%d"),
                "day": i + 1,
                "raw_value": round(raw_vals[i], 4),
                "raw_cumulative": round(running_raw, 4),
                "pixel_scaled_value": round(scaled_vals[i], 4),
                "pixel_scaled_cumulative": round(running_scaled, 4),
            })

        summary = {}
        for window, n in WINDOW_DAYS.items():
            raw_sum = round(float(sum(raw_vals[:n])), 4)
            scaled_sum = round(float(sum(scaled_vals[:n])), 4)

            # what /api/point is actually serving right now for this pixel
            fpath = forecast_path(param, slot, window)
            raster_val = _read_history_pixel_value(fpath, pixel)

            raster_date = None
            if fpath.exists():
                try:
                    with rasterio.open(fpath) as src:
                        raster_date = src.tags().get("acquisition_date")
                except Exception:
                    raster_date = None
            is_stale = (
                raster_date is not None
                and raster_date != reference_date.strftime("%Y-%m-%d")
            )

            summary[window] = {
                "live_raw_sum": raw_sum,                # = /api/point1 summary, today
                "live_pixel_scaled_sum": scaled_sum,    # what /api/point SHOULD show
                "raster_value": raster_val,             # what /api/point ACTUALLY returns
                "raster_acquisition_date": raster_date,
                "raster_is_stale": is_stale,
                "diff_vs_raster": (
                    round(scaled_sum - raster_val, 4) if raster_val is not None else None
                ),
            }

        out[param] = {
            "pixel_today_value": pixel_today_value,
            "template_mean": template_mean,
            "scale_factor": round(scale_factor, 6),
            "daily": daily,
            "summary": summary,
        }

    return out


# ═══════════════════════════════════════════════════════════════════════════
# CHAT ENDPOINTS (unchanged)
# ═══════════════════════════════════════════════════════════════════════════

def _prepare_chat_context(req: ChatRequest) -> Dict[str, Any]:
    query = (req.query or "").strip()
    tool_answer = None
    tool_sources: List[str] = []
    query_type = "knowledge_based"
    structured_context = None
    
    try:
        from chat_data_tools import get_data_tools, safe_llm_context
        tool_result = get_data_tools().answer(query, live_data=None)
        query_type = tool_result.query_type
        tool_answer = tool_result.answer
        tool_sources = tool_result.sources or []
        structured_context = safe_llm_context(tool_result)
    except Exception as exc:
        logger.warning("[chat] structured query tools failed: %s", exc, exc_info=True)
    
    return {
        "query": query,
        "tool_answer": tool_answer,
        "tool_sources": tool_sources,
        "query_type": query_type,
        "structured_context": structured_context,
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
        }
    
    context = await asyncio.to_thread(_prepare_chat_context, req)
    tool_answer = context["tool_answer"]
    tool_sources = context["tool_sources"]
    query_type = context["query_type"]
    structured_context = context["structured_context"]
    
    if tool_answer:
        tool_block = f"## Structured Tool Answer\n{tool_answer}"
        structured_context = tool_block + "\n\n" + structured_context if structured_context else tool_block
    
    try:
        from rag_kb import get_chat_answer
        rag_response = await asyncio.to_thread(
            get_chat_answer,
            query,
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
            answer = llm_unavailable_answer(query)
        except Exception:
            answer = "I could not generate a knowledge-base answer right now because the LLM is unavailable."
        source_ids = tool_sources
        rag_response = {"model_used": "llm_unavailable"}
    
    return {
        "answer": answer,
        "sources": source_ids,
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
            yield _sse("done", {"answer": answer, "sources": [], "query_type": "empty"})
        return StreamingResponse(empty_stream(), media_type="text/event-stream")
    
    context = await asyncio.to_thread(_prepare_chat_context, req)
    structured_context = context["structured_context"]
    tool_answer_text = context.get("tool_answer")
    if tool_answer_text:
        tool_block = f"## Structured Tool Answer\n{tool_answer_text}"
        structured_context = tool_block + "\n\n" + structured_context if structured_context else tool_block
    tool_sources = context["tool_sources"]
    
    def event_stream():
        try:
            from rag_kb import stream_chat_answer
            for event in stream_chat_answer(
                query,
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
                    yield _sse("meta", {
                        "sources": sources,
                        "rag_chunks": event.get("rag_chunks", []),
                        "retrieved_context": event.get("retrieved_context", []),
                        "retrieval_ms": event.get("retrieval_ms"),
                        "rag_backend": event.get("rag_backend"),
                        "query_type": context["query_type"],
                    })
                elif event_type == "done":
                    sources = list(dict.fromkeys(tool_sources + (event.get("sources", []) or [])))
                    yield _sse("done", {**event, "sources": sources, "query_type": context["query_type"]})
        except Exception as exc:
            logger.error("[chat] streaming RAG failed: %s", exc, exc_info=True)
            try:
                from rag_kb import llm_unavailable_answer
                answer = llm_unavailable_answer(query)
            except Exception:
                answer = "I could not generate a knowledge-base answer right now."
            yield _sse("token", {"content": answer})
            yield _sse("done", {"answer": answer, "sources": tool_sources,
                               "query_type": context["query_type"],
                               "model_used": "llm_unavailable"})
    
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


@app.get("/health")
async def health():
    return {"status": "ok", "version": "11.0.0", "model": "LightGBM-v5.0 + Physics CWR/IWR"}


@app.post("/api/refresh")
async def manual_refresh():
    try:
        return {"status": "ok", "result": run_pipeline()}
    except Exception as e:
        logger.exception("Pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/model/info")
async def model_info():
    return {
        "models": {
            "cwr": {"available": _LGB_MODELS["cwr"] is not None},
            "iwr": {"available": _LGB_MODELS["iwr"] is not None},
        },
        "history_slots": HISTORY_DATES,
        "max_seasons": MAX_SEASONS,
        "season_months": sorted(SEASON_MONTHS),
        "allowed_seasons": get_allowed_season_ids(),
        "model_version": "v5.0 (LightGBM with raster-metadata features)",
        "training_method": "TimeSeriesSplit CV + GridSearchCV",
        "feature_count_cwr": len(FEATURES_CWR),
        "feature_count_iwr": len(FEATURES_IWR),
        "physical_relationships": {
            "savi_to_kc": f"Kc = {KC_SLOPE:.4f} × SAVI + {KC_INTERCEPT:.4f}",
            "cwr": "CWR = Kc × PET (FAO-56)",
            "iwr": "IWR = max(CWR − Peff, 0) (FAO-56)",
        },
        "crop_stage_today": get_wheat_stage_info(datetime.utcnow()),
    }


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def main():
    setup_logging()
    logger.info("=" * 65)
    logger.info("Irrigation Monitoring System v11.0 starting …")
    logger.info(f"Seasonal cap: {MAX_SEASONS} seasons | Months: Nov–Apr")
    logger.info(f"Allowed seasons: {get_allowed_season_ids()}")
    logger.info(f"LightGBM v5.0 models loaded: CWR={_LGB_MODELS['cwr'] is not None}, "
               f"IWR={_LGB_MODELS['iwr'] is not None}")
    logger.info("=" * 65)
    
    _get_wheat_mask()
    
    try:
        from rag_kb import warmup_ollama
        warmup_ollama()
        logger.info("✓ Ollama warmed up")
    except Exception as e:
        logger.warning(f"⚠ Ollama warmup failed: {e}")
    
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
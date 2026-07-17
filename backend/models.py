from __future__ import annotations

import logging
import pickle
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import rasterio

from config import DIRECTORIES

logger = logging.getLogger(__name__)

MODEL_DIR = DIRECTORIES["models"]
KC_SLOPE = 1.2088
KC_INTERCEPT = 0.5375
KC_MIN = 0.30
KC_MAX = 1.15
NODATA = -9999.0
SEASON_LENGTH_DAYS = 150
WHEAT_SOWING_DOY = 319


def extract_date(filename: str) -> datetime:
    stem = Path(filename).stem.upper()
    for pattern, fmt in [
        (r"\d{8}", "%Y%m%d"),
        (r"\d{2}[A-Z]{3}\d{4}", "%d%b%Y"),
        (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
    ]:
        match = re.search(pattern, stem)
        if match:
            return datetime.strptime(match.group(), fmt)
    raise ValueError(f"No valid date in: {filename}")


def raster_mean(fp: Path, mask_zeros: bool = True, apply_crop_mask: bool = True) -> float:
    try:
        with rasterio.open(fp) as src:
            data = src.read(1, masked=True)
            arr = np.ma.filled(data, np.nan).astype(np.float64)
            if src.nodata is not None:
                arr[arr == src.nodata] = np.nan
            arr[arr <= -9000] = np.nan
            if mask_zeros:
                arr[arr == 0] = np.nan
            arr = arr[np.isfinite(arr)]
            return float(np.mean(arr)) if arr.size else np.nan
    except Exception as exc:
        logger.warning("Could not read raster mean for %s: %s", fp, exc)
        return np.nan


def savi_to_kc(savi: np.ndarray) -> np.ndarray:
    return np.clip(KC_SLOPE * np.asarray(savi, dtype=float) + KC_INTERCEPT, KC_MIN, KC_MAX)


def kc_to_savi(kc: np.ndarray) -> np.ndarray:
    return np.clip((np.asarray(kc, dtype=float) - KC_INTERCEPT) / KC_SLOPE, -0.1, 0.9)


def _season_start_year(date: datetime) -> int:
    return date.year if date.month >= 11 else date.year - 1


def _season_sowing_date(date: datetime) -> datetime:
    return datetime(_season_start_year(date), 11, 1)


def days_after_sowing(date: datetime, sow_doy: int = WHEAT_SOWING_DOY) -> int:
    if sow_doy == WHEAT_SOWING_DOY:
        return max(0, (date - _season_sowing_date(date)).days)
    doy = date.timetuple().tm_yday
    return doy - sow_doy if doy >= sow_doy else (365 - sow_doy) + doy


def get_wheat_stage_kc(date: datetime) -> Tuple[str, float]:
    das = max(0, days_after_sowing(date))
    kc_ini, kc_mid, kc_end = 0.30, 1.15, 0.40
    l_ini, l_dev, l_mid, l_late = 30, 40, 50, 30
    if das <= l_ini:
        return "initial", kc_ini
    if das <= l_ini + l_dev:
        t = (das - l_ini) / l_dev
        return "development", round(kc_ini + t * (kc_mid - kc_ini), 4)
    if das <= l_ini + l_dev + l_mid:
        return "mid_season", kc_mid
    if das <= l_ini + l_dev + l_mid + l_late:
        t = (das - l_ini - l_dev - l_mid) / l_late
        return "late_season", round(kc_mid + t * (kc_end - kc_mid), 4)
    return "post_harvest", kc_end


def get_wheat_stage_info(date: datetime) -> Dict:
    stage_lengths = {
        "initial": 30,
        "development": 40,
        "mid_season": 50,
        "late_season": 30,
    }
    bounds = {
        "initial": (0, 30, "Germination to emergence"),
        "development": (30, 70, "Tillering to canopy closure"),
        "mid_season": (70, 120, "Heading to flowering"),
        "late_season": (120, 150, "Grain fill to maturity"),
    }
    das = days_after_sowing(date)
    stage, kc_fao56 = get_wheat_stage_kc(date)
    start, end, note = bounds.get(stage, (0, 150, "Outside season"))
    total = sum(stage_lengths.values())
    return {
        "stage": stage,
        "das": das,
        "kc_fao56": kc_fao56,
        "kc_min": KC_MIN,
        "kc_max": KC_MAX,
        "fraction_complete": round(min(max(0, das - start) / max(1, end - start), 1.0), 3),
        "note": note,
        "season_progress": round(min(max(das, 0) / total, 1.0), 3),
    }


def set_forecast_context(
    last_savi: float,
    last_kc: float = 0.75,
    last_pet: Optional[float] = None,
) -> None:
    build_forecast_exog._last_savi = float(last_savi)
    build_forecast_exog._last_kc = float(last_kc)
    build_forecast_exog._last_pet = None if last_pet is None else float(last_pet)


def build_forecast_exog(future_dates: pd.DatetimeIndex, exog_cols: list) -> pd.DataFrame:
    doy = np.array([d.timetuple().tm_yday for d in future_dates], dtype=float)
    angle = 2.0 * np.pi * doy / 365.25
    last_savi = float(getattr(build_forecast_exog, "_last_savi", 0.25))
    last_kc = float(getattr(build_forecast_exog, "_last_kc", KC_INTERCEPT + KC_SLOPE * last_savi))
    feature_map = {
        "sin_doy": np.sin(angle),
        "cos_doy": np.cos(angle),
        "sin2_doy": np.sin(2.0 * angle),
        "cos2_doy": np.cos(2.0 * angle),
        "month": np.array([d.month for d in future_dates], dtype=float),
        "savi": np.full(len(future_dates), last_savi),
        "kc_context": np.full(len(future_dates), last_kc),
    }
    return pd.DataFrame(
        {col: feature_map.get(col, np.zeros(len(future_dates))) for col in exog_cols},
        index=future_dates,
    )
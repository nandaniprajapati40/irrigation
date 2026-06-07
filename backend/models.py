from __future__ import annotations
import logging
import os
import pickle
import re
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PolynomialFeatures
from statsmodels.tsa.statespace.sarimax import SARIMAX

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

from config import DIRECTORIES

# ── Directory paths ──────────────────────────────────────────────────────────
PET_DIR  = DIRECTORIES["raw"]["insat_pet"]
KC_DIR   = DIRECTORIES["processed"]["kc"]
SAVI_DIR = DIRECTORIES["processed"]["savi"]
CWR_DIR  = DIRECTORIES["processed"]["cwr"]
RAIN_DIR = DIRECTORIES["raw"]["insat_rain"]
WHEAT_MASK_PATH = DIRECTORIES["processed"]["masks"] / "wheat_mask.tif"

MODEL_DIR = DIRECTORIES["models"]
os.makedirs(MODEL_DIR, exist_ok=True)

# ── Model file paths ─────────────────────────────────────────────────────────
KC_MODEL_PATH  = MODEL_DIR / "sarima_wheat_kc.pkl"
PET_MODEL_PATH = MODEL_DIR / "sarima_wheat_pet.pkl"

# ── Physical constants from THESIS Table 9 ─────────────────────────────────
# SAVI vs FAO Moving Averaged Kc: Kc = 1.2088 * SAVI + 0.5375 (R² = 0.88)
# This is the REGRESSION equation — SAVI → Kc (§4.3)
KC_SLOPE     = 1.2088
KC_INTERCEPT = 0.5375
KC_MIN       = 0.30
KC_MAX       = 1.15
SEASON_LENGTH_DAYS = 150
MAX_MEAN_PIXELS = 2_000_000

_WHEAT_MASK_CACHE: Dict[tuple, np.ndarray] = {}
_WHEAT_MASK_WARNED = False


# ═══════════════════════════════════════════════════════════════════════════
# Utilities
# ═══════════════════════════════════════════════════════════════════════════

def extract_date(filename: str) -> datetime:
    m = re.search(r"\d{8}", filename)
    if m:
        return datetime.strptime(m.group(), "%Y%m%d")
    m = re.search(r"\d{2}[A-Z]{3}\d{4}", filename.upper())
    if m:
        return datetime.strptime(m.group(), "%d%b%Y")
    raise ValueError(f"No valid date in: {filename}")

def build_date_file_map(directory: Optional[Path]) -> Dict[datetime, Path]:
    fm: Dict[datetime, Path] = {}
    if directory is None or not directory.exists():
        return fm
    for fp in directory.glob("*"):
        if fp.suffix.lower() in {".tif", ".tiff"}:
            try:
                fm[extract_date(fp.name)] = fp
            except Exception:
                pass
    return fm

def is_rabi(date: datetime) -> bool:
    """Rabi season: Nov 15 to Apr 30 (thesis §3.1, §5.6)"""
    return (date.month == 11 and date.day >= 1) or date.month in [12, 1, 2, 3, 4]

def _season_start_year(date: datetime) -> int:
    return date.year if date.month >= 11 else date.year - 1

def _season_sowing_date(date: datetime) -> datetime:
    return datetime(_season_start_year(date), 11, 1)

def _das_norm(date: datetime) -> float:
    return float(np.clip(days_after_sowing(date) / SEASON_LENGTH_DAYS, 0.0, 1.0))

def _wheat_mask_for_raster(src) -> Optional[np.ndarray]:
    global _WHEAT_MASK_WARNED

    if not WHEAT_MASK_PATH.exists():
        if not _WHEAT_MASK_WARNED:
            logger.warning("wheat_mask.tif not found at %s; raster means are unmasked", WHEAT_MASK_PATH)
            _WHEAT_MASK_WARNED = True
        return None

    if src.crs is None:
        logger.warning("Cannot apply wheat mask to %s because raster CRS is missing", src.name)
        return None

    transform_key = tuple(round(v, 9) for v in src.transform)
    cache_key = (src.height, src.width, src.crs.to_string(), transform_key)
    if cache_key in _WHEAT_MASK_CACHE:
        return _WHEAT_MASK_CACHE[cache_key]

    with rasterio.open(WHEAT_MASK_PATH) as mask_src:
        mask_raw = mask_src.read(1).astype("float32")
        same_grid = (
            mask_src.crs == src.crs
            and mask_src.transform == src.transform
            and mask_src.height == src.height
            and mask_src.width == src.width
        )

        if same_grid:
            mask_data = mask_raw
        else:
            mask_data = np.zeros((src.height, src.width), dtype="float32")
            reproject(
                source=mask_raw,
                destination=mask_data,
                src_transform=mask_src.transform,
                src_crs=mask_src.crs,
                dst_transform=src.transform,
                dst_crs=src.crs,
                src_nodata=mask_src.nodata if mask_src.nodata is not None else 0,
                dst_nodata=0,
                resampling=Resampling.average,
            )

    wheat_mask = mask_data > 0
    if not np.any(wheat_mask):
        logger.warning("Wheat mask has no overlap with %s; falling back to unmasked mean", src.name)
        return None

    _WHEAT_MASK_CACHE[cache_key] = wheat_mask
    return wheat_mask

def _mean_out_shape(src, apply_crop_mask: bool) -> Optional[Tuple[int, int]]:
    if apply_crop_mask:
        return None

    n_pixels = src.height * src.width
    if n_pixels <= MAX_MEAN_PIXELS:
        return None

    scale = np.sqrt(MAX_MEAN_PIXELS / float(n_pixels))
    return max(1, int(src.height * scale)), max(1, int(src.width * scale))

def raster_mean(fp: Path, mask_zeros: bool = True, apply_crop_mask: bool = True) -> float:
    try:
        with rasterio.open(fp) as src:
            if not apply_crop_mask:
                try:
                    stats = src.statistics(1, approx=True)
                    mean_val = float(stats.mean)
                    if np.isfinite(mean_val) and (not mask_zeros or float(stats.min) != 0.0):
                        return mean_val
                except Exception:
                    pass

            out_shape = _mean_out_shape(src, apply_crop_mask)
            if out_shape is None:
                data = src.read(1, masked=True)
            else:
                data = src.read(
                    1,
                    out_shape=out_shape,
                    masked=True,
                    resampling=Resampling.average,
                )
            arr = np.ma.filled(data, np.nan).astype(np.float64)
            if src.nodata is not None:
                arr[arr == src.nodata] = np.nan
            arr[arr < -900] = np.nan
            if mask_zeros:
                arr[arr == 0] = np.nan
            if apply_crop_mask:
                wheat_mask = _wheat_mask_for_raster(src)
                if wheat_mask is not None:
                    arr[~wheat_mask] = np.nan
            arr = arr[~np.isnan(arr)]
            return float(np.mean(arr)) if len(arr) > 0 else np.nan
    except Exception:
        return np.nan

def _doy_sin_cos(doy_series):
    angle = 2.0 * np.pi * np.asarray(doy_series, dtype=float) / 365.0
    return np.sin(angle), np.cos(angle)

def savi_to_kc(savi: np.ndarray) -> np.ndarray:
    """Thesis §4.3, Table 9: Kc = 1.2088 * SAVI + 0.5375 (R² = 0.88)
    
    This is the regression relationship used to derive historical Kc maps
    from Sentinel-2 SAVI. SARIMAX still forecasts Kc directly, while SAVI can
    be used as an exogenous phenology signal.
    """
    return np.clip(KC_SLOPE * np.asarray(savi, dtype=float) + KC_INTERCEPT, KC_MIN, KC_MAX)

def kc_to_savi(kc: np.ndarray) -> np.ndarray:
    """Inverse of the thesis SAVI-to-Kc regression for feature generation."""
    return np.clip((np.asarray(kc, dtype=float) - KC_INTERCEPT) / KC_SLOPE, -0.1, 0.9)

def _effective_rainfall(rain_sum: float, interval_days: int) -> float:
    """FAO effective rainfall scaled from monthly formula to interval total."""
    period_factor = max(float(interval_days), 1.0) / 30.0
    pe_threshold = 75.0 * period_factor
    if rain_sum <= pe_threshold:
        return max(0.6 * rain_sum - 10.0 * period_factor, 0.0)
    return max(0.8 * rain_sum - 25.0 * period_factor, 0.0)

def set_forecast_context(
    last_savi: float,
    last_kc: float = 0.75,
    last_pet: Optional[float] = None,
) -> None:
    """Store last observed values for forecast initialization"""
    build_forecast_exog._last_savi = float(last_savi)
    build_forecast_exog._last_kc = float(last_kc)
    build_forecast_exog._last_pet = None if last_pet is None else float(last_pet)


# ═══════════════════════════════════════════════════════════════════════════
# Metrics
# ═══════════════════════════════════════════════════════════════════════════

def compute_validation_metrics(observed, predicted) -> dict:
    obs = np.asarray(observed, dtype=float)
    pred = np.asarray(predicted, dtype=float)
    valid = ~(np.isnan(obs) | np.isnan(pred))
    obs, pred = obs[valid], pred[valid]
    if len(obs) < 2:
        return {k: np.nan for k in ("R2", "NSE", "RMSE", "MAE", "MAPE")}
    ss_res = np.sum((obs - pred) ** 2)
    ss_tot = np.sum((obs - np.mean(obs)) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    rmse = float(np.sqrt(mean_squared_error(obs, pred)))
    mae = float(mean_absolute_error(obs, pred))
    nz = np.abs(obs) > 1e-9
    mape = float(np.mean(np.abs((obs[nz] - pred[nz]) / obs[nz])) * 100) if nz.any() else np.nan
    return {"R2": round(r2, 4), "NSE": round(r2, 4), "RMSE": round(rmse, 4),
            "MAE": round(mae, 4), "MAPE": round(mape, 2)}


# ═══════════════════════════════════════════════════════════════════════════
# Forecast exog builder
# ═══════════════════════════════════════════════════════════════════════════

def build_forecast_exog(future_dates: "pd.DatetimeIndex", exog_cols: list) -> "pd.DataFrame":
    """
    Build out-of-sample regressors for trained SARIMAX models.

    Kc models may include SAVI-derived predictors. Future SAVI is estimated
    from the latest observed SAVI/Kc blended toward FAO-56 stage Kc.
    PET remains meteorological and uses its saved Fourier/month/lag columns.
    """
    n = len(future_dates)
    doy = np.array([d.timetuple().tm_yday for d in future_dates], dtype=float)
    angle = 2.0 * np.pi * doy / 365.0
    angle2 = 4.0 * np.pi * doy / 365.0
    last_savi = float(getattr(build_forecast_exog, "_last_savi", 0.25))
    last_kc = float(getattr(build_forecast_exog, "_last_kc", KC_INTERCEPT + KC_SLOPE * last_savi))
    last_pet = getattr(build_forecast_exog, "_last_pet", None)
    if last_pet is None or not np.isfinite(last_pet):
        last_pet = 4.0
    last_pet = float(last_pet)

    stage_kc = np.array([
        get_wheat_stage_kc(d.to_pydatetime() if hasattr(d, "to_pydatetime") else d)[1]
        for d in future_dates
    ], dtype=float)
    alpha = np.exp(-np.arange(n, dtype=float) / 5.0)
    kc_context = np.clip(alpha * last_kc + (1.0 - alpha) * stage_kc, KC_MIN, KC_MAX)
    savi_context = kc_to_savi(kc_context)
    savi_diff = np.diff(np.r_[last_savi, savi_context])
    savi_trend = pd.Series(savi_context).rolling(5, min_periods=1).mean().values
    das = np.array([
        days_after_sowing(d.to_pydatetime() if hasattr(d, "to_pydatetime") else d)
        for d in future_dates
    ], dtype=float)

    seasonal_pet = 5.5 + 3.2 * np.sin(2.0 * np.pi * (doy - 45.0) / 365.25)
    pet_context = np.clip(seasonal_pet, 0.0, 20.0)
    pet_lag1 = np.r_[last_pet, pet_context[:-1]][:n]
    pet_lag2 = np.r_[last_pet, last_pet, pet_context[:-2]][:n]
    
    feature_map = {
        "sin_doy":   np.sin(angle),
        "cos_doy":   np.cos(angle),
        "sin2_doy":  np.sin(angle2),
        "cos2_doy":  np.cos(angle2),
        "month":     np.array([d.month for d in future_dates], dtype=float),
        "das":       das,
        "das_norm":  np.clip(das / SEASON_LENGTH_DAYS, 0.0, 1.0),
        "savi":      savi_context,
        "savi_diff": savi_diff,
        "savi_trend": savi_trend,
        "savi_kc":   savi_to_kc(savi_context),
        "kc_stage":  stage_kc,
        "kc_context": kc_context,
        "pet_lag1":  pet_lag1,
        "pet_lag2":  pet_lag2,
        "pet_log":   np.log1p(pet_context),
    }
    rows: dict = {}
    for col in exog_cols:
        if col in feature_map:
            rows[col] = feature_map[col]
        else:
            logger.warning("Unknown column '%s' — zeros", col)
            rows[col] = np.zeros(n)
    return pd.DataFrame(rows, index=future_dates)


# ═══════════════════════════════════════════════════════════════════════════
# Dataset loaders — THESIS COMPLIANT
# ═══════════════════════════════════════════════════════════════════════════

def load_wheat_kc_dataset() -> pd.DataFrame:
    """
    Load Kc time series from processed rasters and enrich it with crop-stage
    and SAVI dynamics so the model can learn phenology from existing data.
    """
    logger.info("Loading Kc dataset for SARIMAX training...")
    kc_map = build_date_file_map(KC_DIR)
    
    if not kc_map:
        raise RuntimeError("No Kc rasters found in processed/kc/")
    
    records = []
    for date, kc_fp in sorted(kc_map.items()):
        if not is_rabi(date):
            continue
        # Processed Kc/SAVI rasters are already wheat-masked in processor.py.
        kc_val = raster_mean(kc_fp, mask_zeros=True, apply_crop_mask=False)
        if np.isnan(kc_val):
            continue
        savi_val = float(kc_to_savi([kc_val])[0])
        
        doy = date.timetuple().tm_yday
        s, c = _doy_sin_cos([doy])
        angle2 = 4.0 * np.pi * doy / 365.0  # 2nd harmonic for seasonal capture
        das = days_after_sowing(date)
        
        records.append({
            "date": date, 
            "kc": kc_val,
            "savi": savi_val,
            "das": float(das),
            "das_norm": _das_norm(date),
            "season_year": float(_season_start_year(date)),
            "sin_doy": s[0], 
            "cos_doy": c[0],
            "sin2_doy": float(np.sin(angle2)),
            "cos2_doy": float(np.cos(angle2)),
        })
    
    if not records:
        raise RuntimeError("No valid Kc data found after filtering")
    
    df = pd.DataFrame(records).sort_values("date").set_index("date")
    grouped = df.groupby("season_year", group_keys=False)
    df["kc_smooth"] = grouped["kc"].transform(
        lambda s: s.rolling(3, center=True, min_periods=1).mean()
    )
    df["savi_diff"] = grouped["savi"].diff().fillna(0.0)
    df["savi_trend"] = grouped["savi"].transform(
        lambda s: s.rolling(5, min_periods=1).mean()
    )
    df = df.replace([np.inf, -np.inf], np.nan).dropna(
        subset=["kc_smooth", "savi", "savi_diff", "das_norm"]
    )
    if df.empty:
        raise RuntimeError("No valid Kc rows after feature engineering")
    logger.info("Kc dataset: %d records (%s → %s)", 
                len(df), df.index[0].date(), df.index[-1].date())
    logger.info(
        "Kc range: %.3f to %.3f | smoothed %.3f to %.3f",
        df["kc"].min(),
        df["kc"].max(),
        df["kc_smooth"].min(),
        df["kc_smooth"].max(),
    )
    return df


def load_wheat_pet_dataset() -> pd.DataFrame:
    """
    Load PET time series from INSAT-3D rasters for SARIMA training.
    
    THESIS §4.2, §4.6:
      - PET is derived from INSAT-3D using FAO-56 Penman-Monteith
      - PET is purely meteorological — NO SAVI, NO Kc involvement
      - SARIMA forecasts PET → PET (univariate with Fourier + month exog)
    
    Returns DataFrame with PET, log PET, Fourier seasonality, month, and lags.
    """
    logger.info("Loading PET dataset (INSAT-3D only)...")
    pet_map = build_date_file_map(PET_DIR)
    
    if not pet_map:
        raise RuntimeError("No PET rasters found in raw/insat_pet/")
    
    records = []
    for date, pet_fp in sorted(pet_map.items()):
        if not is_rabi(date):
            continue
        pet_val = raster_mean(pet_fp, mask_zeros=True)
        if np.isnan(pet_val):
            continue
        
        doy = date.timetuple().tm_yday
        s1, c1 = _doy_sin_cos([doy])
        angle2 = 4.0 * np.pi * doy / 365.0
        
        records.append({
            "date": date, 
            "pet": pet_val,
            "season_year": float(_season_start_year(date)),
            "sin_doy": s1[0], 
            "cos_doy": c1[0],
            "sin2_doy": float(np.sin(angle2)), 
            "cos2_doy": float(np.cos(angle2)),
            "month": float(date.month),
        })
    
    df = pd.DataFrame(records).sort_values("date").set_index("date")
    
    # Lag/log features stabilize the MOSDAC PET signal without adding weather inputs.
    df["pet_log"] = np.log1p(df["pet"])
    grouped = df.groupby("season_year", group_keys=False)
    df["pet_lag1"] = grouped["pet"].shift(1)
    df["pet_lag2"] = grouped["pet"].shift(2)
    df = df.dropna()
    if df.empty:
        raise RuntimeError("No valid PET rows after lag/log feature engineering")
    
    logger.info("PET dataset: %d records (%s → %s)", 
                len(df), df.index[0].date(), df.index[-1].date())
    logger.info("PET range: %.2f to %.2f mm/day", df["pet"].min(), df["pet"].max())
    return df


# ═══════════════════════════════════════════════════════════════════════════
# THESIS SARIMA trainer — Seasonal period = 12 (monthly)
# ═══════════════════════════════════════════════════════════════════════════

def _train_sarima(
    y: pd.Series, 
    exog: pd.DataFrame, 
    target_name: str,
    seasonal_period: int = 12,
    inverse_transform=None,
) -> Tuple:
    """
    THESIS §4.6, §5.6, Table 13: SARIMA(1,1,1)(1,1,1,12)
    
    The thesis uses monthly seasonality (period=12) within the Rabi season.
    This captures the monthly progression: Nov→Dec→Jan→Feb→Mar→Apr.
    
    Model selection from thesis Table 13: SARIMA(1,1,1)(1,1,1,12)
    """
    SARIMA_ORDER = (1, 1, 1)
    SARIMA_SEASONAL = (1, 1, 1, seasonal_period)
    
    logger.info("=" * 65)
    logger.info("Training SARIMA%s%s for %s — feature-engineered v13.2", 
                SARIMA_ORDER, SARIMA_SEASONAL, target_name)
    logger.info("=" * 65)
    
    common_idx = y.index.intersection(exog.index)
    y = y.loc[common_idx]
    exog = exog.loc[common_idx]
    mask = ~(exog.isnull().any(axis=1) | y.isnull())
    y, exog = y[mask], exog[mask]
    
    logger.info("Total samples: %d", len(y))
    logger.info("Date range: %s → %s", y.index[0].date(), y.index[-1].date())
    logger.info("Exog: %s", list(exog.columns))
    
    # Train/test split: 80/20
    split_idx = int(len(y) * 0.8)
    if split_idx < 30:
        raise ValueError(f"Too few samples: {len(y)}")
    
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    exog_train, exog_test = exog.iloc[:split_idx], exog.iloc[split_idx:]
    
    logger.info("Train: %d (%s → %s)", len(y_train),
                y_train.index[0].date(), y_train.index[-1].date())
    logger.info("Test:  %d (%s → %s)", len(y_test),
                y_test.index[0].date(), y_test.index[-1].date())
    
    # Fit training split
    logger.info("Fitting SARIMAX...")
    try:
        sarima_train = SARIMAX(
            y_train, 
            exog=exog_train,
            order=SARIMA_ORDER,
            seasonal_order=SARIMA_SEASONAL,
            enforce_stationarity=False,
            enforce_invertibility=False,
        ).fit(disp=False, method="lbfgs", maxiter=500)
    except Exception as exc:
        logger.error("SARIMAX fit failed: %s", exc)
        # Fallback to simpler model if convergence fails
        logger.info("Retrying with SARIMA(1,1,1)(0,1,1,12)...")
        sarima_train = SARIMAX(
            y_train, 
            exog=exog_train,
            order=(1, 1, 1),
            seasonal_order=(0, 1, 1, seasonal_period),
            enforce_stationarity=False,
            enforce_invertibility=False,
        ).fit(disp=False, method="lbfgs", maxiter=500)
    
    logger.info("AIC=%.2f BIC=%.2f", sarima_train.aic, sarima_train.bic)
    
    # Validate
    try:
        fc = sarima_train.forecast(steps=len(y_test), exog=exog_test)
        if inverse_transform is not None:
            metrics = compute_validation_metrics(
                inverse_transform(y_test.values),
                inverse_transform(fc.values),
            )
        else:
            metrics = compute_validation_metrics(y_test.values, fc.values)
    except Exception as exc:
        raise RuntimeError(f"Forecast failed: {exc}") from exc
    
    logger.info("Test  R²=%.4f RMSE=%.4f MAE=%.4f MAPE=%.2f%%",
                metrics["R2"], metrics["RMSE"], metrics["MAE"], metrics["MAPE"])
    
    # Retrain on full dataset
    logger.info("Retraining on full dataset (%d samples)...", len(y))
    try:
        final_model = SARIMAX(
            y, 
            exog=exog,
            order=SARIMA_ORDER,
            seasonal_order=SARIMA_SEASONAL,
            enforce_stationarity=False,
            enforce_invertibility=False,
        ).fit(disp=False, method="lbfgs", maxiter=500)
    except Exception as exc:
        logger.error("Full refit failed: %s", exc)
        final_model = SARIMAX(
            y, 
            exog=exog,
            order=(1, 1, 1),
            seasonal_order=(0, 1, 1, seasonal_period),
            enforce_stationarity=False,
            enforce_invertibility=False,
        ).fit(disp=False, method="lbfgs", maxiter=500)
    
    logger.info("Full fit AIC=%.2f", final_model.aic)
    return final_model, metrics, SARIMA_ORDER


# ═══════════════════════════════════════════════════════════════════════════
# Kc SARIMA trainer — THESIS §4.6, §5.6
# ═══════════════════════════════════════════════════════════════════════════

def train_kc_model():
    """
    SARIMAX model for Kc forecasting using smoothed Kc plus crop-stage and
    SAVI dynamics extracted from the existing Sentinel-2 series.
    """
    df = load_wheat_kc_dataset()
    
    exog_cols = [
        "sin_doy",
        "cos_doy",
        "sin2_doy",
        "cos2_doy",
        "das_norm",
        "savi",
        "savi_diff",
    ]
    exog = df[exog_cols]
    
    model, metrics, order = _train_sarima(df["kc_smooth"], exog, "Kc", seasonal_period=12)
    
    meta = {
        "model": model, 
        "metrics": metrics, 
        "exog_cols": exog_cols,
        "order": order, 
        "last_date": df.index[-1], 
        "last_savi": float(df["savi"].iloc[-1]),
        "last_kc": float(df["kc"].iloc[-1]),
        "target_name": "kc",
        "target_series": "kc_smooth",
        "note": "SARIMAX(1,1,1)(1,1,1,12) for smoothed Kc using DAS, SAVI, and SAVI dynamics.",
    }
    with open(KC_MODEL_PATH, "wb") as f:
        pickle.dump(meta, f)
    logger.info("Kc model saved → %s (R²=%.4f)", KC_MODEL_PATH, metrics["R2"])
    return model, metrics


# ═══════════════════════════════════════════════════════════════════════════
# PET SARIMA trainer — THESIS §4.6, §5.6
# ═══════════════════════════════════════════════════════════════════════════

def train_pet_model():
    """
    THESIS §4.6, §5.6: SARIMA for PET — purely meteorological.
    
    CRITICAL CLARIFICATION:
      - PET is derived from INSAT-3D using FAO-56 Penman-Monteith (§4.2)
      - PET is NOT derived from SAVI or Kc — it's independent meteorological data
      - SARIMA forecasts PET → PET (Fourier + month + PET lag exog)
    
    Input to SARIMA:  PET, historical from INSAT-3D
    Output from SARIMA: PET (forecasted)
    Exogenous: Fourier harmonics + month indicator + PET lag
    """
    df = load_wheat_pet_dataset()
    
    exog_cols = ["sin_doy", "cos_doy", "sin2_doy", "cos2_doy", "month", "pet_lag1"]
    exog = df[exog_cols]
    
    model, metrics, order = _train_sarima(df["pet"], exog, "PET", seasonal_period=7)
    
    meta = {
        "model": model, 
        "metrics": metrics, 
        "exog_cols": exog_cols,
        "order": order, 
        "last_date": df.index[-1], 
        "last_pet": float(df["pet"].iloc[-1]),
        "target_name": "pet",
        "pet_log_available": True,
        "note": "SARIMAX(1,1,1)(1,1,1,12) for PET using Fourier, month, and PET lag. "
                "log1p(PET) is engineered for diagnostics but raw PET validated better here.",
    }
    with open(PET_MODEL_PATH, "wb") as f:
        pickle.dump(meta, f)
    logger.info("PET model saved → %s (R²=%.4f)", PET_MODEL_PATH, metrics["R2"])
    return model, metrics


def train_all_models() -> dict:
    logger.info("=" * 80)
    logger.info("Training Models — v13.2 [FEATURE-ENGINEERED]")
    logger.info("=" * 80)
    results = {}
    
    for name, fn in [("kc", train_kc_model), ("pet", train_pet_model)]:
        try:
            model, metrics = fn()
            results[name] = {"model": model, "metrics": metrics}
        except Exception as exc:
            logger.error("%s FAILED: %s", name.upper(), exc)
            import traceback
            traceback.print_exc()
            results[name] = None
            raise
    
    logger.info("\n" + "=" * 80)
    logger.info("Training Summary — FEATURE ENGINEERED")
    logger.info("=" * 80)
    for name, result in results.items():
        if result:
            m = result["metrics"]
            logger.info("%s:", name.upper())
            for k in ("R2", "NSE", "RMSE", "MAE", "MAPE"):
                v = m.get(k)
                if v is not None and not (isinstance(v, float) and np.isnan(v)):
                    logger.info("  %-6s: %s", k, v)
    return results


def load_model(model_type: str):
    path_map = {"kc": KC_MODEL_PATH, "pet": PET_MODEL_PATH}
    path = path_map.get(model_type)
    if not path or not path.exists():
        raise FileNotFoundError(f"Model not found: {path}")
    with open(path, "rb") as f:
        meta = pickle.load(f)
    logger.info("Loaded %s — %s (R²=%.4f)",
                model_type.upper(), meta.get("note", ""), meta["metrics"]["R2"])
    return meta["model"], meta


# ═══════════════════════════════════════════════════════════════════════════
# Wheat growth-stage model — THESIS §4.3, Table 9
# ═══════════════════════════════════════════════════════════════════════════

WHEAT_SOWING_DOY: int = 319  # Nov 15

WHEAT_STAGE_LENGTHS: Dict[str, int] = {
    "initial": 30,      # Germination
    "development": 40,  # Tillering → jointing
    "mid_season": 50,   # Heading → flowering (peak water demand)
    "late_season": 30   # Grain fill → maturity
}

def days_after_sowing(date: datetime, sow_doy: int = WHEAT_SOWING_DOY) -> int:
    if sow_doy == WHEAT_SOWING_DOY:
        return max(0, (date - _season_sowing_date(date)).days)

    doy = date.timetuple().tm_yday
    if doy >= sow_doy:
        return doy - sow_doy
    return (365 - sow_doy) + doy

def get_wheat_stage_kc(date: datetime) -> Tuple[str, float]:
    """
    FAO-56 stage Kc for wheat (thesis §4.3, §5.3).
    Used for blending with SAVI-derived Kc in forecast.
    """
    das = max(0, days_after_sowing(date))
    kc_ini, kc_mid, kc_end = 0.30, 1.15, 0.40
    L_ini, L_dev, L_mid, L_late = 30, 40, 50, 30
    
    if das <= L_ini:
        return "initial", kc_ini
    if das <= L_ini + L_dev:
        t = (das - L_ini) / L_dev
        return "development", round(kc_ini + t * (kc_mid - kc_ini), 4)
    if das <= L_ini + L_dev + L_mid:
        return "mid_season", kc_mid
    if das <= L_ini + L_dev + L_mid + L_late:
        t = (das - L_ini - L_dev - L_mid) / L_late
        return "late_season", round(kc_mid + t * (kc_end - kc_mid), 4)
    return "post_harvest", kc_end

def get_wheat_stage_info(date: datetime) -> Dict:
    das = days_after_sowing(date)
    stage, kc_fao56 = get_wheat_stage_kc(date)
    total = sum(WHEAT_STAGE_LENGTHS.values())
    bounds = {
        "initial": (0, 30, "Germination → emergence"),
        "development": (30, 70, "Tillering → canopy closure"),
        "mid_season": (70, 120, "Heading → flowering (peak ET)"),
        "late_season": (120, 150, "Grain fill → maturity"),
    }
    start, end, desc = bounds.get(stage, (0, 150, "Outside season"))
    return {
        "stage": stage, 
        "das": das, 
        "kc_fao56": kc_fao56,
        "kc_min": KC_MIN, 
        "kc_max": KC_MAX,
        "fraction_complete": round(min(max(0, das - start) / max(1, end - start), 1.0), 3),
        "note": desc,
        "season_progress": round(min(das / total, 1.0), 3),
    }

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = train_all_models()

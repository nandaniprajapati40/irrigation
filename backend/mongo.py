"""
mongo.py
─────────────────────────────────────────────────────────────────────────────
MongoDB layer for the irrigation monitoring system.

Collections (one per processing stage):
  sentinel_images  – downloaded S2 scenes
  savi_data        – SAVI rasters
  kc_data          – Kc rasters
  etc_data         – ETc rasters
  cwr_data         – CWR rasters
  iwr_data         – IWR rasters
  forecast_data    – SARIMAX forecast records
  processed_data   – legacy flat collection (kept for API backward-compat)

Each stage collection carries a unique index on image_date to prevent
duplicate records.  Every public helper follows the same idempotency
pattern so re-running the pipeline is always safe.
"""

from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
import logging

from pymongo import MongoClient, ASCENDING, errors
from config import MONGODB

logger = logging.getLogger("MONGO")

# ── Connection ─────────────────────────────────────────────────────────────
_client = MongoClient(MONGODB["uri"])
_db     = _client[MONGODB["database"]]

# ── Collections ────────────────────────────────────────────────────────────
sentinel_col = _db["sentinel_images"]
savi_col     = _db["savi_data"]
kc_col       = _db["kc_data"]
etc_col      = _db["etc_data"]
cwr_col      = _db["cwr_data"]
iwr_col      = _db["iwr_data"]
# Daily INSAT download tracking
pet_col        = _db["pet_data"]
rain_col       = _db["rain_data"]

# Interval aggregates per Sentinel scene
pet_stats_col  = _db["pet_stats"]
rain_stats_col = _db["rain_stats"]
forecast_col = _db["forecast_data"]

# Legacy aliases kept for backward-compat with main.py / historical_averages.py
processed_collection = _db["processed_data"]
forecast_collection  = forecast_col

# ── Step → collection mapping (used by generic dispatcher) ─────────────────
_STEP_COLLECTIONS: Dict[str, Any] = {
    "sentinel":   sentinel_col,
    "savi":       savi_col,
    "kc":         kc_col,
    "etc":        etc_col,
    "cwr":        cwr_col,
    "iwr":        iwr_col,
    "pet":        pet_col,        # ← add
    "rain":       rain_col,       # ← add
    "pet_stats":  pet_stats_col,  # ← add
    "rain_stats": rain_stats_col, # ← add
}


# ── Ensure unique indexes on first import ──────────────────────────────────
def _ensure_indexes() -> None:
    for col in (sentinel_col, savi_col, kc_col, etc_col, cwr_col, iwr_col):
        col.create_index(
            [("image_date", ASCENDING)],
            unique=True,
            name="idx_image_date_unique",
        )

    for col in (pet_col, rain_col):
        col.create_index(
            [("image_date", ASCENDING)],
            unique=True,
            name="idx_image_date_unique",
        )
    for col in (pet_stats_col, rain_stats_col):
        col.create_index(
            [("sentinel_date", ASCENDING)],
            unique=True,
            name="idx_sentinel_date_unique",
        )
    forecast_col.create_index(
        [("parameter", ASCENDING), ("forecast_date", ASCENDING)],
        unique=True,
        name="idx_param_forecast_unique",
    )
    processed_collection.create_index(
        [("parameter", ASCENDING), ("date", ASCENDING)],
        unique=True,
        sparse=True,
        name="idx_param_date_unique",
    )
    logger.info("MongoDB indexes ensured")

_ensure_indexes()


# ── Internal helpers ───────────────────────────────────────────────────────

def _day(dt: datetime) -> datetime:
    """Truncate to midnight UTC for date-only comparisons."""
    return datetime(dt.year, dt.month, dt.day)


def _is_processed(collection, date: datetime) -> bool:
    return collection.count_documents({"image_date": _day(date)}, limit=1) > 0


def _mark_processed(
    collection,
    date: datetime,
    raster_path: str,
    stats: Optional[Dict] = None,
    extra: Optional[Dict] = None,
) -> bool:
    doc: Dict[str, Any] = {
        "image_date":        _day(date),
        "raster_path":       raster_path,
        "processing_status": "complete",
        "processed_at":      datetime.utcnow(),
    }
    if stats:
        doc["stats"] = stats
    if extra:
        doc.update(extra)
    try:
        collection.update_one(
            {"image_date": _day(date)},
            {"$set": doc},
            upsert=True,
        )
        return True
    except errors.DuplicateKeyError:
        logger.debug(f"Duplicate ignored for {date.date()}")
        return False
    except Exception as e:
        logger.error(f"MongoDB write error: {e}")
        return False


# ── Generic dispatcher used by processor.py ───────────────────────────────

def step_already_processed(step: str, date: datetime) -> bool:
    """
    Return True if `step` has already been processed for `date`.
    step must be one of: sentinel, savi, kc, etc, cwr, iwr
    """
    col = _STEP_COLLECTIONS.get(step.lower())
    if col is None:
        logger.warning(f"step_already_processed: unknown step '{step}'")
        return False
    return _is_processed(col, date)


# ── Sentinel ───────────────────────────────────────────────────────────────

def is_sentinel_downloaded(date: datetime) -> bool:
    return _is_processed(sentinel_col, date)

def mark_sentinel_downloaded(
    date: datetime,
    filepath: str,
    cloud_pct: Optional[float] = None,
    checksum: Optional[str] = None,
) -> bool:
    extra = {}

    if cloud_pct is not None:
        extra["cloud_pct"] = cloud_pct

    if checksum is not None:
        extra["sha256"] = checksum

    return _mark_processed(sentinel_col, date, filepath, extra=extra)

# ── SAVI ───────────────────────────────────────────────────────────────────

def is_savi_processed(date: datetime) -> bool:
    return _is_processed(savi_col, date)

def mark_savi_processed(date: datetime, filepath: str, stats: Dict) -> bool:
    _write_legacy(date, "savi", stats.get("mean"))
    return _mark_processed(savi_col, date, filepath, stats=stats)


# ── Kc ────────────────────────────────────────────────────────────────────

def is_kc_processed(date: datetime) -> bool:
    return _is_processed(kc_col, date)

def mark_kc_processed(date: datetime, filepath: str, stats: Dict) -> bool:
    _write_legacy(date, "kc", stats.get("mean"))
    return _mark_processed(kc_col, date, filepath, stats=stats)


# ── ETc ───────────────────────────────────────────────────────────────────

def is_etc_processed(date: datetime) -> bool:
    return _is_processed(etc_col, date)

def mark_etc_processed(date: datetime, filepath: str, stats: Dict) -> bool:
    _write_legacy(date, "etc", stats.get("mean"))
    return _mark_processed(etc_col, date, filepath, stats=stats)


# ── CWR ───────────────────────────────────────────────────────────────────

def is_cwr_processed(date: datetime) -> bool:
    return _is_processed(cwr_col, date)

def mark_cwr_processed(date: datetime, filepath: str, stats: Dict) -> bool:
    _write_legacy(date, "cwr", stats.get("mean"))
    return _mark_processed(cwr_col, date, filepath, stats=stats)


# ── IWR ───────────────────────────────────────────────────────────────────

def is_iwr_processed(date: datetime) -> bool:
    return _is_processed(iwr_col, date)

def mark_iwr_processed(date: datetime, filepath: str, stats: Dict) -> bool:
    _write_legacy(date, "iwr", stats.get("mean"))
    return _mark_processed(iwr_col, date, filepath, stats=stats)


# ── Forecast ──────────────────────────────────────────────────────────────

def save_forecast(parameter: str, forecast_dict: dict, date: datetime) -> None:
    try:
        forecast_col.update_one(
            {"parameter": parameter, "forecast_date": _day(date)},
            {"$set": {
                "parameter":       parameter,
                "forecast_date":   _day(date),
                "forecast_values": forecast_dict,
                "created_at":      datetime.utcnow(),
            }},
            upsert=True,
        )
        logger.info(f"Forecast saved: {parameter} @ {date.date()}")
    except Exception as e:
        logger.error(f"Forecast save error: {e}")


# ── Legacy / backward-compat helpers ──────────────────────────────────────

def _write_legacy(date: datetime, parameter: str, value: Optional[float]) -> None:
    """Write to the old flat processed_data collection for API backward-compat."""
    if value is None:
        return
    try:
        processed_collection.update_one(
            {"parameter": parameter, "date": _day(date)},
            {"$set": {
                "parameter":  parameter,
                "value":      value,
                "date":       _day(date),
                "created_at": datetime.utcnow(),
            }},
            upsert=True,
        )
    except Exception:
        pass


def save_processed_data(
    parameter: str,
    value: float,
    date: datetime,
    *,
    raster_path: Optional[str] = None,
    metadata: Optional[Dict] = None,
) -> None:
    """
    Write to the legacy flat processed_data collection.
    Also optionally records raster_path and metadata as extra fields.
    Called by processor.py for backward-compat.
    """
    try:
        doc: Dict[str, Any] = {
            "parameter":  parameter,
            "value":      value,
            "date":       _day(date),
            "created_at": datetime.utcnow(),
        }
        if raster_path:
            doc["raster_path"] = raster_path
        if metadata:
            doc["metadata"] = metadata

        processed_collection.update_one(
            {"parameter": parameter, "date": _day(date)},
            {"$set": doc},
            upsert=True,
        )
    except Exception as e:
        logger.error(f"save_processed_data error: {e}")

"""
mongo_additions.py  (updated)
─────────────────────────────────────────────────────────────────────────────
Paste these additions into your existing mongo.py.

Two-collection design per product (why):
  ┌──────────────────┬──────────────────────────────────────────────────────┐
  │ pet_col          │ One record per downloaded daily INSAT file            │
  │                  │ image_date = calendar date of the file                │
  │                  │ Purpose: idempotency — never re-download              │
  ├──────────────────┼──────────────────────────────────────────────────────┤
  │ pet_stats_col    │ One record per Sentinel overpass date                 │
  │                  │ sentinel_date = Sentinel scene date                   │
  │                  │ Stores: interval_start, interval_end, n_days,         │
  │                  │   mean/min/max/sum over the 5-day window (mm)         │
  │                  │ Purpose: traceability + SARIMAX training input        │
  └──────────────────┴──────────────────────────────────────────────────────┘
Same structure for rain_col / rain_stats_col.
"""

# ═══════════════════════════════════════════════════════════════════════════
# SECTION A — paste after:  iwr_col = _db["iwr_data"]
# ═══════════════════════════════════════════════════════════════════════════

"""
# Daily INSAT download tracking (idempotency)
pet_col        = _db["pet_data"]       # one doc per downloaded daily PET file
rain_col       = _db["rain_data"]      # one doc per downloaded daily rain file

# Interval aggregates tied to each Sentinel scene
pet_stats_col  = _db["pet_stats"]      # 5-day summed PET per Sentinel date
rain_stats_col = _db["rain_stats"]     # 5-day summed rain per Sentinel date
"""

# ═══════════════════════════════════════════════════════════════════════════
# SECTION B — update _STEP_COLLECTIONS dict
# ═══════════════════════════════════════════════════════════════════════════

"""
_STEP_COLLECTIONS: Dict[str, Any] = {
    "sentinel":   sentinel_col,
    "savi":       savi_col,
    "kc":         kc_col,
    "etc":        etc_col,
    "cwr":        cwr_col,
    "iwr":        iwr_col,
    "pet":        pet_col,
    "rain":       rain_col,
    "pet_stats":  pet_stats_col,
    "rain_stats": rain_stats_col,
}
"""

# ═══════════════════════════════════════════════════════════════════════════
# SECTION C — inside _ensure_indexes(), add after the iwr index block
# ═══════════════════════════════════════════════════════════════════════════

"""
    # Daily download collections — unique per calendar date
    for col in (pet_col, rain_col):
        col.create_index(
            [("image_date", ASCENDING)],
            unique=True,
            name="idx_image_date_unique",
        )

    # Interval stats — unique per Sentinel overpass date
    for col in (pet_stats_col, rain_stats_col):
        col.create_index(
            [("sentinel_date", ASCENDING)],
            unique=True,
            name="idx_sentinel_date_unique",
        )
"""

# ═══════════════════════════════════════════════════════════════════════════
# SECTION D — paste at the bottom of mongo.py
# ═══════════════════════════════════════════════════════════════════════════

# ── Daily download helpers ─────────────────────────────────────────────────

def is_pet_downloaded(date):
    """True if the daily INSAT PET file for `date` is already in DB."""
    return _is_processed(pet_col, date)


def mark_pet_downloaded(date, filepath: str) -> bool:
    """Record that the INSAT PET file for `date` has been downloaded."""
    return _mark_processed(pet_col, date, filepath)


def is_rain_downloaded(date) -> bool:
    """True if the daily INSAT rainfall file for `date` is already in DB."""
    return _is_processed(rain_col, date)


def mark_rain_downloaded(date, filepath: str) -> bool:
    """Record that the INSAT rainfall file for `date` has been downloaded."""
    return _mark_processed(rain_col, date, filepath)


# ── Interval stats helpers ─────────────────────────────────────────────────

def save_pet_interval_stats(
    sentinel_date,
    interval_start,
    interval_end,
    n_days: int,
    pixel_stats: dict,
) -> bool:
    """
    Store 5-day aggregated PET statistics for a Sentinel scene.
    Called from processor.select_pet_sum() after computing the interval total.

    pixel_stats keys expected:  sum, mean, min, max  (all in mm)

    Example document stored in pet_stats:
    {
        sentinel_date:   ISODate("2025-01-07"),
        interval_start:  ISODate("2025-01-02"),
        interval_end:    ISODate("2025-01-07"),
        n_days:          5,
        sum_mm:          12.4,        <- total ETo over interval (feed to ETc)
        mean_mm_per_day: 2.48,        <- average daily ETo
        mean_mm:         12.4,        <- same as sum for the interval mean pixel
        min_mm:          0.1,         <- spatial minimum across wheat pixels
        max_mm:          4.2,         <- spatial maximum
        units:           "mm_per_interval",
        updated_at:      ISODate(...)
    }
    """
    try:
        doc = {
            "sentinel_date":   _day(sentinel_date),
            "interval_start":  _day(interval_start),
            "interval_end":    _day(interval_end),
            "n_days":          n_days,
            "sum_mm":          float(pixel_stats.get("sum",  0.0)),
            "mean_mm_per_day": float(pixel_stats.get("sum",  0.0)) / max(n_days, 1),
            "mean_mm":         float(pixel_stats.get("mean", 0.0)),
            "min_mm":          float(pixel_stats.get("min",  0.0)),
            "max_mm":          float(pixel_stats.get("max",  0.0)),
            "units":           "mm_per_interval",
            "updated_at":      datetime.utcnow(),
        }
        pet_stats_col.update_one(
            {"sentinel_date": _day(sentinel_date)},
            {"$set": doc},
            upsert=True,
        )
        logger.debug(
            f"PET stats saved for {sentinel_date.date()}: "
            f"sum={doc['sum_mm']:.2f} mm over {n_days} days"
        )
        return True
    except Exception as e:
        logger.error(f"save_pet_interval_stats error: {e}")
        return False


def save_rain_interval_stats(
    sentinel_date,
    interval_start,
    interval_end,
    n_days: int,
    pixel_stats: dict,
) -> bool:
    """
    Store 5-day aggregated rainfall statistics for a Sentinel scene.
    Called from processor.select_rainfall_sum().

    Example document stored in rain_stats:
    {
        sentinel_date:    ISODate("2025-01-07"),
        interval_start:   ISODate("2025-01-02"),
        interval_end:     ISODate("2025-01-07"),
        n_days:           5,
        sum_mm:           8.3,         <- total rainfall (feed to IWR)
        mean_mm_per_day:  1.66,
        mean_mm:          8.3,
        min_mm:           0.0,
        max_mm:           6.1,
        eff_rain_sum_mm:  null,        <- filled in by calculate_iwr()
        units:            "mm_per_interval",
        updated_at:       ISODate(...)
    }
    """
    try:
        doc = {
            "sentinel_date":   _day(sentinel_date),
            "interval_start":  _day(interval_start),
            "interval_end":    _day(interval_end),
            "n_days":          n_days,
            "sum_mm":          float(pixel_stats.get("sum",  0.0)),
            "mean_mm_per_day": float(pixel_stats.get("sum",  0.0)) / max(n_days, 1),
            "mean_mm":         float(pixel_stats.get("mean", 0.0)),
            "min_mm":          float(pixel_stats.get("min",  0.0)),
            "max_mm":          float(pixel_stats.get("max",  0.0)),
            "eff_rain_sum_mm": None,   # filled later by calculate_iwr
            "units":           "mm_per_interval",
            "updated_at":      datetime.utcnow(),
        }
        rain_stats_col.update_one(
            {"sentinel_date": _day(sentinel_date)},
            {"$set": doc},
            upsert=True,
        )
        logger.debug(
            f"Rain stats saved for {sentinel_date.date()}: "
            f"sum={doc['sum_mm']:.2f} mm over {n_days} days"
        )
        return True
    except Exception as e:
        logger.error(f"save_rain_interval_stats error: {e}")
        return False


def update_rain_eff_rain(sentinel_date, eff_rain_sum_mm: float) -> bool:
    """
    Back-fill the effective_rainfall field after IWR calculation.
    Called from processor.calculate_iwr().
    """
    try:
        rain_stats_col.update_one(
            {"sentinel_date": _day(sentinel_date)},
            {"$set": {
                "eff_rain_sum_mm": float(eff_rain_sum_mm),
                "updated_at":      datetime.utcnow(),
            }},
        )
        return True
    except Exception as e:
        logger.error(f"update_rain_eff_rain error: {e}")
        return False


def get_pet_stats_for_date(sentinel_date) -> dict:
    """Retrieve stored PET interval stats for a given Sentinel date."""
    return pet_stats_col.find_one(
        {"sentinel_date": _day(sentinel_date)}, {"_id": 0}
    )


def get_rain_stats_for_date(sentinel_date) -> dict:
    """Retrieve stored rainfall interval stats for a given Sentinel date."""
    return rain_stats_col.find_one(
        {"sentinel_date": _day(sentinel_date)}, {"_id": 0}
    )


def get_all_pet_stats(season_start, season_end) -> list:
    """All PET stats in a season window — for SARIMAX training."""
    return list(
        pet_stats_col.find(
            {"sentinel_date": {
                "$gte": _day(season_start),
                "$lte": _day(season_end),
            }},
            {"_id": 0},
            sort=[("sentinel_date", 1)],
        )
    )


def get_all_rain_stats(season_start, season_end) -> list:
    """All rainfall stats in a season window — for SARIMAX training."""
    return list(
        rain_stats_col.find(
            {"sentinel_date": {
                "$gte": _day(season_start),
                "$lte": _day(season_end),
            }},
            {"_id": 0},
            sort=[("sentinel_date", 1)],
        )
    )


# ── Utility ────────────────────────────────────────────────────────────────

def count_documents(collection) -> int:
    return collection.count_documents({})

def get_latest_processed_date() -> Optional[datetime]:
    doc = processed_collection.find_one(sort=[("date", -1)])
    return doc["date"] if doc else None

def get_db():
    return _db

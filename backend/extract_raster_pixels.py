import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import rasterio
from rasterio.transform import rowcol, xy
from rasterio.warp import transform as warp_transform
from rasterio.windows import Window

from config import DIRECTORIES

logger = logging.getLogger(__name__)


# Direct raster source of truth for historical pixel values.
HISTORY_DIR = DIRECTORIES["export"]["geoserver"] / "history"
RASTER_PARAMS: Tuple[str, ...] = ("savi", "kc", "cwr", "iwr", "etc")
NODATA = -9999.0
EXTRA_NODATA_VALUES = (-9999.0, -999.0)
WGS84_CRS_NAMES = {"EPSG:4326", "OGC:CRS84"}
SEASON_START_MONTH = 11
SEASON_END_MONTH = 4
SEASON_MONTHS = {11, 12, 1, 2, 3, 4}
MAX_SEASONS = 5


class RasterPixelError(Exception):
    """Base exception for raster pixel lookup failures."""


class RasterGridUnavailable(RasterPixelError):
    """Raised when no history raster can be used as the reference grid."""


class RasterCoordinateError(RasterPixelError):
    """Raised when a coordinate cannot be transformed into raster space."""


class RasterOutOfBoundsError(RasterPixelError):
    """Raised when a coordinate falls outside the reference raster grid."""


class RasterLookupCancelled(RasterPixelError):
    """Raised when a newer pixel request supersedes this lookup."""


_PIXEL_GRID: Optional[Dict] = None
_HISTORY_FILE_CACHE: Dict[str, List[Tuple[datetime, Path]]] = {}
_DATE_RE = re.compile(r"(\d{8})")


def get_season_id(date: datetime) -> Optional[str]:
    if date.month >= SEASON_START_MONTH:
        return f"{date.year}-{str(date.year + 1)[-2:]}"
    if date.month <= SEASON_END_MONTH:
        return f"{date.year - 1}-{str(date.year)[-2:]}"
    return None


def is_in_season(date: datetime) -> bool:
    return date.month in SEASON_MONTHS


def get_allowed_season_ids(today: Optional[datetime] = None) -> List[str]:
    today = today or datetime.utcnow()
    current = get_season_id(today)
    if current is None:
        anchor_year = today.year - 1
        current = f"{anchor_year}-{str(anchor_year + 1)[-2:]}"

    anchor_start_year = int(current.split("-")[0])
    seasons = []
    for i in range(MAX_SEASONS):
        year = anchor_start_year - i
        seasons.append(f"{year}-{str(year + 1)[-2:]}")
    return seasons


def clear_raster_pixel_cache() -> None:
    """Clear cached grid and file metadata, useful after regenerating rasters."""
    global _PIXEL_GRID
    _PIXEL_GRID = None
    _HISTORY_FILE_CACHE.clear()


def _is_wgs84(crs) -> bool:
    return crs is None or str(crs).upper() in WGS84_CRS_NAMES


def _param_dir(param: str) -> Path:
    return HISTORY_DIR / param.lower()


def parse_date_from_name(name: str) -> Optional[datetime]:
    match = _DATE_RE.search(name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d")
    except ValueError:
        return None


def acquisition_date_for_raster(tif_path: Path) -> Optional[datetime]:
    """
    Return a raster acquisition date from tags first, then from an 8-digit
    filename date. Slot-named history rasters such as savi_today.tif rely on
    the acquisition_date tag written during history raster generation.
    """
    try:
        with rasterio.open(tif_path) as src:
            tags = src.tags()
        raw_date = tags.get("acquisition_date") or tags.get("reference_date")
        if raw_date:
            return datetime.strptime(raw_date[:10], "%Y-%m-%d")
    except Exception as exc:
        logger.warning("[pixel-ts] cannot read date tag from %s: %s", tif_path.name, exc)

    return parse_date_from_name(tif_path.name)


def history_files_for_param(param: str, refresh: bool = False) -> List[Tuple[datetime, Path]]:
    """
    Return all dated history rasters for one parameter, sorted by date.

    The function caches the date/path list because a single pixel trend request
    otherwise has to reopen every GeoTIFF just to inspect tags.
    """
    param = param.lower()
    if not refresh and param in _HISTORY_FILE_CACHE:
        return _HISTORY_FILE_CACHE[param]

    files: List[Tuple[datetime, Path]] = []
    for path in sorted(_param_dir(param).glob(f"{param}_*.tif")):
        date_obj = acquisition_date_for_raster(path)
        if date_obj is not None:
            files.append((date_obj, path))

    files.sort(key=lambda item: item[0])
    _HISTORY_FILE_CACHE[param] = files
    return files


def get_pixel_grid(params: Sequence[str] = RASTER_PARAMS) -> Dict:
    """
    Return the reference grid used by the displayed history rasters.

    A clicked map coordinate is first converted to this grid's row/col. Every
    same-grid history raster is then sampled by that exact row/col so the chart
    uses the displayed raster pixel, not a separate Parquet key.
    """
    global _PIXEL_GRID
    if _PIXEL_GRID is not None:
        return _PIXEL_GRID

    for param in params:
        param = param.lower()
        files = sorted(_param_dir(param).glob(f"{param}_*.tif"))
        if not files:
            continue

        today_path = _param_dir(param) / f"{param}_today.tif"
        ref_path = today_path if today_path.exists() else files[0]
        try:
            with rasterio.open(ref_path) as ref:
                _PIXEL_GRID = {
                    "path": ref_path,
                    "crs": ref.crs,
                    "transform": ref.transform,
                    "width": ref.width,
                    "height": ref.height,
                }
            logger.info(
                "Pixel history grid loaded from %s: %sx%s %s",
                ref_path.name,
                _PIXEL_GRID["width"],
                _PIXEL_GRID["height"],
                _PIXEL_GRID["crs"],
            )
            return _PIXEL_GRID
        except Exception as exc:
            logger.warning("[pixel-ts] cannot read grid from %s: %s", ref_path, exc)

    raise RasterGridUnavailable("History raster grid is not available for pixel lookup.")


def pixel_from_latlon(lat: float, lon: float, params: Sequence[str] = RASTER_PARAMS) -> Dict:
    """Convert a WGS84 coordinate to the reference history-raster pixel."""
    grid = get_pixel_grid(params=params)

    try:
        if _is_wgs84(grid["crs"]):
            x, y = float(lon), float(lat)
        else:
            xs, ys = warp_transform("EPSG:4326", grid["crs"], [lon], [lat])
            x, y = float(xs[0]), float(ys[0])

        row, col = rowcol(grid["transform"], x, y)
        row, col = int(row), int(col)
    except Exception as exc:
        raise RasterCoordinateError("Invalid coordinate for pixel lookup.") from exc

    if row < 0 or row >= grid["height"] or col < 0 or col >= grid["width"]:
        raise RasterOutOfBoundsError("Clicked point is outside the history raster grid.")

    center_x, center_y = xy(grid["transform"], row, col)
    if _is_wgs84(grid["crs"]):
        center_lon = float(center_x)
        center_lat = float(center_y)
    else:
        center_lons, center_lats = warp_transform(
            grid["crs"],
            "EPSG:4326",
            [float(center_x)],
            [float(center_y)],
        )
        center_lon = float(center_lons[0])
        center_lat = float(center_lats[0])

    return {
        "pixel_id": f"{row}_{col}",
        "row": row,
        "col": col,
        "latitude": center_lat,
        "longitude": center_lon,
        "native_x": float(center_x),
        "native_y": float(center_y),
    }


def _same_grid(src, grid: Dict, row: int, col: int) -> bool:
    return (
        row >= 0
        and col >= 0
        and row < src.height
        and col < src.width
        and str(src.crs) == str(grid["crs"])
        and src.transform == grid["transform"]
    )


def _is_valid_value(value: float, nodata: Optional[float]) -> bool:
    if not np.isfinite(value):
        return False
    invalid_values = set(EXTRA_NODATA_VALUES)
    if nodata is not None:
        invalid_values.add(float(nodata))
    return not any(np.isclose(value, invalid) for invalid in invalid_values)


def read_history_pixel_value(path: Path, pixel: Dict, params: Sequence[str] = RASTER_PARAMS) -> Optional[float]:
    """
    Read one pixel value from one history raster.

    Same-grid rasters are read by exact row/col. If a historical raster ever has
    a different transform, it is sampled at the selected pixel center in that
    raster's own CRS.
    """
    if not path.exists():
        return None

    try:
        grid = get_pixel_grid(params=params)
        row = int(pixel["row"])
        col = int(pixel["col"])

        with rasterio.open(path) as src:
            if _same_grid(src, grid, row, col):
                value = src.read(1, window=Window(col, row, 1, 1))[0, 0]
            else:
                x, y = float(pixel["longitude"]), float(pixel["latitude"])
                if not _is_wgs84(src.crs):
                    xs, ys = warp_transform("EPSG:4326", src.crs, [x], [y])
                    x, y = float(xs[0]), float(ys[0])
                value = list(src.sample([(x, y)]))[0][0]

            nodata = src.nodata

        value = float(value)
        if not _is_valid_value(value, nodata):
            return None
        return round(value, 4)
    except Exception as exc:
        logger.warning("[pixel-ts] cannot read %s: %s", path.name, exc)
        return None


def normalise_pixel_records(
    rows: Iterable[Tuple[datetime, Optional[float]]],
    allowed_seasons: Optional[Iterable[str]] = None,
    season_id_fn: Optional[Callable[[datetime], Optional[str]]] = None,
    in_season_fn: Optional[Callable[[datetime], bool]] = None,
) -> List[Dict]:
    """Convert raw date/value tuples into sorted API records."""
    allowed = set(allowed_seasons) if allowed_seasons is not None else None
    records = []
    seen_dates = set()

    for raw_date, raw_value in rows:
        if raw_value is None:
            continue

        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if not np.isfinite(value):
            continue

        date_obj = raw_date if isinstance(raw_date, datetime) else None
        if date_obj is None:
            try:
                date_obj = datetime.strptime(str(raw_date)[:10], "%Y-%m-%d")
            except ValueError:
                continue

        if in_season_fn is not None and not in_season_fn(date_obj):
            continue
        if allowed is not None and season_id_fn is not None:
            season_id = season_id_fn(date_obj)
            if not season_id or season_id not in allowed:
                continue

        date_str = date_obj.strftime("%Y-%m-%d")
        if date_str in seen_dates:
            continue

        seen_dates.add(date_str)
        records.append({"date": date_str, "value": round(value, 4)})

    records.sort(key=lambda item: item["date"])
    return records


def pixel_timeseries_for_pixel(
    pixel: Dict,
    params: Sequence[str] = RASTER_PARAMS,
    allowed_seasons: Optional[Iterable[str]] = None,
    season_id_fn: Optional[Callable[[datetime], Optional[str]]] = None,
    in_season_fn: Optional[Callable[[datetime], bool]] = None,
    cancelled_fn: Optional[Callable[[], bool]] = None,
) -> Dict[str, List[Dict]]:
    """Read all dated history rasters for a selected pixel."""
    result: Dict[str, List[Dict]] = {}

    for param in params:
        if cancelled_fn and cancelled_fn():
            raise RasterLookupCancelled("Pixel lookup was superseded by a newer request.")

        rows = []
        for date_obj, raster_path in history_files_for_param(param):
            if cancelled_fn and cancelled_fn():
                raise RasterLookupCancelled("Pixel lookup was superseded by a newer request.")

            value = read_history_pixel_value(raster_path, pixel, params=params)
            if value is not None:
                rows.append((date_obj, value))
        result[param] = normalise_pixel_records(
            rows,
            allowed_seasons=allowed_seasons,
            season_id_fn=season_id_fn,
            in_season_fn=in_season_fn,
        )

    return result


def raster_mean_value(path: Path) -> Optional[float]:
    """Return a raster mean from tags when available, otherwise compute it."""
    try:
        with rasterio.open(path) as src:
            tag_mean = src.tags().get("mean")
            if tag_mean not in (None, ""):
                value = float(tag_mean)
                if np.isfinite(value):
                    return value

            data = src.read(1).astype(np.float64)
            nodata = src.nodata
    except Exception as exc:
        logger.warning("[graph] cannot read mean from %s: %s", path.name, exc)
        return None

    if nodata is not None:
        data[np.isclose(data, float(nodata))] = np.nan
    for invalid in EXTRA_NODATA_VALUES:
        data[np.isclose(data, invalid)] = np.nan

    if np.all(np.isnan(data)):
        return None
    value = float(np.nanmean(data))
    return value if np.isfinite(value) else None

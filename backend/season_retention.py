"""Shared rolling-retention rules for Nov-Apr irrigation seasons."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union


SEASON_START_MONTH = 11
SEASON_END_MONTH = 4
SEASON_MONTHS = frozenset({11, 12, 1, 2, 3, 4})
MAX_SEASONS = 5

_FILENAME_DATE_RE = re.compile(r"(?<!\d)(\d{8})(?!\d)")
_TAG_DATE_FORMATS = ("%Y-%m-%d", "%Y%m%d")

DateValue = Union[datetime, date]
DateResolver = Callable[[Path], Optional[datetime]]


def _as_datetime(value: DateValue) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    return datetime(value.year, value.month, value.day)


def get_season_id(value: DateValue) -> Optional[str]:
    """Return the Nov-Apr season label for a date, or None outside the season."""
    value = _as_datetime(value)
    if value.month >= SEASON_START_MONTH:
        return f"{value.year}-{str(value.year + 1)[-2:]}"
    if value.month <= SEASON_END_MONTH:
        return f"{value.year - 1}-{str(value.year)[-2:]}"
    return None


def is_in_season(value: DateValue) -> bool:
    return _as_datetime(value).month in SEASON_MONTHS


def get_allowed_season_ids(
    now: Optional[DateValue] = None,
    max_seasons: int = MAX_SEASONS,
) -> List[str]:
    """Newest-first labels for the rolling retention window."""
    anchor_date = _as_datetime(now or datetime.utcnow())
    current = get_season_id(anchor_date)
    anchor_year = int(current.split("-")[0]) if current else anchor_date.year - 1
    return [
        f"{year}-{str(year + 1)[-2:]}"
        for year in range(anchor_year, anchor_year - max_seasons, -1)
    ]


def retained_season_ranges(
    now: Optional[DateValue] = None,
    max_seasons: int = MAX_SEASONS,
) -> List[Tuple[datetime, datetime]]:
    """Inclusive date ranges for every retained Nov-Apr season."""
    ranges: List[Tuple[datetime, datetime]] = []
    for season_id in get_allowed_season_ids(now=now, max_seasons=max_seasons):
        start_year = int(season_id.split("-")[0])
        ranges.append((datetime(start_year, 11, 1), datetime(start_year + 1, 4, 30)))
    return ranges


def oldest_retained_season_start(
    now: Optional[DateValue] = None,
    max_seasons: int = MAX_SEASONS,
) -> datetime:
    """The first day of the oldest season still allowed by retention."""
    return retained_season_ranges(now=now, max_seasons=max_seasons)[-1][0]


def is_retained_date(
    value: Optional[DateValue],
    now: Optional[DateValue] = None,
    max_seasons: int = MAX_SEASONS,
) -> bool:
    if value is None or not is_in_season(value):
        return False
    return get_season_id(value) in set(get_allowed_season_ids(now=now, max_seasons=max_seasons))


def parse_date_from_filename(name: str) -> Optional[datetime]:
    """Extract a YYYYMMDD acquisition date from a pipeline raster filename."""
    match = _FILENAME_DATE_RE.search(name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d")
    except ValueError:
        return None


def _parse_tag_date(value: str) -> Optional[datetime]:
    value = value.strip()
    for date_format in _TAG_DATE_FORMATS:
        try:
            return datetime.strptime(value[:10], date_format)
        except ValueError:
            continue
    return None


def raster_acquisition_date(path: Path) -> Optional[datetime]:
    """Read a raster's source date from metadata, with a filename fallback."""
    try:
        import rasterio

        with rasterio.open(path) as raster:
            tags = raster.tags()
        for key in ("acquisition_date", "reference_date"):
            value = tags.get(key)
            if value:
                parsed = _parse_tag_date(value)
                if parsed is not None:
                    return parsed
    except Exception:
        pass
    return parse_date_from_filename(path.name)


def prune_raster_directory(
    directory: Path,
    *,
    now: Optional[DateValue] = None,
    date_resolver: DateResolver = raster_acquisition_date,
    delete_unknown: bool = False,
) -> Dict[str, int]:
    """Delete stale GeoTIFFs in one known pipeline output directory.

    Unknown files are kept by default. Generated slot files in GeoServer output
    directories can opt into ``delete_unknown`` because they are regenerated
    from the retained processed rasters on every successful pipeline run.
    """
    result = {"removed": 0, "kept": 0, "unknown": 0, "errors": 0}
    if not directory.exists():
        return result

    paths = sorted({*directory.glob("*.tif"), *directory.glob("*.tiff")})
    for path in paths:
        acquisition_date = date_resolver(path)
        should_remove = acquisition_date is None and delete_unknown
        if acquisition_date is not None:
            should_remove = not is_retained_date(acquisition_date, now=now)

        if not should_remove:
            if acquisition_date is None:
                result["unknown"] += 1
            else:
                result["kept"] += 1
            continue

        try:
            path.unlink()
            result["removed"] += 1
        except OSError:
            result["errors"] += 1
    return result


def cleanup_pipeline_rasters(
    directories: Mapping[str, Mapping[str, Path]],
    *,
    extra_forecast_directories: Iterable[Path] = (),
    now: Optional[DateValue] = None,
) -> Dict[str, object]:
    """Apply rolling retention to processed and exported pipeline rasters."""
    allowed_seasons = get_allowed_season_ids(now=now)
    print(
        f"[retention] Starting raster cleanup. Keeping seasons: {', '.join(allowed_seasons)}",
        flush=True,
    )

    processed = directories["processed"]
    geoserver_dir = directories["export"]["geoserver"]
    history_dir = geoserver_dir / "history"
    forecast_dir = geoserver_dir / "forecast"

    managed_directories: List[Tuple[str, Path, bool]] = [
        ("processed/savi", processed["savi"], False),
        ("processed/kc", processed["kc"], False),
        ("processed/etc", processed["ETc"], False),
        ("processed/cwr", processed["cwr"], False),
        ("processed/iwr", processed["iwr"], False),
    ]
    managed_directories.extend(
        (f"export/geoserver/history/{param}", history_dir / param, True)
        for param in ("savi", "kc", "etc", "cwr", "iwr")
    )
    managed_directories.extend(
        (f"export/geoserver/forecast/{param}", forecast_dir / param, True)
        for param in ("cwr", "iwr")
    )

    known_paths = {path.resolve() for _, path, _ in managed_directories}
    for directory in extra_forecast_directories:
        if directory.resolve() not in known_paths:
            managed_directories.append(("export/forecast", directory, False))
            known_paths.add(directory.resolve())

    by_directory: Dict[str, Dict[str, int]] = {}
    totals = {"removed": 0, "kept": 0, "unknown": 0, "errors": 0}
    for label, directory, delete_unknown in managed_directories:
        print(f"[retention] Scanning {label}: {directory}", flush=True)
        result = prune_raster_directory(
            directory,
            now=now,
            delete_unknown=delete_unknown,
        )
        by_directory[label] = result
        for key in totals:
            totals[key] += result[key]
        print(
            "[retention] "
            f"{label} -> removed={result['removed']} kept={result['kept']} "
            f"unknown={result['unknown']} errors={result['errors']}",
            flush=True,
        )

    print(
        "[retention] Cleanup complete: "
        f"removed={totals['removed']} kept={totals['kept']} "
        f"unknown={totals['unknown']} errors={totals['errors']}",
        flush=True,
    )
    return {
        "allowed_seasons": allowed_seasons,
        "directories": by_directory,
        **totals,
    }


def out_of_retention_query(
    field: str,
    *,
    now: Optional[DateValue] = None,
) -> Dict[str, object]:
    """MongoDB query that selects dated records outside the rolling window."""
    valid_ranges = [
        {field: {"$gte": start, "$lte": end}}
        for start, end in retained_season_ranges(now=now)
    ]
    return {
        "$and": [
            {field: {"$exists": True}},
            {"$nor": valid_ranges},
        ]
    }

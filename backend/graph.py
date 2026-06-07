import logging
import math
from calendar import monthrange
from collections import defaultdict
from typing import Dict, List, Tuple

from fastapi import APIRouter, HTTPException, Query

from extract_raster_pixels import (
    get_allowed_season_ids,
    get_season_id,
    history_files_for_param,
    is_in_season,
    raster_mean_value,
)


router = APIRouter(
    prefix="/api/graph",
    tags=["Graph"],
)

logger = logging.getLogger(__name__)

LAYER_CONFIGS = {
    "savi": {
        "full_name": "Soil Adjusted Vegetation Index",
        "unit": "index",
        "monthly_unit": "index",
    },
    "kc": {
        "full_name": "Crop Coefficient",
        "unit": "coefficient",
        "monthly_unit": "coefficient",
    },
    "cwr": {
        "full_name": "Crop Water Requirement",
        "unit": "mm/day",
        "monthly_unit": "mm/day",
        "cumulative_unit": "mm",
    },
    "etc": {
        "full_name": "Actual Evapotranspiration",
        "unit": "mm/day",
        "monthly_unit": "mm/day",
    },
    "iwr": {
        "full_name": "Irrigation Water Requirement",
        "unit": "mm/day",
        "monthly_unit": "mm/day",
        "cumulative_unit": "mm",
    },
}

CUMULATIVE_LAYERS = {"cwr", "iwr"}

MONTH_NAMES = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}

SEASON_MONTHS = [11, 12, 1, 2, 3, 4]
SEASON_MONTH_INDEX = {month: index for index, month in enumerate(SEASON_MONTHS)}


def _season_start_year(season_id: str) -> int:
    try:
        return int(str(season_id).split("-")[0])
    except (TypeError, ValueError):
        return 0


def _season_month_year(season_id: str, month: int) -> int:
    start_year = _season_start_year(season_id)
    return start_year if month in (11, 12) else start_year + 1


def _history_monthly_means(layer: str) -> List[Dict]:
    grouped: Dict[Tuple[str, int], List[float]] = defaultdict(list)
    allowed_seasons = set(get_allowed_season_ids())

    for date_obj, raster_path in history_files_for_param(layer):
        season_id = get_season_id(date_obj)
        if not is_in_season(date_obj) or season_id not in allowed_seasons:
            continue

        value = raster_mean_value(raster_path)
        if value is None or not math.isfinite(value):
            continue
        grouped[(season_id, date_obj.month)].append(float(value))

    results = []
    for (season, month), values in sorted(
        grouped.items(),
        key=lambda item: (_season_start_year(item[0][0]), SEASON_MONTH_INDEX.get(item[0][1], 99)),
    ):
        if not values:
            continue
        results.append(
            {
                "season": season,
                "year": _season_start_year(season),
                "month": month,
                "monthly_avg": sum(values) / len(values),
            }
        )
    return results


@router.get("/seasonal-chart")
async def seasonal_chart(
    layer: str = Query(...),
    mode: str = Query("monthly"),
):
    layer = layer.lower()
    mode = mode.lower()

    if layer not in LAYER_CONFIGS:
        raise HTTPException(status_code=400, detail="Invalid layer")
    if mode not in {"monthly", "cumulative"}:
        raise HTTPException(status_code=400, detail="Invalid chart mode")
    if mode == "cumulative" and layer not in CUMULATIVE_LAYERS:
        raise HTTPException(
            status_code=400,
            detail="Cumulative trend is available only for CWR and IWR",
        )

    results = _history_monthly_means(layer)
    if not results:
        raise HTTPException(status_code=404, detail="No raster history data found")

    seasons = sorted({r["season"] for r in results}, key=_season_start_year)
    months = [month for month in SEASON_MONTHS if any(r["month"] == month for r in results)]

    season_map: Dict[str, Dict[int, float]] = {}
    for row in results:
        season_map.setdefault(row["season"], {})
        season_map[row["season"]][row["month"]] = row["monthly_avg"]

    chart_data = []
    for season in seasons:
        monthly_vals = []
        cumulative_vals = []
        running = 0.0

        for month in months:
            value = season_map.get(season, {}).get(month)
            if value is not None and math.isfinite(value):
                monthly_vals.append(round(value, 6))
                if layer in CUMULATIVE_LAYERS:
                    year_for_month = _season_month_year(season, month)
                    running += value * monthrange(year_for_month, month)[1]
                else:
                    running += value
                cumulative_vals.append(round(running, 6))
            else:
                monthly_vals.append(None)
                cumulative_vals.append(None)

        entry = {
            "season": season,
            "year": _season_start_year(season),
        }
        if mode == "monthly":
            entry["monthly"] = monthly_vals
        elif mode == "cumulative":
            entry["cumulative"] = cumulative_vals
        else:
            entry["monthly"] = monthly_vals
            entry["cumulative"] = cumulative_vals
        chart_data.append(entry)

    return {
        "layer": layer,
        "layer_config": LAYER_CONFIGS[layer],
        "mode": mode,
        "seasons": seasons,
        "years": [_season_start_year(season) for season in seasons],
        "months": months,
        "month_names": [MONTH_NAMES[m] for m in months],
        "data": chart_data,
        "source": "history_rasters",
        "allowed_layers": {
            "monthly": list(LAYER_CONFIGS.keys()),
            "cumulative": sorted(CUMULATIVE_LAYERS),
        },
        "calculation": {
            "monthly": "Mean of valid history GeoTIFF pixel values for each Rabi month.",
            "cumulative": (
                "For CWR/IWR only: monthly mean daily rate multiplied by calendar days "
                "in that month, then accumulated across the Rabi season."
            ),
        },
    }

"""MOSDAC GeoTIFF downloader for the Udham Singh Nagar irrigation pipeline.

Flow: SFTP order discovery -> GeoTIFF download/size validation -> EPSG:4326
normalisation -> USN polygon crop -> LZW GeoTIFF -> MongoDB metadata.
"""
from __future__ import annotations

import datetime
import logging
import os
import re
import socket
import stat as stat_mod
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import rasterio
import schedule
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.mask import mask as rio_mask
from rasterio.warp import calculate_default_transform, reproject
from shapely.geometry import mapping, shape

try:
    import pysftp
    SFTP_AVAILABLE = True
except ImportError:
    SFTP_AVAILABLE = False

try:
    from mongo import is_pet_downloaded, is_rain_downloaded, pet_col, rain_col
    from config import BASE_DIR, STUDY_AREA

    BOUNDS = STUDY_AREA["bounds"]
    GEOJSON = STUDY_AREA.get("geojson", {"type": "FeatureCollection", "features": []})
    MONGO_AVAILABLE = True
except ImportError as exc:
    print(f"[WARN] MongoDB / config not available: {exc}")
    BASE_DIR = Path(__file__).resolve().parent
    BOUNDS = {"north": 29.3853, "south": 28.7156, "west": 78.7139, "east": 80.1567}
    GEOJSON = {"type": "FeatureCollection", "features": []}
    MONGO_AVAILABLE = False

HOST = "ftp.mosdac.gov.in"
USER = os.getenv("MOSDAC_USERNAME", "")
PASS = os.getenv("MOSDAC_PASSWORD", "")
MAX_RETRIES = 3
START_DATE = datetime.date(2021, 11, 1)

pet_tif_dir = BASE_DIR / "data" / "raw" / "insat_pet"
rain_tif_dir = BASE_DIR / "data" / "raw" / "insat_rain"
for directory in (pet_tif_dir, rain_tif_dir):
    directory.mkdir(parents=True, exist_ok=True)

log_dir = BASE_DIR / "data" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[logging.FileHandler(log_dir / "mosdac_download.log"), logging.StreamHandler()],
)
logger = logging.getLogger("MOSDAC")


def is_wheat_season(date: datetime.date) -> bool:
    """Extended Rabi collection window: November through September."""
    return date.month in {11, 12, 1, 2, 3, 4, 5, 6, 7, 8, 9}


def _parse_date_from_filename(filename: str) -> Optional[datetime.date]:
    match = re.search(r"3RIMG_(\d{2}[A-Z]{3}\d{4})_", filename.upper())
    if not match:
        return None
    try:
        return datetime.datetime.strptime(match.group(1), "%d%b%Y").date()
    except ValueError:
        return None


def _product_stem(date: datetime.date, product: str) -> str:
    stamp = date.strftime("%d%b%Y").upper()
    code = "L3C_PET_DLY" if product == "pet" else "L3G_IMR_DLY"
    return f"3RIMG_{stamp}_0015_{code}_V01R00"


def _output_path(date: datetime.date, product: str) -> Path:
    folder = pet_tif_dir if product == "pet" else rain_tif_dir
    return folder / f"{_product_stem(date, product)}.tif"


def is_valid_raster(path: Path) -> bool:
    """Return true only for a non-empty, readable GeoTIFF with data and a CRS."""
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with rasterio.open(path) as src:
            return src.driver == "GTiff" and src.count >= 1 and src.width > 0 and src.height > 0
    except (rasterio.errors.RasterioError, OSError, ValueError):
        return False


def _get_usn_shapes() -> Tuple[List[dict], bool]:
    """Return the configured USN polygon, falling back to the configured bbox."""
    features = GEOJSON.get("features", [])
    if features:
        return [mapping(shape(feature["geometry"])) for feature in features], True
    b = BOUNDS
    return [{"type": "Polygon", "coordinates": [[
        [b["west"], b["south"]], [b["east"], b["south"]],
        [b["east"], b["north"]], [b["west"], b["north"]],
        [b["west"], b["south"]],
    ]]}], False


def check_boundary() -> None:
    shapes, polygon = _get_usn_shapes()
    logger.info(
        "USN boundary W=%s E=%s S=%s N=%s; mask=%s; shapes=%s",
        BOUNDS["west"], BOUNDS["east"], BOUNDS["south"], BOUNDS["north"],
        "polygon" if polygon else "bbox", len(shapes),
    )


def _discover_orders(sftp, order_keys: Optional[List[str]] = None) -> Dict:
    """Find GeoTIFF order folders, optionally restricted to scheduler order keys."""
    try:
        entries = sftp.listdir_attr("/Order")
    except Exception as exc:
        raise RuntimeError(f"[ORDERS] Cannot list /Order on SFTP: {exc}") from exc

    all_dirs = [e for e in entries if (e.st_mode is None or stat_mod.S_ISDIR(e.st_mode))]

    requested_keys = set(order_keys or [])
    folders = all_dirs
    if requested_keys:
        matched_dirs = [e for e in all_dirs if e.filename in requested_keys]
        missing_keys = requested_keys - {entry.filename for entry in matched_dirs}
        for key in sorted(missing_keys):
            logger.warning("[ORDERS] Requested order folder is not available: %s", key)

        if matched_dirs:
            folders = matched_dirs
        else:
            # None of the scraped order keys correspond to a real /Order
            # folder (e.g. mosdac_agent.py's MyOrder-page scrape returned a
            # value in the wrong format — MOSDAC's real delivery folders are
            # named like "Jul26_186162", not "ORD_...").  Don't trust a
            # fragile UI-scraped key enough to make Stage 3 silently return
            # nothing; fall back to scanning every /Order folder the same
            # way we do when order_keys is empty from the start.
            logger.warning(
                "[ORDERS] None of the requested keys %s matched a real "
                "/Order folder. Falling back to an unrestricted scan. "
                "Folders actually present on SFTP (newest %d shown): %s",
                sorted(requested_keys),
                min(10, len(all_dirs)),
                sorted((e.filename for e in all_dirs), reverse=True)[:10],
            )
            folders = all_dirs
    folders.sort(key=lambda entry: (entry.st_mtime or 0), reverse=True)
    result: Dict[str, Optional[object]] = {
        "pet_order": None, "rain_order": None, "pet_max_date": None, "rain_max_date": None,
    }
    for entry in folders:
        # if result["pet_order"] and result["rain_order"]:
        #     break
        try:
            files = [name for name in sftp.listdir(f"/Order/{entry.filename}") if name.lower().endswith((".tif", ".tiff"))]
        except Exception as exc:
            logger.debug("[ORDERS] Cannot list %s: %s", entry.filename, exc)
            continue
        for product, marker in (("pet", "L3C_PET"), ("rain", "L3G_IMR")):
            key = f"{product}_order"
            # matched = [name for name in files if marker in name.upper()]

            matched = []

            for attr in sftp.listdir_attr(f"/Order/{entry.filename}"):

                if not attr.filename.lower().endswith(".tif"):
                    continue

                if marker not in attr.filename.upper():
                    continue

                # Ignore incomplete uploads
                if attr.st_size < 500000:   # 500 KB threshold
                    logger.warning(
                        "[ORDERS] Ignoring tiny file %s (%d bytes)",
                        attr.filename,
                        attr.st_size,
                    )
                    continue

                matched.append(attr.filename)
            if matched:
                dates = [
                    d for f in matched
                    if (d := _parse_date_from_filename(f))
                ]

                newest = max(dates) if dates else None

                if (
                    result[f"{product}_max_date"] is None
                    or (
                        newest
                        and newest >= result[f"{product}_max_date"]
                    )
                ):
                    result[key] = entry.filename
                    result[f"{product}_max_date"] = newest

                    logger.info(
                        "[LATEST %s] folder=%s date=%s",
                        product.upper(),
                        entry.filename,
                        newest,
                    )
            # if matched and not result[key]:
            #     dates = [date for name in matched if (date := _parse_date_from_filename(name))]
            #     result[key] = entry.filename
                result[f"{product}_max_date"] = max(dates) if dates else None
                logger.info("[ORDERS] %s folder=%s files=%d max_date=%s", product.upper(), entry.filename, len(matched), result[f"{product}_max_date"])
    return result


def _find_remote_geotiff(sftp, order_id: str, date: datetime.date, product: str) -> Optional[str]:
    marker = "L3C_PET" if product == "pet" else "L3G_IMR"
    stamp = date.strftime("%d%b%Y").upper()
    try:
        files = sftp.listdir(f"/Order/{order_id}")
    except Exception as exc:
        logger.warning("[%s] Cannot list order %s: %s", product.upper(), order_id, exc)
        return None
    # candidates = [
    #     name for name in files
    #     if name.lower().endswith((".tif", ".tiff")) and marker in name.upper() and stamp in name.upper()
    # ]
    candidates = [
        name
        for name in files
        if name.lower().endswith(".tif")
        and marker in name.upper()
    ]

    if not candidates:
        return None

    candidates.sort(reverse=True)

    return candidates[0]
    return sorted(candidates)[0] if candidates else None


def _download_geotiff(sftp, remote_path: str, destination: Path, label: str) -> None:
    """Download to a temporary file and require exact remote/local byte equality."""
    remote_size = sftp.stat(remote_path).st_size
    if not remote_size:
        raise ValueError(f"Remote GeoTIFF is empty: {remote_path}")
    temporary = destination.with_suffix(destination.suffix + ".part")
    destination.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            temporary.unlink(missing_ok=True)
            with sftp.open(remote_path, "rb") as source, temporary.open("wb") as target:
                while chunk := source.read(1024 * 1024):
                    target.write(chunk)
            if temporary.stat().st_size != remote_size:
                raise ValueError(f"size mismatch remote={remote_size} local={temporary.stat().st_size}")
            if not is_valid_raster(temporary):
                raise ValueError("download is not a readable GeoTIFF")
            temporary.replace(destination)
            logger.info("[%s] Downloaded %s (%d bytes)", label, destination.name, remote_size)
            return
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            logger.warning("[%s] download attempt %d/%d failed: %s", label, attempt, MAX_RETRIES, exc)
            if attempt == MAX_RETRIES:
                raise
            time.sleep(2)


def _reproject_to_wgs84(src) -> Tuple[np.ndarray, dict]:
    """Read a raster as EPSG:4326, reprojecting only when the CRS requires it."""
    if src.crs is None:
        logger.warning("Source GeoTIFF has no CRS; treating it as EPSG:4326")
        profile = src.profile.copy()
        profile.update(crs=CRS.from_epsg(4326))
        return src.read(), profile
    if src.crs.to_epsg() == 4326:
        return src.read(), src.profile.copy()
    dst_crs = CRS.from_epsg(4326)
    transform, width, height = calculate_default_transform(src.crs, dst_crs, src.width, src.height, *src.bounds)
    data = np.empty((src.count, height, width), dtype=src.dtypes[0])
    for band in range(1, src.count + 1):
        reproject(
            source=rasterio.band(src, band), destination=data[band - 1],
            src_transform=src.transform, src_crs=src.crs, src_nodata=src.nodata,
            dst_transform=transform, dst_crs=dst_crs, dst_nodata=src.nodata,
            resampling=Resampling.nearest,
        )
    profile = src.profile.copy()
    profile.update(crs=dst_crs, transform=transform, width=width, height=height)
    return data, profile


def _crop_to_usn(source_path: Path, output_path: Path, product: str, order_id: str) -> None:
    """Reproject a downloaded GeoTIFF if needed, then polygon-crop and LZW-compress it."""
    shapes, using_polygon = _get_usn_shapes()
    with rasterio.open(source_path) as src:
        data, profile = _reproject_to_wgs84(src)
        profile.update(driver="GTiff", count=data.shape[0])
        if profile.get("nodata") is None:
            profile.update(nodata=-9999.0)
        with MemoryFile() as memory:
            with memory.open(**profile) as normalized:
                normalized.write(data)
            with memory.open() as normalized:
                cropped, transform = rio_mask(normalized, shapes, crop=True, all_touched=True, filled=True)
                nodata = normalized.nodata if normalized.nodata is not None else -9999.0
    valid = cropped != nodata
    if np.issubdtype(cropped.dtype, np.floating):
        valid &= ~np.isnan(cropped)
    valid_pixels = int(np.count_nonzero(valid[0]))
    if valid_pixels == 0:
        raise ValueError("GeoTIFF does not contain valid pixels inside Udham Singh Nagar")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    out_profile = profile.copy()
    out_profile.update(
        driver="GTiff", height=cropped.shape[1], width=cropped.shape[2],
        transform=transform, crs=CRS.from_epsg(4326), compress="lzw", nodata=nodata,
    )
    if cropped.shape[1] >= 16 and cropped.shape[2] >= 16:
        out_profile.update(tiled=True, blockxsize=16, blockysize=16)
    else:
        out_profile.pop("tiled", None)
        out_profile.pop("blockxsize", None)
        out_profile.pop("blockysize", None)
    tags = {
        "source": "MOSDAC INSAT-3DR", "product": product.upper(), "order_id": order_id,
        "study_area": "Udham Singh Nagar, Uttarakhand",
        "mask_type": "polygon" if using_polygon else "bbox",
        "source_file": source_path.name, "valid_pixels": str(valid_pixels),
        "pipeline": "GeoTIFF->EPSG:4326->polygon_crop->LZW_GeoTIFF",
        "processed_at": datetime.datetime.utcnow().isoformat(),
    }
    with rasterio.open(output_path, "w", **out_profile) as dst:
        dst.write(cropped)
        dst.update_tags(**tags)
    logger.info("[%s] Wrote %s (%dx%d, %d valid pixels)", product.upper(), output_path.name, cropped.shape[2], cropped.shape[1], valid_pixels)


def _to_dt(date: datetime.date) -> datetime.datetime:
    return datetime.datetime.combine(date, datetime.time.min)


def _is_in_db(date: datetime.date, product: str) -> bool:
    if not MONGO_AVAILABLE:
        return False
    return is_pet_downloaded(_to_dt(date)) if product == "pet" else is_rain_downloaded(_to_dt(date))


def _mark_complete(date: datetime.date, product: str, filepath: str, order_id: str = "", extra: Optional[Dict] = None, recovered: bool = False) -> bool:
    if not MONGO_AVAILABLE:
        return False
    now, dt = datetime.datetime.utcnow(), _to_dt(date)
    document: Dict = {
        "image_date": dt, "raster_path": filepath, "output_tif": filepath,
        "download_status": "complete", "processing_status": "complete",
        "downloaded_at": now, "processed_at": now, "order_id": order_id,
        "season": "rabi" if is_wheat_season(date) else "non_rabi", "recovered": recovered,
        "pipeline": "GeoTIFF->EPSG:4326->polygon_crop->LZW_GeoTIFF",
    }
    if extra:
        document.update(extra)
    try:
        collection = pet_col if product == "pet" else rain_col
        collection.update_one({"image_date": dt}, {"$set": document}, upsert=True)
        return True
    except Exception as exc:
        logger.error("[%s] MongoDB metadata update failed: %s", product.upper(), exc)
        return False


def _mark_failed(date: datetime.date, product: str, error: str, order_id: str) -> None:
    if not MONGO_AVAILABLE:
        return
    try:
        collection = pet_col if product == "pet" else rain_col
        collection.update_one({"image_date": _to_dt(date)}, {"$set": {
            "download_status": "failed", "processing_status": "failed", "error": error,
            "failed_at": datetime.datetime.utcnow(), "order_id": order_id,
        }}, upsert=True)
    except Exception as exc:
        logger.error("[%s] MongoDB failure update failed: %s", product.upper(), exc)


def already_complete(date: datetime.date, data_type: str) -> bool:
    output = _output_path(date, data_type)
    if _is_in_db(date, data_type):
        logger.info("[%s] %s already recorded in MongoDB", data_type.upper(), date)
        return True
    if is_valid_raster(output):
        if not _is_in_db(date, data_type):
            _mark_complete(date, data_type, str(output), recovered=True)
        return True
    return False


def _download_product(date: datetime.date, sftp, order_id: Optional[str], product: str) -> bool:
    label = product.upper()
    if already_complete(date, product):
        logger.info("[%s] %s already complete", label, date)
        return True
    if not order_id:
        logger.warning("[%s] %s has no ready GeoTIFF order folder", label, date)
        return False
    output = _output_path(date, product)
    incoming = output.with_suffix(".source.tif")
    try:
        remote_name = _find_remote_geotiff(sftp, order_id, date, product)
        if not remote_name:
            raise FileNotFoundError(f"No {label} GeoTIFF for {date} in /Order/{order_id}")
        _download_geotiff(sftp, f"/Order/{order_id}/{remote_name}", incoming, label)
        _crop_to_usn(incoming, output, product, order_id)
        _mark_complete(date, product, str(output), order_id, {
            "source_file": str(incoming), "source_size_bytes": incoming.stat().st_size,
            "tif_size_bytes": output.stat().st_size,
        })
        return True
    except Exception as exc:
        message = f"{label} GeoTIFF processing failed: {exc}"
        logger.exception("[%s] %s", label, message)
        _mark_failed(date, product, message, order_id)
        return False
    finally:
        incoming.unlink(missing_ok=True)


def download_pet(date: datetime.date, sftp, order_id: str) -> bool:
    return _download_product(date, sftp, order_id, "pet")


def download_rainfall(date: datetime.date, sftp, order_id: str) -> bool:
    return _download_product(date, sftp, order_id, "rain")


def _make_sftp_connection():
    if not SFTP_AVAILABLE:
        raise RuntimeError("pysftp not installed – install with: pip install pysftp")
    # MOSDAC advertises IPv6 first on this network, but this host has no IPv6
    # route. Resolve an A record explicitly so pysftp cannot select the
    # unreachable AAAA record.
    try:
        host = socket.getaddrinfo(HOST, 22, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
    except socket.gaierror as exc:
        raise RuntimeError(f"Cannot resolve an IPv4 address for {HOST}: {exc}") from exc
    options = pysftp.CnOpts()
    options.hostkeys = None  # MOSDAC does not provide a verified host key.
    logger.info("Opening MOSDAC SFTP connection to IPv4 address %s", host)
    return pysftp.Connection(host, username=USER, password=PASS, cnopts=options)


# def _run_day(date: datetime.date, sftp, orders: Dict) -> Dict:
#     if not is_wheat_season(date):
#         return {"pet": False, "rain": False, "skipped": True, "reason": "outside_season"}
#     result = {"pet": False, "rain": False, "skipped": False}
#     for product, function in (("rain", download_rainfall), ("pet", download_pet)):
#         maximum = orders.get(f"{product}_max_date")
#         if maximum and date > maximum:
#             logger.info("[%s] %s is newer than order data (%s); skipped", product.upper(), date, maximum)
#             continue
#         result[product] = function(date, sftp, orders.get(f"{product}_order"))
#     return result
def _run_day(date: datetime.date, sftp, orders: Dict) -> Dict:
    """
    Download the requested date if available.
    Otherwise, automatically download the latest available date from MOSDAC.
    """

    if not is_wheat_season(date):
        return {
            "pet": False,
            "rain": False,
            "skipped": True,
            "reason": "outside_season",
        }

    result = {
        "pet": False,
        "rain": False,
        "skipped": False,
    }

    for product, function in (
        ("rain", download_rainfall),
        ("pet", download_pet),
    ):

        requested_date = date
        latest_available = orders.get(f"{product}_max_date")
        order_id = orders.get(f"{product}_order")

        if not order_id:
            logger.warning("[%s] No order folder found.", product.upper())
            continue

        # If today's data isn't available yet,
        # automatically download the newest available file.
        download_date = requested_date

        if latest_available and requested_date > latest_available:
            logger.warning(
                "[%s] Requested %s not available. "
                "Downloading latest available date %s instead.",
                product.upper(),
                requested_date,
                latest_available,
            )
            download_date = latest_available

        result[product] = function(
            download_date,
            sftp,
            order_id,
        )

    return result

def download_day(date: datetime.date) -> Dict:
    try:
        with _make_sftp_connection() as sftp:
            return _run_day(date, sftp, _discover_orders(sftp))
    except Exception as exc:
        logger.error("SFTP session error for %s: %s", date, exc)
        return {"pet": False, "rain": False, "skipped": False}


def backfill_historical(start_date: Optional[datetime.date] = None, end_date: Optional[datetime.date] = None) -> Dict[str, int]:
    start, end = start_date or START_DATE, end_date or datetime.date.today()
    stats = {"total": 0, "pet_ok": 0, "rain_ok": 0, "skipped": 0}
    try:
        with _make_sftp_connection() as sftp:
            orders = _discover_orders(sftp)
            current = start
            while current <= end:
                stats["total"] += 1
                result = _run_day(current, sftp, orders)
                stats["pet_ok"] += int(result.get("pet", False))
                stats["rain_ok"] += int(result.get("rain", False))
                stats["skipped"] += int(result.get("skipped", False))
                current += datetime.timedelta(days=1)
    except Exception as exc:
        logger.error("Backfill SFTP session failed: %s", exc)
    return stats


def scheduled_daily_download() -> None:
    logger.info("Scheduled GeoTIFF download triggered")
    download_day(datetime.date.today())


class MosdacDownloader:
    """Scheduler-compatible interface for the GeoTIFF-only MOSDAC flow."""
    def __init__(self) -> None:
        self.logger = logger

    def download_from_orders(self, order_keys: Optional[List[str]] = None) -> Dict:
        """
        Download the latest PET / RAIN GeoTIFFs delivered to MOSDAC's /Order
        SFTP folder.

        `order_keys` is an OPTIONAL restriction, not a requirement:
        - If provided, only those SFTP folder names are considered.
        - If empty/None (e.g. Stage 2 couldn't scrape an order id from the
          MyOrder page UI, or judged no new order was needed), we still
          connect and let `_discover_orders` auto-pick the newest PET and
          newest RAIN order folder by mtime + filename marker — the same
          fallback the CLI's `download_day()` uses. This avoids depending on
          a fragile UI-scraped "Order ID" that may not even match the real
          SFTP folder name.
        """
        result = {product: {"downloaded": 0, "failed": 0, "skipped": 0} for product in ("pet", "rain")}
        if order_keys:
            self.logger.info("MOSDAC order keys supplied, restricting to: %s", order_keys)
        else:
            self.logger.info(
                "No MOSDAC order keys supplied; auto-discovering latest "
                "PET/RAIN order folders from SFTP instead"
            )
        try:
            with _make_sftp_connection() as sftp:
                orders = _discover_orders(sftp, order_keys)
                for product, function in (("pet", download_pet), ("rain", download_rainfall)):
                    date, order = orders.get(f"{product}_max_date"), orders.get(f"{product}_order")
                    if not date or not order:
                        result[product]["skipped"] += 1
                    elif already_complete(date, product):
                        self.logger.info("[%s] %s already complete", product.upper(), date)
                        result[product]["skipped"] += 1
                    elif function(date, sftp, order):
                        result[product]["downloaded"] += 1
                    else:
                        result[product]["failed"] += 1
        except Exception as exc:
            self.logger.error("SFTP session error: %s", exc)
        return result

    def download_single_date(self, date: datetime.date, pet_order: str, rain_order: str) -> Dict:
        try:
            with _make_sftp_connection() as sftp:
                return {"pet": download_pet(date, sftp, pet_order), "rain": download_rainfall(date, sftp, rain_order)}
        except Exception as exc:
            self.logger.error("SFTP session error for %s: %s", date, exc)
            return {"pet": False, "rain": False}

    def backfill_range(self, start_date: datetime.date, end_date: datetime.date) -> Dict[str, int]:
        return backfill_historical(start_date, end_date)

    def check_complete(self, date: datetime.date, data_type: str) -> bool:
        return already_complete(date, data_type)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="MOSDAC GeoTIFF-only SFTP downloader")
    parser.add_argument("--backfill", action="store_true")
    parser.add_argument("--start", type=str)
    parser.add_argument("--end", type=str)
    parser.add_argument("--date", type=str)
    parser.add_argument("--stream", action="store_true")
    parser.add_argument("--check-boundary", action="store_true")
    args = parser.parse_args()
    if args.check_boundary:
        check_boundary()
    elif args.backfill or args.start or args.end:
        start = datetime.datetime.strptime(args.start, "%Y-%m-%d").date() if args.start else START_DATE
        end = datetime.datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else datetime.date.today()
        backfill_historical(start, end)
    elif args.date:
        download_day(datetime.datetime.strptime(args.date, "%Y-%m-%d").date())
    elif args.stream:
        schedule.every().day.at("00:00").do(scheduled_daily_download)
        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        download_day(datetime.date.today())

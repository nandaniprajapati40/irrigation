# backend/downloader.py
"""
SatelliteDownloader — Real-Overpass-Only Sentinel-2 Downloader
═══════════════════════════════════════════════════════════════════════════════

DESIGN PRINCIPLE — only real data, no synthetic dates:
───────────────────────────────────────────────────────
Sentinel-2 revisits Udham Singh Nagar roughly every 5 days.  Previous
versions iterated every calendar day and "filled" missing dates with pixels
borrowed from ±3 neighbouring days.  This produced a GeoTIFF file for every
single day in the season — most of which contained fabricated observations.
Feeding fabricated dates into the SARIMAX model corrupts training.

The correct pipeline has two steps:
  Step 1 — discover_real_dates():
      Query GEE once for the entire date range and extract only the calendar
      dates on which at least one Sentinel-2 granule actually intersected
      the district.  No granule → no file.

  Step 2 — export_real_date(date):
      For each real date, mosaic ALL granules from that exact calendar day
      (there can be 2–4 MGRS tiles on a single overpass).  Apply per-pixel
      SCL cloud masking, then fall back to QA60, then to the raw unmasked
      mosaic for any remaining NoData pixels.  This fills within the same
      day's data only — no temporal borrowing from other dates.

THREE-LAYER SAME-DAY COMPOSITE (no temporal gap filling):
──────────────────────────────────────────────────────────
  Layer 1  Same-day SCL-masked mosaic   → best quality, cloud-free pixels
  Layer 2  Same-day QA60-masked mosaic  → fills hazy pixels SCL over-masks
  Layer 3  Same-day raw unmasked mosaic → fills any remaining NoData pixels
                                           (last resort; real DN values only)

All three layers use only the target calendar day's granules.

SCL=11 (Snow/Ice) is intentionally NOT masked — the Sentinel-2 atmospheric
correction (Sen2Cor) frequently misclassifies bright sand, dry farmland, and
high-reflectance terrain in the Terai foothills as snow.  Masking it removes
valid land pixels from the NW corner of the district.

DOWNLOAD STRATEGY — chunked getDownloadURL (no Google Drive, no OAuth):
────────────────────────────────────────────────────────────────────────
GEE's getDownloadURL caps each request at ~48 MB.  Udham Singh Nagar at
10 m resolution produces 100–450 MB GeoTIFFs.  The solution is to split the
district bounding box into a regular grid of small tiles, download each tile
as a separate GeoTIFF via getDownloadURL, then merge them locally with
rasterio into one seamless S2_YYYYMMDD.tif.

Tile sizing:  CHUNK_DEGREES × CHUNK_DEGREES degree cells.  At 10 m/px and
4 bands the district produces ~35–45 MB per 0.15° tile — safely under the
48 MB cap.  Adjust CHUNK_DEGREES down if you see "output too large" errors.

Temp chunk files are written to  <out_dir>/chunks/<date>/
and deleted automatically after a successful merge.

Output naming: S2_YYYYMMDD.tif  (one file per real overpass date only)
"""

from __future__ import annotations

import io
import logging
import re
import shutil
import tempfile
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import ee
import requests
import rasterio
import rasterio.mask as rio_mask
from rasterio.crs import CRS
from rasterio.merge import merge as rio_merge
from pyproj import Transformer
from shapely.geometry import shape, mapping
from shapely.ops import transform as shapely_transform

from config import STUDY_AREA, DIRECTORIES
from mongo import is_sentinel_downloaded, mark_sentinel_downloaded
from ee_init import init_ee

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
RABI_MONTHS        = {11, 12, 1, 2, 3, 4}

# Scene-level pre-filter — very permissive (90%).
# Per-pixel SCL/QA60 masking handles the real cloud removal.
CLOUD_THRESHOLD    = 100

SENTINEL_SCALE     = 10              # metres — Sentinel-2 native resolution
BANDS              = ["B2", "B3", "B4", "B8"]   # Blue, Green, Red, NIR
HISTORY_START_YEAR = 2021
EXPORT_CRS         = "EPSG:32644"    # UTM Zone 44N — matches the district

TASK_POLL_INTERVAL = 30              # seconds between GEE status polls
TASK_MAX_WAIT      = 7200            # 2-hour hard timeout per task

# ── Chunk download settings ────────────────────────────────────────────────────
# Each tile is CHUNK_DEGREES × CHUNK_DEGREES degrees.
# At 10 m/px, 4 bands, 0.15° ≈ ~40 MB — safely under the GEE 48 MB cap.
# Lower this value (e.g. 0.10) if you ever get "output too large" errors.
CHUNK_DEGREES      = 0.15

# How many times to retry a failed chunk download before giving up the date.
CHUNK_MAX_RETRIES  = 3

# Seconds to wait between chunk retry attempts.
CHUNK_RETRY_WAIT   = 15


DOWNLOAD_BBOX = {
    "west":  78.62,
    "east":  80.22,
    "south": 28.62,
    "north": 29.46,
}


# ── Per-pixel cloud masking ────────────────────────────────────────────────────

def _mask_scl(image):
    """
    Per-pixel cloud mask using the Scene Classification Layer (SCL).

    Masked (removed):
        3  = Cloud Shadow
        8  = Cloud Medium Probability
        9  = Cloud High Probability
        10 = Thin Cirrus

    Kept (NOT masked):
        11 = Snow/Ice — deliberately kept because Sen2Cor often misclassifies
             bright sand and dry farmland in the Terai foothills as snow,
             which would remove valid land pixels from the NW corner.
    """
    scl   = image.select("SCL")
    valid = (
        scl.neq(3)
        .And(scl.neq(8))
        .And(scl.neq(9))
        .And(scl.neq(10))
    )
    return image.updateMask(valid)


def _mask_qa60(image):
    """
    Lenient per-pixel cloud mask using the QA60 bitmask.

    Only removes opaque cloud (bit 10) and cirrus (bit 11).
    Keeps hazy, semi-transparent pixels that the stricter SCL mask removes.
    Used as Layer 2 to recover pixels that SCL over-masks.
    """
    qa    = image.select("QA60")
    valid = (
        qa.bitwiseAnd(1 << 10).eq(0)
        .And(qa.bitwiseAnd(1 << 11).eq(0))
    )
    return image.updateMask(valid)


# ── Helper functions ───────────────────────────────────────────────────────────

def is_rabi_month(date):
    return date.month in RABI_MONTHS


def get_all_rabi_seasons(from_year=HISTORY_START_YEAR):
    today, seasons, year = datetime.today(), [], from_year
    while True:
        s = datetime(year, 11, 1)
        e = datetime(year + 1, 4, 30)
        if s > today:
            break
        seasons.append((s, min(e, today)))
        year += 1
    return seasons


def _build_tile_grid(bounds: dict, chunk_deg: float) -> List[Tuple[float,float,float,float]]:
    """
    Divide the bounding box into a regular grid of tiles.

    Returns a list of (west, south, east, north) tuples, each no larger
    than chunk_deg × chunk_deg degrees.
    """
    west  = bounds["west"]
    east  = bounds["east"]
    south = bounds["south"]
    north = bounds["north"]

    tiles = []
    x = west
    while x < east:
        y = south
        while y < north:
            tile_w = x
            tile_s = y
            tile_e = min(x + chunk_deg, east)
            tile_n = min(y + chunk_deg, north)
            tiles.append((tile_w, tile_s, tile_e, tile_n))
            y += chunk_deg
        x += chunk_deg

    return tiles


# ══════════════════════════════════════════════════════════════════════════════
class SatelliteDownloader:

    def __init__(self):
        init_ee()
        self.study_area    = STUDY_AREA
        self.out_dir       = DIRECTORIES["raw"]["sentinel2"]
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.study_polygon = self._load_boundary()
        self._bounds       = self.study_area["bounds"]   # dict with N/S/E/W
        # District boundary as WGS-84 GeoJSON geometries for rasterio.mask.
        # Reprojected to raster CRS inside _merge_chunks before use.
        self._district_shapes = self._load_district_shapes()
        logger.info(
            f"SatelliteDownloader ready | CRS={EXPORT_CRS} | "
            f"scale={SENTINEL_SCALE}m | real-dates-only | out={self.out_dir}"
        )

    # ── Boundary ───────────────────────────────────────────────────────────────
    def _load_boundary(self):
        try:
            districts = ee.FeatureCollection("FAO/GAUL/2015/level2")
            feat = districts.filter(
                ee.Filter.And(
                    ee.Filter.eq("ADM1_NAME", "Uttarakhand"),
                    ee.Filter.eq("ADM2_NAME", "Udham Singh Nagar"),
                )
            ).first()
            geom = feat.geometry()
            geom.area().getInfo()
            logger.info("Boundary: exact FAO/GAUL district polygon loaded")
            return geom
        except Exception as exc:
            logger.warning(f"Exact boundary unavailable, using bbox: {exc}")
            b = self.study_area["bounds"]
            return ee.Geometry.Rectangle(
                [b["west"], b["south"], b["east"], b["north"]]
            )

    def _load_district_shapes(self) -> list:
        """
        Return the district boundary as a list of GeoJSON geometry dicts
        in EPSG:4326, ready to be reprojected and passed to rasterio.mask.

        Priority:
          1. GeoJSON from config (OSM/Nominatim polygon — most accurate)
          2. Bbox rectangle fallback
        """
        geojson  = self.study_area.get("geojson", {})
        features = geojson.get("features", [])
        shapes   = [f["geometry"] for f in features if f.get("geometry")]

        if shapes:
            logger.info(
                f"District mask: {len(shapes)} polygon(s) loaded from config GeoJSON"
            )
            return shapes

        logger.warning(
            "District mask: no GeoJSON features in config — using bbox rectangle. "
            "Output will be rectangular rather than the exact district outline."
        )
        b = self.study_area["bounds"]
        return [{
            "type": "Polygon",
            "coordinates": [[
                [b["west"], b["south"]],
                [b["east"], b["south"]],
                [b["east"], b["north"]],
                [b["west"], b["north"]],
                [b["west"], b["south"]],
            ]]
        }]

    # ── STEP 1: Discover real overpass dates ───────────────────────────────────
    def discover_real_dates(self, start, end):
        """
        Query GEE once for the full date range and return only the calendar
        dates that actually have a Sentinel-2 overpass over the district.

        No granule on a date = no date returned = no file exported.
        This is the only authoritative source of "which dates are real".
        """
        logger.info(
            f"Discovering real overpass dates: {start.date()} -> {end.date()} ..."
        )
        col = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(self.study_polygon)
            .filterDate(
                start.strftime("%Y-%m-%d"),
                (end + timedelta(days=1)).strftime("%Y-%m-%d"),
            )
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", CLOUD_THRESHOLD))
        )

        timestamps = col.aggregate_array("system:time_start").getInfo()

        if not timestamps:
            logger.info("No granules found in this range.")
            return []

        # Deduplicate by calendar date (multiple MGRS tiles = same date)
        real_dates = sorted({
            datetime.utcfromtimestamp(ts / 1000).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            for ts in timestamps
        })

        # Rabi months filter
        real_dates = [d for d in real_dates if is_rabi_month(d)]

        logger.info(
            f"Found {len(real_dates)} real overpass date(s): "
            + ", ".join(d.strftime("%Y-%m-%d") for d in real_dates)
        )
        return real_dates

    # ── STEP 2: Build same-day mosaic ─────────────────────────────────────────
    def _build_same_day_mosaic(self, date):
        """
        Merge all granules from exactly `date` into one unified image.

        Layer 1: SCL cloud mask   (best quality)
        Layer 2: QA60 cloud mask  (recovers SCL over-masking)
        Layer 3: Raw unmasked     (fills remaining NoData — real values only)

        NO data from other dates is used.
        """
        date_str = date.strftime("%Y-%m-%d")
        next_str = (date + timedelta(days=1)).strftime("%Y-%m-%d")

        col = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(self.study_polygon)
            .filterDate(date_str, next_str)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", CLOUD_THRESHOLD))
            .sort("CLOUDY_PIXEL_PERCENTAGE")   # cleanest tile wins overlaps
        )

        n = col.size().getInfo()
        if n == 0:
            return None

        avg_cloud = float(col.aggregate_mean("CLOUDY_PIXEL_PERCENTAGE").getInfo())
        logger.info(f"  {date_str}: {n} granule(s) | avg_cloud={avg_cloud:.1f}%")

        layer1 = col.map(_mask_scl).select(BANDS).mosaic()
        layer2 = col.map(_mask_qa60).select(BANDS).mosaic()
        layer3 = col.select(BANDS).mosaic()   # raw — real DN, not synthesised

        composite = (
            ee.ImageCollection([layer1, layer2, layer3])
            .mosaic()
            .clip(self.study_polygon)
        )
        return composite

    # ── STEP 3: Download one chunk tile via getDownloadURL ────────────────────
    def _download_chunk(
        self,
        image: ee.Image,
        tile_bounds: Tuple[float, float, float, float],
        chunk_path: Path,
    ) -> bool:
        """
        Download a single spatial chunk of `image` to `chunk_path`.

        GEE's getDownloadURL can return three different response shapes:
          A) A ZIP containing one GeoTIFF per band  (e.g. B2.tif, B3.tif …)
          B) A ZIP containing a single multi-band GeoTIFF
          C) A raw GeoTIFF  (when format='GeoTIFF' and bands fit in one file)

        We detect the actual content type from the raw bytes and handle all
        three cases.  If GEE returns an error (HTML or JSON body instead of
        binary data) we decode and log the real message before retrying.

        Returns True on success, False on permanent failure.
        """
        tile_w, tile_s, tile_e, tile_n = tile_bounds
        region = ee.Geometry.Rectangle([tile_w, tile_s, tile_e, tile_n])

        for attempt in range(1, CHUNK_MAX_RETRIES + 1):
            try:
                # ── 1. Ask GEE for a download URL ─────────────────────────────
                url = image.getDownloadURL({
                    "bands":     BANDS,
                    "region":    region,
                    "scale":     SENTINEL_SCALE,
                    "crs":       EXPORT_CRS,
                    "format":    "GeoTIFF",
                    "maxPixels": 1e9,
                })
                logger.debug(
                    f"    Chunk ({tile_w:.3f},{tile_s:.3f})-"
                    f"({tile_e:.3f},{tile_n:.3f}) attempt {attempt} — downloading ..."
                )

                # ── 2. Fetch the bytes ────────────────────────────────────────
                resp = requests.get(url, timeout=300)
                resp.raise_for_status()
                raw = resp.content

                # ── 3. Detect what GEE actually sent ─────────────────────────
                # GEE error responses are JSON or HTML — neither starts with the
                # ZIP magic bytes (PK\x03\x04) or TIFF magic bytes (II / MM).
                is_zip  = raw[:2] == b"PK"
                is_tiff = raw[:2] in (b"II", b"MM")   # little-endian / big-endian

                if not is_zip and not is_tiff:
                    # It's a GEE error body — decode and surface the real message
                    try:
                        err_text = raw.decode("utf-8", errors="replace")
                    except Exception:
                        err_text = repr(raw[:200])
                    raise RuntimeError(f"GEE returned an error response: {err_text[:400]}")

                # ── 4a. Handle ZIP (one TIF per band or one multi-band TIF) ──
                if is_zip:
                    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                        tif_names = sorted(
                            n for n in zf.namelist() if n.lower().endswith(".tif")
                        )
                        if not tif_names:
                            raise RuntimeError(
                                f"ZIP from GEE contained no .tif files: {zf.namelist()}"
                            )

                        with tempfile.TemporaryDirectory() as tmpdir:
                            zf.extractall(tmpdir)
                            band_paths = [Path(tmpdir) / n for n in tif_names]

                            # Extract band names from filenames.
                            # GEE names per-band files like "download.B2.tif"
                            # or "eecu_download.B2.tif".  Take the last dot-segment
                            # before the .tif extension as the band name.
                            def _band_name_from_path(p: Path) -> str:
                                parts = p.stem.split(".")
                                name = parts[-1].upper() if parts else ""
                                # Accept only known band names; fall back to BANDS order
                                return name if name in BANDS else ""

                            # One file → might already be multi-band
                            if len(band_paths) == 1:
                                with rasterio.open(band_paths[0]) as src:
                                    data    = src.read()        # shape: (bands, H, W)
                                    profile = src.profile.copy()
                                    # Single-file band names from the source
                                    chunk_band_names = list(src.descriptions) or BANDS[:data.shape[0]]
                            else:
                                # Multiple single-band files → stack them
                                bands_data       = []
                                chunk_band_names = []
                                profile          = None
                                for bp in band_paths:
                                    with rasterio.open(bp) as src:
                                        if profile is None:
                                            profile = src.profile.copy()
                                        bands_data.append(src.read(1))
                                        chunk_band_names.append(
                                            _band_name_from_path(bp)
                                        )
                                import numpy as np
                                data = np.stack(bands_data, axis=0)

                                # If filename-based names didn't work, fall back
                                # to the canonical BANDS order (B2, B3, B4, B8).
                                if not all(chunk_band_names):
                                    chunk_band_names = BANDS[:len(bands_data)]

                            profile.update(
                                count=data.shape[0],
                                compress="lzw",
                                tiled=True,
                                blockxsize=256,
                                blockysize=256,
                            )
                            with rasterio.open(chunk_path, "w", **profile) as dst:
                                dst.write(data)
                                # Write band descriptions so QGIS / gdalinfo show
                                # "B2 / B3 / B4 / B8" instead of "Gray / Undefined"
                                for i, bname in enumerate(chunk_band_names, 1):
                                    if bname:
                                        dst.update_tags(i, DESCRIPTION=bname)

                # ── 4b. Handle raw GeoTIFF ────────────────────────────────────
                else:
                    with tempfile.TemporaryDirectory() as tmpdir:
                        tmp_tif = Path(tmpdir) / "raw.tif"
                        tmp_tif.write_bytes(raw)
                        with rasterio.open(tmp_tif) as src:
                            data    = src.read()
                            profile = src.profile.copy()
                            raw_descriptions = src.descriptions   # preserve if present
                        profile.update(
                            compress="lzw",
                            tiled=True,
                            blockxsize=256,
                            blockysize=256,
                        )
                        with rasterio.open(chunk_path, "w", **profile) as dst:
                            dst.write(data)
                            # Preserve any descriptions from the source; if absent
                            # fall back to canonical BANDS order.
                            resolved = (
                                list(raw_descriptions)
                                if raw_descriptions and any(raw_descriptions)
                                else BANDS[:data.shape[0]]
                            )
                            for i, bname in enumerate(resolved, 1):
                                if bname:
                                    dst.update_tags(i, DESCRIPTION=bname)

                logger.debug(
                    f"    Chunk saved: {chunk_path.name} "
                    f"({chunk_path.stat().st_size / 1e6:.1f} MB)"
                )
                return True

            except Exception as exc:
                logger.warning(
                    f"    Chunk attempt {attempt}/{CHUNK_MAX_RETRIES} failed: {exc}"
                )
                if chunk_path.exists():
                    chunk_path.unlink()          # remove partial file before retry
                if attempt < CHUNK_MAX_RETRIES:
                    time.sleep(CHUNK_RETRY_WAIT)

        logger.error(f"    Chunk permanently failed after {CHUNK_MAX_RETRIES} attempts.")
        return False

    # ── STEP 4: Merge all chunk tiles → mask to district boundary ────────────
    def _merge_chunks(self, chunk_paths: List[Path], dest: Path) -> bool:
        """
        Two-step process:
          1. Mosaic all rectangular chunk GeoTIFFs into one raster.
          2. Reproject district polygon from EPSG:4326 → raster CRS (EPSG:32644)
             then apply rasterio.mask so pixels outside the district boundary
             become NoData — producing the exact district shape, not a rectangle.
        """
        if not chunk_paths:
            logger.error("No chunks to merge.")
            return False

        try:
            # ── Step 1: Mosaic all chunks ─────────────────────────────────────
            src_files = [rasterio.open(p) for p in chunk_paths]
            mosaic, transform = rio_merge(src_files)
            raster_crs = src_files[0].crs          # EPSG:32644 (UTM metres)
            merged_meta = src_files[0].meta.copy()
            for src in src_files:
                src.close()

            merged_meta.update({
                "driver":      "GTiff",
                "height":      mosaic.shape[1],
                "width":       mosaic.shape[2],
                "transform":   transform,
                "compress":    "lzw",
                "tiled":       True,
                "blockxsize":  256,
                "blockysize":  256,
                "photometric": "MINISBLACK",
            })

            # ── Step 2: Reproject district shapes 4326 → raster CRS ──────────
            # The district GeoJSON from config is in WGS-84 (EPSG:4326).
            # rasterio.mask compares shapes and raster in the same pixel space,
            # so they must share a CRS — otherwise "Input shapes do not overlap".
            transformer = Transformer.from_crs(
                "EPSG:4326", raster_crs.to_epsg() or raster_crs.to_wkt(),
                always_xy=True,
            )
            projected_shapes = []
            for geom_dict in self._district_shapes:
                geom_wgs84    = shape(geom_dict)
                geom_utm      = shapely_transform(transformer.transform, geom_wgs84)
                projected_shapes.append(mapping(geom_utm))

            logger.debug(
                f"  District shapes reprojected EPSG:4326 → {raster_crs.to_string()} "
                f"({len(projected_shapes)} polygon(s))"
            )

            # ── Step 3: Write merged raster to temp file, then mask it ────────
            # rasterio.mask needs an open file handle — can't work in-memory.
            with tempfile.TemporaryDirectory() as tmpdir:
                merged_tmp = Path(tmpdir) / "merged_tmp.tif"

                with rasterio.open(merged_tmp, "w", **merged_meta) as tmp_dst:
                    tmp_dst.write(mosaic)

                with rasterio.open(merged_tmp) as tmp_src:
                    masked_data, masked_transform = rio_mask.mask(
                        tmp_src,
                        projected_shapes,
                        crop=True,          # trim extent to district bbox
                        nodata=0,           # pixels outside boundary → 0
                        all_touched=False,  # only pixels whose centre is inside
                        invert=False,
                    )
                    masked_meta = tmp_src.meta.copy()

            masked_meta.update({
                "driver":      "GTiff",
                "height":      masked_data.shape[1],
                "width":       masked_data.shape[2],
                "transform":   masked_transform,
                "compress":    "lzw",
                "tiled":       True,
                "blockxsize":  256,
                "blockysize":  256,
                "photometric": "MINISBLACK",
                "nodata":      0,
            })

            with rasterio.open(dest, "w", **masked_meta) as final_dst:
                final_dst.write(masked_data)
                # Stamp band descriptions on the final file so gdalinfo shows
                # "Description = B2 / B3 / B4 / B8" and QGIS renders correctly.
                for i, bname in enumerate(BANDS[:masked_data.shape[0]], 1):
                    final_dst.update_tags(i, DESCRIPTION=bname)

            size_mb = dest.stat().st_size / 1e6
            logger.info(
                f"  Merged {len(chunk_paths)} chunk(s) + district mask applied "
                f"→ {dest.name} ({size_mb:.1f} MB)"
            )
            return True

        except Exception as exc:
            logger.error(f"  Merge+mask failed: {exc}", exc_info=True)
            return False

    # ── STEP 5: Export one real date (chunk + merge) ───────────────────────────
    def export_real_date(self, date):
        date_str = date.strftime("%Y%m%d")
        filename = f"S2_{date_str}"
        out_path = self.out_dir / f"{filename}.tif"

        if is_sentinel_downloaded(date):
            logger.debug(f"{filename}: already in MongoDB — skipping")
            return {"date": date, "filepath": out_path, "skipped": True}
        if out_path.exists():
            logger.info(f"{filename}: on disk but not in DB — registering")
            mark_sentinel_downloaded(date, str(out_path), cloud_pct=0.0)
            return {"date": date, "filepath": out_path, "skipped": True}

        logger.info(f"[{date_str}] Building same-day mosaic ...")
        mosaic = self._build_same_day_mosaic(date)
        if mosaic is None:
            logger.info(f"[{date_str}] No granules on this date — skipping")
            return None

        # ── Build tile grid from the FIXED download bbox ──────────────────────
        # IMPORTANT: use DOWNLOAD_BBOX (hardcoded constant), NOT self._bounds.
        # self._bounds comes from OSM/Nominatim at config import time and can
        # shift between runs, producing different tile grids and different output
        # extents, causing area loss at district edges and QGIS misalignment.
        tiles = _build_tile_grid(DOWNLOAD_BBOX, CHUNK_DEGREES)
        logger.info(
            f"[{date_str}] Downloading {len(tiles)} chunk(s) "
            f"({CHUNK_DEGREES}° fixed-bbox tiles, ~{SENTINEL_SCALE}m res) ..."
        )

        # ── Temp directory for this date's chunks ─────────────────────────────
        chunk_dir = self.out_dir / "chunks" / date_str
        chunk_dir.mkdir(parents=True, exist_ok=True)

        chunk_paths: List[Path] = []
        all_ok = True

        for i, tile_bounds in enumerate(tiles):
            chunk_path = chunk_dir / f"chunk_{i:04d}.tif"

            if chunk_path.exists() and chunk_path.stat().st_size > 1024:
                # Already downloaded in a previous interrupted run — reuse it.
                logger.debug(f"  Chunk {i+1}/{len(tiles)}: reusing cached file")
                chunk_paths.append(chunk_path)
                continue

            logger.info(f"  Chunk {i+1}/{len(tiles)} ...")
            ok = self._download_chunk(mosaic, tile_bounds, chunk_path)

            if ok:
                chunk_paths.append(chunk_path)
            else:
                logger.error(
                    f"[{date_str}] Chunk {i+1}/{len(tiles)} failed permanently — "
                    f"aborting date."
                )
                all_ok = False
                break

        if not all_ok or not chunk_paths:
            logger.error(f"[{date_str}] Incomplete chunk set — no output written.")
            # Leave chunks on disk so the next run can resume from where it stopped.
            return None

        # ── Merge chunks into final GeoTIFF ───────────────────────────────────
        logger.info(f"[{date_str}] Merging {len(chunk_paths)} chunk(s) ...")
        ok = self._merge_chunks(chunk_paths, out_path)

        if not ok:
            if out_path.exists():
                out_path.unlink()
            return None

        # ── Clean up temporary chunk files ────────────────────────────────────
        try:
            shutil.rmtree(chunk_dir)
            logger.debug(f"[{date_str}] Chunk temp directory removed.")
        except Exception as exc:
            logger.warning(f"[{date_str}] Could not remove chunk dir: {exc}")

        size_mb = out_path.stat().st_size / 1e6
        logger.info(f"[{date_str}] Saved: {out_path.name} ({size_mb:.1f} MB)")
        sha256_hash = get_sha256(out_path)
        logger.info(f"[{date_str}] SHA256: {sha256_hash}")
        mark_sentinel_downloaded(
	    date,
	    str(out_path),
	    cloud_pct=0.0,
	    checksum=sha256_hash
	)
        return {"date": date, "filepath": out_path}

    # ── Core range processor ───────────────────────────────────────────────────
    def _process_date_range(self, start, end):
        """
        Discover real overpass dates in [start, end] then export each one.
        Never processes a date that has no real Sentinel-2 overpass.
        """
        results = {"downloaded": [], "skipped": [], "no_image": [], "failed": []}

        real_dates = self.discover_real_dates(start, end)
        if not real_dates:
            logger.info("No real overpass dates found — nothing to export.")
            return results

        print(f"\n  {len(real_dates)} real overpass date(s) to process:")
        for d in real_dates:
            print(f"    {d.strftime('%Y-%m-%d')}")
        print()

        for date in real_dates:
            try:
                result = self.export_real_date(date)
                if result is None:
                    results["no_image"].append(str(date.date()))
                elif result.get("skipped"):
                    results["skipped"].append(str(date.date()))
                else:
                    results["downloaded"].append(str(date.date()))
            except Exception as exc:
                logger.error(f"Error on {date.date()}: {exc}", exc_info=True)
                results["failed"].append(str(date.date()))

        return results

    # ── Public: historical ─────────────────────────────────────────────────────
    def download_historical_seasons(self):
        seasons = get_all_rabi_seasons(HISTORY_START_YEAR)
        total   = {"downloaded": [], "skipped": [], "no_image": [], "failed": []}
        print(f"\n  Processing {len(seasons)} Rabi season(s) — real dates only")
        print("  GEE queried once per season to find real overpass dates.\n")
        for start, end in seasons:
            print(f"\n  -- Season: {start.date()} -> {end.date()} --")
            for k, v in self._process_date_range(start, end).items():
                total[k].extend(v)
        self._print_summary(total)
        return total

    # ── Public: incremental ────────────────────────────────────────────────────
    def download_new_only(self):
        if not is_rabi_month(datetime.today()):
            logger.info("Outside Rabi season — download_new_only skipped")
            return {"downloaded": [], "skipped": [], "no_image": [], "failed": []}

        last  = self._get_last_downloaded_date()
        today = datetime.today()

        if last is None:
            last = (
                datetime(today.year, 11, 1) - timedelta(days=1)
                if today.month >= 11
                else datetime(today.year - 1, 11, 1) - timedelta(days=1)
            )

        start = last + timedelta(days=1)
        if start > today:
            logger.info("Already up-to-date")
            return {"downloaded": [], "skipped": [], "no_image": [], "failed": []}

        logger.info(f"Checking for new real overpasses: {start.date()} -> {today.date()}")
        result = self._process_date_range(start, today)
        self._print_summary(result)
        return result

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _get_last_downloaded_date(self):
        try:
            from mongo import sentinel_col
            doc = sentinel_col.find_one(sort=[("image_date", -1)])
            if doc:
                return doc["image_date"]
        except Exception as exc:
            logger.warning(f"MongoDB query failed: {exc}")
        files = sorted(self.out_dir.glob("S2_*.tif"))
        if files:
            m = re.search(r"\d{8}", files[-1].name)
            if m:
                return datetime.strptime(m.group(), "%Y%m%d")
        return None

    @staticmethod
    def _print_summary(results):
        print("\n" + "=" * 55)
        print(f"  Downloaded : {len(results['downloaded'])} new scene(s)")
        print(f"  Skipped    : {len(results['skipped'])} (already on disk/DB)")
        print(f"  No image   : {len(results['no_image'])} (cloud filter)")
        print(f"  Failed     : {len(results.get('failed', []))} (task/chunk error)")
        print("=" * 55)
        for d in results["downloaded"]:
            print(f"    + S2_{d.replace('-', '')}.tif")


# ── CLI utility: list real dates without exporting ────────────────────────────
def list_real_dates(start_str, end_str):
    """
    Print all real Sentinel-2 overpass dates in a range, with MGRS tile IDs
    and cloud %, without submitting any export task.
    """
    from ee_init import init_ee
    init_ee()

    start = datetime.fromisoformat(start_str)
    end   = datetime.fromisoformat(end_str)

    districts = ee.FeatureCollection("FAO/GAUL/2015/level2")
    boundary  = districts.filter(
        ee.Filter.And(
            ee.Filter.eq("ADM1_NAME", "Uttarakhand"),
            ee.Filter.eq("ADM2_NAME", "Udham Singh Nagar"),
        )
    ).first().geometry()

    col = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(boundary)
        .filterDate(
            start.strftime("%Y-%m-%d"),
            (end + timedelta(days=1)).strftime("%Y-%m-%d"),
        )
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", CLOUD_THRESHOLD))
    )

    timestamps = col.aggregate_array("system:time_start").getInfo()
    tiles      = col.aggregate_array("MGRS_TILE").getInfo()
    clouds     = col.aggregate_array("CLOUDY_PIXEL_PERCENTAGE").getInfo()

    from collections import defaultdict
    by_date = defaultdict(list)
    for ts, tile, cloud in zip(timestamps, tiles, clouds):
        d = datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")
        by_date[d].append((tile, cloud))

    rabi_dates = {
        d: v for d, v in by_date.items()
        if is_rabi_month(datetime.fromisoformat(d))
    }

    print(f"\n{'='*62}")
    print(f"  Real Sentinel-2 Overpass Dates — Udham Singh Nagar")
    print(f"  Range  : {start_str} -> {end_str}")
    print(f"  Result : {len(rabi_dates)} overpass date(s) in Rabi months")
    print(f"{'='*62}")
    for date_str in sorted(rabi_dates.keys()):
        granules = rabi_dates[date_str]
        tile_str = ", ".join(f"{t}({c:.0f}%)" for t, c in granules)
        print(f"  {date_str}  [{len(granules)} tile(s)]  {tile_str}")
    print("=" * 62)

import hashlib

def get_sha256(file_path):
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
    
# ── CLI ────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    import logging as _logging

    _logging.basicConfig(
        level=_logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
    )

    p = argparse.ArgumentParser(
        description="Sentinel-2 downloader — real overpass dates only"
    )
    p.add_argument("--historical",  action="store_true")
    p.add_argument("--new-only",    action="store_true")
    p.add_argument("--start",       metavar="YYYY-MM-DD")
    p.add_argument("--end",         metavar="YYYY-MM-DD")
    p.add_argument("--list-dates",  action="store_true",
                   help="List real overpass dates in range (no export)")
    args = p.parse_args()

    if args.list_dates:
        if not (args.start and args.end):
            p.error("--list-dates requires --start and --end")
        list_real_dates(args.start, args.end)
    else:
        dl = SatelliteDownloader()
        if args.historical:
            dl.download_historical_seasons()
        elif args.new_only:
            dl.download_new_only()
        elif args.start and args.end:
            dl._process_date_range(
                datetime.fromisoformat(args.start),
                datetime.fromisoformat(args.end),
            )
        else:
            print(
                "\nUsage:\n"
                "  python downloader.py --list-dates --start 2021-11-01 --end 2022-04-30\n"
                "  python downloader.py --start 2022-11-01 --end 2022-04-30\n"
                "  python downloader.py --new-only\n"
                "  python downloader.py --historical\n"
            )

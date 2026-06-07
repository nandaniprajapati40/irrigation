import logging
import numpy as np
import rasterio
import rasterio.warp
from rasterio.enums import Resampling
from datetime import datetime, timedelta
from pathlib import Path
from scipy.ndimage import zoom
from typing import Dict, List, Optional, Tuple

from config import STUDY_AREA, WHEAT_PARAMS, DIRECTORIES
from mongo import (
    save_processed_data,
    step_already_processed,
    mark_savi_processed,
    mark_kc_processed,
    mark_etc_processed,
    mark_cwr_processed,
    mark_iwr_processed,
    save_pet_interval_stats,
    save_rain_interval_stats,
    update_rain_eff_rain,
)

logger = logging.getLogger(__name__)

NODATA       = -9999.0
INSAT_NODATA = -999.0          # MOSDAC fill value for both PET and Rain

# FAO-56 wheat Kc bounds (Allen et al. 1998, thesis Table 9 footnote)
KC_MIN = 0.30   # Kc_ini (germination / initial stage)
KC_MAX = 1.5   # Kc_mid (heading / flowering stage)



def compute_effective_rainfall(P_interval_mm: float, interval_days: int) -> float:
    interval_days = max(int(interval_days), 1)
    if P_interval_mm <= 0:
        return 0.0

    period_factor = interval_days / 30.0
    threshold = 75.0 * period_factor
    if P_interval_mm <= threshold:
        pe_total = max(0.0, 0.6 * P_interval_mm - 10.0 * period_factor)
    else:
        pe_total = max(0.0, 0.8 * P_interval_mm - 25.0 * period_factor)

    return pe_total / interval_days
# ═══════════════════════════════════════════════════════════════════════════
# DataProcessor
# ═══════════════════════════════════════════════════════════════════════════

class DataProcessor:

    def __init__(self):
        self.study_area   = STUDY_AREA
        self.wheat_params = WHEAT_PARAMS
        self.dirs         = DIRECTORIES
        self._mask_cache: Dict = {}

    # ── GeoTIFF writer ────────────────────────────────────────────────────

    def save_geotiff(self, data: np.ndarray, filepath: Path, profile: Dict) -> None:
        """Write a single-band float64 GeoTIFF with LZW compression."""
        data = np.where(np.isnan(data), NODATA, data)
        p = dict(profile)
        p.update(
            dtype="float64", nodata=NODATA, compress="lzw",
            count=1, tiled=True, blockxsize=256, blockysize=256,
        )
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(filepath, "w", **p) as dst:
            dst.write(data.astype("float64"), 1)

    # ── Wheat crop mask ───────────────────────────────────────────────────

    def load_wheat_mask(
        self,
        date: datetime,
        shape: Tuple[int, int],
        sentinel_profile: Optional[Dict] = None,
    ) -> np.ndarray:
        
        mask_dir  = self.dirs["processed"]["masks"]
        mask_path = mask_dir / "wheat_mask.tif"

        if not mask_path.exists():
            raise FileNotFoundError(
                f"wheat_mask.tif not found in {mask_dir}. "
                "Run the GEE Random-Forest crop classifier first."
            )

        if sentinel_profile is not None:
            dst_crs       = sentinel_profile["crs"]
            dst_transform = sentinel_profile["transform"]
            dst_h, dst_w  = shape
            cache_key     = (str(mask_path), dst_h, dst_w, str(dst_crs))

            if cache_key in self._mask_cache:
                return self._mask_cache[cache_key]

            with rasterio.open(mask_path) as src:
                src_nodata = src.nodata if src.nodata is not None else 0
                src_data   = src.read(1).astype("float64")
                dst_data   = np.zeros((dst_h, dst_w), dtype="float64")
                rasterio.warp.reproject(
                    source=src_data, destination=dst_data,
                    src_transform=src.transform, src_crs=src.crs,
                    dst_transform=dst_transform, dst_crs=dst_crs,
                    resampling=Resampling.nearest,
                    src_nodata=src_nodata, dst_nodata=0,
                )

            mask = dst_data > 0
            self._mask_cache[cache_key] = mask
            logger.info(
                f"Wheat mask reprojected → {dst_crs} | "
                f"coverage = {mask.sum() / mask.size * 100:.1f}%"
            )
            return mask

        with rasterio.open(mask_path) as src:
            mask_raw = src.read(1)
        mask = mask_raw > 0
        if mask.shape != shape:
            mask = zoom(
                mask.astype(float),
                (shape[0] / mask.shape[0], shape[1] / mask.shape[1]),
                order=0,
            ) > 0
        return mask

    # ── INSAT raster loader (CRS-aware reproject) ─────────────────────────

    def load_insat_raster(
        self,
        filepath: Path,
        sentinel_profile: Dict,
    ) -> np.ndarray:
       
        dst_crs       = sentinel_profile["crs"]
        dst_transform = sentinel_profile["transform"]
        dst_h         = sentinel_profile["height"]
        dst_w         = sentinel_profile["width"]

        with rasterio.open(filepath) as src:
            src_data   = src.read(1).astype("float64")
            src_nodata = src.nodata if src.nodata is not None else INSAT_NODATA
            src_data   = np.where(src_data == src_nodata, np.nan, src_data)

            dst_data = np.full((dst_h, dst_w), np.nan, dtype="float64")
            rasterio.warp.reproject(
                source=src_data, destination=dst_data,
                src_transform=src.transform, src_crs=src.crs,
                dst_transform=dst_transform, dst_crs=dst_crs,
                resampling=Resampling.bilinear,
                src_nodata=np.nan, dst_nodata=np.nan,
            )

        dst_data = np.where(np.isnan(dst_data), 0.0, dst_data)
        dst_data = np.maximum(dst_data, 0.0)
        return dst_data.astype("float64")

    # ── File selection helpers ─────────────────────────────────────────────

    def _find_files_in_interval(
        self,
        start_date: datetime,
        end_date: datetime,
        file_list: List[Dict],
    ) -> List[Dict]:
        """Files where start_date < file_date <= end_date."""
        selected = [f for f in file_list if start_date < f["date"] <= end_date]
        if not selected:
            previous = [f for f in file_list if f["date"] <= end_date]
            if not previous:
                raise ValueError(f"No raster available before {end_date.date()}")
            selected = [max(previous, key=lambda x: x["date"])]
            logger.warning(
                f"No files in ({start_date.date()}, {end_date.date()}] — "
                f"using nearest: {selected[0]['date'].date()}"
            )
        return selected

    def _find_nearest_file(
        self,
        target_date: datetime,
        file_list: List[Dict],
        max_delta_days: int = 2,
    ) -> Optional[Dict]:
        """
        Find the file whose date is closest to target_date within ±max_delta_days.
        Used to match a daily INSAT PET file to a Sentinel acquisition date.

        Thesis §5.4: "INSAT 3D daily reference evapotranspiration data…
        multiplied with Kc maps of available dates."
        """
        candidates = [
            f for f in file_list
            if abs((f["date"] - target_date).days) <= max_delta_days
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda f: abs((f["date"] - target_date).days))

    # ── Public PET accessors ──────────────────────────────────────────────

    def select_pet_daily(
        self,
        sentinel_date: datetime,
        pet_files: List[Dict],
        sentinel_profile: Dict,
    ) -> Optional[Dict]:
        """
        Fetch the INSAT daily PET raster nearest to sentinel_date (±2 days).

        Returns the reprojected array in mm day⁻¹, ready for multiplication
        with the Kc raster.

        Thesis §5.4 (p. 51): "INSAT 3D daily reference evapotranspiration
        data of 4 km were resampled and used to multiply with Kc maps of
        available dates and generated crop evapotranspiration maps."
        """
        item = self._find_nearest_file(sentinel_date, pet_files)
        if item is None:
            logger.warning(
                f"No INSAT PET file within ±2 days of {sentinel_date.date()}"
            )
            return None

        arr = self.load_insat_raster(item["filepath"], sentinel_profile)
        h, w = arr.shape
        wheat_mask = self.load_wheat_mask(sentinel_date, (h, w), sentinel_profile)
        wheat_vals = arr[wheat_mask]
        stats = {
            "mean": float(np.nanmean(wheat_vals)) if wheat_vals.size else 0.0,
            "min":  float(np.nanmin(wheat_vals))  if wheat_vals.size else 0.0,
            "max":  float(np.nanmax(wheat_vals))  if wheat_vals.size else 0.0,
        }
        logger.info(
            f"INSAT PET for {sentinel_date.date()} "
            f"(file={item['date'].date()}) | "
            f"mean={stats['mean']:.2f} mm/day"
        )
        return {"data": arr, "date": item["date"], "stats": stats}

    def select_pet_interval_sum(
        self,
        prev_date: datetime,
        current_date: datetime,
        pet_files: List[Dict],
        sentinel_profile: Dict,
    ) -> Dict:
        """
        Sum daily INSAT PET over (prev_date, current_date] → mm per interval.

        Used by the SARIMAX CWR model trainer (models.py) as the exogenous
        PET variable (interval-sum PET correlates better with CWR than
        single-day PET for model training on Sentinel cadence).

        Also used as a fallback if select_pet_daily() finds no nearby file.
        Saves interval stats to MongoDB (pet_stats collection).
        """
        selected = self._find_files_in_interval(prev_date, current_date, pet_files)
        n_days   = len(selected)
        h = sentinel_profile["height"]
        w = sentinel_profile["width"]
        total = np.zeros((h, w), dtype="float64")
        for item in selected:
            total += self.load_insat_raster(item["filepath"], sentinel_profile)

        wheat_mask  = self.load_wheat_mask(current_date, (h, w), sentinel_profile)
        wheat_vals  = total[wheat_mask]
        pixel_stats = {
            "sum":  float(np.nansum(wheat_vals)),
            "mean": float(np.nanmean(wheat_vals)) if wheat_vals.size else 0.0,
            "min":  float(np.nanmin(wheat_vals))  if wheat_vals.size else 0.0,
            "max":  float(np.nanmax(wheat_vals))  if wheat_vals.size else 0.0,
        }
        save_pet_interval_stats(
            sentinel_date  = current_date,
            interval_start = prev_date,
            interval_end   = current_date,
            n_days         = n_days,
            pixel_stats    = pixel_stats,
        )
        logger.info(
            f"PET interval ({prev_date.date()}, {current_date.date()}]: "
            f"{n_days} files | sum={pixel_stats['sum']:.1f} mm | "
            f"mean={pixel_stats['mean']:.2f} mm/day"
        )
        return {"data": total, "date": current_date, "stats": pixel_stats, "n_days": n_days}

    
    def select_rainfall_sum(
        self,
        prev_date: datetime,
        current_date: datetime,
        rain_files: List[Dict],
        sentinel_profile: Dict,
    ) -> Dict:
        """
        Improved version: works even if MongoDB rain_stats is empty.
        Always calculates from raw files.
        """
        selected = self._find_files_in_interval(prev_date, current_date, rain_files)
        n_days = len(selected)

        if n_days == 0:
            logger.warning(f"No rain files found for interval {prev_date.date()} to {current_date.date()}")
            n_days = max((current_date - prev_date).days, 1)

        h = sentinel_profile["height"]
        w = sentinel_profile["width"]
        total = np.zeros((h, w), dtype="float64")

        for item in selected:
            total += self.load_insat_raster(item["filepath"], sentinel_profile)

        wheat_mask = self.load_wheat_mask(current_date, (h, w), sentinel_profile)
        wheat_vals = total[wheat_mask]

        pixel_stats = {
            "sum": float(np.nansum(wheat_vals)),
            "mean": float(np.nanmean(wheat_vals)) if wheat_vals.size else 0.0,
            "min": float(np.nanmin(wheat_vals)) if wheat_vals.size else 0.0,
            "max": float(np.nanmax(wheat_vals)) if wheat_vals.size else 0.0,
        }

        # Save to MongoDB again (re-seed)
        save_rain_interval_stats(
            sentinel_date=current_date,
            interval_start=prev_date,
            interval_end=current_date,
            n_days=n_days,
            pixel_stats=pixel_stats,
        )

        logger.info(
            f"Rain interval ({prev_date.date()} → {current_date.date()}]: "
            f"{n_days} days | sum={pixel_stats['sum']:.1f} mm"
        )
        return {"data": total, "date": current_date, "stats": pixel_stats, "n_days": n_days}
    # ═══════════════════════════════════════════════════════════════════════
    # STEP 1 — SAVI  (thesis Eq. 3, §4.3)
    # ═══════════════════════════════════════════════════════════════════════

    def calculate_savi(self, sentinel2_data: Dict) -> Dict:
        """
        Compute SAVI from Sentinel-2A harmonised surface reflectance.

        SAVI = (1 + L) × (ρ_NIR − ρ_Red) / (ρ_NIR + ρ_Red + L)
        L = 0.5  (optimal for arid zones and sparse canopy, Huete 1988)

        Bands used (Sentinel-2 L2A / harmonised product):
            Band 4 (Red):  670 nm
            Band 8 (NIR):  842 nm
        Scale factor: ×0.0001 (from digital number to surface reflectance)

        Thesis §5.3: SAVI values range from ~0.05–0.10 at germination
        (Nov) to ~0.50–0.60 at heading/flowering (Feb–Mar), then decline
        to ~0.15–0.25 at maturity (Apr).

        Output: SAVI raster in [-1, 1], NaN outside the wheat mask.
        """
        date     = sentinel2_data["date"]
        date_str = date.strftime("%Y%m%d")
        out_path = self.dirs["processed"]["savi"] / f"savi_{date_str}.tif"

        if step_already_processed("savi", date):
            logger.info(f"SAVI already processed {date_str} — skip")
            return {"filepath": out_path, "skipped": True}

        logger.info(f"Calculating SAVI for {date_str}")
        L = 0.5   # soil adjustment factor (Huete 1988; thesis §4.3 Eq. 3)

        with rasterio.open(sentinel2_data["filepath"]) as src:
            red     = src.read(3).astype("float64") * 0.0001   # Band 4 (Red)
            nir     = src.read(4).astype("float64") * 0.0001   # Band 8 (NIR)
            profile = src.profile.copy()

        # Valid reflectance range [0, 1]
        valid = (red >= 0) & (nir >= 0) & (red <= 1) & (nir <= 1)
        savi  = np.full(red.shape, np.nan, dtype="float64")

        # Thesis Eq. 3: SAVI = (1+L) × (NIR−Red) / (NIR+Red+L)
        denom = nir[valid] + red[valid] + L
        with np.errstate(invalid="ignore", divide="ignore"):
            savi[valid] = np.where(
                denom != 0,
                ((nir[valid] - red[valid]) / denom) * (1.0 + L),
                np.nan,
            )
        savi = np.clip(savi, -1.0, 1.0)

        wheat_mask        = self.load_wheat_mask(date, savi.shape, profile)
        savi[~wheat_mask] = np.nan

        self.save_geotiff(savi, out_path, profile)

        stats = {
            "mean": float(np.nanmean(savi)),
            "min":  float(np.nanmin(savi)),
            "max":  float(np.nanmax(savi)),
            "std":  float(np.nanstd(savi)),
        }
        mark_savi_processed(date, str(out_path), stats)
        save_processed_data("savi", stats["mean"], date,
                            raster_path=str(out_path), metadata=stats)
        logger.info(f"SAVI {out_path.name} | mean={stats['mean']:.4f} "
                    f"(range [{stats['min']:.3f}, {stats['max']:.3f}])")
        return {"data": savi, "stats": stats, "filepath": out_path, "profile": profile}

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 2 — Kc  (thesis Table 9, §5.3)
    # ═══════════════════════════════════════════════════════════════════════

    def calculate_kc(self, savi_data: Dict) -> Dict:
        """
        Derive the crop coefficient from SAVI using the best-fit linear
        regression calibrated in thesis Table 9:

            Kc = 1.2088 × SAVI + 0.5375      R² = 0.882

        This is the "SAVI-FAO Moving-Averaged Kc" equation — best among
        six Kc parameterisations tested (NDVI/SAVI × FAO Kc / Moving-Avg
        Kc / Instrumental Kc).

        The slope (1.2088) and intercept (0.5375) are stored in config.py
        (WHEAT_PARAMS["savi_kc"]["slope"] and ["intercept"]).

        Kc is clipped to [0.30, 1.15]:
            0.30 = FAO-56 Kc_ini for spring wheat  (germination stage)
            1.15 = FAO-56 Kc_mid for spring wheat  (heading/flowering stage)
        This prevents physically unrealistic values from noisy SAVI pixels.

        Thesis §5.3 observations:
          - Kc ~0.30–0.40  in Nov–Dec (initial / germination stage)
          - Kc ~0.70–0.90  in Jan (development / tillering stage)
          - Kc ~1.00–1.15  in Feb–Mar (mid-season / heading/flowering stage)
          - Kc ~0.40–0.60  in Apr (late-season / maturity stage)
        """
        filepath = savi_data["filepath"]
        date_str = Path(filepath).stem.split("_")[-1]
        date_obj = datetime.strptime(date_str, "%Y%m%d")
        out_path = self.dirs["processed"]["kc"] / f"kc_{date_str}.tif"

        if step_already_processed("kc", date_obj):
            logger.info(f"Kc already processed {date_str} — skip")
            return {"filepath": out_path, "skipped": True}

        with rasterio.open(filepath) as src:
            savi    = src.read(1).astype("float64")
            nd      = src.nodata
            savi    = np.where(savi == nd, np.nan, savi) if nd is not None else savi
            profile = src.profile.copy()

        # Thesis Table 9 best-fit equation
        slope     = self.wheat_params["savi_kc"]["slope"]      # 1.2088
        intercept = self.wheat_params["savi_kc"]["intercept"]  # 0.5375
        kc = slope * savi + intercept

        # Clip to FAO-56 wheat Kc physiological range
        kc = np.where(np.isnan(savi), np.nan, np.clip(kc, KC_MIN, KC_MAX))

        wheat_mask      = self.load_wheat_mask(date_obj, savi.shape, profile)
        kc[~wheat_mask] = np.nan

        self.save_geotiff(kc, out_path, profile)
        stats = {
            "mean": float(np.nanmean(kc)),
            "min":  float(np.nanmin(kc)),
            "max":  float(np.nanmax(kc)),
            "std":  float(np.nanstd(kc)),
        }
        mark_kc_processed(date_obj, str(out_path), stats)
        save_processed_data("kc", stats["mean"], date_obj,
                            raster_path=str(out_path), metadata=stats)
        logger.info(f"Kc {out_path.name} | mean={stats['mean']:.4f} "
                    f"(range [{stats['min']:.3f}, {stats['max']:.3f}])")
        return {"data": kc, "stats": stats, "filepath": out_path, "profile": profile}

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 3 — ETc = Kc × ET₀  (thesis Eq. 4, §4.4)  [units: mm day⁻¹]
    # ═══════════════════════════════════════════════════════════════════════

    def calculate_etc(self, kc_data: Dict, pet_data: Dict) -> Dict:
        """
        Compute crop evapotranspiration per thesis Eq. 4:

            ETc = Kc × ET₀                        [mm day⁻¹]

        where:
          Kc  = crop coefficient (dimensionless) from Step 2
          ET₀ = INSAT-3DR daily potential evapotranspiration (mm day⁻¹)
                obtained from select_pet_daily() for the Sentinel date

        Thesis §5.4 (p. 51): "INSAT 3D daily reference evapotranspiration
        data of 4 km were resampled and used to multiply with Kc maps of
        available dates."

        Observed seasonal range (thesis §5.4):
          Nov–Dec: ETc = 2.0–3.7 mm/day  (germination / tillering)
          Jan:     ETc = 3.1–4.5 mm/day  (jointing)
          Feb:     ETc = 5.5–6.5 mm/day  ← PEAK (heading / flowering)
          Mar:     ETc = 4.5–6.6 mm/day  (grain filling)
          Apr:     ETc = 4.0–7.0 mm/day  (maturity / harvest)

        pet_data: output of select_pet_daily() — must contain 'data' array
                  in mm day⁻¹ and 'n_days' (= 1 for daily, or interval count
                  when falling back to interval-sum divided by interval_days).
        """
        filepath = kc_data["filepath"]
        date_str = Path(filepath).stem.split("_")[-1]
        date_obj = datetime.strptime(date_str, "%Y%m%d")
        out_path = self.dirs["processed"]["ETc"] / f"etc_{date_str}.tif"

        if step_already_processed("etc", date_obj):
            logger.info(f"ETc already processed {date_str} — skip")
            return {"filepath": out_path, "skipped": True}

        with rasterio.open(filepath) as src:
            kc      = src.read(1).astype("float64")
            nd      = src.nodata
            kc      = np.where(kc == nd, np.nan, kc) if nd is not None else kc
            profile = src.profile.copy()

        # If pet_data was built from select_pet_interval_sum, divide by n_days
        # to convert mm/interval → mm/day before multiplication.
        n_days = pet_data.get("n_days", 1)
        eto = pet_data["data"].astype("float64")
        if n_days > 1:
            eto = eto / float(n_days)
            logger.debug(f"ETc: converted interval PET → daily ({n_days} days)")

        # Resize if INSAT grid doesn't exactly match Kc (shouldn't happen
        # after load_insat_raster, but safeguard).
        if eto.shape != kc.shape:
            eto = zoom(
                eto,
                (kc.shape[0] / eto.shape[0], kc.shape[1] / eto.shape[1]),
                order=1,
            )

        # ETc = Kc × ET₀  [mm day⁻¹]  (thesis Eq. 4)
        etc = np.where(np.isnan(kc), np.nan, np.maximum(kc * eto, 0.0))

        wheat_mask       = self.load_wheat_mask(date_obj, kc.shape, profile)
        etc[~wheat_mask] = np.nan

        self.save_geotiff(etc, out_path, profile)
        stats = {
            "mean":  float(np.nanmean(etc)),
            "min":   float(np.nanmin(etc)),
            "max":   float(np.nanmax(etc)),
            "std":   float(np.nanstd(etc)),
            "units": "mm_per_day",
        }
        mark_etc_processed(date_obj, str(out_path), stats)
        save_processed_data("etc", stats["mean"], date_obj,
                            raster_path=str(out_path), metadata=stats)
        logger.info(
            f"ETc {out_path.name} | mean={stats['mean']:.2f} mm/day "
            f"(range [{stats['min']:.2f}, {stats['max']:.2f}])"
        )
        return {"data": etc, "stats": stats, "filepath": out_path, "profile": profile}

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 4 — CWR = ETc  (thesis §4.4)  [units: mm day⁻¹]
    # ═══════════════════════════════════════════════════════════════════════

    def calculate_cwr(self, etc_tif: Path) -> Dict:
        """
        Crop Water Requirement = crop evapotranspiration.

        Thesis §4.4 (p. 35): "CWR is the volume of water required to
        replenish ET loss from a cropped area."

        CWR = ETc   [mm day⁻¹]

        Seasonal CWR is obtained externally by time-series integration:
            CWR_seasonal = Σ (CWR_i × Δt_i)
        where Δt_i = days between consecutive Sentinel acquisition dates.

        Observed seasonal totals (thesis §5.4):
            2022-23: 395–680 mm/season
            2023-24: 495–720 mm/season
        These are consistent with ETc × ~150-season-days.
        """
        date_str = etc_tif.stem.split("_")[-1]
        date_obj = datetime.strptime(date_str, "%Y%m%d")
        out_path = self.dirs["processed"]["cwr"] / f"cwr_{date_str}.tif"

        if step_already_processed("cwr", date_obj):
            logger.info(f"CWR already processed {date_str} — skip")
            return {"filepath": out_path, "skipped": True}

        with rasterio.open(etc_tif) as src:
            etc     = src.read(1).astype("float64")
            nd      = src.nodata
            etc     = np.where(etc == nd, np.nan, etc) if nd is not None else etc
            profile = src.profile.copy()

        cwr = np.maximum(etc, 0.0)   # CWR ≥ 0 by physical constraint
        cwr = np.where(np.isnan(etc), np.nan, cwr)

        wheat_mask       = self.load_wheat_mask(date_obj, cwr.shape, profile)
        cwr[~wheat_mask] = np.nan

        self.save_geotiff(cwr, out_path, profile)
        stats = {
            "mean":  float(np.nanmean(cwr)),
            "min":   float(np.nanmin(cwr)),
            "max":   float(np.nanmax(cwr)),
            "std":   float(np.nanstd(cwr)),
            "units": "mm_per_day",
        }
        mark_cwr_processed(date_obj, str(out_path), stats)
        save_processed_data("cwr", stats["mean"], date_obj,
                            raster_path=str(out_path), metadata=stats)
        logger.info(f"CWR {out_path.name} | mean={stats['mean']:.2f} mm/day")
        return {"data": cwr, "stats": stats, "filepath": out_path, "profile": profile}

    # ═══════════════════════════════════════════════════════════════════════
    # STEP 5 — IWR = max(CWR − Pe, 0)  (thesis §4.5/§5.5)  [mm day⁻¹]
    # ═══════════════════════════════════════════════════════════════════════

    def calculate_iwr(
        self,
        cwr_tif: Path,
        rainfall_data: Dict,
    ) -> Dict:
        """
        Irrigation Water Requirement per thesis §4.5:

            IWR = max(CWR − Pe, 0)                [mm day⁻¹]

        Effective Rainfall  (FAO USDA-SCS formula, thesis §4.5 / §5.5):
        ─────────────────────────────────────────────────────────────────
            Pe = max(0.6·P_interval − 10, 0)      when P_interval ≤ 75 mm
            Pe = 0.8·P_interval − 25              when P_interval  > 75 mm

        where P_interval = cumulative rainfall over the Sentinel interval
        (5 days, mm).  The formula is calibrated for period totals.

        Pe_daily = Pe_interval / interval_days

        Typical Rabi-season rainfall in USN (thesis §5.5):
          "There was only scattered rainfall for 2-3 days in March."
          → P_interval ≈ 2–5 mm during rain events
          → Pe = max(0.6×3 − 10, 0) = 0   (almost always zero)
          → IWR ≈ CWR  throughout the season

        rainfall_data: output of select_rainfall_sum() containing:
          'data'   → 2-D raster of interval-sum rainfall (mm/interval)
          'n_days' → number of INSAT files summed over the interval
        """
        date_str = cwr_tif.stem.split("_")[-1]
        date_obj = datetime.strptime(date_str, "%Y%m%d")
        out_path = self.dirs["processed"]["iwr"] / f"iwr_{date_str}.tif"

        if step_already_processed("iwr", date_obj):
            logger.info(f"IWR already processed {date_str} — skip")
            return {"filepath": out_path, "skipped": True}

        with rasterio.open(cwr_tif) as src:
            cwr     = src.read(1).astype("float64")
            nd      = src.nodata
            cwr     = np.where(cwr == nd, np.nan, cwr) if nd is not None else cwr
            profile = src.profile.copy()

        # Interval rainfall (mm/interval) from INSAT rain product
        rain_interval = rainfall_data["data"].astype("float64")
        rain_interval = np.where(rain_interval < 0, 0.0, rain_interval)
        n_days        = max(int(rainfall_data.get("n_days", 1)), 1)

        if rain_interval.shape != cwr.shape:
            rain_interval = zoom(
                rain_interval,
                (cwr.shape[0] / rain_interval.shape[0],
                 cwr.shape[1] / rain_interval.shape[1]),
                order=1,
            )

        # FAO USDA-SCS effective rainfall on interval totals (thesis §4.5).
        # Threshold is scaled to the interval duration so the monthly-calibrated
        # formula applies correctly at the ~5-day Sentinel cadence.
        # See module-level compute_effective_rainfall() for scalar equivalent.
        _period_factor = float(n_days) / 30.0
        _pe_threshold = 75.0 * _period_factor
        eff_rain_interval = np.where(
            rain_interval <= _pe_threshold,
            np.maximum(0.6 * rain_interval - 10.0 * _period_factor, 0.0),
            np.maximum(0.8 * rain_interval - 25.0 * _period_factor, 0.0),
        )
        eff_rain_interval = np.maximum(eff_rain_interval, 0.0)

        # Convert effective rainfall interval total → daily rate for consistency
        # with CWR (mm/day).  Then subtract per unit time.
        eff_rain_daily = eff_rain_interval / float(n_days)  # mm/day

        # IWR = max(CWR − Pe, 0)  [mm day⁻¹]  — thesis §4.5
        iwr = np.clip(cwr - eff_rain_daily, 0.0, cwr)
        iwr = np.where(np.isnan(cwr), np.nan, iwr)

        wheat_mask       = self.load_wheat_mask(date_obj, cwr.shape, profile)
        iwr[~wheat_mask] = np.nan

        self.save_geotiff(iwr, out_path, profile)

        # Back-fill effective rainfall stats into rain_stats collection
        wheat_eff_int = eff_rain_interval[wheat_mask]
        update_rain_eff_rain(date_obj, float(np.nansum(wheat_eff_int))
                             if wheat_eff_int.size else 0.0)

        wheat_rain = rain_interval[wheat_mask]
        wheat_eff  = eff_rain_daily[wheat_mask]
        iwr_le_cwr = bool(np.nanmax(iwr[~np.isnan(cwr)] -
                                    cwr[~np.isnan(cwr)]) <= 0.001)

        stats = {
            "mean":              float(np.nanmean(iwr)),
            "min":               float(np.nanmin(iwr)),
            "max":               float(np.nanmax(iwr)),
            "std":               float(np.nanstd(iwr)),
            "iwr_le_cwr":        iwr_le_cwr,
            "mean_rain_mm_day":  float(np.nanmean(wheat_rain)) / n_days if wheat_rain.size else 0.0,
            "mean_eff_rain_mm_day": float(np.nanmean(wheat_eff))  if wheat_eff.size else 0.0,
            "interval_days":     n_days,
            "units":             "mm_per_day",
        }

        if not iwr_le_cwr:
            logger.error(f"IWR > CWR detected for {date_str} — check rainfall data")

        mark_iwr_processed(date_obj, str(out_path), stats)
        save_processed_data("iwr", stats["mean"], date_obj,
                            raster_path=str(out_path), metadata=stats)
        logger.info(
            f"IWR {out_path.name} | mean={stats['mean']:.2f} mm/day | "
            f"rain={stats['mean_rain_mm_day']:.2f} mm/day | "
            f"eff_rain={stats['mean_eff_rain_mm_day']:.2f} mm/day | "
            f"IWR≤CWR={iwr_le_cwr}"
        )
        return {"data": iwr, "stats": stats, "filepath": out_path, "profile": profile}

    # ═══════════════════════════════════════════════════════════════════════
    # Seasonal integration helper
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def compute_seasonal_total(
        raster_means: List[float],
        acquisition_dates: List[datetime],
    ) -> float:
        if len(raster_means) != len(acquisition_dates) or len(raster_means) < 2:
            raise ValueError("Need at least 2 scenes with matching dates")

        dates = sorted(zip(acquisition_dates, raster_means), key=lambda x: x[0])
        total = 0.0
        for i in range(len(dates)):
            d_curr, val = dates[i]
            if i == 0:
                # First scene: assume 5-day interval (Sentinel cadence)
                delta = 5
            else:
                delta = (d_curr - dates[i - 1][0]).days
            total += val * delta

        return total
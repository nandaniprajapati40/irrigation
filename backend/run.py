
import sys
import os
import re
import logging
import traceback
from datetime import datetime, timedelta
from pathlib import Path

import rasterio

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import DIRECTORIES
from processor import DataProcessor
import models
from ee_init import init_ee
from mongo import step_already_processed

# ── Logging ────────────────────────────────────────────────────────────────
log_file = DIRECTORIES["logs"] / "pipeline.log"
log_file.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# DATE EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

def extract_date(filename: str) -> datetime:
    m = re.search(r"\d{8}", filename)
    if m:
        return datetime.strptime(m.group(), "%Y%m%d")
    m = re.search(r"\d{2}[A-Z]{3}\d{4}", filename.upper())
    if m:
        return datetime.strptime(m.group(), "%d%b%Y")
    raise ValueError(f"No valid date in filename: {filename}")


# ═══════════════════════════════════════════════════════════════════════════
# FILE COLLECTORS
# ═══════════════════════════════════════════════════════════════════════════

def get_sentinel2_files():
    return sorted(DIRECTORIES["raw"]["sentinel2"].glob("S2_*.tif"))

def get_savi_files():
    return sorted(DIRECTORIES["processed"]["savi"].glob("savi_*.tif"))

def get_kc_files():
    return sorted(DIRECTORIES["processed"]["kc"].glob("kc_*.tif"))

def get_etc_files():
    return sorted(DIRECTORIES["processed"]["ETc"].glob("etc_*.tif"))

def get_cwr_files():
    return sorted(DIRECTORIES["processed"]["cwr"].glob("cwr_*.tif"))

def get_pet_files():
    return [
        {"date": extract_date(f.name), "filepath": f}
        for f in sorted(DIRECTORIES["raw"]["insat_pet"].glob("*.tif"))
    ]

def get_rainfall_files():
    return [
        {"date": extract_date(f.name), "filepath": f}
        for f in sorted(DIRECTORIES["raw"]["insat_rain"].glob("*.tif"))
    ]


# ═══════════════════════════════════════════════════════════════════════════
# INCREMENTAL GUARD
# ═══════════════════════════════════════════════════════════════════════════

def _output_exists(path: Path) -> bool:
    """True if output file exists and is not empty (corrupt-safe)."""
    return path.exists() and path.stat().st_size > 0


def _needs_processing(step: str, date: datetime, out_path: Path) -> bool:
    """
    Return True if this step/date genuinely needs to be (re)processed.

    Rules:
      1. Output file missing or empty → always process.
      2. Output file present but MongoDB says NOT done → process (DB lagged).
      3. MongoDB says done AND file present → skip.
    """
    db_done   = step_already_processed(step, date)
    file_done = _output_exists(out_path)

    if db_done and file_done:
        return False          # already complete — skip

    if db_done and not file_done:
        logger.warning(
            f"[{step}] DB says done for {date.date()} but output missing "
            f"({out_path.name}) — will re-process."
        )
        return True

    if not db_done and file_done:
        logger.warning(
            f"[{step}] Output exists for {date.date()} but not in DB "
            f"({out_path.name}) — will re-process to re-register."
        )
        return True

    return True               # neither done


# ═══════════════════════════════════════════════════════════════════════════
# PIPELINE STEPS  (all incremental, all error-isolated)
# ═══════════════════════════════════════════════════════════════════════════

def run_savi(processor: DataProcessor):
    """
    SAVI — incremental.
    Skips any Sentinel file whose savi_YYYYMMDD.tif already exists + DB record.
    """
    print("\n── SAVI ─────────────────────────────────────────────────────────")
    files = get_sentinel2_files()
    if not files:
        print("  No Sentinel-2 files found in raw/sentinel2/")
        return

    todo = []
    for tif in files:
        try:
            date     = extract_date(tif.name)
            out_path = DIRECTORIES["processed"]["savi"] / f"savi_{date.strftime('%Y%m%d')}.tif"
            if _needs_processing("savi", date, out_path):
                todo.append((tif, date))
        except Exception as e:
            logger.warning(f"SAVI pre-check failed for {tif.name}: {e}")

    total = len(files)
    skip  = total - len(todo)
    print(f"  {total} Sentinel files | {skip} already done | {len(todo)} to process")

    ok = err = 0
    for tif, date in todo:
        try:
            processor.calculate_savi({"date": date, "filepath": tif})
            ok += 1
        except Exception as e:
            err += 1
            logger.error(f"SAVI failed for {tif.name}: {e}\n{traceback.format_exc()}")

    print(f"  SAVI done — processed={ok}, errors={err}, skipped={skip}")


def run_kc(processor: DataProcessor):
    """
    Kc — incremental.
    Skips any SAVI file whose kc_YYYYMMDD.tif already exists + DB record.
    """
    print("\n── Kc ───────────────────────────────────────────────────────────")
    files = get_savi_files()
    if not files:
        print("  No SAVI files found — run SAVI first.")
        return

    todo = []
    for tif in files:
        try:
            date_str = Path(tif).stem.split("_")[-1]
            date     = datetime.strptime(date_str, "%Y%m%d")
            out_path = DIRECTORIES["processed"]["kc"] / f"kc_{date_str}.tif"
            if _needs_processing("kc", date, out_path):
                todo.append(tif)
        except Exception as e:
            logger.warning(f"Kc pre-check failed for {tif.name}: {e}")

    total = len(files)
    skip  = total - len(todo)
    print(f"  {total} SAVI files | {skip} already done | {len(todo)} to process")

    ok = err = 0
    for tif in todo:
        try:
            processor.calculate_kc({"filepath": tif})
            ok += 1
        except Exception as e:
            err += 1
            logger.error(f"Kc failed for {tif.name}: {e}\n{traceback.format_exc()}")

    print(f"  Kc done — processed={ok}, errors={err}, skipped={skip}")


def run_etc(processor: DataProcessor):
    """
    ETc = Kc × ET₀              [mm day⁻¹]

    ET₀ = single daily INSAT-3D/3DR/3DS PET value on (or nearest to, ±2 days)
          the Sentinel-2 acquisition date.

    Thesis §5.4: "INSAT 3D daily reference evapotranspiration data of 4 km
    were resampled and used to multiply with Kc maps of available dates."

    PET reprojected bilinear from native CRS (EPSG:3857) → EPSG:32644 (Sentinel 10 m grid).
    Incremental: skips any Kc file whose etc_YYYYMMDD.tif already exists + DB record.
    """
    print("\n── ETc ──────────────────────────────────────────────────────────")
    pet_files = get_pet_files()
    kc_files  = get_kc_files()

    if not pet_files:
        print("  No PET files found in raw/insat_pet/")
        return
    if not kc_files:
        print("  No Kc files found — run Kc first.")
        return

    # Build full list with prev_date pre-computed
    all_items = []
    for i, kc_tif in enumerate(kc_files):
        try:
            kc_date   = extract_date(kc_tif.name)
            prev_date = (
                extract_date(kc_files[i - 1].name)
                if i > 0
                else kc_date - timedelta(days=5)
            )
            date_str = kc_date.strftime("%Y%m%d")
            out_path = DIRECTORIES["processed"]["ETc"] / f"etc_{date_str}.tif"
            all_items.append((kc_tif, kc_date, prev_date, out_path))
        except Exception as e:
            logger.warning(f"ETc pre-check failed for {kc_tif.name}: {e}")

    todo  = [(t, d, p, o) for (t, d, p, o) in all_items if _needs_processing("etc", d, o)]
    total = len(all_items)
    skip  = total - len(todo)
    print(f"  {len(pet_files)} daily PET files | {total} Kc scenes | "
          f"{skip} ETc already done | {len(todo)} to process")

    ok = err = 0
    for kc_tif, kc_date, prev_date, _ in todo:
        try:
            with rasterio.open(kc_tif) as src:
                kc_arr  = src.read(1)
                profile = src.profile.copy()

           
            kc_data  = {"filepath": kc_tif, "profile": profile}
            pet_data = processor.select_pet_daily(
                kc_date, pet_files, sentinel_profile=profile
            )
            if pet_data is None:
                logger.warning(
                    f"ETc skipped {kc_date.date()} — "
                    "no INSAT PET within ±2 days. Check MOSDAC download coverage."
                )
                err += 1
                continue
            processor.calculate_etc(kc_data, pet_data)
            ok += 1
        except Exception as e:
            err += 1
            logger.error(f"ETc failed for {kc_tif.name}: {e}\n{traceback.format_exc()}")

    print(f"  ETc done — processed={ok}, errors={err}, skipped={skip}")


def run_cwr(processor: DataProcessor):
    """
    CWR — incremental.
    Skips any ETc file whose cwr_YYYYMMDD.tif already exists + DB record.
    """
    print("\n── CWR ──────────────────────────────────────────────────────────")
    etc_files = get_etc_files()
    if not etc_files:
        print("  No ETc files found — run ETc first.")
        return

    todo = []
    for etc_tif in etc_files:
        try:
            date_str = etc_tif.stem.split("_")[-1]
            date     = datetime.strptime(date_str, "%Y%m%d")
            out_path = DIRECTORIES["processed"]["cwr"] / f"cwr_{date_str}.tif"
            if _needs_processing("cwr", date, out_path):
                todo.append(etc_tif)
        except Exception as e:
            logger.warning(f"CWR pre-check failed for {etc_tif.name}: {e}")

    total = len(etc_files)
    skip  = total - len(todo)
    print(f"  {total} ETc files | {skip} already done | {len(todo)} to process")

    ok = err = 0
    for etc_tif in todo:
        try:
            processor.calculate_cwr(etc_tif)
            ok += 1
        except Exception as e:
            err += 1
            logger.error(f"CWR failed for {etc_tif.name}: {e}\n{traceback.format_exc()}")

    print(f"  CWR done — processed={ok}, errors={err}, skipped={skip}")


def run_iwr(processor: DataProcessor):
    """
    IWR = max(CWR − Pe, 0)
    Pe  = USDA-SCS effective rainfall on PERIOD total (mm per interval).
    Rain = SUM of daily INSAT rainfall over (prev_sentinel_date, curr_sentinel_date].

    Incremental: skips any CWR file whose iwr_YYYYMMDD.tif already exists + DB record.
    """
    print("\n── IWR ──────────────────────────────────────────────────────────")
    rain_files = get_rainfall_files()
    cwr_files  = get_cwr_files()

    if not cwr_files:
        print("  No CWR files found — run CWR first.")
        return
    if not rain_files:
        print("  No rainfall files found in raw/insat_rain/")
        return

    # Build full list with prev_date
    all_items = []
    for i, cwr_tif in enumerate(cwr_files):
        try:
            cwr_date  = extract_date(cwr_tif.name)
            prev_date = (
                extract_date(cwr_files[i - 1].name)
                if i > 0
                else cwr_date - timedelta(days=5)
            )
            date_str = cwr_date.strftime("%Y%m%d")
            out_path = DIRECTORIES["processed"]["iwr"] / f"iwr_{date_str}.tif"
            all_items.append((cwr_tif, cwr_date, prev_date, out_path))
        except Exception as e:
            logger.warning(f"IWR pre-check failed for {cwr_tif.name}: {e}")

    todo  = [(t, d, p, o) for (t, d, p, o) in all_items if _needs_processing("iwr", d, o)]
    total = len(all_items)
    skip  = total - len(todo)
    print(f"  {len(rain_files)} daily rain files | {total} CWR scenes | "
          f"{skip} IWR already done | {len(todo)} to process")

    ok = err = 0
    for cwr_tif, cwr_date, prev_date, _ in todo:
        try:
            with rasterio.open(cwr_tif) as src:
                cwr_profile = src.profile.copy()

            rain_data = processor.select_rainfall_sum(
                prev_date, cwr_date, rain_files, sentinel_profile=cwr_profile
            )
            
            processor.calculate_iwr(
                cwr_tif      = cwr_tif,
                rainfall_data = rain_data,
            )
            ok += 1
        except Exception as e:
            err += 1
            logger.error(f"IWR failed for {cwr_tif.name}: {e}\n{traceback.format_exc()}")

    print(f"  IWR done — processed={ok}, errors={err}, skipped={skip}")


def run_full_pipeline(processor: DataProcessor):
    print("\n" + "=" * 65)
    print("  FULL PIPELINE — INCREMENTAL (new files only)")
    print("=" * 65)
    run_savi(processor)
    run_kc(processor)
    run_etc(processor)
    run_cwr(processor)
    run_iwr(processor)
    # train_models()
    print("\n" + "=" * 65)
    print("  PIPELINE COMPLETE")
    print("=" * 65)


# ═══════════════════════════════════════════════════════════════════════════
# STATUS REPORT  (new helper — shows what's done / pending at a glance)
# ═══════════════════════════════════════════════════════════════════════════

def run_status():
    """Print a quick summary of how many files exist at each stage."""
    print("\n" + "=" * 65)
    print("  PIPELINE STATUS REPORT")
    print("=" * 65)

    stages = [
        ("Sentinel-2 raw",  list(DIRECTORIES["raw"]["sentinel2"].glob("S2_*.tif"))),
        ("SAVI",            list(DIRECTORIES["processed"]["savi"].glob("savi_*.tif"))),
        ("Kc",              list(DIRECTORIES["processed"]["kc"].glob("kc_*.tif"))),
        ("ETc",             list(DIRECTORIES["processed"]["ETc"].glob("etc_*.tif"))),
        ("CWR",             list(DIRECTORIES["processed"]["cwr"].glob("cwr_*.tif"))),
        ("IWR",             list(DIRECTORIES["processed"]["iwr"].glob("iwr_*.tif"))),
        ("PET (INSAT)",     list(DIRECTORIES["raw"]["insat_pet"].glob("*.tif"))),
        ("Rain (INSAT)",    list(DIRECTORIES["raw"]["insat_rain"].glob("*.tif"))),
    ]

    for name, files in stages:
        if files:
            dates = sorted(files)
            first = extract_date(dates[0].name).strftime("%Y-%m-%d")
            last  = extract_date(dates[-1].name).strftime("%Y-%m-%d")
            print(f"  {name:<18} {len(files):>4} files   [{first} → {last}]")
        else:
            print(f"  {name:<18}    0 files")

    print()
    # Pending work
    s2    = len(list(DIRECTORIES["raw"]["sentinel2"].glob("S2_*.tif")))
    savi  = len(list(DIRECTORIES["processed"]["savi"].glob("savi_*.tif")))
    kc    = len(list(DIRECTORIES["processed"]["kc"].glob("kc_*.tif")))
    etc   = len(list(DIRECTORIES["processed"]["ETc"].glob("etc_*.tif")))
    cwr   = len(list(DIRECTORIES["processed"]["cwr"].glob("cwr_*.tif")))
    iwr   = len(list(DIRECTORIES["processed"]["iwr"].glob("iwr_*.tif")))

    print(f"  Pending SAVI:  {s2  - savi:>4}  (of {s2}  Sentinel files)")
    print(f"  Pending Kc:    {savi - kc:>4}  (of {savi} SAVI files)")
    print(f"  Pending ETc:   {kc  - etc:>4}  (of {kc}  Kc files)")
    print(f"  Pending CWR:   {etc - cwr:>4}  (of {etc} ETc files)")
    print(f"  Pending IWR:   {cwr - iwr:>4}  (of {cwr} CWR files)")
    print("=" * 65)


# ═══════════════════════════════════════════════════════════════════════════
# DOWNLOAD OPTIONS
# ═══════════════════════════════════════════════════════════════════════════

def run_download_historical():
    """Option 8 — download all historical Sentinel-2 (GEE) data."""
    from downloader import SatelliteDownloader, get_all_rabi_seasons, HISTORY_START_YEAR
    seasons = get_all_rabi_seasons(HISTORY_START_YEAR)
    print("\n" + "=" * 65)
    print("  SENTINEL HISTORICAL DOWNLOAD — All Rabi Seasons 2021 → Today")
    print("=" * 65)
    for s, e in seasons:
        print(f"    {s.date()}  →  {e.date()}")
    if input("\n  Start? (y/n): ").strip().lower() != "y":
        print("  Cancelled.")
        return
    SatelliteDownloader().download_historical_seasons()


def run_download_new_only():
    """Option 9 — download only new Sentinel-2 images since last download."""
    from downloader import SatelliteDownloader
    print("\n" + "=" * 65)
    print("  SENTINEL NEW-ONLY DOWNLOAD")
    print("=" * 65)
    SatelliteDownloader().download_new_only()


def run_mosdac_historical():
    """Option 10 — AI agent: seed disk + download all historical MOSDAC PET + rainfall."""
    from mosdac_agent import MosdacDownloader
    MosdacDownloader().download_historical()


def run_mosdac_new_only():
    """Option 11 — AI agent: download only new MOSDAC PET + rainfall."""
    from mosdac_agent import MosdacDownloader
    MosdacDownloader().download_new_only()


def run_mosdac_seed():
    """Option 12 — Register all existing on-disk MOSDAC files in MongoDB."""
    from mosdac_agent import MosdacDownloader
    MosdacDownloader().seed_from_disk()


def train_models():
    print("\nTraining SARIMAX models …")
    models.train_all_models()
    print("Training done.")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN MENU
# ═══════════════════════════════════════════════════════════════════════════

def main():
    init_ee()
    processor = DataProcessor()

    print("\n" + "=" * 65)
    print("  IRRIGATION PIPELINE — INCREMENTAL RUNNER")
    print("=" * 65)
    print("  PROCESSING  (all steps are incremental — new files only)")
    print("  1.  Calculate SAVI")
    print("  2.  Calculate Kc")
    print("  3.  Calculate ETc  (Kc × Σ PET,  mm/interval)")
    print("  4.  Calculate CWR")
    print("  5.  Calculate IWR  (CWR − USDA-SCS(Σ Rain), mm/interval)")
    print("  6.  Run FULL pipeline (steps 1 → 5, incremental)")
    print("  7.  Train SARIMAX models")
    print("  STATUS")
    print("  s.  Show pipeline status (files counts at each stage)")
    print("  SENTINEL DOWNLOAD (GEE)")
    print("  8.  Download ALL historical Sentinel data (2021 → today)")
    print("  9.  Download NEW Sentinel images only")
    print("  MOSDAC DOWNLOAD — AI Agent (HTTP fast-path + browser fallback)")
    print("  10. Download ALL historical MOSDAC data (seed + fill gaps)")
    print("  11. Download NEW MOSDAC data only  (last 7 days)")
    print("  12. Seed from disk  (register existing files in MongoDB)")
    print("  0.  Exit")
    print("=" * 65)

    choice = input("Select: ").strip().upper()

    match choice:
        case "1":  
            run_savi(processor)
        case "2":  
            run_kc(processor)
        case "3":  
            run_etc(processor)
        case "4":  
            run_cwr(processor)
        case "5":  
            run_iwr(processor)
        case "6":  
            run_full_pipeline(processor)
        case "7":  
            train_models()
        case "S":  
            run_status()
        case "8":  
            run_download_historical()
        case "9":  
            run_download_new_only()
        case "10": 
            run_mosdac_historical()
        case "11": 
            run_mosdac_new_only()
        case "12": 
            run_mosdac_seed()
        case "0":
            print("Exiting.")
            sys.exit(0)
        case _:
            print("Invalid choice.")
            sys.exit(1)


if __name__ == "__main__":
    main()
    print("Done.")

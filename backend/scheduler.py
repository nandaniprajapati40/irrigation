"""
scheduler.py — Sequential dynamic nightly pipeline
═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import asyncio
import logging
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Dict

from apscheduler.schedulers.background import BackgroundScheduler
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent

from config import DIRECTORIES

logger = logging.getLogger(__name__)

# ── Shared state ───────────────────────────────────────────────────────────
MAINTENANCE_MODE = False
_pipeline_lock   = threading.Lock()


def is_rabi_season(dt: datetime | None = None) -> bool:
    dt = dt or datetime.now()
    return dt.month in (11, 12, 1, 2, 3, 4)


# ═══════════════════════════════════════════════════════════════════════════
# STAGE HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _count_local_sentinel_files() -> int:
    """Return the number of S2_*.tif files currently on disk."""
    return len(list(DIRECTORIES["raw"]["sentinel2"].glob("S2_*.tif")))


def _ensure_thread_event_loop() -> None:
    """
    APScheduler worker threads inherit the main uvicorn asyncio event loop
    reference via asyncio.get_event_loop(). Playwright's sync API calls
    loop.is_running() and crashes if it finds a running loop.

    This helper assigns a fresh idle event loop to the current thread,
    so any Playwright code executed in this thread sees no running loop.
    Must be called at the top of every stage function that (directly or
    indirectly) uses Playwright sync API.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.set_event_loop(asyncio.new_event_loop())
    except RuntimeError:
        # No current event loop at all — create one
        asyncio.set_event_loop(asyncio.new_event_loop())


# ── Stage 1: Sentinel check + direct download ──────────────────────────────

def _stage1_sentinel_sync(
    single_image_callback: Optional[Callable[[Path], None]] = None,
) -> List[Path]:
    """
    Ask GEE whether any new Sentinel overpass occurred since our last file.
    Downloads new images directly via SatelliteDownloader.

    Returns a list of newly downloaded local paths.
    Returns an empty list if nothing new — pipeline CONTINUES with existing
    data on disk.
    """
    logger.info("▶ Stage 1 — Sentinel check + direct download")

    before = _count_local_sentinel_files()

    try:
        from downloader import SatelliteDownloader

        dl = SatelliteDownloader()
        result = dl.download_new_only()   # returns dict with 'downloaded' etc.

        after = _count_local_sentinel_files()
        n_new = after - before

        new_tifs = []
        for date_str in result.get('downloaded', []):
            ymd = date_str.replace('-', '')
            tif = DIRECTORIES["raw"]["sentinel2"] / f"S2_{ymd}.tif"
            if tif.exists():
                new_tifs.append(tif)

        if n_new == 0 and not new_tifs:
            logger.info(
                "  Stage 1 — no new Sentinel files found. "
                "Pipeline will continue with existing data on disk."
            )
            return []

        logger.info(
            f"  Stage 1 ✓ — {len(new_tifs)} new file(s) downloaded: "
            + ", ".join(p.name for p in new_tifs)
        )
        return new_tifs

    except Exception as e:
        logger.error(f"  Stage 1 FAILED: {e}", exc_info=True)
        return []


# ── Stage 2: MOSDAC order placement ────────────────────────────────────────

def _stage2_mosdac_order() -> Optional[List[str]]:
    """
    Use MosdacAgent to place orders for any missing MOSDAC data.
    No download happens here; only order placement.
    Returns order_keys list if successful, None on failure.

    IMPORTANT: _ensure_thread_event_loop() MUST be called first.
    APScheduler worker threads inherit uvicorn's running asyncio loop.
    Playwright's sync API detects this and raises:
      "It looks like you are using Playwright Sync API inside the asyncio loop."
    Assigning a fresh idle loop to this thread prevents that crash and allows
    unlimited nightly re-runs.
    """
    _ensure_thread_event_loop()

    logger.info("▶ Stage 2 — MOSDAC order placement")
    try:
        from mosdac_agent import MosdacAgent
        agent = MosdacAgent(headless=True)

        order_keys = agent.place_orders_and_return_keys()

        if order_keys:
            logger.info(f"  Stage 2 ✓ — orders placed: {order_keys}")
        else:
            logger.info("  Stage 2 ✓ — no orders needed or placed")

        return order_keys
    except Exception as e:
        logger.error(f"  Stage 2 FAILED: {e}", exc_info=True)
        return None


# ── Stage 3: MOSDAC download ───────────────────────────────────────────────

def _stage3_mosdac_download(order_keys: List[str] = None) -> bool:
    """
    Use MosdacDownloader to fetch files from the latest order.

    Args:
        order_keys: List of order folder names from Stage 2

    Returns True if successful (or no data to download), False on failure.
    """
    logger.info("▶ Stage 3 — MOSDAC download")

    if not order_keys:
        logger.warning("  Stage 3 — No order_keys provided, skipping download")
        return True  # Non-fatal: continue pipeline

    try:
        from mosdac_downloader import MosdacDownloader
        downloader = MosdacDownloader()

        stats = downloader.download_from_orders(order_keys)

        pet_ok  = stats.get("pet",  {}).get("downloaded", 0)
        rain_ok = stats.get("rain", {}).get("downloaded", 0)
        logger.info(f"  Stage 3 ✓ — PET downloaded={pet_ok}, RAIN downloaded={rain_ok}")
        return True
    except Exception as e:
        logger.error(f"  Stage 3 FAILED: {e}", exc_info=True)
        return False


# ── Stage 4: Incremental processing pipeline ───────────────────────────────

def _stage4_process() -> bool:
    """
    Run SAVI → Kc → ETc → CWR → IWR for any Sentinel dates not yet processed.
    Returns True on success, False if any critical error occurred.
    """
    logger.info("▶ Stage 4 — Incremental processing pipeline")
    try:
        from run import run_savi, run_kc, run_etc, run_cwr, run_iwr
        from processor import DataProcessor

        p = DataProcessor()
        run_savi(p)
        run_kc(p)
        run_etc(p)
        run_cwr(p)
        run_iwr(p)

        logger.info("  Stage 4 ✓ — processing pipeline complete")
        return True
    except Exception as e:
        logger.error(f"  Stage 4 FAILED: {e}", exc_info=True)
        return False


# ── Stage 5: GeoServer raster update ───────────────────────────────────────

def _stage5_geoserver(generate_callback: Optional[Callable] = None) -> bool:
    """
    Reassign numbered raster names, delete the file that fell out of the
    60-day window, and push the new rasters to GeoServer coverage stores.
    """
    logger.info("▶ Stage 5 — GeoServer raster update")
    try:
        if generate_callback is not None:
            generate_callback()
        else:
            from main import generate_operational_rasters
            generate_operational_rasters()

        logger.info("  Stage 5 ✓ — GeoServer updated, rasters renumbered")
        return True
    except Exception as e:
        logger.error(f"  Stage 5 FAILED: {e}", exc_info=True)
        return False


# ── Invalidate dataset cache ───────────────────────────────────────────────

def _invalidate_forecast_cache() -> None:
    """Tell main.py to reload the CWR/IWR datasets on the next forecast call."""
    try:
        import main as _main
        _main._fc_cache["cwr_count"] = -1
        _main._fc_cache["iwr_count"] = -1
        logger.debug("  Forecast dataset cache invalidated.")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# MASTER PIPELINE — runs all five stages in sequence
# ═══════════════════════════════════════════════════════════════════════════

def run_nightly_pipeline(
    generate_callback: Optional[Callable] = None,
    single_image_callback: Optional[Callable[[Path], None]] = None,
) -> None:
    """
    Full sequential pipeline triggered at 00:00 IST.

    Flow (ALL five stages always run):
      Stage 1 — Sentinel check + direct download
      Stage 2 — MOSDAC order placement (only orders) -> returns order_keys
      Stage 3 — MOSDAC download (SFTP) with order_keys
      Stage 4 — Incremental processing (SAVI → Kc → ETc → CWR → IWR)
      Stage 5 — GeoServer raster renaming + update
    """
    global MAINTENANCE_MODE

    if not is_rabi_season():
        logger.info(
            f"[pipeline] Outside Rabi season ({datetime.now().strftime('%b')}) "
            "— nightly pipeline skipped."
        )
        return

    if not _pipeline_lock.acquire(blocking=False):
        logger.warning("[pipeline] Already running — skipped (lock held).")
        return

    MAINTENANCE_MODE = True
    start_time = datetime.now()
    logger.info("═" * 65)
    logger.info(f"  NIGHTLY PIPELINE STARTED  {start_time.strftime('%Y-%m-%d %H:%M:%S IST')}")
    logger.info("═" * 65)

    stage_results = {}
    order_keys = None

    try:
        # Stage 1
        new_files = _stage1_sentinel_sync(single_image_callback)
        stage_results["stage1"] = bool(new_files)

        # Stage 2 — asyncio loop isolation is handled inside _stage2_mosdac_order
        order_keys = _stage2_mosdac_order()
        stage_results["stage2"] = order_keys is not None

        # Stage 3
        s3_ok = _stage3_mosdac_download(order_keys)
        stage_results["stage3"] = s3_ok

        # Stage 4
        s4_ok = _stage4_process()
        stage_results["stage4"] = s4_ok
        if s4_ok:
            _invalidate_forecast_cache()

        # Stage 5
        s5_ok = _stage5_geoserver(generate_callback)
        stage_results["stage5"] = s5_ok

    except Exception as e:
        logger.error(f"[pipeline] Unexpected error: {e}", exc_info=True)
        traceback.print_exc()
    finally:
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info("═" * 65)
        logger.info(f"  NIGHTLY PIPELINE COMPLETE  elapsed={elapsed/60:.1f} min")
        for stage, ok in stage_results.items():
            logger.info(f"    {'✓' if ok else '✗'} {stage}")
        logger.info("═" * 65)
        MAINTENANCE_MODE = False
        _pipeline_lock.release()


# ═══════════════════════════════════════════════════════════════════════════
# WATCHDOG — fires Stage 4 + 5 immediately when a new .tif appears on disk
# ═══════════════════════════════════════════════════════════════════════════

class NewSentinelHandler(FileSystemEventHandler):
    """Watches raw/sentinel2/ for new S2_YYYYMMDD.tif files."""

    def __init__(
        self,
        generate_callback: Optional[Callable] = None,
        single_image_callback: Optional[Callable[[Path], None]] = None,
    ):
        super().__init__()
        self.generate_callback      = generate_callback
        self.single_image_callback  = single_image_callback

    def on_created(self, event: FileCreatedEvent):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() != ".tif":
            return
        if not path.name.startswith("S2_"):
            return
        logger.info(f"Watchdog: new file detected → {path.name}")
        threading.Thread(
            target=self._safe_run, args=(path,), daemon=True
        ).start()

    def _safe_run(self, path: Path):
        global MAINTENANCE_MODE

        if not _pipeline_lock.acquire(blocking=False):
            logger.warning(
                f"Watchdog: pipeline already running — "
                f"{path.name} will be processed on the next run."
            )
            return

        MAINTENANCE_MODE = True
        try:
            logger.info(f"Watchdog pipeline: {path.name}")

            if self.single_image_callback:
                self.single_image_callback(path)
            else:
                _stage4_process()

            _invalidate_forecast_cache()
            _stage5_geoserver(self.generate_callback)
            logger.info(f"Watchdog pipeline complete for {path.name}")

        except Exception as e:
            logger.error(f"Watchdog pipeline error for {path.name}: {e}", exc_info=True)
        finally:
            MAINTENANCE_MODE = False
            _pipeline_lock.release()


# ═══════════════════════════════════════════════════════════════════════════
# SEASON GATE NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════════════════

def _season_start():
    logger.info(
        "★ Rabi season OPEN (November 1). "
        "Nightly pipeline active until May 1."
    )

def _season_end():
    logger.info(
        "★ Rabi season CLOSED (May 1). "
        "Nightly pipeline suspended until November 1."
    )


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def start_scheduler(
    delete_callback: Callable,
    generate_callback: Callable,
    download_and_process_callback: Optional[Callable] = None,
    single_image_pipeline_callback: Optional[Callable[[Path], None]] = None,
) -> tuple:
    """
    Start APScheduler (time trigger) + Watchdog (file-system trigger).
    """
    sentinel_dir = DIRECTORIES["raw"]["sentinel2"]
    sentinel_dir.mkdir(parents=True, exist_ok=True)

    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

    # 00:00 nightly — full sequential pipeline
    scheduler.add_job(
        func               = run_nightly_pipeline,
        trigger            = "cron",
        hour               = 10,
        minute             = 0,
        kwargs             = {
            "generate_callback":     generate_callback,
            "single_image_callback": single_image_pipeline_callback,
        },
        id                 = "nightly_pipeline",
        replace_existing   = True,
        misfire_grace_time = 3600,
    )

    # Nov 1 — season open
    scheduler.add_job(
        _season_start,
        trigger          = "cron",
        month=11, day=1, hour=0, minute=1,
        id               = "season_start",
        replace_existing = True,
    )

    # May 1 — season close
    scheduler.add_job(
        _season_end,
        trigger          = "cron",
        month=5, day=1, hour=0, minute=1,
        id               = "season_end",
        replace_existing = True,
    )

    scheduler.start()
    logger.info("APScheduler started (IST):")
    logger.info("  00:00 daily — nightly pipeline (5 stages, Rabi season only)")
    logger.info("  Nov 1       — season-open notification")
    logger.info("  May 1       — season-close notification")

    # Watchdog
    handler = NewSentinelHandler(
        generate_callback      = generate_callback,
        single_image_callback  = single_image_pipeline_callback,
    )
    observer = Observer()
    observer.schedule(handler, str(sentinel_dir), recursive=False)
    observer.start()
    logger.info(f"Watchdog active — watching: {sentinel_dir}")

    return scheduler, observer
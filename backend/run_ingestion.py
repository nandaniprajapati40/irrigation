"""
run_ingestion.py
═══════════════════════════════════════════════════════════════════════════════
Entry point for running data ingestion system in production.

Usage:
  python run_ingestion.py --mode once --date 2024-03-15
  python run_ingestion.py --mode batch --days 7
  python run_ingestion.py --mode scheduler --start
  python run_ingestion.py --status
  python run_ingestion.py --cleanup-cache
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=os.getenv("INGESTION_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("./logs/ingestion.log"),
    ],
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

def load_config() -> dict:
    """Load configuration from environment and defaults."""
    return {
        "mongodb_uri": os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
        "mongodb_db": os.getenv("MONGODB_DB", "irrigation"),
        "cache_dir": Path(os.getenv("INGESTION_CACHE_DIR", "./data/cache")),
        "temp_dir": Path(os.getenv("INGESTION_TEMP_DIR", "/tmp/ingestion")),
        "collection_name": "sentinel_images",
        "max_retries": int(os.getenv("INGESTION_MAX_RETRIES", 3)),
        "lookback_days": int(os.getenv("INGESTION_LOOKBACK_DAYS", 7)),
        "cache_ttl_days": int(os.getenv("INGESTION_CACHE_TTL_DAYS", 180)),
        "aoi_bounds": {
            "north": float(os.getenv("AOI_NORTH", 30.5)),
            "south": float(os.getenv("AOI_SOUTH", 29.5)),
            "east": float(os.getenv("AOI_EAST", 81.0)),
            "west": float(os.getenv("AOI_WEST", 79.5)),
        },
        "max_cloud_cover": float(os.getenv("SENTINEL_MAX_CLOUD_COVER", 20.0)),
    }


# ═══════════════════════════════════════════════════════════════════════════
# INITIALIZATION
# ═══════════════════════════════════════════════════════════════════════════

def setup_system(config: dict):
    """Initialize ingestion system."""
    from storage_mongodb import create_mongodb_backend
    from cache_manager import create_local_cache
    from sentinel_data_source import create_sentinel_source
    from ingestion_manager import IngestionManager
    
    logger.info("Initializing data ingestion system...")
    
    # Create storage
    storage = create_mongodb_backend(
        collection_name=config["collection_name"],
        mongo_uri=config["mongodb_uri"],
    )
    
    # Create cache
    cache = create_local_cache(
        cache_dir=config["cache_dir"],
        ttl_days=config["cache_ttl_days"],
    )
    
    # Create data source
    data_source = create_sentinel_source(
        aoi_bounds=config["aoi_bounds"],
        max_cloud_cover=config["max_cloud_cover"],
    )
    
    # Create manager
    manager = IngestionManager(
        data_source=data_source,
        storage_backend=storage,
        cache_backend=cache,
        temp_dir=config["temp_dir"],
        max_retries=config["max_retries"],
    )
    
    logger.info("✓ System initialized")
    return manager


# ═══════════════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

def cmd_ingest_once(manager, date_str: str):
    """Ingest data for a single date."""
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        logger.error(f"Invalid date format: {date_str}. Use YYYY-MM-DD")
        return False
    
    logger.info(f"Ingesting data for {date.date()}")
    result = manager.ingest(date)
    
    logger.info(f"Result: {result.success}")
    logger.info(f"Stage: {result.stage_completed}/6")
    logger.info(f"Duration: {result.duration_seconds:.2f}s")
    
    if not result.success:
        logger.error(f"Error: {result.error}")
        return False
    
    return True


def cmd_ingest_batch(manager, days: int):
    """Ingest last N days."""
    logger.info(f"Ingesting last {days} days...")
    
    dates = [
        datetime.now() - timedelta(days=i)
        for i in range(1, days + 1)
    ]
    
    results = manager.ingest_batch(dates)
    
    successful = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    
    logger.info(f"Results: {successful}/{len(results)} successful, {failed} failed")
    
    for result in results:
        status = "✓" if result.success else "✗"
        logger.info(f"  {status} {result.date.date()}: stage {result.stage_completed}")
    
    return failed == 0


def cmd_scheduler_start(manager, config: dict):
    """Start daily scheduler."""
    try:
        from ingestion_scheduler import IngestionScheduler
        
        scheduler = IngestionScheduler(
            manager=manager,
            lookback_days=config["lookback_days"],
            job_name="sentinel_daily_ingest",
        )
        
        # Schedule for 2 AM UTC daily
        scheduler.schedule_daily(hour=2, minute=0)
        
        logger.info("Scheduler started")
        logger.info("Press Ctrl+C to stop")
        
        # Keep running
        import time
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Stopping scheduler...")
            scheduler.stop()
            
    except ImportError:
        logger.error("APScheduler not installed")
        logger.info("Install with: pip install apscheduler")
        return False
    except Exception as e:
        logger.error(f"Scheduler error: {e}")
        return False
    
    return True


def cmd_scheduler_status(manager):
    """Get scheduler status."""
    try:
        from ingestion_scheduler import IngestionScheduler
        
        # Create temporary scheduler to check job status
        scheduler = IngestionScheduler(manager, lookback_days=7)
        status = scheduler.get_status()
        
        logger.info(f"Job: {status['job_name']}")
        logger.info(f"Running: {status['scheduler_running']}")
        logger.info(f"Next run: {status['job_next_run']}")
        logger.info(f"Last run: {status['last_run']}")
        
        if status['last_result']:
            result = status['last_result']
            logger.info(f"Last result:")
            logger.info(f"  Total: {result.get('total_dates')}")
            logger.info(f"  Successful: {result.get('successful')}")
            logger.info(f"  Failed: {result.get('failed')}")
        
    except ImportError:
        logger.error("APScheduler not installed")
        return False
    except Exception as e:
        logger.error(f"Error: {e}")
        return False
    
    return True


def cmd_status_report(manager):
    """Generate status report."""
    logger.info("Generating status report...")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    status = manager.get_ingestion_status(start_date, end_date)
    
    logger.info("=" * 70)
    logger.info("INGESTION STATUS (Last 30 days)")
    logger.info("=" * 70)
    logger.info(f"Available in source: {status.get('total_available_in_source')}")
    logger.info(f"Stored in MongoDB: {status.get('total_stored_in_mongodb')}")
    logger.info(f"Not yet stored: {status.get('not_yet_stored')}")
    logger.info(f"Coverage: {status.get('coverage_percent')}%")
    
    cache_stats = status.get('cache_stats', {})
    logger.info("\nCache Statistics:")
    logger.info(f"  Files: {cache_stats.get('total_files')}")
    logger.info(f"  Size: {cache_stats.get('total_size_mb')} MB")
    logger.info(f"  Oldest: {cache_stats.get('oldest_file_age_days')} days")
    logger.info(f"  TTL: {cache_stats.get('ttl_days')} days")
    
    return True


def cmd_cleanup_cache(manager):
    """Clean up expired cache files."""
    logger.info("Cleaning up expired cache files...")
    
    deleted = manager.cache.cleanup_expired()
    logger.info(f"Deleted {deleted} files")
    
    cache_stats = manager.cache.get_cache_stats()
    logger.info(f"Cache now contains {cache_stats['total_files']} files ({cache_stats['total_size_mb']} MB)")
    
    return True


def cmd_cleanup_temp(manager):
    """Clean up temporary files."""
    logger.info("Cleaning up temporary files...")
    
    deleted = manager.cleanup_temp_dir()
    logger.info(f"Deleted {deleted} temporary files")
    
    return True


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Data ingestion system for Sentinel-2 satellite imagery"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Ingest single date
    ingest_parser = subparsers.add_parser("ingest-once", help="Ingest single date")
    ingest_parser.add_argument("--date", required=True, help="Date (YYYY-MM-DD)")
    
    # Ingest batch
    batch_parser = subparsers.add_parser("ingest-batch", help="Ingest multiple days")
    batch_parser.add_argument("--days", type=int, default=7, help="Number of days")
    
    # Scheduler
    scheduler_parser = subparsers.add_parser("scheduler", help="Scheduler commands")
    scheduler_parser.add_argument("--action", choices=["start", "status"], default="status")
    
    # Status
    subparsers.add_parser("status", help="Show ingestion status")
    
    # Cleanup
    cleanup_parser = subparsers.add_parser("cleanup", help="Cleanup operations")
    cleanup_parser.add_argument("--target", choices=["cache", "temp"], default="cache")
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config()
    
    # Create output directories
    Path("./logs").mkdir(exist_ok=True)
    
    # Setup system
    try:
        manager = setup_system(config)
    except Exception as e:
        logger.error(f"Failed to initialize system: {e}")
        return 1
    
    # Execute command
    success = False
    
    try:
        if args.command == "ingest-once":
            success = cmd_ingest_once(manager, args.date)
        elif args.command == "ingest-batch":
            success = cmd_ingest_batch(manager, args.days)
        elif args.command == "scheduler":
            if args.action == "start":
                success = cmd_scheduler_start(manager, config)
            else:
                success = cmd_scheduler_status(manager)
        elif args.command == "status":
            success = cmd_status_report(manager)
        elif args.command == "cleanup":
            if args.target == "cache":
                success = cmd_cleanup_cache(manager)
            else:
                success = cmd_cleanup_temp(manager)
        else:
            parser.print_help()
            success = False
            
    except Exception as e:
        logger.error(f"Command failed: {e}", exc_info=True)
        success = False
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

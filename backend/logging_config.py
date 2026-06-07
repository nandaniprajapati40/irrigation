"""
logging_config.py — centralised logging for the Irrigation Monitoring System.
Called once at startup: from logging_config import setup_logging; setup_logging()
"""
import logging, sys
from pathlib import Path


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if root.handlers:          # already configured — skip
        return
    root.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(level)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    try:
        from config import DIRECTORIES
        log_dir = DIRECTORIES["logs"]
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_dir / "app.log", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:
        pass   # no file handler if config not available

    for noisy in ("urllib3", "google", "googleapiclient", "apscheduler",
                  "watchdog"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger(__name__).info("Logging initialised.")
"""
Centralized logging configuration.
All loggers write to:
  - stdout  (so Streamlit subprocess streaming picks them up)
  - logs/trading_sim.log  (rotating, 10 MB × 5 backups)
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
LOG_FILE = os.path.join(LOG_DIR, "trading_sim.log")

_CONSOLE_FMT = "%(asctime)s %(levelname)-8s %(message)s"
_FILE_FMT    = "%(asctime)s %(levelname)-8s %(name)s %(message)s"
_DATE_FMT    = "%Y-%m-%d %H:%M:%S"

_configured: set = set()


def get_logger(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """
    Return a named logger with console + file handlers.
    Safe to call multiple times — handlers are added only once.
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    logger = logging.getLogger(name)
    if name in _configured:
        return logger
    _configured.add(name)

    logger.setLevel(level)
    logger.propagate = False

    # ── Console (stdout so Streamlit subprocess captures it) ──────────────────
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(_CONSOLE_FMT, datefmt=_DATE_FMT))
    logger.addHandler(console)

    # ── Rotating file (DEBUG and above) ───────────────────────────────────────
    try:
        file_h = RotatingFileHandler(
            LOG_FILE,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_h.setLevel(logging.DEBUG)
        file_h.setFormatter(logging.Formatter(_FILE_FMT, datefmt=_DATE_FMT))
        logger.addHandler(file_h)
    except Exception:
        pass  # log dir unwritable — console only

    return logger

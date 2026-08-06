"""Issue #9: Centralized logging configuration.

One function called once at program start. Writes to both stdout (for
humans watching) and logs/etl.log (for grep/debugging after the fact).

Every log line includes a run_id so you can trace one execution end-to-end:
    grep 'run_id=a1b2c3d4' logs/etl.log
"""
from __future__ import annotations

import logging
import sys
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging(log_level: str = "INFO") -> str:
    """Set up logging for the whole pipeline.

    Returns:
        A short run_id embedded in every log record. Also returned so
        main.py can print it prominently at the start of a run.
    """
    project_root = Path(__file__).resolve().parent.parent
    logs_dir = project_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    run_id = uuid.uuid4().hex[:12]

    # Format includes run_id so every line is traceable
    fmt = f"%(asctime)s [%(levelname)s] [run_id={run_id}] %(name)s - %(message)s"
    formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

    # Console handler — for humans
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)

    # Rotating file handler — 5 MB per file, keep 5 backups.
    # Rotation prevents logs from filling the disk on a long-running scheduler.
    file_handler = RotatingFileHandler(
        logs_dir / "etl.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    # Configure root logger — every module's getLogger(__name__) inherits this
    root = logging.getLogger()
    root.setLevel(log_level.upper())
    # Clear any existing handlers (important when re-running in Jupyter/tests)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)

    # Quiet down noisy third-party loggers
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    return run_id
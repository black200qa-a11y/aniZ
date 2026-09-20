from __future__ import annotations

import logging
import sys
from pathlib import Path

from loguru import logger


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        logger.opt(exception=record.exc_info, depth=6).log(level, record.getMessage())


def configure_logging(level: str = "INFO", log_dir: Path = Path("./logs")) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(sys.stdout, level=level.upper(), colorize=False, enqueue=True, backtrace=True, diagnose=False,
               format="{time:YYYY-MM-DDTHH:mm:ss.SSSZ} | {level:<8} | {name}:{line} | {message}")
    logger.add(log_dir / "pipeline.log", level="DEBUG", rotation="00:00", retention="14 days", compression="gz", enqueue=True,
               backtrace=True, diagnose=False, format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{line} | {message}")
    logger.add(log_dir / "errors.log", level="WARNING", rotation="00:00", retention="30 days", compression="gz", enqueue=True,
               backtrace=True, diagnose=True, format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{line} | {message}\n{exception}")
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "fastapi", "pyrogram"):
        logging.getLogger(name).handlers = [InterceptHandler()]
        logging.getLogger(name).propagate = False

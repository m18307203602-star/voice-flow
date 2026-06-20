"""应用日志 — 同时输出到文件和 stderr"""
import sys
import logging
from pathlib import Path

LOG_DIR = Path.home() / ".voice_flow"
LOG_PATH = LOG_DIR / "app.log"


def setup_logging() -> logging.Logger:
    """配置日志：写入 ~/.voice_flow/app.log"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("voice_flow")
    logger.setLevel(logging.DEBUG)

    # 文件 handler（每次启动清空旧日志，避免无限增长）
    fh = logging.FileHandler(str(LOG_PATH), mode='w', encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    ))
    logger.addHandler(fh)

    # stderr handler
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.WARNING)
    sh.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    logger.addHandler(sh)

    return logger

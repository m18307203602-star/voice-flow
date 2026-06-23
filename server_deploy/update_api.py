"""更新 API — 版本检查 + 安装包下载"""

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

VERSION_FILE = Path(os.environ.get(
    "VERSION_FILE",
    "/opt/voice-flow-server/version.json"
))

DOWNLOADS_DIR = Path(os.environ.get(
    "DOWNLOADS_DIR",
    "/opt/voice-flow-server/downloads"
))


def _load_version() -> dict:
    """加载版本清单，文件不存在返回默认值"""
    if VERSION_FILE.exists():
        return json.loads(VERSION_FILE.read_text(encoding="utf-8"))
    return {"version": "1.0.0", "url": "", "size": 0, "notes": ""}


@router.get("/api/version")
def get_version():
    """返回最新版本信息（公开端点，无需认证）"""
    return _load_version()


@router.get("/downloads/{filename}")
def download_file(filename: str):
    """下载安装包"""
    path = DOWNLOADS_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        str(path),
        media_type="application/octet-stream",
        filename=filename,
    )

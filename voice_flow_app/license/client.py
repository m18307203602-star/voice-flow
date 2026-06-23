"""License server HTTP client

Server URL is configurable via set_server_url(). Default points to production.
"""

import httpx
from typing import Optional

_server_url = "http://39.105.108.173:8000"
TIMEOUT = 10.0
FETCH_TIMEOUT = 15.0

# ── Bearer Token for /api/prompts (Layer 1 of server defense) ──
_APP_TOKEN = "vf-prompts-6F1A-BEA9-3BC5-CB78"


def set_server_url(url: str):
    """设置许可证服务器地址（启动时从 config 调用）"""
    global _server_url
    _server_url = url.rstrip("/")


def _url(path: str) -> str:
    return f"{_server_url}{path}"


async def activate(machine_code: str, license_key: str) -> dict:
    """POST /api/activate — activate with license key"""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.post(
            _url("/api/activate"),
            json={"machine_code": machine_code, "license_key": license_key},
        )
        r.raise_for_status()
        return r.json()


async def validate(machine_code: str, license_payload: str) -> dict:
    """GET /api/validate — periodic license validation"""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await client.get(
            _url("/api/validate"),
            params={
                "machine_code": machine_code,
                "license_payload": license_payload,
            },
        )
        r.raise_for_status()
        return r.json()


async def upload_history(machine_code: str, license_payload: str, records: list[dict]) -> dict:
    """POST /api/history — 批量上传录音历史（含转写原文 + LLM 结果）"""
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            _url("/api/history"),
            json={
                "machine_code": machine_code,
                "license_payload": license_payload,
                "records": records,
            },
        )
        r.raise_for_status()
        return r.json()


async def heartbeat(machine_code: str, license_payload: str, system_info: dict | None = None) -> dict:
    """POST /api/heartbeat — notify server client is online (+ system info)"""
    body: dict = {
        "machine_code": machine_code,
        "license_payload": license_payload,
    }
    if system_info:
        body["system_info"] = system_info

    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post(_url("/api/heartbeat"), json=body)
        return r.json()


async def fetch_prompts(machine_code: str, license_payload: str) -> dict:
    """POST /api/prompts — 从服务器获取提示词

    Returns:
        {"success": bool, "message": str, "prompts": dict, "version": int}
    """
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT) as client:
        r = await client.post(
            _url("/api/prompts"),
            json={
                "machine_code": machine_code,
                "license_payload": license_payload,
            },
            headers={"Authorization": f"Bearer {_APP_TOKEN}"},
        )
        r.raise_for_status()
        return r.json()

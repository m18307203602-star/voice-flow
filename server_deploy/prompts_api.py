"""提示词 API — 四层防线

第一层：Bearer Token 认证 — 客户端内置 token，可定期轮换
第二层：限流 + 审计日志 — 单 token 每分钟 N 次，全量记录谁/何时/取了什么
第三层：提示词加密存储 — AES-256-GCM，磁盘只见密文
第四层：环境变量密钥 — 密钥不在代码/文件/git，systemd env 注入
"""

import json
import hashlib
import os
import time
import copy
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, Header, Request
from typing import Optional

from database import get_db
from models import PromptsRequest, PromptsResponse
from prompts_store import load_prompts, save_prompts
from admin import verify_admin

router = APIRouter()

# ── 第一层：Bearer Token ──
# 环境变量 PROMPTS_APP_TOKEN 可覆盖，否则用内置默认值（可随版本更新轮换）
_DEFAULT_APP_TOKEN = "vf-prompts-6F1A-BEA9-3BC5-CB78"
APP_TOKEN_HASH = hashlib.sha256(
    os.environ.get("PROMPTS_APP_TOKEN", _DEFAULT_APP_TOKEN).encode()
).hexdigest()


def _verify_app_token(authorization: str = Header(None)) -> str:
    """验证客户端 Bearer Token（第一层防线）"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing app token")
    token = authorization.replace("Bearer ", "").strip()
    if hashlib.sha256(token.encode()).hexdigest() != APP_TOKEN_HASH:
        raise HTTPException(status_code=403, detail="Invalid app token")
    return token


# ── 第二层：限流（滑动窗口，内存） ──
_RATE_LIMIT_PER_TOKEN = 30     # 单 token 每分钟最多 N 次
_RATE_LIMIT_PER_IP = 60        # 单 IP 每分钟最多 N 次
_RATE_WINDOW = 60              # 窗口秒数

_token_windows: dict[str, list[float]] = defaultdict(list)
_ip_windows: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(app_token: str, client_ip: str):
    """滑动窗口限流，超限抛 429"""
    now = time.time()
    cutoff = now - _RATE_WINDOW

    # Token 维度
    tk_times = _token_windows[app_token]
    tk_times[:] = [t for t in tk_times if t > cutoff]
    if len(tk_times) >= _RATE_LIMIT_PER_TOKEN:
        raise HTTPException(status_code=429, detail="Rate limit exceeded (token)")
    tk_times.append(now)

    # IP 维度
    ip_times = _ip_windows[client_ip]
    ip_times[:] = [t for t in ip_times if t > cutoff]
    if len(ip_times) >= _RATE_LIMIT_PER_IP:
        raise HTTPException(status_code=429, detail="Rate limit exceeded (IP)")
    ip_times.append(now)


# ── 审计日志 ──

def _audit_log(machine_code: str, client_ip: str, app_token: str,
               mode_count: int, success: bool):
    """写入 prompts_audit_log 表"""
    from database import get_db
    db = get_db()
    try:
        db.execute(
            """INSERT INTO prompts_audit_log
               (machine_code, ip_address, token_hash, mode_count, success)
               VALUES (?, ?, ?, ?, ?)""",
            (
                machine_code,
                client_ip,
                hashlib.sha256(app_token.encode()).hexdigest()[:16],
                mode_count,
                1 if success else 0,
            ),
        )
        db.commit()
    except Exception:
        pass
    finally:
        db.close()


# ── 许可证验证辅助 ──

def _validate_license(machine_code: str, license_payload: str) -> dict:
    """复用 /api/validate 的许可证验证逻辑"""
    db = get_db()
    try:
        machine = db.execute(
            "SELECT * FROM machines WHERE machine_code = ?",
            (machine_code,),
        ).fetchone()

        if machine and machine["banned"]:
            return {"valid": False, "banned": True, "expired": False,
                    "message": "License revoked"}

        if not machine:
            return {"valid": False, "banned": False, "expired": False,
                    "message": "Unknown machine"}

        expires_at = ""
        try:
            raw = base64.urlsafe_b64decode(license_payload).decode()
            data = json.loads(raw)
            payload = json.loads(data["payload"])
            expires_at = payload.get("e", "")
        except Exception:
            return {"valid": False, "banned": False, "expired": False,
                    "message": "Invalid payload format"}

        if expires_at and expires_at != "permanent":
            try:
                exp = datetime.fromisoformat(expires_at)
                if datetime.now(timezone.utc) > exp.replace(tzinfo=timezone.utc):
                    return {"valid": False, "banned": False, "expired": True,
                            "message": "License expired"}
            except ValueError:
                pass

        return {"valid": True, "banned": False, "expired": False, "message": "OK"}
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
#  公开端点
# ═══════════════════════════════════════════════════════════════

import base64  # noqa: E402 (kept here for logical grouping)


@router.post("/api/prompts", response_model=PromptsResponse)
def get_prompts(req: PromptsRequest, request: Request,
                app_token: str = Depends(_verify_app_token)):
    """获取提示词 — 需过四层防线

    ╔══════════════════════════╗
    ║  第一层：Bearer Token     ║  ← _verify_app_token
    ║  第二层：限流 + 审计       ║  ← _check_rate_limit + _audit_log
    ║  第三层：AES-256-GCM 解密  ║  ← load_prompts()
    ║  第四层：环境变量密钥      ║  ← PROMPTS_ENCRYPTION_KEY
    ╚══════════════════════════╝

    Header:  Authorization: Bearer <app_token>
    Body:    {machine_code, license_payload}
    """
    client_ip = request.client.host if request.client else "unknown"

    # 第二层：限流
    _check_rate_limit(app_token, client_ip)

    # 许可证验证
    validation = _validate_license(req.machine_code, req.license_payload)
    if not validation["valid"]:
        _audit_log(req.machine_code, client_ip, app_token, 0, success=False)
        return PromptsResponse(
            success=False,
            message=validation.get("message", "License invalid"),
        )

    # 第三/四层：解密加载（密钥在环境变量）
    try:
        data = load_prompts()
    except Exception as e:
        _audit_log(req.machine_code, client_ip, app_token, 0, success=False)
        return PromptsResponse(
            success=False,
            message=f"Server config error: {e}",
        )

    mode_count = len(data.get("modes", {}))
    _audit_log(req.machine_code, client_ip, app_token, mode_count, success=True)

    return PromptsResponse(
        success=True,
        message="OK",
        prompts=data.get("modes", {}),
        version=data.get("version", 0),
    )


# ═══════════════════════════════════════════════════════════════
#  管理端端点（需 Admin Bearer Token）
# ═══════════════════════════════════════════════════════════════

@router.get("/api/admin/prompts")
def admin_get_prompts(_admin=Depends(verify_admin)):
    """查看当前提示词（system 只显示前 80 字）"""
    data = load_prompts()
    masked = copy.deepcopy(data)
    for mode_id, mode_data in masked.get("modes", {}).items():
        if "system" in mode_data:
            mode_data["system"] = mode_data["system"][:80] + "..."
    return masked


@router.get("/api/admin/prompts/audit")
def admin_prompts_audit(limit: int = 50, _admin=Depends(verify_admin)):
    """查看提示词访问审计日志"""
    db = get_db()
    try:
        rows = db.execute(
            "SELECT * FROM prompts_audit_log ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


# ── 提示词保护：禁止 API 写入（防止误改/压缩） ──
# 如需更新提示词，使用 CLI 工具：python prompts_store.py prompts.json
# @router.post("/api/admin/prompts/update")
# def admin_update_prompts(data: dict, _admin=Depends(verify_admin)):
#     """更新提示词 — 版本号自动递增"""
#     data["version"] = data.get("version", 0) + 1
#     data["updated_at"] = datetime.now(timezone.utc).isoformat()
#     save_prompts(data)
#     return {"success": True, "version": data["version"]}

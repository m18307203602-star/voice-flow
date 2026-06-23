"""管理端点 — /api/admin/*（需 Bearer Token 认证）"""
import hashlib
import secrets
import os
import sqlite3
from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional

from .database import get_db
from .models import (
    AdminLoginRequest, AdminLoginResponse,
    GenerateRequest, GenerateResponse,
    UpdateNotesRequest,
)
from .license import generate_license_key, compute_expiry, sign_license_payload

router = APIRouter(prefix="/api/admin")

# 管理员密码的 SHA-256 哈希（从环境变量读取）
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")
if not ADMIN_PASSWORD_HASH:
    # 默认密码: "voiceflow2026" — 首次部署后请修改！
    ADMIN_PASSWORD_HASH = hashlib.sha256("voiceflow2026".encode()).hexdigest()


def verify_admin(authorization: str = Header(None)) -> str:
    """验证 Bearer Token"""
    if not authorization:
        raise HTTPException(status_code=401, detail="需要认证")
    token = authorization.replace("Bearer ", "").strip()
    db = get_db()
    try:
        row = db.execute(
            "SELECT * FROM admin_sessions WHERE token = ?",
            (token,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="无效的认证令牌")
        return "admin"
    finally:
        db.close()


@router.post("/login", response_model=AdminLoginResponse)
def admin_login(req: AdminLoginRequest):
    """管理员登录"""
    pw_hash = hashlib.sha256(req.password.encode()).hexdigest()
    if pw_hash != ADMIN_PASSWORD_HASH:
        return AdminLoginResponse(token=None)

    token = secrets.token_hex(32)
    db = get_db()
    try:
        # 清理旧 sessions
        db.execute("DELETE FROM admin_sessions")
        db.execute("INSERT INTO admin_sessions (token) VALUES (?)", (token,))
        db.commit()
    finally:
        db.close()

    return AdminLoginResponse(token=token)


@router.post("/generate", response_model=GenerateResponse)
def generate_license(req: GenerateRequest, _admin=Depends(verify_admin)):
    """生成 License Key（仅管理员）"""
    mc = req.machine_code.strip()
    duration = req.duration_days
    notes = req.notes or ""

    license_key = generate_license_key(mc)
    expires_at = compute_expiry(duration)

    db = get_db()
    try:
        # 插入或更新机器记录
        db.execute(
            """INSERT INTO machines (machine_code, license_key, notes)
               VALUES (?, ?, ?)
               ON CONFLICT(machine_code) DO UPDATE SET
               license_key = excluded.license_key,
               notes = excluded.notes,
               last_seen = datetime('now')""",
            (mc, license_key, notes),
        )

        # 创建激活记录
        db.execute(
            """INSERT INTO activations (machine_code, license_key, expires_at)
               VALUES (?, ?, ?)""",
            (mc, license_key, expires_at),
        )
        db.commit()

    finally:
        db.close()

    return GenerateResponse(license_key=license_key, expires_at=expires_at)


@router.get("/stats")
def get_stats(_admin=Depends(verify_admin)):
    """获取统计数据"""
    db = get_db()
    try:
        total = db.execute("SELECT COUNT(*) FROM machines").fetchone()[0]
        active = db.execute(
            "SELECT COUNT(DISTINCT machine_code) FROM activations "
            "WHERE datetime(expires_at) > datetime('now')"
        ).fetchone()[0]
        expired = db.execute(
            "SELECT COUNT(DISTINCT machine_code) FROM activations "
            "WHERE datetime(expires_at) <= datetime('now')"
        ).fetchone()[0]
        recent = db.execute(
            "SELECT machine_code, ip_address, timestamp FROM validation_log "
            "ORDER BY timestamp DESC LIMIT 20"
        ).fetchall()

        return {
            "total_machines": total,
            "active_licenses": active,
            "expired_licenses": expired,
            "recent_validations": [
                {"machine_code": r["machine_code"], "ip": r["ip_address"], "time": r["timestamp"]}
                for r in recent
            ],
        }
    finally:
        db.close()


@router.get("/machines")
def list_machines(search: str = "", limit: int = 50, offset: int = 0, _admin=Depends(verify_admin)):
    """列出所有机器"""
    db = get_db()
    try:
        if search:
            rows = db.execute(
                "SELECT * FROM machines WHERE machine_code LIKE ? OR notes LIKE ? "
                "ORDER BY last_seen DESC LIMIT ? OFFSET ?",
                (f"%{search}%", f"%{search}%", limit, offset),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM machines ORDER BY last_seen DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()

        result = []
        for r in rows:
            last_activation = db.execute(
                "SELECT * FROM activations WHERE machine_code = ? "
                "ORDER BY activated_at DESC LIMIT 1",
                (r["machine_code"],),
            ).fetchone()

            result.append({
                "machine_code": r["machine_code"],
                "license_key": r["license_key"],
                "first_seen": r["first_seen"],
                "last_seen": r["last_seen"],
                "banned": bool(r["banned"]),
                "notes": r["notes"],
                "latest_expiry": last_activation["expires_at"] if last_activation else "",
            })

        return result
    finally:
        db.close()


@router.post("/ban")
def ban_machine(machine_code: str, _admin=Depends(verify_admin)):
    """封禁机器"""
    db = get_db()
    try:
        db.execute("UPDATE machines SET banned = 1 WHERE machine_code = ?", (machine_code,))
        db.commit()
        return {"success": True}
    finally:
        db.close()


@router.post("/unban")
def unban_machine(machine_code: str, _admin=Depends(verify_admin)):
    """解封机器"""
    db = get_db()
    try:
        db.execute("UPDATE machines SET banned = 0 WHERE machine_code = ?", (machine_code,))
        db.commit()
        return {"success": True}
    finally:
        db.close()


@router.post("/machines/notes")
def update_notes(req: UpdateNotesRequest, machine_code: str, _admin=Depends(verify_admin)):
    """Update notes for a machine"""
    db = get_db()
    try:
        db.execute(
            "UPDATE machines SET notes = ? WHERE machine_code = ?",
            (req.notes, machine_code),
        )
        db.commit()
        return {"success": True}
    finally:
        db.close()

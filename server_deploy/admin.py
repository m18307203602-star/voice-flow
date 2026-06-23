"""Admin endpoints — /api/admin/* (Bearer Token auth)"""
import hashlib
import secrets
import os
import sqlite3
from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional

from database import get_db
from models import (
    AdminLoginRequest, AdminLoginResponse,
    GenerateRequest, GenerateResponse,
    TrialCardGenerateRequest, TrialCardGenerateResponse,
    UpdateNotesRequest,
)
from license import generate_license_key, compute_expiry, sign_license_payload, generate_trial_cards as gen_trial_cards

router = APIRouter(prefix="/api/admin")

ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")
if not ADMIN_PASSWORD_HASH:
    ADMIN_PASSWORD_HASH = hashlib.sha256("voiceflow2026".encode()).hexdigest()


def verify_admin(authorization: str = Header(None)) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization.replace("Bearer ", "").strip()
    db = get_db()
    try:
        row = db.execute(
            "SELECT * FROM admin_sessions WHERE token = ?",
            (token,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid token")
        return "admin"
    finally:
        db.close()


@router.post("/login", response_model=AdminLoginResponse)
def admin_login(req: AdminLoginRequest):
    pw_hash = hashlib.sha256(req.password.encode()).hexdigest()
    if pw_hash != ADMIN_PASSWORD_HASH:
        return AdminLoginResponse(token=None)

    token = secrets.token_hex(32)
    db = get_db()
    try:
        db.execute("DELETE FROM admin_sessions")
        db.execute("INSERT INTO admin_sessions (token) VALUES (?)", (token,))
        db.commit()
    finally:
        db.close()

    return AdminLoginResponse(token=token)


@router.post("/generate", response_model=GenerateResponse)
def generate_license(req: GenerateRequest, _admin=Depends(verify_admin)):
    mc = req.machine_code.strip()
    duration = req.duration_days
    notes = req.notes or ""

    license_key = generate_license_key(mc)
    expires_at = compute_expiry(duration)

    db = get_db()
    try:
        db.execute(
            """INSERT INTO machines (machine_code, license_key, notes)
               VALUES (?, ?, ?)
               ON CONFLICT(machine_code) DO UPDATE SET
               license_key = excluded.license_key,
               notes = excluded.notes,
               last_seen = datetime('now')""",
            (mc, license_key, notes),
        )

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

            activation_count = db.execute(
                "SELECT COUNT(*) FROM activations WHERE machine_code = ?",
                (r["machine_code"],),
            ).fetchone()[0]

            history_count = db.execute(
                "SELECT COUNT(*) FROM recording_history WHERE machine_code = ?",
                (r["machine_code"],),
            ).fetchone()[0]

            result.append({
                "machine_code": r["machine_code"],
                "license_key": r["license_key"],
                "first_seen": r["first_seen"],
                "last_seen": r["last_seen"],
                "last_heartbeat": r["last_heartbeat"] if r["last_heartbeat"] else "",
                "banned": bool(r["banned"]),
                "notes": r["notes"],
                "latest_expiry": last_activation["expires_at"] if last_activation else "",
                "activation_count": activation_count,
                "history_count": history_count,
                "system_info": r["system_info"] if r["system_info"] else "",
            })

        return result
    finally:
        db.close()


@router.post("/ban")
def ban_machine(machine_code: str, _admin=Depends(verify_admin)):
    db = get_db()
    try:
        db.execute("UPDATE machines SET banned = 1 WHERE machine_code = ?", (machine_code,))
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


@router.post("/trial-cards", response_model=TrialCardGenerateResponse)
def generate_trial_cards(req: TrialCardGenerateRequest, _admin=Depends(verify_admin)):
    """Generate trial cards (VF-TRIAL-XXXX-XXXX)"""
    count = req.count
    cards, expires_at = gen_trial_cards(count)

    db = get_db()
    try:
        for ck in cards:
            db.execute(
                "INSERT INTO trial_cards (card_key, expires_at) VALUES (?, ?)",
                (ck, expires_at),
            )
        db.commit()
    finally:
        db.close()

    return TrialCardGenerateResponse(cards=cards, expires_at=expires_at)


@router.post("/unban")
def unban_machine(machine_code: str, _admin=Depends(verify_admin)):
    db = get_db()
    try:
        db.execute("UPDATE machines SET banned = 0 WHERE machine_code = ?", (machine_code,))
        db.commit()
        return {"success": True}
    finally:
        db.close()


@router.get("/history")
def get_history(machine_code: str, limit: int = 30, _admin=Depends(verify_admin)):
    """Get recording history for a machine"""
    db = get_db()
    try:
        rows = db.execute(
            "SELECT * FROM recording_history WHERE machine_code = ? "
            "ORDER BY client_record_id DESC LIMIT ?",
            (machine_code.strip(), limit),
        ).fetchall()

        records = []
        for r in rows:
            try:
                engines = __import__('json').loads(r["engines"])
            except Exception:
                engines = []
            try:
                transcripts = __import__('json').loads(r["transcripts"])
            except Exception:
                transcripts = {}

            records.append({
                "id": r["client_record_id"],
                "created_at": r["created_at"],
                "duration": r["duration"],
                "engines": engines,
                "mode": r["mode"],
                "mode_name": r["mode_name"],
                "transcripts": transcripts,
                "result": r["result"],
                "model_used": r["model_used"],
                "status": r["status"],
                "stt_engine": r["stt_engine"],
                "llm_prompt_tokens": r["llm_prompt_tokens"],
                "llm_completion_tokens": r["llm_completion_tokens"],
                "uploaded_at": r["uploaded_at"],
            })

        total = db.execute(
            "SELECT COUNT(*) FROM recording_history WHERE machine_code = ?",
            (machine_code.strip(),),
        ).fetchone()[0]

        return {"records": records, "total": total}
    finally:
        db.close()


@router.get("/history/all")
def get_all_history(limit: int = 100, _admin=Depends(verify_admin)):
    """Get recent recording history across all machines"""
    db = get_db()
    try:
        rows = db.execute(
            "SELECT * FROM recording_history ORDER BY uploaded_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

        records = []
        for r in rows:
            try:
                transcripts = __import__('json').loads(r["transcripts"])
            except Exception:
                transcripts = {}

            records.append({
                "machine_code": r["machine_code"][:16] + "...",
                "id": r["client_record_id"],
                "created_at": r["created_at"],
                "duration": r["duration"],
                "mode_name": r["mode_name"],
                "result": (r["result"] or "")[:200],
                "model_used": r["model_used"],
                "stt_engine": r["stt_engine"],
                "uploaded_at": r["uploaded_at"],
            })

        total = db.execute("SELECT COUNT(*) FROM recording_history").fetchone()[0]
        return {"records": records, "total": total}
    finally:
        db.close()

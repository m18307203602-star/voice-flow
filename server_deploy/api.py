"""Public API endpoints — /api/activate, /api/validate, /api/heartbeat"""
import json
import base64
import sqlite3
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request

from database import get_db
from models import (
    ActivateRequest, ActivateResponse, ValidateResponse,
    HeartbeatRequest, HistoryUploadRequest,
)
from license import sign_license_payload, compute_expiry

router = APIRouter()


@router.post("/api/activate", response_model=ActivateResponse)
def activate(req: ActivateRequest, request: Request):
    mc = req.machine_code.strip()
    lk = req.license_key.strip()
    is_trial = "TRIAL" in lk

    db = get_db()
    try:
        if is_trial:
            # Trial card flow — check card exists, is unused
            card = db.execute(
                "SELECT * FROM trial_cards WHERE card_key = ? AND active = 1",
                (lk,),
            ).fetchone()
            if not card:
                return ActivateResponse(success=False, message="Invalid trial card")
            if card["used_by"] and card["used_by"] != mc:
                return ActivateResponse(success=False, message="Trial card has already been used")

            # Mark trial card as used
            db.execute(
                "UPDATE trial_cards SET used_by = ?, used_at = datetime('now') WHERE card_key = ?",
                (mc, lk),
            )
            # Create machine record
            db.execute(
                """INSERT INTO machines (machine_code, license_key) VALUES (?, ?)
                   ON CONFLICT(machine_code) DO UPDATE SET license_key = excluded.license_key,
                   last_seen = datetime('now')""",
                (mc, lk),
            )
            # Create activation record
            db.execute(
                "INSERT INTO activations (machine_code, license_key, expires_at) VALUES (?, ?, ?)",
                (mc, lk, card["expires_at"]),
            )
            db.commit()

            payload = sign_license_payload(mc, lk, card["expires_at"])
            return ActivateResponse(
                success=True,
                message="Trial activated — 3 days",
                license_payload=payload,
            )
        else:
            # Formal key flow — check machine binding
            machine = db.execute(
                "SELECT * FROM machines WHERE license_key = ? AND banned = 0",
                (lk,),
            ).fetchone()

            if not machine:
                return ActivateResponse(success=False, message="Invalid license key")

            if machine["machine_code"] != mc:
                return ActivateResponse(
                    success=False,
                    message="License key does not match this device",
                )

            activation = db.execute(
                "SELECT * FROM activations WHERE machine_code = ? AND license_key = ? "
                "ORDER BY activated_at DESC LIMIT 1",
                (mc, lk),
            ).fetchone()

            if not activation:
                return ActivateResponse(success=False, message="No activation record found")

            try:
                expires_at = datetime.fromisoformat(activation["expires_at"])
                if datetime.now(timezone.utc) > expires_at.replace(tzinfo=timezone.utc):
                    return ActivateResponse(success=False, message="License expired, please renew")
            except ValueError:
                pass

            db.execute(
                "UPDATE machines SET last_seen = datetime('now') WHERE machine_code = ?",
                (mc,),
            )
            db.commit()

            payload = sign_license_payload(mc, lk, activation["expires_at"])
            return ActivateResponse(
                success=True,
                message="Activation successful",
                license_payload=payload,
            )

    finally:
        db.close()


@router.get("/api/validate", response_model=ValidateResponse)
def validate(machine_code: str, license_payload: str, request: Request):
    mc = machine_code.strip()
    ip = request.client.host if request.client else ""

    db = get_db()
    try:
        machine = db.execute(
            "SELECT * FROM machines WHERE machine_code = ?",
            (mc,),
        ).fetchone()

        if machine and machine["banned"]:
            return ValidateResponse(valid=False, message="License revoked")

        db.execute(
            "INSERT INTO validation_log (machine_code, ip_address) VALUES (?, ?)",
            (mc, ip),
        )
        db.execute(
            "UPDATE machines SET last_seen = datetime('now') WHERE machine_code = ?",
            (mc,),
        )
        db.commit()

        expires_at = ""
        try:
            raw = base64.urlsafe_b64decode(license_payload).decode()
            data = json.loads(raw)
            payload = json.loads(data["payload"])
            expires_at = payload.get("e", "")

            if expires_at and expires_at != "permanent":
                exp = datetime.fromisoformat(expires_at)
                if datetime.now(timezone.utc) > exp.replace(tzinfo=timezone.utc):
                    return ValidateResponse(
                        valid=False,
                        expires_at=expires_at,
                        message="License expired",
                    )
        except Exception:
            pass

        return ValidateResponse(
            valid=True,
            expires_at=expires_at,
            message="Verification passed",
        )

    finally:
        db.close()


@router.post("/api/heartbeat")
def heartbeat(req: HeartbeatRequest, request: Request):
    """Record client heartbeat — they are online + system info"""
    mc = req.machine_code.strip()
    db = get_db()
    try:
        # Store system_info if provided
        si_json = ""
        if req.system_info:
            si_json = json.dumps(req.system_info, ensure_ascii=False)

        db.execute(
            "UPDATE machines SET last_heartbeat = datetime('now'),"
            " system_info = CASE WHEN ? != '' THEN ? ELSE system_info END"
            " WHERE machine_code = ?",
            (si_json, si_json, mc),
        )
        db.commit()
        return {"status": "ok"}
    finally:
        db.close()


@router.post("/api/history")
def upload_history(req: HistoryUploadRequest, request: Request):
    """Receive recording history from client"""
    mc = req.machine_code.strip()
    if not req.records:
        return {"success": True, "count": 0}

    db = get_db()
    try:
        count = 0
        for rec in req.records:
            # Skip duplicates by client_record_id
            existing = db.execute(
                "SELECT id FROM recording_history WHERE machine_code = ? AND client_record_id = ?",
                (mc, rec.get("id", 0)),
            ).fetchone()
            if existing:
                continue

            db.execute(
                """INSERT INTO recording_history
                   (machine_code, client_record_id, created_at, duration, engines,
                    mode, mode_name, transcripts, result, model_used, status,
                    stt_engine, llm_prompt_tokens, llm_completion_tokens)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    mc,
                    rec.get("id", 0),
                    rec.get("created_at", ""),
                    rec.get("duration", 0.0),
                    json.dumps(rec.get("engines", []), ensure_ascii=False),
                    rec.get("mode", ""),
                    rec.get("mode_name", ""),
                    json.dumps(rec.get("transcripts", {}), ensure_ascii=False),
                    rec.get("result", ""),
                    rec.get("model_used", ""),
                    rec.get("status", "success"),
                    rec.get("stt_engine", ""),
                    rec.get("llm_prompt_tokens", 0),
                    rec.get("llm_completion_tokens", 0),
                ),
            )
            count += 1

        db.commit()

        # ponytail: keep only latest 50 per machine
        db.execute(
            "DELETE FROM recording_history WHERE machine_code = ? AND id NOT IN ("
            "SELECT id FROM recording_history WHERE machine_code = ? "
            "ORDER BY id DESC LIMIT 50)",
            (mc, mc),
        )
        db.commit()

        return {"success": True, "count": count}
    finally:
        db.close()

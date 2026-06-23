"""公开 API 端点 — /api/activate, /api/validate, /api/ping"""
import sqlite3
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request

from .database import get_db
from .models import ActivateRequest, ActivateResponse, ValidateResponse
from .license import sign_license_payload

router = APIRouter()


@router.get("/api/ping")
def ping():
    return {"status": "ok", "version": "1.0.0"}


@router.post("/api/activate", response_model=ActivateResponse)
def activate(req: ActivateRequest, request: Request):
    mc = req.machine_code.strip()
    lk = req.license_key.strip()

    db = get_db()
    try:
        # 查找 License Key
        machine = db.execute(
            "SELECT * FROM machines WHERE license_key = ? AND banned = 0",
            (lk,),
        ).fetchone()

        if not machine:
            return ActivateResponse(success=False, message="无效的许可证密钥")

        # 检查是否已绑定到此机器码
        if machine["machine_code"] != mc:
            return ActivateResponse(
                success=False,
                message="许可证密钥与当前设备不匹配",
            )

        # 获取最新激活记录
        activation = db.execute(
            "SELECT * FROM activations WHERE machine_code = ? AND license_key = ? "
            "ORDER BY activated_at DESC LIMIT 1",
            (mc, lk),
        ).fetchone()

        if not activation:
            return ActivateResponse(success=False, message="未找到激活记录")

        # 检查是否过期
        try:
            expires_at = datetime.fromisoformat(activation["expires_at"])
            if datetime.now(timezone.utc) > expires_at.replace(tzinfo=timezone.utc):
                return ActivateResponse(success=False, message="许可证已过期，请续费")
        except ValueError:
            pass

        # 更新最后在线时间
        db.execute(
            "UPDATE machines SET last_seen = datetime('now') WHERE machine_code = ?",
            (mc,),
        )
        db.commit()

        # 签名 License payload
        payload = sign_license_payload(mc, lk, activation["expires_at"])
        return ActivateResponse(
            success=True,
            message="激活成功",
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
        # 检查机器是否被 ban
        machine = db.execute(
            "SELECT * FROM machines WHERE machine_code = ?",
            (mc,),
        ).fetchone()

        if machine and machine["banned"]:
            return ValidateResponse(valid=False, message="许可证已被吊销")

        # 记录验证日志
        db.execute(
            "INSERT INTO validation_log (machine_code, ip_address) VALUES (?, ?)",
            (mc, ip),
        )
        db.execute(
            "UPDATE machines SET last_seen = datetime('now') WHERE machine_code = ?",
            (mc,),
        )
        db.commit()

        # 解析 payload 检查过期
        import json
        import base64
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
                        message="许可证已过期",
                    )
        except Exception:
            pass

        return ValidateResponse(
            valid=True,
            expires_at=expires_at if 'expires_at' in dir() else "",
            message="验证通过",
        )

    finally:
        db.close()

"""License state machine — LOCKED → TRIAL → ACTIVATED → EXPIRED"""
import time
import json
import asyncio
import threading
from enum import Enum
from pathlib import Path


class LicenseState(Enum):
    LOCKED = "locked"                   # No license at all, software unusable
    TRIAL_ACTIVE = "trial_active"       # Trial card active (7 days)
    TRIAL_EXPIRED = "trial_expired"     # Trial ended, must activate
    ACTIVATED = "activated"             # Activated with formal key
    ACTIVATED_OFFLINE = "activated_offline"  # Offline > 7 days
    EXPIRED = "expired"                 # License expired
    PERMANENT = "permanent"             # Permanent activation


TRIAL_DAYS = 7
OFFLINE_GRACE_DAYS = 7
VALIDATION_INTERVAL_DAYS = 3
HEARTBEAT_INTERVAL_SECONDS = 300  # 5 minutes
LICENSE_FILE = ".license"


class LicenseManager:
    """Manages Voice Flow license lifecycle"""

    def __init__(self, config):
        self._config = config
        self._license_path = Path.home() / ".voice_flow" / LICENSE_FILE
        self._state = LicenseState.LOCKED
        self._remaining_days = 0

        self._license_payload: str | None = None
        self._decoded_payload: dict | None = None
        self._last_validation: float | None = None
        self._activated_at: float | None = None  # 首次激活时间戳
        self._machine_code: str | None = None
        self._heartbeat_thread: threading.Thread | None = None
        self._heartbeat_stop = threading.Event()

    # ── Public API ──

    def get_state(self) -> LicenseState:
        return self._state

    def is_usable(self) -> bool:
        return self._state in (
            LicenseState.TRIAL_ACTIVE,
            LicenseState.ACTIVATED,
            LicenseState.PERMANENT,
        )

    def is_locked(self) -> bool:
        return self._state == LicenseState.LOCKED

    def get_status_text(self) -> str:
        if self._state == LicenseState.LOCKED:
            return "未升级Pro — 请输入升级码"
        elif self._state == LicenseState.TRIAL_ACTIVE:
            return f"试用剩余 {self._remaining_days} 天"
        elif self._state == LicenseState.TRIAL_EXPIRED:
            return "试用已过期，请升级Pro"
        elif self._state == LicenseState.ACTIVATED:
            exp = self._decoded_payload.get("e", "?") if self._decoded_payload else "?"
            return f"Pro 版，有效期至 {exp[:10]}"
        elif self._state == LicenseState.ACTIVATED_OFFLINE:
            return "离线状态，请连接网络验证"
        elif self._state == LicenseState.EXPIRED:
            return "许可证已过期，请续费"
        elif self._state == LicenseState.PERMANENT:
            return "Pro 永久版"
        return "未知"

    def get_machine_code(self) -> str:
        if self._machine_code is None:
            from .fingerprint import generate_machine_code
            self._machine_code = generate_machine_code()
        return self._machine_code

    @property
    def license_payload(self) -> str | None:
        """许可证 payload 字符串，用于服务端认证 (如获取提示词)"""
        return self._license_payload

    def get_remaining_days(self) -> int:
        return self._remaining_days

    def get_license_usage(self) -> dict | None:
        """返回许可证用量信息（供 UI 横幅使用）

        Returns:
            {"used": int, "total": int} 或 None（无法计算时）
            - TRIAL_ACTIVE: used = 已使用天数, total = 7
            - ACTIVATED: used = 激活后已过天数, total = 许可证总天数
        """
        if self._state == LicenseState.TRIAL_ACTIVE:
            return {
                "used": TRIAL_DAYS - self._remaining_days,
                "total": TRIAL_DAYS,
            }
        elif self._state == LicenseState.ACTIVATED:
            at = self._activated_at or self._last_validation
            if not at or not self._decoded_payload:
                return None
            exp_str = self._decoded_payload.get("e", "")
            if not exp_str or exp_str == "permanent":
                return None
            try:
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                activated = datetime.fromtimestamp(at, tz=timezone.utc)
                expires = datetime.fromisoformat(exp_str)
                used = max(0, round((now - activated).total_seconds() / 86400))
                total = max(used, round((expires - activated).total_seconds() / 86400))
                return {"used": used, "total": total}
            except Exception:
                return None
        return None

    # ── Startup ──

    def load_state(self) -> LicenseState:
        """Determine license state at startup"""
        # Load existing license file
        if self._license_path.exists():
            self._load_license_file()

        if self._decoded_payload:
            self._evaluate_activated_state()
        else:
            # No license → LOCKED
            self._state = LicenseState.LOCKED
            self._remaining_days = 0

        return self._state

    # ── Activation ──

    def activate(self, license_key: str) -> dict:
        """Contact server to activate with a license key"""
        mc = self.get_machine_code()
        is_trial = license_key.startswith("VF-TRIAL")

        async def _do():
            from .client import activate as api_activate
            return await api_activate(mc, license_key)

        try:
            result = self._run_async(_do())
        except Exception as e:
            return {"success": False, "message": f"Cannot connect to activation server: {e}"}

        if result.get("success") and result.get("license_payload"):
            from .crypto import verify_license_payload
            verified = verify_license_payload(result["license_payload"])
            if verified:
                if not is_trial and verified.get("m") != mc:
                    return {"success": False, "message": "License does not match this device"}
                self._license_payload = result["license_payload"]
                self._decoded_payload = verified
                self._last_validation = time.time()
                if not is_trial and not self._activated_at:
                    self._activated_at = time.time()  # 首次正式激活
                self._save_license_file()
                exp = verified.get("e", "")
                if is_trial:
                    self._state = LicenseState.TRIAL_ACTIVE
                    self._remaining_days = TRIAL_DAYS
                elif exp == "permanent":
                    self._state = LicenseState.PERMANENT
                else:
                    self._state = LicenseState.ACTIVATED
                return {"success": True, "message": "Activation successful!"}
            else:
                return {"success": False, "message": "Signature verification failed, please retry"}

        return {"success": False, "message": result.get("message", "Activation failed")}

    # ── Validation ──

    def needs_validation(self) -> bool:
        if self._state not in (LicenseState.ACTIVATED, LicenseState.TRIAL_ACTIVE, LicenseState.PERMANENT):
            return False
        if self._last_validation is None:
            return True
        return (time.time() - self._last_validation) / 86400 > VALIDATION_INTERVAL_DAYS

    def validate(self) -> dict:
        """Contact server to validate license"""
        async def _do():
            from .client import validate as api_validate
            return await api_validate(self.get_machine_code(), self._license_payload)

        try:
            result = self._run_async(_do())
        except Exception:
            result = {"valid": None, "offline": True}

        if result.get("valid"):
            self._last_validation = time.time()
            if result.get("renewed_payload"):
                from .crypto import verify_license_payload
                verified = verify_license_payload(result["renewed_payload"])
                if verified:
                    self._license_payload = result["renewed_payload"]
                    self._decoded_payload = verified
            self._save_license_file()
            if self._state != LicenseState.PERMANENT:
                self._state = LicenseState.ACTIVATED
        elif result.get("offline"):
            if self._last_validation:
                days_offline = (time.time() - self._last_validation) / 86400
                if days_offline > OFFLINE_GRACE_DAYS:
                    self._state = LicenseState.ACTIVATED_OFFLINE
        else:
            self._state = LicenseState.EXPIRED

        return result

    # ── Heartbeat ──

    def start_heartbeat(self):
        """Start background heartbeat thread"""
        if self._state not in (LicenseState.TRIAL_ACTIVE, LicenseState.ACTIVATED, LicenseState.PERMANENT):
            return
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        self._heartbeat_stop.clear()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def stop_heartbeat(self):
        """Stop heartbeat thread"""
        self._heartbeat_stop.set()

    def _heartbeat_loop(self):
        """Send heartbeat every 5 minutes"""
        while not self._heartbeat_stop.is_set():
            try:
                async def _do():
                    from .client import heartbeat as api_heartbeat
                    return await api_heartbeat(self.get_machine_code(), self._license_payload)
                self._run_async(_do())
            except Exception:
                pass
            self._heartbeat_stop.wait(HEARTBEAT_INTERVAL_SECONDS)

    # ── Internal ──

    def _evaluate_trial_state(self):
        """Check trial card expiry"""
        if not self._decoded_payload:
            self._state = LicenseState.LOCKED
            return
        exp_str = self._decoded_payload.get("e", "")
        try:
            from datetime import datetime, timezone
            expires = datetime.fromisoformat(exp_str)
            if datetime.now(timezone.utc) > expires:
                self._state = LicenseState.TRIAL_EXPIRED
                self._remaining_days = 0
                return
            remaining = round((expires - datetime.now(timezone.utc)).total_seconds() / 86400)
            self._remaining_days = max(0, remaining)
            self._state = LicenseState.TRIAL_ACTIVE
        except Exception:
            self._state = LicenseState.TRIAL_ACTIVE
            self._remaining_days = TRIAL_DAYS

    def _evaluate_activated_state(self):
        """Evaluate formal license state"""
        exp_str = self._decoded_payload.get("e", "")
        if exp_str == "permanent":
            self._state = LicenseState.PERMANENT
            return

        # Check if trial card
        k = self._decoded_payload.get("k", "")
        if k and "TRIAL" in k:
            self._evaluate_trial_state()
            return

        try:
            from datetime import datetime, timezone
            expires = datetime.fromisoformat(exp_str)
            if datetime.now(timezone.utc) > expires:
                self._state = LicenseState.EXPIRED
                return
        except Exception:
            pass

        if self._last_validation:
            days_since = (time.time() - self._last_validation) / 86400
            self._state = (
                LicenseState.ACTIVATED_OFFLINE if days_since > OFFLINE_GRACE_DAYS
                else LicenseState.ACTIVATED
            )
        else:
            self._state = LicenseState.ACTIVATED

    def _load_license_file(self):
        try:
            with open(self._license_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._license_payload = data.get("payload")
            self._last_validation = data.get("last_validation")
            self._activated_at = data.get("activated_at")
            if self._license_payload:
                from .crypto import verify_license_payload
                self._decoded_payload = verify_license_payload(self._license_payload)
                if self._decoded_payload is None:
                    self._license_payload = None
        except (json.JSONDecodeError, KeyError, IOError):
            self._license_payload = None
            self._decoded_payload = None

    def _save_license_file(self):
        self._license_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._license_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "payload": self._license_payload,
                    "last_validation": self._last_validation,
                    "activated_at": self._activated_at,
                },
                f,
                indent=2,
            )

    @staticmethod
    def _run_async(coro):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        import concurrent.futures
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=15)

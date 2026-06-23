"""License signing / verification / generation — server-side"""
import json
import time
import base64
import hashlib
import secrets
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

KEYS_DIR = Path(os.environ.get("RSA_KEY_DIR", os.path.join(os.path.dirname(__file__), "keys")))
PRIVATE_KEY_PATH = KEYS_DIR / "private.pem"


_private_key = None


def _load_private_key():
    global _private_key
    if _private_key is None:
        with open(PRIVATE_KEY_PATH, "rb") as f:
            _private_key = serialization.load_pem_private_key(f.read(), password=None)
    return _private_key


def sign_license_payload(machine_code: str, license_key: str, expires_at: str) -> str:
    """RSA-PSS sign license payload, returns base64 string"""
    payload = {
        "m": machine_code,
        "k": license_key,
        "e": expires_at,
        "i": int(time.time()),
    }
    payload_json = json.dumps(payload, separators=(",", ":"))

    sig = _load_private_key().sign(
        payload_json.encode(),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )

    full = {"payload": payload_json, "sig": sig.hex()}
    return base64.urlsafe_b64encode(json.dumps(full).encode()).decode()


def generate_license_key(machine_code: str) -> str:
    """Generate human-readable License Key: VF-XXXX-XXXX-XXXX-XXXX"""
    random_part = secrets.token_hex(4).upper()

    bind_seed = hashlib.sha256(
        f"{machine_code}{random_part}".encode()
    ).hexdigest()[:8].upper()

    raw = f"{random_part}{bind_seed}{machine_code}"
    checksum = hashlib.sha256(raw.encode()).hexdigest()[:8].upper()

    return f"VF-{random_part[:4]}-{random_part[4:8]}-{bind_seed[:4]}-{checksum[:4]}"


def generate_trial_cards(count: int) -> tuple[list[str], str]:
    """Generate bulk trial cards VF-TRIAL-XXXX-XXXX, 3-day expiry"""
    expires_at = compute_expiry(3)
    cards = []
    for _ in range(count):
        hex_part = secrets.token_hex(4).upper()  # 8 hex chars → 2x4
        card = f"VF-TRIAL-{hex_part[:4]}-{hex_part[4:8]}"
        cards.append(card)
    return cards, expires_at


def compute_expiry(duration_days: int) -> str:
    """Compute ISO UTC expiry timestamp"""
    expiry = datetime.now(timezone.utc) + timedelta(days=duration_days)
    return expiry.strftime("%Y-%m-%dT%H:%M:%SZ")

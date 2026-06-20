"""RSA 签名验证 — 内嵌公钥验签，阻止 License 篡改"""
import json
import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.exceptions import InvalidSignature

from .public_key import PUBLIC_KEY_PEM

_public_key = None


def _load_public_key():
    global _public_key
    if _public_key is None:
        _public_key = serialization.load_pem_public_key(PUBLIC_KEY_PEM.encode())
    return _public_key


def verify_license_payload(payload_b64: str) -> dict | None:
    """
    验证 RSA-PSS 签名并返回解析后的 payload。
    Returns: {"m":机器码, "k":key, "e":过期时间, "i":签发时间} 或 None
    """
    try:
        raw = base64.urlsafe_b64decode(payload_b64).decode()
        data = json.loads(raw)
        payload_json = data["payload"]
        sig_bytes = bytes.fromhex(data["sig"])

        _load_public_key().verify(
            sig_bytes,
            payload_json.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return json.loads(payload_json)
    except (InvalidSignature, KeyError, ValueError, Exception):
        return None

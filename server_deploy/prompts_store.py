"""提示词加密存储 — AES-256-GCM 加密，密钥来自环境变量 PROMPTS_ENCRYPTION_KEY

数据格式: JSON → UTF-8 → AES-256-GCM → hex
存储文件: data/prompts/prompts.enc (可配置 PROMPTS_DATA_DIR)
"""

import json
import os
import sys
from pathlib import Path
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PROMPTS_FILE = "prompts.enc"
DEFAULT_DATA_DIR = Path(__file__).parent / "data" / "prompts"


def _get_key() -> bytes:
    """从环境变量读取加密密钥 (hex, 64 字符 = 32 字节)"""
    hex_key = os.environ.get("PROMPTS_ENCRYPTION_KEY", "")
    if not hex_key:
        print("FATAL: PROMPTS_ENCRYPTION_KEY 环境变量未设置，拒绝启动", file=sys.stderr)
        sys.exit(1)
    try:
        return bytes.fromhex(hex_key)
    except ValueError:
        print("FATAL: PROMPTS_ENCRYPTION_KEY 不是有效的 hex 字符串", file=sys.stderr)
        sys.exit(1)


def _data_dir() -> Path:
    return Path(os.environ.get("PROMPTS_DATA_DIR", str(DEFAULT_DATA_DIR)))


def _encrypt(data: bytes, key: bytes) -> str:
    """AES-256-GCM 加密，返回 "nonce_hex:ciphertext_hex" """
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return nonce.hex() + ":" + ciphertext.hex()


def _decrypt(encoded: str, key: bytes) -> bytes:
    """AES-256-GCM 解密"""
    nonce_hex, ct_hex = encoded.split(":", 1)
    nonce = bytes.fromhex(nonce_hex)
    ciphertext = bytes.fromhex(ct_hex)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


def load_prompts() -> dict:
    """从加密文件加载提示词 JSON，返回完整 dict

    Returns:
        {
          "version": 1,
          "updated_at": "...",
          "modes": {
            "1": {"name": "...", "temperature": 0.1, "system": "..."},
            ...
          },
          "synthesis": {"1": "...", "2": "..."}
        }
    """
    key = _get_key()
    file_path = _data_dir() / PROMPTS_FILE

    if not file_path.exists():
        print(f"FATAL: 提示词文件不存在: {file_path}", file=sys.stderr)
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8") as f:
        encrypted = f.read().strip()

    raw = _decrypt(encrypted, key)
    return json.loads(raw)


def save_prompts(data: dict):
    """加密保存提示词 JSON 到文件"""
    key = _get_key()
    raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    encrypted = _encrypt(raw, key)

    dir_path = _data_dir()
    dir_path.mkdir(parents=True, exist_ok=True)

    file_path = dir_path / PROMPTS_FILE
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(encrypted)

    print(f"Prompts saved: {file_path} ({len(encrypted)} bytes encrypted)")


# ── 预加密工具：从 prompts.json 生成 prompts.enc ──

def encrypt_from_json(json_path: str, output_dir: str = None):
    """从明文 JSON 生成加密文件（首次部署用）

    Usage:
        python prompts_store.py /path/to/prompts.json
        PROMPTS_ENCRYPTION_KEY=xxx python prompts_store.py /path/to/prompts.json
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    key = _get_key()
    raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    encrypted = _encrypt(raw, key)

    out_dir = Path(output_dir) if output_dir else _data_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / PROMPTS_FILE
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(encrypted)

    print(f"Encrypted prompts saved: {out_path}")
    print(f"  Modes: {list(data.get('modes', {}).keys())}")
    print(f"  Version: {data.get('version', 'N/A')}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python prompts_store.py <prompts.json> [output_dir]", file=sys.stderr)
        sys.exit(1)
    encrypt_from_json(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)

"""认证后端 — 抽象接口 + 本地 SQLite 实现（后续可替换为云端后端）"""
import hashlib
import os
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

# ── 数据模型 ──

@dataclass
class AuthResult:
    success: bool
    message: str = ""
    user_id: str = ""       # 登录成功后的用户标识
    token: str = ""         # 云端方案时用


# ── 抽象后端接口 ──

class AuthBackend(ABC):
    """认证后端抽象接口。后续替换为腾讯云/阿里云后端时只需实现此接口"""

    @abstractmethod
    def register(self, phone: str, password: str) -> AuthResult:
        """注册新用户。返回 AuthResult"""
        ...

    @abstractmethod
    def login(self, phone: str, password: str) -> AuthResult:
        """登录。返回 AuthResult"""
        ...

    @abstractmethod
    def is_initialized(self) -> bool:
        """后端是否已初始化（如数据库是否就绪）"""
        ...


# ── 本地实现（SQLite + 密码哈希） ──

class LocalAuthBackend(AuthBackend):
    """本地 SQLite 认证后端。后续替换为云端后端不影响 UI"""

    def __init__(self):
        from pathlib import Path
        import sqlite3

        db_dir = Path.home() / ".voice_flow"
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / "auth.db"

        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                phone TEXT PRIMARY KEY,
                token TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        self._conn.commit()

    @staticmethod
    def _hash_password(password: str, salt: str = None) -> tuple[str, str]:
        """SHA-256 哈希密码，返回 (hash, salt)"""
        if salt is None:
            salt = os.urandom(16).hex()
        h = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return h, salt

    def register(self, phone: str, password: str) -> AuthResult:
        phone = phone.strip()
        if not phone or len(phone) != 11 or not phone.isdigit():
            return AuthResult(False, "请输入有效的 11 位手机号")
        if len(password) < 6:
            return AuthResult(False, "密码至少 6 位")

        # 检查是否已注册
        existing = self._conn.execute(
            "SELECT id FROM users WHERE phone = ?", (phone,)
        ).fetchone()
        if existing:
            return AuthResult(False, "该手机号已注册")

        pw_hash, salt = self._hash_password(password)
        cursor = self._conn.execute(
            "INSERT INTO users (phone, password_hash, salt) VALUES (?, ?, ?)",
            (phone, pw_hash, salt),
        )
        self._conn.commit()
        return AuthResult(True, "注册成功", user_id=str(cursor.lastrowid))

    def login(self, phone: str, password: str) -> AuthResult:
        phone = phone.strip()
        user = self._conn.execute(
            "SELECT id, password_hash, salt FROM users WHERE phone = ?", (phone,)
        ).fetchone()
        if not user:
            return AuthResult(False, "手机号未注册")

        pw_hash, _ = self._hash_password(password, user["salt"])
        if pw_hash != user["password_hash"]:
            return AuthResult(False, "密码错误")

        return AuthResult(True, "登录成功", user_id=str(user["id"]))

    def create_session(self, phone: str) -> str:
        """为用户创建会话令牌，返回 token"""
        token = secrets.token_hex(32)
        self._conn.execute(
            "INSERT OR REPLACE INTO sessions (phone, token, created_at) "
            "VALUES (?, ?, datetime('now', 'localtime'))",
            (phone, token),
        )
        self._conn.commit()
        return token

    def validate_session(self, phone: str, token: str) -> bool:
        """验证会话令牌是否有效"""
        row = self._conn.execute(
            "SELECT token FROM sessions WHERE phone = ?", (phone,)
        ).fetchone()
        if not row:
            return False
        return row["token"] == token

    def delete_session(self, phone: str):
        """删除会话令牌（退出登录）"""
        self._conn.execute("DELETE FROM sessions WHERE phone = ?", (phone,))
        self._conn.commit()

    def is_initialized(self) -> bool:
        return True

    def close(self):
        self._conn.close()

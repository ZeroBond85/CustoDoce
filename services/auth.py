import base64
import hashlib
import hmac
import os
import struct
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt as pyjwt

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24
PBKDF2_ITERATIONS = 600_000
TOTP_INTERVAL = 30
TOTP_DIGITS = 6


@dataclass
class AuthConfig:
    secret_key: str
    admin_password_hash: str
    totp_secret: Optional[str] = None
    totp_enabled: bool = False


def generate_secret_key(length: int = 32) -> str:
    return base64.urlsafe_b64encode(os.urandom(length)).decode()


def _derive_key(secret: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256", secret.encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=32
    )


def hash_password(password: str) -> str:
    salt = os.urandom(32)
    dk = _derive_key(password, salt)
    return base64.b64encode(salt + dk).decode("utf-8")


def verify_password(password: str, stored: str) -> bool:
    raw = base64.b64decode(stored.encode("utf-8"))
    salt, dk = raw[:32], raw[32:]
    dk2 = _derive_key(password, salt)
    return hmac.compare_digest(dk, dk2)


def create_token(user_id: str, secret_key: str, expiry_hours: int = JWT_EXPIRY_HOURS) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(hours=expiry_hours),
    }
    return pyjwt.encode(payload, secret_key, algorithm=JWT_ALGORITHM)


def verify_token(token: str, secret_key: str) -> Optional[dict]:
    try:
        return pyjwt.decode(token, secret_key, algorithms=[JWT_ALGORITHM])
    except pyjwt.ExpiredSignatureError:
        return None
    except pyjwt.InvalidTokenError:
        return None


def generate_totp_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode("utf-8")


def _totp_int(secret: str, time_slice: int) -> int:
    key = base64.b32decode(secret.upper().encode("utf-8"))
    msg = struct.pack(">Q", time_slice)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    code = struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF
    return code % (10**TOTP_DIGITS)


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    try:
        expected = int(code)
    except (ValueError, TypeError):
        return False
    now = int(time.time()) // TOTP_INTERVAL
    for i in range(-window, window + 1):
        if _totp_int(secret, now + i) == expected:
            return True
    return False


def get_totp_uri(secret: str, label: str = "CustoDoce", issuer: str = "CustoDoce") -> str:
    return (
        f"otpauth://totp/{issuer}:{label}?"
        f"secret={secret}&issuer={issuer}&algorithm=SHA1&"
        f"digits={TOTP_DIGITS}&period={TOTP_INTERVAL}"
    )


def load_config() -> AuthConfig:
    import os as _os
    sk = _os.environ.get("AUTH_SECRET_KEY", "")
    if not sk:
        sk = base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8")
    pw_env = _os.environ.get("ADMIN_PASSWORD_HASH", "")
    pw_plain = _os.environ.get("ADMIN_PASSWORD") or _os.environ.get("ADMIN_PASSWORD_HASH", "") or ""
    pw_hash = pw_env if pw_env else hash_password(pw_plain)
    totp_secret = _os.environ.get("TOTP_SECRET", "") or None
    totp_enabled = bool(_os.environ.get("TOTP_ENABLED", ""))
    return AuthConfig(
        secret_key=sk,
        admin_password_hash=pw_hash,
        totp_secret=totp_secret,
        totp_enabled=totp_enabled,
    )

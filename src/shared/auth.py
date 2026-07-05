import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from src.shared import config


# PBKDF2-HMAC-SHA256 con 200,000 iteraciones (OWASP 2023 recommendation).
# builtin de Python - no requiere C extensions y es compatible con AWS Lambda
# Python 3.11 (que corre en AL2 con glibc 2.26).
#
# Hash format: pbkdf2_sha256#200000#<salt-hex>#<digest-hex>
#              ^scheme        ^iter     ^salt        ^expected
_ITERATIONS = 200_000
_SALT_BYTES = 16
_HASH_ALGO = "sha256"
_SCHEME_PREFIX = f"pbkdf2_{_HASH_ALGO}"


def _derive(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        _HASH_ALGO,
        password.encode("utf-8"),
        salt,
        _ITERATIONS,
    )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = _derive(password, salt)
    return f"{_SCHEME_PREFIX}#{_ITERATIONS}#{salt.hex()}#{digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        parts = password_hash.split("#")
        if len(parts) != 4:
            return False
        scheme, iter_str, salt_hex, digest_hex = parts
        if scheme != _SCHEME_PREFIX:
            return False
        if int(iter_str) != _ITERATIONS:
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = _derive(password, salt)
        return hmac.compare_digest(expected, actual)
    except (ValueError, AttributeError, TypeError):
        return False


def create_token(user):
    expires_at = datetime.now(timezone.utc) + timedelta(hours=12)
    payload = {
        "userId": user["userId"],
        "tenantId": user.get("tenantId") or "",
        "role": user["role"],
        "email": user["email"],
        "name": user.get("name", ""),
        "exp": expires_at,
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def decode_token(token):
    return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])


def get_bearer_token(headers):
    if not headers:
        return None
    authorization = headers.get("authorization") or headers.get("Authorization")
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from src.shared import config


def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password, password_hash):
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_token(user):
    expires_at = datetime.now(timezone.utc) + timedelta(hours=12)
    payload = {
        "userId": user["userId"],
        "tenantId": user["tenantId"],
        "storeId": user.get("storeId") or "",
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

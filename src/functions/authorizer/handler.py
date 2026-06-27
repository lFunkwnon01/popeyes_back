from src.shared.auth import decode_token, get_bearer_token


def lambda_handler(event, _context):
    headers = event.get("headers") or {}
    token = get_bearer_token(headers)
    if not token:
        return {"isAuthorized": False, "context": {"error": "Missing bearer token"}}

    try:
        claims = decode_token(token)
    except Exception:
        return {"isAuthorized": False, "context": {"error": "Invalid token"}}

    return {
        "isAuthorized": True,
        "context": {
            "userId": str(claims.get("userId", "")),
            "tenantId": str(claims.get("tenantId", "")),
            "storeId": str(claims.get("storeId", "")),
            "role": str(claims.get("role", "")),
            "email": str(claims.get("email", "")),
            "name": str(claims.get("name", "")),
        },
    }

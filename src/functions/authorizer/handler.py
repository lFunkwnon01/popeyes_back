from src.shared.auth import decode_token, get_bearer_token


def lambda_handler(event, _context):
    headers = event.get("headers") or {}
    token = get_bearer_token(headers)
    if not token:
        print("AUTHORIZER: isAuthorized=False reason=missing_bearer_token")
        return {"isAuthorized": False, "context": {"error": "Missing bearer token"}}

    try:
        claims = decode_token(token)
    except Exception as exc:
        print(f"AUTHORIZER: isAuthorized=False reason=invalid_token error={exc}")
        return {"isAuthorized": False, "context": {"error": "Invalid token"}}

    print(
        "AUTHORIZER: isAuthorized=True "
        f"userId={claims.get('userId', '')} "
        f"role={claims.get('role', '')} "
        f"tenantId={claims.get('tenantId', '')} "
        f"email={claims.get('email', '')}"
    )

    return {
        "isAuthorized": True,
        "context": {
            "userId": str(claims.get("userId", "")),
            "tenantId": str(claims.get("tenantId", "")),
            "role": str(claims.get("role", "")),
            "email": str(claims.get("email", "")),
            "name": str(claims.get("name", "")),
        },
    }

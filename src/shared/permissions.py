from fastapi import HTTPException, Request


def get_event_from_request(request: Request):
    return request.scope.get("aws.event", {})


def get_current_user(request: Request):
    event = get_event_from_request(request)
    authorizer = event.get("requestContext", {}).get("authorizer", {})
    lambda_context = authorizer.get("lambda", authorizer)
    if not lambda_context or not lambda_context.get("userId"):
        raise HTTPException(status_code=401, detail="Unauthorized")

    return {
        "userId": lambda_context.get("userId"),
        "tenantId": lambda_context.get("tenantId"),
        "storeId": lambda_context.get("storeId") or "",
        "role": lambda_context.get("role"),
        "email": lambda_context.get("email"),
        "name": lambda_context.get("name", ""),
    }


def require_roles(user, allowed_roles):
    if user.get("role") not in allowed_roles:
        raise HTTPException(status_code=403, detail="Forbidden")

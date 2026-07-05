from fastapi import HTTPException, Request

from src.shared import config


def get_event_from_request(request: Request):
    return request.scope.get("aws.event", {})


def get_current_user(request: Request):
    """Requiere autenticación. Usar en cualquier endpoint que no sea de browsing público."""
    event = get_event_from_request(request)
    authorizer = event.get("requestContext", {}).get("authorizer", {})
    lambda_context = authorizer.get("lambda", authorizer)
    if not lambda_context or not lambda_context.get("userId"):
        raise HTTPException(status_code=401, detail="Unauthorized")

    return {
        "userId": lambda_context.get("userId"),
        "tenantId": lambda_context.get("tenantId") or "",
        "role": lambda_context.get("role"),
        "email": lambda_context.get("email"),
        "name": lambda_context.get("name", ""),
    }


def get_current_user_or_anonymous(request: Request):
    """
    Solo para endpoints de browsing público (GET /stores, GET /products) que
    ya no llevan el authorizer de API Gateway. Si viene JWT válido, se usa
    (para que ADMIN/worker sigan viendo solo lo suyo); si no, ANONYMOUS_USER.
    """
    try:
        return get_current_user(request)
    except HTTPException:
        return dict(config.ANONYMOUS_USER)


def require_roles(user, allowed_roles):
    if user.get("role") not in allowed_roles:
        raise HTTPException(status_code=403, detail="Forbidden")


def resolve_tenant_id(user, request: Request):
    """
    Resuelve el tenantId a usar para una operación scoped-por-sede.

    - ADMIN/workers: siempre tienen tenantId fijo en el JWT (su sede).
    - CLIENT: no tiene tenantId fijo (es global), así que debe venir
      como query param `tenantId` (la sede que eligió en el frontend).
    """
    if user.get("tenantId"):
        return user["tenantId"]
    tenant_id = request.query_params.get("tenantId")
    if not tenant_id:
        raise HTTPException(
            status_code=400,
            detail="tenantId es requerido (selecciona una sede)",
        )
    return tenant_id

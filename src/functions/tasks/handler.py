import json

import boto3
from boto3.dynamodb.conditions import Key
from fastapi import Body, HTTPException, Request
from mangum import Mangum

from src.shared import config
from src.shared.app import create_app
from src.shared.auth import decode_token, get_bearer_token
from src.shared.dynamodb import now_iso, orders_table, workflow_tasks_table
from src.shared.permissions import get_current_user, resolve_tenant_id
from src.shared.response import success_response_safe, success_response


app = create_app("workflow-task-service")
_stepfunctions = boto3.client("stepfunctions", region_name=config.REGION)


def get_task_or_404(tenant_id, task_id):
    response = workflow_tasks_table().get_item(Key={"tenantId": tenant_id, "taskId": task_id})
    task = response.get("Item")
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _complete_task(task, completed_by, notes=""):
    """
    Marca la tarea COMPLETED y dispara send_task_success para desbloquear
    el siguiente paso del state machine. Compartido por POST /tasks/{taskId}/complete
    y POST /tasks/rappi/confirm-by-external-order.
    """
    if task.get("status") != "PENDING":
        raise HTTPException(status_code=409, detail="Task is not pending")

    completed_at = now_iso()
    workflow_tasks_table().update_item(
        Key={"tenantId": task["tenantId"], "taskId": task["taskId"]},
        UpdateExpression="SET #status = :status, completedAt = :completedAt, completedBy = :completedBy",
        ConditionExpression="#status = :pending",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": "COMPLETED",
            ":completedAt": completed_at,
            ":completedBy": completed_by,
            ":pending": "PENDING",
        },
    )

    callback_payload = {
        "taskId": task["taskId"],
        "stepName": task["stepName"],
        "completedAt": completed_at,
        "completedBy": completed_by,
        "notes": notes,
    }
    _stepfunctions.send_task_success(taskToken=task["taskToken"], output=json.dumps(callback_payload))
    return success_response_safe({"taskId": task["taskId"], "status": "COMPLETED", "completedAt": completed_at})


def user_can_access_task(user, task):
    """
    Verifica si el user puede ver/completar esta tarea.

    Al estar la tarea ya scoped por tenantId (una sede), lo único que
    falta validar es el rol requerido:
    - CLIENT: la tarea es suya (el order es suyo)
    - Workers (COOK/DISPATCHER/DRIVER/RESTAURANT_WORKER): la tarea requiere
      su rol
    - ADMIN: puede ver cualquier tarea de su sede
    """
    if user["role"] == "CLIENT":
        order = orders_table().get_item(Key={"tenantId": task["tenantId"], "orderId": task["orderId"]}).get("Item")
        return bool(order and order.get("customerId") == user["userId"])

    if task.get("requiredRole") != user["role"] and user["role"] != "ADMIN":
        return False

    return True


@app.get("/tasks")
def list_tasks(request: Request):
    user = get_current_user(request)
    tenant_id = resolve_tenant_id(user, request)
    response = workflow_tasks_table().query(
        KeyConditionExpression=Key("tenantId").eq(tenant_id),
    )
    status_filter = request.query_params.get("status") or "PENDING"
    order_id_filter = request.query_params.get("orderId")

    items = []
    for task in response.get("Items", []):
        if status_filter and task.get("status") != status_filter:
            continue
        if order_id_filter and task.get("orderId") != order_id_filter:
            continue
        if not user_can_access_task(user, task):
            continue
        items.append(task)

    items.sort(key=lambda item: item.get("startedAt", ""))
    return success_response_safe(items)


@app.get("/tasks/rappi")
def list_tasks_rappi(request: Request):
    """
    Lista las tareas de un pedido de Rappi sin JWT (x-api-key), para que
    el simulador pueda descubrir el taskId pendiente y luego completarlo
    vía POST /tasks/{taskId}/complete.

    Query params requeridos: tenantId, externalOrderId.
    Query param opcional: status (default "PENDING", igual que GET /tasks).
    """
    headers = request.scope.get("aws.event", {}).get("headers", {}) or {}
    api_key = headers.get("x-api-key") or headers.get("X-Api-Key")
    if api_key != config.RAPPI_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid x-api-key")

    tenant_id = request.query_params.get("tenantId")
    external_order_id = request.query_params.get("externalOrderId")
    if not tenant_id or not external_order_id:
        raise HTTPException(status_code=400, detail="tenantId y externalOrderId son requeridos")

    # No hay GSI sobre externalOrderId: se hace Query por tenantId (partition
    # key real) y se filtra en memoria. Con el volumen de pedidos Rappi de
    # este proyecto es suficiente; evita agregar un GSI nuevo a la tabla.
    orders = orders_table().query(
        KeyConditionExpression=Key("tenantId").eq(tenant_id),
    ).get("Items", [])
    order = next((o for o in orders if o.get("externalOrderId") == external_order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    tasks = workflow_tasks_table().query(
        IndexName="orderId-index",
        KeyConditionExpression=Key("orderId").eq(order["orderId"]),
    ).get("Items", [])

    status_filter = request.query_params.get("status") or "PENDING"
    items = [t for t in tasks if not status_filter or t.get("status") == status_filter]
    items.sort(key=lambda item: item.get("startedAt", ""))
    return success_response_safe(items)


def _get_user_from_jwt_manual(request: Request):
    """
    Decodifica el JWT a mano. Esta ruta ya NO tiene lambdaAuthorizer (ver
    serverless.yml), así que request.scope no trae el contexto del
    autorizador — hay que repetir lo que hacía authorizer/handler.py.
    """
    headers = request.scope.get("aws.event", {}).get("headers", {}) or {}
    token = get_bearer_token(headers)
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        claims = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {
        "userId": claims.get("userId"),
        "tenantId": claims.get("tenantId") or "",
        "role": claims.get("role"),
        "email": claims.get("email"),
        "name": claims.get("name", ""),
    }


@app.post("/tasks/{task_id}/complete")
def complete_task(task_id: str, request: Request, payload=Body(default=None)):
    """
    Completa una tarea del workflow. Dos formas de autenticarse (la ruta
    ya no tiene lambdaAuthorizer, se valida todo aquí adentro):

    1. x-api-key == RAPPI_API_KEY: llamada externa (Rappi/GCP). Sin JWT,
       sin chequeo de rol — requiere `tenantId` explícito en el body o
       query, porque no hay usuario del cual resolverlo.
    2. JWT (Authorization: Bearer ...): flujo normal de un worker/admin/
       cliente de Popeyes, con el mismo chequeo de rol de siempre.
    """
    headers = request.scope.get("aws.event", {}).get("headers", {}) or {}
    api_key = headers.get("x-api-key") or headers.get("X-Api-Key")

    if api_key and api_key == config.RAPPI_API_KEY:
        tenant_id = (payload or {}).get("tenantId") or request.query_params.get("tenantId")
        if not tenant_id:
            raise HTTPException(status_code=400, detail="tenantId es requerido")
        task = get_task_or_404(tenant_id, task_id)
        completed_by = "rappi-integration"
    else:
        user = _get_user_from_jwt_manual(request)
        tenant_id = resolve_tenant_id(user, request)
        task = get_task_or_404(tenant_id, task_id)
        if not user_can_access_task(user, task):
            raise HTTPException(status_code=403, detail="Forbidden")
        completed_by = user["userId"]

    return _complete_task(task, completed_by, notes=(payload or {}).get("notes", ""))


@app.post("/tasks/rappi/confirm-by-external-order")
def confirm_task_by_external_order(request: Request, payload=Body(...)):
    """
    Completa el paso CONFIRM_RECEPTION de un pedido de Rappi identificándolo
    por externalOrderId, sin que Rappi necesite conocer el taskId interno
    (a diferencia de GET /tasks/rappi + POST /complete, que son dos pasos).

    Solo x-api-key (sin JWT), igual que el resto de rutas /tasks/rappi/*.
    Body: { externalOrderId, tenantId }.
    """
    headers = request.scope.get("aws.event", {}).get("headers", {}) or {}
    api_key = headers.get("x-api-key") or headers.get("X-Api-Key")
    if api_key != config.RAPPI_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid x-api-key")

    tenant_id = payload.get("tenantId")
    external_order_id = payload.get("externalOrderId")
    if not tenant_id or not external_order_id:
        raise HTTPException(status_code=400, detail="tenantId y externalOrderId son requeridos")

    # Mismo patrón que GET /tasks/rappi: sin GSI sobre externalOrderId,
    # Query por tenantId (partition key) y filtro en memoria. La tabla de
    # tasks es chica, así que se escanea por tenantId igual para el filtro
    # de stepName/status en vez de usar el GSI de orderId-index.
    orders = orders_table().query(
        KeyConditionExpression=Key("tenantId").eq(tenant_id),
    ).get("Items", [])
    order = next((o for o in orders if o.get("externalOrderId") == external_order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    tasks = workflow_tasks_table().query(
        KeyConditionExpression=Key("tenantId").eq(tenant_id),
    ).get("Items", [])
    task = next(
        (
            t
            for t in tasks
            if t.get("orderId") == order["orderId"]
            and t.get("stepName") == "CONFIRM_RECEPTION"
            and t.get("status") == "PENDING"
        ),
        None,
    )
    if not task:
        raise HTTPException(status_code=404, detail="Pending CONFIRM_RECEPTION task not found")

    return _complete_task(task, "rappi-integration")


lambda_handler = Mangum(app)

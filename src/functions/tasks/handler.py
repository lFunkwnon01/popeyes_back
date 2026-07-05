import json

import boto3
from boto3.dynamodb.conditions import Key
from fastapi import Body, HTTPException, Request
from mangum import Mangum

from src.shared import config
from src.shared.app import create_app
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


@app.post("/tasks/{task_id}/complete")
def complete_task(task_id: str, request: Request, payload=Body(default=None)):
    user = get_current_user(request)
    tenant_id = resolve_tenant_id(user, request)
    task = get_task_or_404(tenant_id, task_id)

    if not user_can_access_task(user, task):
        raise HTTPException(status_code=403, detail="Forbidden")

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
            ":completedBy": user["userId"],
            ":pending": "PENDING",
        },
    )

    callback_payload = {
        "taskId": task["taskId"],
        "stepName": task["stepName"],
        "completedAt": completed_at,
        "completedBy": user["userId"],
        "notes": (payload or {}).get("notes", ""),
    }
    _stepfunctions.send_task_success(taskToken=task["taskToken"], output=json.dumps(callback_payload))
    return success_response_safe({"taskId": task["taskId"], "status": "COMPLETED", "completedAt": completed_at})


lambda_handler = Mangum(app)

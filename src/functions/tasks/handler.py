import json

import boto3
from boto3.dynamodb.conditions import Key
from fastapi import Body, HTTPException, Request
from mangum import Mangum

from src.shared import config
from src.shared.app import create_app
from src.shared.dynamodb import now_iso, orders_table, workflow_tasks_table
from src.shared.permissions import get_current_user
from src.shared.response import success_response


app = create_app("workflow-task-service")
_stepfunctions = boto3.client("stepfunctions", region_name=config.REGION)


def get_task_or_404(tenant_id, task_id):
    response = workflow_tasks_table().get_item(Key={"tenantId": tenant_id, "taskId": task_id})
    task = response.get("Item")
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def user_can_access_task(user, task):
    if user["role"] == "ADMIN":
        return True
    if task.get("requiredRole") != user["role"]:
        return False
    if user["role"] == "CLIENT":
        order = orders_table().get_item(Key={"tenantId": task["tenantId"], "orderId": task["orderId"]}).get("Item")
        return bool(order and order.get("customerId") == user["userId"])
    if user.get("storeId"):
        return task.get("storeId") == user.get("storeId")
    return True


@app.get("/tasks")
def list_tasks(request: Request):
    user = get_current_user(request)
    response = workflow_tasks_table().query(
        KeyConditionExpression=Key("tenantId").eq(user["tenantId"]),
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
    return success_response(items)


@app.post("/tasks/{task_id}/complete")
def complete_task(task_id: str, request: Request, payload=Body(default=None)):
    user = get_current_user(request)
    task = get_task_or_404(user["tenantId"], task_id)

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
    return success_response({"taskId": task["taskId"], "status": "COMPLETED", "completedAt": completed_at})


lambda_handler = Mangum(app)

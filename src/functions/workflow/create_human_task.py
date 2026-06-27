from src.shared.dynamodb import now_iso, workflow_tasks_table
from src.shared.ids import new_id


def lambda_handler(event, _context):
    task = {
        "tenantId": event["tenantId"],
        "taskId": new_id("tsk"),
        "orderId": event["orderId"],
        "storeId": event["storeId"],
        "stepName": event["stepName"],
        "requiredRole": event["requiredRole"],
        "status": "PENDING",
        "taskToken": event["taskToken"],
        "startedAt": now_iso(),
        "completedAt": None,
        "completedBy": None,
    }
    workflow_tasks_table().put_item(Item=task)
    return {"taskId": task["taskId"], "status": task["status"]}

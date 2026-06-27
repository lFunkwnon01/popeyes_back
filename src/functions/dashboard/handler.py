from boto3.dynamodb.conditions import Key
from fastapi import Request
from mangum import Mangum

from src.shared.app import create_app
from src.shared.dynamodb import orders_table, workflow_tasks_table
from src.shared.permissions import get_current_user, require_roles
from src.shared.response import success_response


app = create_app("dashboard-service")


@app.get("/dashboard/summary")
def get_summary(request: Request):
    user = get_current_user(request)
    require_roles(user, {"ADMIN"})

    orders = orders_table().query(
        KeyConditionExpression=Key("tenantId").eq(user["tenantId"]),
    ).get("Items", [])
    tasks = workflow_tasks_table().query(
        KeyConditionExpression=Key("tenantId").eq(user["tenantId"]),
    ).get("Items", [])

    total_orders = len(orders)
    orders_by_status = {}
    orders_by_origin = {}
    orders_by_store = {}

    for order in orders:
        orders_by_status[order.get("status")] = orders_by_status.get(order.get("status"), 0) + 1
        orders_by_origin[order.get("origin")] = orders_by_origin.get(order.get("origin"), 0) + 1
        orders_by_store[order.get("storeId")] = orders_by_store.get(order.get("storeId"), 0) + 1

    average_time_by_step = {}
    step_totals = {}
    step_counts = {}
    for task in tasks:
        if not task.get("completedAt") or not task.get("startedAt"):
            continue
        duration_seconds = int(
            (
                __import__("datetime").datetime.fromisoformat(task["completedAt"].replace("Z", "+00:00"))
                - __import__("datetime").datetime.fromisoformat(task["startedAt"].replace("Z", "+00:00"))
            ).total_seconds()
        )
        step_name = task.get("stepName")
        step_totals[step_name] = step_totals.get(step_name, 0) + duration_seconds
        step_counts[step_name] = step_counts.get(step_name, 0) + 1

    for step_name, total in step_totals.items():
        average_time_by_step[step_name] = round(total / step_counts[step_name], 2)

    recent_orders = sorted(orders, key=lambda item: item.get("createdAt", ""), reverse=True)[:10]

    return success_response(
        {
            "totalOrders": total_orders,
            "ordersByStatus": orders_by_status,
            "ordersByOrigin": orders_by_origin,
            "ordersByStore": orders_by_store,
            "averageTimeByStep": average_time_by_step,
            "recentOrders": recent_orders,
        }
    )


lambda_handler = Mangum(app)

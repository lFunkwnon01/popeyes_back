from boto3.dynamodb.conditions import Key
from fastapi import Body, HTTPException, Request
from mangum import Mangum

from src.shared import config
from src.shared.app import create_app
from src.shared.dynamodb import now_iso, order_events_table, orders_table
from src.shared.events import put_event
from src.shared.ids import new_id
from src.shared.permissions import get_current_user, require_roles
from src.shared.response import success_response


app = create_app("orders-service")


def calculate_total(items, explicit_total):
    if explicit_total is not None:
        return float(explicit_total)

    total = 0.0
    for item in items:
        total += float(item.get("price", 0)) * int(item.get("quantity", 1))
    return round(total, 2)


def save_order_and_emit(order):
    orders_table().put_item(Item=order)

    event_record = {
        "tenantId": order["tenantId"],
        "eventId": new_id("evt"),
        "orderId": order["orderId"],
        "storeId": order["storeId"],
        "eventType": "OrderCreated",
        "status": order["status"],
        "createdAt": now_iso(),
        "metadata": {"origin": order["origin"]},
    }
    order_events_table().put_item(Item=event_record)

    put_event(
        "popeyes.orders",
        "OrderCreated",
        {
            "tenantId": order["tenantId"],
            "storeId": order["storeId"],
            "orderId": order["orderId"],
            "origin": order["origin"],
            "externalOrderId": order.get("externalOrderId"),
        },
    )


def normalize_order_items(items):
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="items must be a non-empty array")
    return items


@app.post("/orders")
def create_order(request: Request, payload=Body(...)):
    user = get_current_user(request)
    require_roles(user, {"CLIENT", "ADMIN"})

    items = normalize_order_items(payload.get("items"))
    store_id = payload.get("storeId") or user.get("storeId") or config.DEFAULT_STORE_ID
    order = {
        "tenantId": user["tenantId"],
        "orderId": new_id("ord"),
        "storeId": store_id,
        "customerId": user["userId"],
        "customerName": payload.get("customerName") or user.get("name") or user["email"],
        "origin": "WEB_POPEYES",
        "externalOrderId": None,
        "items": items,
        "total": calculate_total(items, payload.get("total")),
        "status": "ORDER_CREATED",
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "completedAt": None,
    }
    save_order_and_emit(order)
    return success_response(order, 201)


@app.post("/orders/rappi")
def create_rappi_order(request: Request, payload=Body(...)):
    headers = request.scope.get("aws.event", {}).get("headers", {})
    api_key = headers.get("x-api-key") or headers.get("X-Api-Key")
    if api_key != config.RAPPI_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid x-api-key")

    items = normalize_order_items(payload.get("items"))
    tenant_id = payload.get("tenantId") or config.DEFAULT_TENANT_ID
    store_id = payload.get("storeId") or config.DEFAULT_STORE_ID
    external_order_id = payload.get("externalOrderId")
    if not external_order_id:
        raise HTTPException(status_code=400, detail="externalOrderId is required")

    order = {
        "tenantId": tenant_id,
        "orderId": new_id("ord"),
        "storeId": store_id,
        "customerId": payload.get("customerId") or "rappi-customer",
        "customerName": payload.get("customerName") or "Rappi Customer",
        "origin": "RAPPI",
        "externalOrderId": external_order_id,
        "items": items,
        "total": calculate_total(items, payload.get("total")),
        "status": "ORDER_CREATED",
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
        "completedAt": None,
    }
    save_order_and_emit(order)
    return success_response(order, 201)


@app.get("/orders")
def list_orders(request: Request):
    user = get_current_user(request)
    response = orders_table().query(KeyConditionExpression=Key("tenantId").eq(user["tenantId"]))
    items = response.get("Items", [])

    query_params = request.query_params
    status = query_params.get("status")
    origin = query_params.get("origin")
    store_id = query_params.get("storeId")

    filtered = []
    for order in items:
        if user["role"] == "CLIENT" and order.get("customerId") != user["userId"]:
            continue
        if user["role"] not in {"ADMIN", "CLIENT"} and user.get("storeId") and order.get("storeId") != user.get("storeId"):
            continue
        if status and order.get("status") != status:
            continue
        if origin and order.get("origin") != origin:
            continue
        if store_id and order.get("storeId") != store_id:
            continue
        filtered.append(order)

    filtered.sort(key=lambda item: item.get("createdAt", ""), reverse=True)
    return success_response(filtered)


@app.get("/orders/{order_id}")
def get_order(order_id: str, request: Request):
    user = get_current_user(request)
    response = orders_table().get_item(Key={"tenantId": user["tenantId"], "orderId": order_id})
    order = response.get("Item")
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if user["role"] == "CLIENT" and order.get("customerId") != user["userId"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    if user["role"] not in {"ADMIN", "CLIENT"} and user.get("storeId") and order.get("storeId") != user.get("storeId"):
        raise HTTPException(status_code=403, detail="Forbidden")

    return success_response(order)


lambda_handler = Mangum(app)

from decimal import Decimal

from boto3.dynamodb.conditions import Key
from fastapi import Body, HTTPException, Request
from mangum import Mangum

from src.shared import config
from src.shared.app import create_app
from src.shared.dynamodb import now_iso, order_events_table, orders_table
from src.shared.events import put_event
from src.shared.ids import new_id
from src.shared.permissions import get_current_user, require_roles, resolve_tenant_id
from src.shared.response import success_response_safe, success_response


app = create_app("orders-service")


def _to_decimal(value):
    if value is None:
        return None
    if isinstance(value, (int, Decimal)):
        return Decimal(value)
    return Decimal(str(value))


def calculate_total(items, explicit_total):
    if explicit_total is not None:
        return _to_decimal(explicit_total)

    total = Decimal("0")
    for item in items:
        price = _to_decimal(item.get("price", 0))
        quantity = int(item.get("quantity", 1))
        total += price * quantity
    return total.quantize(Decimal("0.01"))


def save_order_and_emit(order):
    orders_table().put_item(Item=order)

    event_record = {
        "tenantId": order["tenantId"],
        "eventId": new_id("evt"),
        "orderId": order["orderId"],
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
            "orderId": order["orderId"],
            "origin": order["origin"],
            "externalOrderId": order.get("externalOrderId"),
        },
    )


def normalize_order_items(items):
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=400, detail="items must be a non-empty array")
    # Convertir price a Decimal para DynamoDB
    normalized = []
    for item in items:
        normalized.append({
            "productId": item.get("productId"),
            "name": item.get("name"),
            "price": _to_decimal(item.get("price", 0)),
            "quantity": int(item.get("quantity", 1)),
        })
    return normalized


@app.post("/orders")
def create_order(request: Request, payload=Body(...)):
    """
    Crea un pedido en la sede (tenant) del usuario.

    El `tenantId` se toma de:
    1. JWT (si el user tiene sede asignada) - ADMIN/worker
    2. body (si viene) - CLIENT, que elige sede en el frontend

    Para un CLIENT (sin tenantId fijo en el JWT), DEBE venir tenantId
    en el body. Para un ADMIN, se usa su tenant asignado (ignora el
    body para evitar que un admin de Miraflores cree pedidos en Surco).
    """
    user = get_current_user(request)
    require_roles(user, {"CLIENT", "ADMIN"})

    items = normalize_order_items(payload.get("items"))

    if user["role"] == "ADMIN":
        tenant_id = user.get("tenantId")
        if not tenant_id:
            raise HTTPException(
                status_code=400,
                detail="Admin sin sede asignada no puede crear pedidos",
            )
    else:
        tenant_id = payload.get("tenantId") or user.get("tenantId")
        if not tenant_id:
            raise HTTPException(
                status_code=400,
                detail="tenantId es requerido en el body (el cliente debe elegir sede)",
            )

    payment_method = payload.get("paymentMethod") or ""

    order = {
        "tenantId": tenant_id,
        "orderId": new_id("ord"),
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
        "deliveryAddress": payload.get("deliveryAddress") or "",
        "paymentMethod": payment_method,
    }
    save_order_and_emit(order)
    return success_response_safe(order, 201)


@app.post("/orders/rappi")
def create_rappi_order(request: Request, payload=Body(...)):
    headers = request.scope.get("aws.event", {}).get("headers", {})
    api_key = headers.get("x-api-key") or headers.get("X-Api-Key")
    if api_key != config.RAPPI_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid x-api-key")

    items = normalize_order_items(payload.get("items"))
    tenant_id = payload.get("tenantId") or config.DEFAULT_TENANT_ID
    external_order_id = payload.get("externalOrderId")
    if not external_order_id:
        raise HTTPException(status_code=400, detail="externalOrderId is required")

    payment_method = payload.get("paymentMethod") or ""

    order = {
        "tenantId": tenant_id,
        "orderId": new_id("ord"),
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
        "deliveryAddress": payload.get("deliveryAddress") or "",
        "paymentMethod": payment_method,
    }
    save_order_and_emit(order)
    return success_response_safe(order, 201)


@app.get("/orders")
def list_orders(request: Request):
    """
    Lista los pedidos visibles para el usuario actual, dentro de UNA sede.

    - ADMIN/worker: su tenantId (JWT) fija la sede, no hay ambigüedad.
    - CLIENT: no tiene tenantId fijo, así que debe indicar `tenantId` en
      el query (la sede que tiene seleccionada en el frontend). Dentro de
      esa sede, solo ve SUS pedidos (customerId == userId).

    Filtros opcionales vía query params: status, origin.
    """
    user = get_current_user(request)
    tenant_id = resolve_tenant_id(user, request)
    response = orders_table().query(KeyConditionExpression=Key("tenantId").eq(tenant_id))
    items = response.get("Items", [])

    query_params = request.query_params
    status = query_params.get("status")
    origin = query_params.get("origin")

    filtered = []
    for order in items:
        if user["role"] == "CLIENT" and order.get("customerId") != user["userId"]:
            continue
        if status and order.get("status") != status:
            continue
        if origin and order.get("origin") != origin:
            continue
        filtered.append(order)

    filtered.sort(key=lambda item: item.get("createdAt", ""), reverse=True)
    return success_response_safe(filtered)


@app.get("/orders/{order_id}")
def get_order(order_id: str, request: Request):
    user = get_current_user(request)
    tenant_id = resolve_tenant_id(user, request)
    response = orders_table().get_item(Key={"tenantId": tenant_id, "orderId": order_id})
    order = response.get("Item")
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if user["role"] == "CLIENT" and order.get("customerId") != user["userId"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    return success_response_safe(order)


lambda_handler = Mangum(app)

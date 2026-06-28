from decimal import Decimal

from boto3.dynamodb.conditions import Key
from fastapi import Body, HTTPException, Request
from mangum import Mangum

from src.shared import config
from src.shared.app import create_app
from src.shared.dynamodb import now_iso, order_events_table, orders_table
from src.shared.events import put_event
from src.shared.ids import new_id
from src.shared.permissions import get_current_user, require_roles
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
    Crea un pedido en una tienda específica.

    El `storeId` se toma de:
    1. body (si viene) - útil para CLIENT que selecciona tienda en el frontend
    2. JWT (si el user tiene tienda asignada) - útil para ADMIN
    3. DEFAULT_STORE_ID (fallback)

    Para un CLIENT sin tienda asignada en el JWT, DEBE venir storeId en el body.
    Para un ADMIN, se usa su tienda asignada (ignora el body para evitar
    que un admin de Miraflores cree pedidos en Surco).
    """
    user = get_current_user(request)
    require_roles(user, {"CLIENT", "ADMIN"})

    items = normalize_order_items(payload.get("items"))

    # Resolver el storeId según el rol
    if user["role"] == "ADMIN":
        # Admin: usa su tienda asignada (ignora el body)
        store_id = user.get("storeId")
        if not store_id:
            raise HTTPException(
                status_code=400,
                detail="Admin sin tienda asignada no puede crear pedidos",
            )
    else:
        # CLIENT: usa el del body (que viene del frontend al elegir tienda)
        # o el del JWT si lo tiene
        store_id = payload.get("storeId") or user.get("storeId")
        if not store_id:
            raise HTTPException(
                status_code=400,
                detail="storeId es requerido en el body (el cliente debe elegir tienda)",
            )

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
    return success_response_safe(order, 201)


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
    return success_response_safe(order, 201)


@app.get("/orders")
def list_orders(request: Request):
    """
    Lista los pedidos visibles para el usuario actual.

    Reglas de visibilidad:
    - CLIENT: solo SUS pedidos (customerId == userId), en cualquier tienda
    - ADMIN: solo los pedidos de SU tienda (storeId del JWT)
    - Workers (COOK/DISPATCHER/etc): solo los pedidos de SU tienda

    Filtros opcionales vía query params:
    - status: filtrar por OrderStatus
    - origin: filtrar por WEB_POPEYES o RAPPI
    - storeId: filtrar por tienda (CLIENT puede usar cualquiera;
      admin/worker solo su tienda; si pide otra → 403)
    """
    user = get_current_user(request)
    response = orders_table().query(KeyConditionExpression=Key("tenantId").eq(user["tenantId"]))
    items = response.get("Items", [])

    query_params = request.query_params
    status = query_params.get("status")
    origin = query_params.get("origin")
    store_id = query_params.get("storeId")
    user_store = user.get("storeId") or ""

    # Validar que admin/workers no pidan otra tienda
    if store_id and user["role"] != "CLIENT" and user_store and store_id != user_store:
        raise HTTPException(
            status_code=403,
            detail=f"Usuario de tienda {user_store} no puede ver pedidos de {store_id}",
        )

    filtered = []
    for order in items:
        # Visibilidad por rol
        if user["role"] == "CLIENT" and order.get("customerId") != user["userId"]:
            continue
        # Admin y workers: solo los de su tienda
        if user["role"] in {"ADMIN", "COOK", "DISPATCHER", "DELIVERY_DRIVER", "RESTAURANT_WORKER"}:
            if user_store and order.get("storeId") != user_store:
                continue
        # Filtros de query
        if status and order.get("status") != status:
            continue
        if origin and order.get("origin") != origin:
            continue
        if store_id and order.get("storeId") != store_id:
            continue
        filtered.append(order)

    filtered.sort(key=lambda item: item.get("createdAt", ""), reverse=True)
    return success_response_safe(filtered)


@app.get("/orders/{order_id}")
def get_order(order_id: str, request: Request):
    user = get_current_user(request)
    response = orders_table().get_item(Key={"tenantId": user["tenantId"], "orderId": order_id})
    order = response.get("Item")
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    user_store = user.get("storeId") or ""

    if user["role"] == "CLIENT" and order.get("customerId") != user["userId"]:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Admin/workers solo de su tienda
    if user["role"] != "CLIENT" and user_store and order.get("storeId") != user_store:
        raise HTTPException(
            status_code=403,
            detail=f"Usuario de tienda {user_store} no puede ver pedidos de {order.get('storeId')}",
        )

    return success_response_safe(order)


lambda_handler = Mangum(app)

from decimal import Decimal

from boto3.dynamodb.conditions import Key
from fastapi import Body, HTTPException, Query, Request
from mangum import Mangum

from src.shared.app import create_app
from src.shared.dynamodb import now_iso, products_table, stores_table
from src.shared.ids import new_id
from src.shared.permissions import get_current_user, require_roles
from src.shared.response import success_response_safe, success_response


def _to_decimal(value):
    """DynamoDB no acepta float - convertir a Decimal."""
    if value is None or isinstance(value, (int, Decimal)):
        return Decimal(value) if value is not None else Decimal("0")
    return Decimal(str(value))


app = create_app("catalog-service")


@app.get("/products")
def list_products(
    request: Request,
    storeId: str | None = Query(default=None, description="Filtrar por tienda"),
):
    """
    Lista los productos del tenant actual.

    Reglas de filtrado:
    - Si el query trae `storeId` y el usuario es CLIENT: devuelve los productos de ESA tienda.
    - Si el query trae `storeId` y el usuario es worker/admin: valida que sea SU tienda;
      si no, devuelve 403.
    - Si NO trae `storeId`:
        - CLIENT: ve todos los productos del tenant (puede navegar entre tiendas).
        - worker/admin: solo ve los productos de SU tienda.
    """
    user = get_current_user(request)
    tenant_id = user["tenantId"]
    role = user["role"]
    user_store = user.get("storeId") or ""

    # Si el query pide una tienda específica
    if storeId:
        if role == "CLIENT":
            # Cliente puede explorar cualquier tienda
            target = storeId
        elif role == "ADMIN":
            # Admin solo de su tienda
            if user_store and storeId != user_store:
                raise HTTPException(
                    status_code=403,
                    detail=f"Admin de tienda {user_store} no puede ver productos de {storeId}",
                )
            target = user_store or storeId
        else:
            # Workers (COOK, DISPATCHER, etc.) solo de su tienda
            if user_store and storeId != user_store:
                raise HTTPException(
                    status_code=403,
                    detail=f"Worker de tienda {user_store} no puede ver productos de {storeId}",
                )
            target = user_store or storeId
    else:
        # Sin storeId en query
        if role == "CLIENT":
            # Sin tienda seleccionada: devolver lista VACÍA (forzamos a elegir tienda)
            return success_response_safe([])
        # Workers y admins: solo su tienda
        target = user_store
        if not target:
            return success_response_safe([])

    # Query al SK compuesto: "storeId#productId"
    response = products_table().query(
        KeyConditionExpression=Key("tenantId").eq(tenant_id)
        & Key("storeIdProductId").begins_with(f"{target}#")
    )
    return success_response_safe(response.get("Items", []))


@app.post("/products")
def create_product(request: Request, payload=Body(...)):
    """
    Crea un producto en la tienda del ADMIN que llama.

    El `storeId` del body es IGNORADO: se fuerza al del JWT del usuario.
    Esto garantiza que un admin de Miraflores NUNCA pueda crear productos
    en Surco o Barranco.
    """
    user = get_current_user(request)
    require_roles(user, {"ADMIN"})

    store_id = user.get("storeId")
    if not store_id:
        raise HTTPException(
            status_code=400,
            detail="El usuario admin no tiene tienda asignada",
        )

    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    product_id = new_id("prd")
    product = {
        "tenantId": user["tenantId"],
        "storeId": store_id,
        "storeIdProductId": f"{store_id}#{product_id}",  # SK compuesta
        "productId": product_id,
        "name": name,
        "description": payload.get("description") or "",
        "price": _to_decimal(payload.get("price") or 0),
        "imageUrl": payload.get("imageUrl") or "",
        "category": payload.get("category") or "General",
        "active": bool(payload.get("active", True)),
        "createdAt": now_iso(),
    }
    products_table().put_item(Item=product)
    return success_response_safe(product, 201)


@app.get("/stores")
def list_stores(request: Request):
    """
    Lista todas las tiendas del tenant actual.
    Disponible para cualquier usuario autenticado (incluyendo CLIENT).
    El home del frontend usa este endpoint para mostrar el selector de sede.
    """
    user = get_current_user(request)
    response = stores_table().query(KeyConditionExpression=Key("tenantId").eq(user["tenantId"]))
    return success_response_safe(response.get("Items", []))


@app.post("/stores")
def create_store(request: Request, payload=Body(...)):
    """
    Crea una nueva tienda en el tenant actual.
    Solo permitido para ADMIN (que gestiona el catálogo multi-sede).
    """
    user = get_current_user(request)
    require_roles(user, {"ADMIN"})

    name = (payload.get("name") or "").strip()
    store_id = (payload.get("storeId") or "").strip()
    if not name or not store_id:
        raise HTTPException(status_code=400, detail="name and storeId are required")

    store = {
        "tenantId": user["tenantId"],
        "storeId": store_id,
        "name": name,
        "address": payload.get("address") or "",
        "active": bool(payload.get("active", True)),
        "createdAt": now_iso(),
    }
    stores_table().put_item(Item=store)
    return success_response_safe(store, 201)


lambda_handler = Mangum(app)

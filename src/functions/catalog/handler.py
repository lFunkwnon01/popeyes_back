import uuid
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from fastapi import Body, HTTPException, Query, Request
from mangum import Mangum

from src.shared import config
from src.shared.app import create_app
from src.shared.dynamodb import now_iso, products_table, stores_table
from src.shared.ids import new_id
from src.shared.permissions import get_current_user, get_current_user_or_anonymous, require_roles
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
    tenantId: str | None = Query(default=None, description="Sede a consultar"),
):
    """
    Lista los productos de una sede (tenant).

    - Endpoint público (sin JWT): requiere `tenantId` en query (browsing).
    - ADMIN/worker autenticado: solo puede ver los de SU tenant (ignora el
      query si no coincide, 403 si pide otra sede).
    - CLIENT autenticado: puede explorar cualquier sede vía `tenantId`.
    """
    user = get_current_user_or_anonymous(request)
    role = user["role"]
    user_tenant = user.get("tenantId") or ""

    if role in {"ADMIN", "RESTAURANT_WORKER", "COOK", "DISPATCHER", "DELIVERY_DRIVER"}:
        if not user_tenant:
            raise HTTPException(status_code=400, detail="Usuario sin sede asignada")
        if tenantId and tenantId != user_tenant:
            raise HTTPException(
                status_code=403,
                detail=f"No puede ver productos de otra sede ({tenantId})",
            )
        target_tenant = user_tenant
    else:
        # CLIENT (o anónimo browseando): requiere elegir sede
        if not tenantId:
            return success_response_safe([])
        target_tenant = tenantId

    response = products_table().query(
        KeyConditionExpression=Key("tenantId").eq(target_tenant)
    )
    items = response.get("Items", [])
    for item in items:
        item.pop("storeIdProductId", None)
    return success_response_safe(items)


@app.post("/products")
def create_product(request: Request, payload=Body(...)):
    """
    Crea un producto en la sede (tenant) del ADMIN que llama.
    """
    user = get_current_user(request)
    require_roles(user, {"ADMIN"})

    tenant_id = user.get("tenantId")
    if not tenant_id:
        raise HTTPException(
            status_code=400,
            detail="El usuario admin no tiene sede asignada",
        )

    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    product_id = new_id("prd")
    product = {
        "tenantId": tenant_id,
        "productId": product_id,
        # storeIdProductId es la sort key física de la tabla (heredada de
        # cuando storeId existía). Ya no representa una sede distinta del
        # tenant, se guarda igual a productId para satisfacer el schema.
        "storeIdProductId": product_id,
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


@app.post("/upload-url")
def generate_upload_url(request: Request, payload=Body(...)):
    """
    Genera una presigned URL de S3 para que el frontend suba la imagen de
    un producto directo al bucket (sin pasar el binario por Lambda).

    Flujo: POST /upload-url -> PUT binario a uploadUrl -> POST /products
    con imageUrl = publicUrl.
    """
    user = get_current_user(request)
    require_roles(user, {"ADMIN"})

    tenant_id = user.get("tenantId")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="El usuario admin no tiene sede asignada")

    filename = payload.get("filename") or "image.jpg"
    content_type = payload.get("contentType") or "image/jpeg"
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "jpg"
    object_key = f"assets/{tenant_id}/{uuid.uuid4().hex}.{ext}"

    s3 = boto3.client("s3", region_name=config.REGION)
    upload_url = s3.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": config.ASSETS_BUCKET,
            "Key": object_key,
            "ContentType": content_type,
        },
        ExpiresIn=3600,
    )
    public_url = f"https://{config.ASSETS_BUCKET}.s3.{config.REGION}.amazonaws.com/{object_key}"

    return success_response_safe({
        "uploadUrl": upload_url,
        "objectKey": object_key,
        "publicUrl": public_url,
    })


_PRODUCT_FIELD_ALIASES = {
    "name": "#name",
    "description": "#description",
    "price": "#price",
    "category": "#category",
    "imageUrl": "#imageUrl",
    "active": "#active",
}


@app.put("/products/{product_id}")
def update_product(product_id: str, request: Request, payload=Body(...)):
    """
    Edita un producto de la sede (tenant) del ADMIN que llama (nombre,
    descripción, precio, categoría, imageUrl, active). Solo puede editar
    productos de su propia sede; no acepta tenantId del body.
    """
    user = get_current_user(request)
    require_roles(user, {"ADMIN"})

    tenant_id = user.get("tenantId")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="El usuario admin no tiene sede asignada")

    existing = products_table().get_item(
        Key={"tenantId": tenant_id, "storeIdProductId": product_id}
    ).get("Item")
    if not existing:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    updates = {}
    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="name no puede estar vacío")
        updates["name"] = name
    if "description" in payload:
        updates["description"] = payload.get("description") or ""
    if "price" in payload:
        updates["price"] = _to_decimal(payload.get("price") or 0)
    if "category" in payload:
        updates["category"] = payload.get("category") or "General"
    if "imageUrl" in payload:
        updates["imageUrl"] = payload.get("imageUrl") or ""
    if "active" in payload:
        updates["active"] = bool(payload.get("active"))

    if not updates:
        raise HTTPException(status_code=400, detail="No hay campos para actualizar")

    set_parts = [f"{_PRODUCT_FIELD_ALIASES[k]} = :{k}" for k in updates]
    products_table().update_item(
        Key={"tenantId": tenant_id, "storeIdProductId": product_id},
        UpdateExpression="SET " + ", ".join(set_parts),
        ExpressionAttributeNames={_PRODUCT_FIELD_ALIASES[k]: k for k in updates},
        ExpressionAttributeValues={f":{k}": v for k, v in updates.items()},
    )

    updated = products_table().get_item(
        Key={"tenantId": tenant_id, "storeIdProductId": product_id}
    ).get("Item")
    updated.pop("storeIdProductId", None)
    return success_response_safe(updated)


@app.delete("/products/{product_id}")
def delete_product(product_id: str, request: Request):
    """
    Elimina un producto de la sede (tenant) del ADMIN que llama.
    """
    user = get_current_user(request)
    require_roles(user, {"ADMIN"})

    tenant_id = user.get("tenantId")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="El usuario admin no tiene sede asignada")

    existing = products_table().get_item(
        Key={"tenantId": tenant_id, "storeIdProductId": product_id}
    ).get("Item")
    if not existing:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    products_table().delete_item(Key={"tenantId": tenant_id, "storeIdProductId": product_id})
    return success_response_safe({"productId": product_id, "deleted": True})


@app.get("/stores")
def list_stores(request: Request):
    """
    Directorio público de todas las sedes (tenants) existentes.

    En este modelo, cada sede ES un tenant (tenantId = "popeyes-<distrito>"),
    así que listar "todas las sedes" es cruzar tenants a propósito: es la
    única operación de este backend que no está scoped a un solo tenant,
    porque es justamente la pantalla donde el usuario ELIGE su tenant.
    No requiere JWT (browsing antes de login).
    """
    response = stores_table().scan()
    items = []
    for item in response.get("Items", []):
        if not item.get("active", True):
            continue
        # storeId es un artefacto interno de la sort key física; no es un
        # concepto de negocio en este modelo (tenantId ya identifica la sede).
        item.pop("storeId", None)
        items.append(item)
    return success_response_safe(items)


@app.post("/stores")
def create_store(request: Request, payload=Body(...)):
    """
    Registra una nueva sede (tenant) en el directorio. Solo ADMIN.
    El tenantId se toma del propio JWT del admin (una sede = su propio tenant).
    """
    user = get_current_user(request)
    require_roles(user, {"ADMIN"})

    tenant_id = user.get("tenantId")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="El usuario admin no tiene sede asignada")

    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    store = {
        "tenantId": tenant_id,
        # storeId es la sort key física de la tabla (heredada de cuando
        # existían varias tiendas por tenant). Ahora 1 tenant = 1 sede,
        # así que se guarda igual a tenantId para satisfacer el schema.
        "storeId": tenant_id,
        "name": name,
        "address": payload.get("address") or "",
        "active": bool(payload.get("active", True)),
        "createdAt": now_iso(),
    }
    stores_table().put_item(Item=store)
    return success_response_safe(store, 201)


lambda_handler = Mangum(app)

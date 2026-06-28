from decimal import Decimal

from boto3.dynamodb.conditions import Key
from fastapi import Body, HTTPException, Request
from mangum import Mangum

from src.shared import config
from src.shared.app import create_app
from src.shared.auth import hash_password
from src.shared.dynamodb import now_iso, products_table, stores_table, users_table
from src.shared.ids import new_id
from src.shared.permissions import get_current_user, require_roles
from src.shared.response import success_response_safe, success_response
from src.shared.seed_data import (
    SEED_PRODUCTS_BY_STORE,
    SEED_STORES,
    SEED_USERS,
)


app = create_app("admin-service")

# Roles que un ADMIN puede asignar al crear un nuevo user.
# ADMIN puede crear otros ADMINs (escalación controlada: solo de su tienda).
ROLES_CREATABLE = {
    "ADMIN",
    "RESTAURANT_WORKER",
    "COOK",
    "DISPATCHER",
    "DELIVERY_DRIVER",
    "CLIENT",
}


def find_user_by_email(email):
    response = users_table().query(IndexName="email-index", KeyConditionExpression=Key("email").eq(email.lower()), Limit=1)
    items = response.get("Items", [])
    return items[0] if items else None


def _to_decimal(value):
    """DynamoDB no acepta float - convertir todo número a Decimal."""
    if isinstance(value, float):
        return Decimal(str(value))
    return value


@app.post("/admin/seed")
def seed_demo_data(request: Request):
    """
    Crea 3 tiendas (Miraflores, Surco, Barranco) con sus productos y usuarios.

    Idempotente: si los recursos ya existen, los salta. El primer ADMIN
    que llame a este endpoint crea todo el catálogo demo.

    Retorna: {seeded, created: {stores: ["store-001", ...], products: [names], users: [emails]}}
    """
    user = get_current_user(request)
    require_roles(user, {"ADMIN"})

    created = {"stores": [], "products": [], "users": []}

    # === 1. Crear las 3 tiendas ===
    for store_def in SEED_STORES:
        existing = stores_table().get_item(
            Key={"tenantId": store_def["tenantId"], "storeId": store_def["storeId"]}
        ).get("Item")
        if not existing:
            store = {**store_def, "createdAt": now_iso()}
            stores_table().put_item(Item=store)
            created["stores"].append(store_def["storeId"])

    # === 2. Crear productos por tienda ===
    for store_id, products_list in SEED_PRODUCTS_BY_STORE.items():
        # Verificar si ya hay productos en esta tienda
        existing_products = products_table().query(
            KeyConditionExpression=Key("tenantId").eq(config.DEFAULT_TENANT_ID)
            & Key("storeIdProductId").begins_with(f"{store_id}#")
        ).get("Items", [])
        existing_names = {p.get("name") for p in existing_products}

        for product in products_list:
            if product["name"] in existing_names:
                continue
            product_id = new_id("prd")
            product_item = {
                "tenantId": config.DEFAULT_TENANT_ID,
                "storeId": store_id,
                "storeIdProductId": f"{store_id}#{product_id}",
                "productId": product_id,
                **{k: _to_decimal(v) for k, v in product.items()},
                "createdAt": now_iso(),
            }
            products_table().put_item(Item=product_item)
            created["products"].append(f"[{store_id}] {product['name']}")

    # === 3. Crear los 15 users (3 admins, 12 workers, 1 client) ===
    for seed_user in SEED_USERS:
        if find_user_by_email(seed_user["email"]):
            continue
        user_item = {
            "userId": new_id("usr"),
            "email": seed_user["email"],
            "passwordHash": hash_password("password123"),
            "name": seed_user["name"],
            "role": seed_user["role"],
            "tenantId": config.DEFAULT_TENANT_ID,
            "storeId": seed_user.get("storeId") or "",
            "createdAt": now_iso(),
        }
        users_table().put_item(Item=user_item)
        created["users"].append(seed_user["email"])

    return success_response_safe({"seeded": True, "created": created})


@app.post("/admin/users")
def create_user(request: Request, payload=Body(...)):
    """
    Crea un nuevo usuario en el tenant del ADMIN que llama.

    Body:
        {
            "email": "nuevo.cocinero@popeyes.pe",
            "password": "temp123",
            "name": "Pedro Cocinero",
            "role": "COOK"  // o ADMIN, RESTAURANT_WORKER, DISPATCHER, DELIVERY_DRIVER, CLIENT
        }

    Reglas:
    - Solo ADMIN puede llamar.
    - `tenantId` se fuerza al del JWT (no se acepta del body).
    - `storeId` se resuelve así:
        * Si role == "CLIENT" → storeId = "" (CLIENT global)
        * Si role != "CLIENT" → storeId = storeId del ADMIN (siempre en su tienda)
    - El ADMIN solo puede crear users en SU propia tienda (no en otras).
    - El email debe ser único en el tenant.
    - ADMINs pueden crear otros ADMINs (de su misma tienda).
    - El password se hashea con el mismo algoritmo que /auth/register.
    """
    caller = get_current_user(request)
    require_roles(caller, {"ADMIN"})

    # === Validar campos requeridos ===
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    name = (payload.get("name") or "").strip()
    requested_role = (payload.get("role") or "").strip().upper()

    if not email or not password or not name:
        raise HTTPException(
            status_code=400,
            detail="email, password, name and role are required",
        )
    if requested_role not in ROLES_CREATABLE:
        raise HTTPException(
            status_code=400,
            detail=f"role inválido. Permitidos: {sorted(ROLES_CREATABLE)}",
        )
    if len(password) < 6:
        raise HTTPException(
            status_code=400,
            detail="password debe tener al menos 6 caracteres",
        )

    # === Validar email único ===
    if find_user_by_email(email):
        raise HTTPException(
            status_code=409,
            detail=f"El email {email} ya está registrado",
        )

    # === Resolver storeId según el rol ===
    if requested_role == "CLIENT":
        # CLIENTs son globales (pueden pedir en cualquier tienda)
        assigned_store_id = ""
    else:
        # Workers y otros ADMINs van a la tienda del ADMIN que los crea
        admin_store = caller.get("storeId")
        if not admin_store:
            raise HTTPException(
                status_code=400,
                detail="El ADMIN que llama no tiene tienda asignada",
            )
        assigned_store_id = admin_store

    # === Crear el user ===
    new_user = {
        "userId": new_id("usr"),
        "email": email,
        "passwordHash": hash_password(password),
        "name": name,
        "role": requested_role,
        "tenantId": caller["tenantId"],   # forzado del JWT
        "storeId": assigned_store_id,     # forzado según rol
        "createdAt": now_iso(),
        "createdBy": caller["userId"],    # auditoría
    }
    users_table().put_item(Item=new_user)

    # === Respuesta sin passwordHash ===
    safe_user = {
        "userId": new_user["userId"],
        "email": new_user["email"],
        "name": new_user["name"],
        "role": new_user["role"],
        "tenantId": new_user["tenantId"],
        "storeId": new_user["storeId"],
        "createdAt": new_user["createdAt"],
        "createdBy": new_user["createdBy"],
    }
    return success_response_safe(safe_user, 201)


lambda_handler = Mangum(app)

from boto3.dynamodb.conditions import Key
from fastapi import Body, HTTPException, Request
from mangum import Mangum

from src.shared.app import create_app
from src.shared.dynamodb import now_iso, products_table, stores_table
from src.shared.ids import new_id
from src.shared.permissions import get_current_user, require_roles
from src.shared.response import success_response


app = create_app("catalog-service")


@app.get("/products")
def list_products(request: Request):
    user = get_current_user(request)
    response = products_table().query(KeyConditionExpression=Key("tenantId").eq(user["tenantId"]))
    return success_response(response.get("Items", []))


@app.post("/products")
def create_product(request: Request, payload=Body(...)):
    user = get_current_user(request)
    require_roles(user, {"ADMIN"})

    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    product = {
        "tenantId": user["tenantId"],
        "productId": new_id("prd"),
        "name": name,
        "description": payload.get("description") or "",
        "price": float(payload.get("price") or 0),
        "imageUrl": payload.get("imageUrl") or "",
        "category": payload.get("category") or "General",
        "active": bool(payload.get("active", True)),
        "createdAt": now_iso(),
    }
    products_table().put_item(Item=product)
    return success_response(product, 201)


@app.get("/stores")
def list_stores(request: Request):
    user = get_current_user(request)
    response = stores_table().query(KeyConditionExpression=Key("tenantId").eq(user["tenantId"]))
    return success_response(response.get("Items", []))


@app.post("/stores")
def create_store(request: Request, payload=Body(...)):
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
    return success_response(store, 201)


lambda_handler = Mangum(app)

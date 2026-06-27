from boto3.dynamodb.conditions import Key
from fastapi import Request
from mangum import Mangum

from src.shared import config
from src.shared.app import create_app
from src.shared.auth import hash_password
from src.shared.dynamodb import now_iso, products_table, stores_table, users_table
from src.shared.ids import new_id
from src.shared.permissions import get_current_user, require_roles
from src.shared.response import success_response
from src.shared.seed_data import SEED_PRODUCTS, SEED_STORE, SEED_USERS


app = create_app("admin-service")


def find_user_by_email(email):
    response = users_table().query(IndexName="email-index", KeyConditionExpression=Key("email").eq(email.lower()), Limit=1)
    items = response.get("Items", [])
    return items[0] if items else None


@app.post("/admin/seed")
def seed_demo_data(request: Request):
    user = get_current_user(request)
    require_roles(user, {"ADMIN"})

    created = {"store": False, "products": [], "users": []}

    existing_store = stores_table().get_item(Key={"tenantId": SEED_STORE["tenantId"], "storeId": SEED_STORE["storeId"]}).get("Item")
    if not existing_store:
        store = {**SEED_STORE, "createdAt": now_iso()}
        stores_table().put_item(Item=store)
        created["store"] = True

    existing_products = products_table().query(
        KeyConditionExpression=Key("tenantId").eq(config.DEFAULT_TENANT_ID),
    ).get("Items", [])
    existing_product_names = {product.get("name") for product in existing_products}
    for product in SEED_PRODUCTS:
        if product["name"] in existing_product_names:
            continue
        product_item = {
            "tenantId": config.DEFAULT_TENANT_ID,
            "productId": new_id("prd"),
            **product,
            "createdAt": now_iso(),
        }
        products_table().put_item(Item=product_item)
        created["products"].append(product_item["name"])

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
            "storeId": config.DEFAULT_STORE_ID,
            "createdAt": now_iso(),
        }
        users_table().put_item(Item=user_item)
        created["users"].append(seed_user["email"])

    return success_response({"seeded": True, "created": created})


lambda_handler = Mangum(app)

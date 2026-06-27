from boto3.dynamodb.conditions import Attr, Key
from fastapi import Body, HTTPException, Request
from mangum import Mangum

from src.shared import config
from src.shared.app import create_app
from src.shared.auth import create_token, hash_password, verify_password
from src.shared.dynamodb import now_iso, users_table
from src.shared.ids import new_id
from src.shared.permissions import get_current_user
from src.shared.response import success_response


app = create_app("auth-service")


def find_user_by_email(email):
    response = users_table().query(
        IndexName="email-index",
        KeyConditionExpression=Key("email").eq(email.lower()),
        Limit=1,
    )
    items = response.get("Items", [])
    return items[0] if items else None


def admin_exists():
    response = users_table().scan(FilterExpression=Attr("role").eq("ADMIN"), Select="COUNT")
    return response.get("Count", 0) > 0


@app.post("/auth/register")
def register(payload=Body(...)):
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    name = (payload.get("name") or "").strip()
    requested_role = (payload.get("role") or "CLIENT").strip().upper()
    tenant_id = payload.get("tenantId") or config.DEFAULT_TENANT_ID
    store_id = payload.get("storeId") or config.DEFAULT_STORE_ID

    if not email or not password or not name:
        raise HTTPException(status_code=400, detail="email, password and name are required")

    if requested_role not in config.ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")

    if find_user_by_email(email):
        raise HTTPException(status_code=409, detail="User already exists")

    role = requested_role if (requested_role == "CLIENT" or not admin_exists()) else "CLIENT"

    user = {
        "userId": new_id("usr"),
        "email": email,
        "passwordHash": hash_password(password),
        "name": name,
        "role": role,
        "tenantId": tenant_id,
        "storeId": store_id,
        "createdAt": now_iso(),
    }
    users_table().put_item(Item=user)

    return success_response(
        {
            "user": {
                "userId": user["userId"],
                "email": user["email"],
                "name": user["name"],
                "role": user["role"],
                "tenantId": user["tenantId"],
                "storeId": user["storeId"],
            },
            "token": create_token(user),
            "bootstrapRoleGranted": role != "CLIENT",
        },
        201,
    )


@app.post("/auth/login")
def login(payload=Body(...)):
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password are required")

    user = find_user_by_email(email)
    if not user or not verify_password(password, user.get("passwordHash", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return success_response(
        {
            "token": create_token(user),
            "user": {
                "userId": user["userId"],
                "email": user["email"],
                "name": user["name"],
                "role": user["role"],
                "tenantId": user["tenantId"],
                "storeId": user.get("storeId") or "",
            },
        }
    )


@app.get("/auth/me")
def me(request: Request):
    return success_response(get_current_user(request))


lambda_handler = Mangum(app)

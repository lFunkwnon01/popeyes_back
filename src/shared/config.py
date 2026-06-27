import os


def get_env(name, default=None):
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


STAGE = get_env("STAGE", "dev")
REGION = get_env("REGION", "us-east-1")
JWT_SECRET = get_env("JWT_SECRET", "change-this-secret")
RAPPI_API_KEY = get_env("RAPPI_API_KEY", "change-this-rappi-key")
RAPPI_STATUS_API_URL = get_env("RAPPI_STATUS_API_URL", "")
EVENT_BUS_NAME = get_env("EVENT_BUS_NAME", f"popeyes-orders-bus-{STAGE}")
USERS_TABLE = get_env("USERS_TABLE")
PRODUCTS_TABLE = get_env("PRODUCTS_TABLE")
STORES_TABLE = get_env("STORES_TABLE")
ORDERS_TABLE = get_env("ORDERS_TABLE")
WORKFLOW_TASKS_TABLE = get_env("WORKFLOW_TASKS_TABLE")
ORDER_EVENTS_TABLE = get_env("ORDER_EVENTS_TABLE")
ASSETS_BUCKET = get_env("ASSETS_BUCKET")
ORDER_WORKFLOW_ARN = get_env("ORDER_WORKFLOW_ARN")

DEFAULT_TENANT_ID = "popeyes"
DEFAULT_STORE_ID = "store-001"

ROLES = {
    "CLIENT",
    "RESTAURANT_WORKER",
    "COOK",
    "DISPATCHER",
    "DELIVERY_DRIVER",
    "ADMIN",
}

ORDER_STATUSES = {
    "ORDER_CREATED",
    "ORDER_RECEIVED",
    "COOKING",
    "COOKED",
    "PACKING",
    "PACKED",
    "OUT_FOR_DELIVERY",
    "DELIVERED",
    "COMPLETED",
}

STEP_ROLE_MAP = {
    "RECEIVE_ORDER": "RESTAURANT_WORKER",
    "COOK_ORDER": "COOK",
    "PACK_ORDER": "DISPATCHER",
    "DELIVER_ORDER": "DELIVERY_DRIVER",
    "CONFIRM_RECEPTION": "CLIENT",
}

from datetime import datetime, timezone

import boto3

from src.shared import config


_dynamodb = boto3.resource("dynamodb", region_name=config.REGION)


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def table(name):
    return _dynamodb.Table(name)


def users_table():
    return table(config.USERS_TABLE)


def products_table():
    return table(config.PRODUCTS_TABLE)


def stores_table():
    return table(config.STORES_TABLE)


def orders_table():
    return table(config.ORDERS_TABLE)


def workflow_tasks_table():
    return table(config.WORKFLOW_TASKS_TABLE)


def order_events_table():
    return table(config.ORDER_EVENTS_TABLE)

from src.shared.dynamodb import now_iso, order_events_table, orders_table
from src.shared.events import put_event
from src.shared.ids import new_id


def lambda_handler(event, _context):
    timestamp = now_iso()
    existing_order = orders_table().get_item(Key={"tenantId": event["tenantId"], "orderId": event["orderId"]}).get("Item")
    if not existing_order:
        raise RuntimeError("Order not found")

    update_expression = "SET #status = :status, updatedAt = :updatedAt"
    expression_attribute_names = {"#status": "status"}
    expression_attribute_values = {":status": event["status"], ":updatedAt": timestamp}
    if event["status"] == "COMPLETED":
        update_expression += ", completedAt = :completedAt"
        expression_attribute_values[":completedAt"] = timestamp

    orders_table().update_item(
        Key={"tenantId": event["tenantId"], "orderId": event["orderId"]},
        UpdateExpression=update_expression,
        ExpressionAttributeNames=expression_attribute_names,
        ExpressionAttributeValues=expression_attribute_values,
    )

    order_events_table().put_item(
        Item={
            "tenantId": event["tenantId"],
            "eventId": new_id("evt"),
            "orderId": event["orderId"],
            "storeId": event["storeId"],
            "eventType": "OrderStatusChanged",
            "status": event["status"],
            "createdAt": timestamp,
            "metadata": {"stepName": event["stepName"]},
        }
    )

    put_event(
        "popeyes.workflow",
        "OrderStatusChanged",
        {
            "tenantId": event["tenantId"],
            "storeId": event["storeId"],
            "orderId": event["orderId"],
            "origin": event.get("origin") or existing_order.get("origin"),
            "externalOrderId": event.get("externalOrderId") or existing_order.get("externalOrderId"),
            "status": event["status"],
            "timestamp": timestamp,
        },
    )

    return {"orderId": event["orderId"], "status": event["status"], "updatedAt": timestamp}

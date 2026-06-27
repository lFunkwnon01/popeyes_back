from src.shared.dynamodb import now_iso, orders_table


def lambda_handler(event, _context):
    timestamp = now_iso()
    orders_table().update_item(
        Key={"tenantId": event["tenantId"], "orderId": event["orderId"]},
        UpdateExpression="SET updatedAt = :updatedAt, completedAt = if_not_exists(completedAt, :completedAt)",
        ExpressionAttributeValues={":updatedAt": timestamp, ":completedAt": timestamp},
    )
    return {"orderId": event["orderId"], "closedAt": timestamp}

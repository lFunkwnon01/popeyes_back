import json
from urllib import request as urllib_request

from src.shared import config


def lambda_handler(event, _context):
    detail = event.get("detail", {})
    if detail.get("origin") != "RAPPI":
        return {"notified": False, "reason": "origin is not RAPPI"}

    if not config.RAPPI_STATUS_API_URL:
        raise RuntimeError("RAPPI_STATUS_API_URL is required for RAPPI notifications")

    payload = {
        "externalOrderId": detail.get("externalOrderId"),
        "orderId": detail.get("orderId"),
        "tenantId": detail.get("tenantId"),
        "storeId": detail.get("storeId"),
        "status": detail.get("status"),
        "timestamp": detail.get("timestamp"),
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        config.RAPPI_STATUS_API_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib_request.urlopen(req, timeout=10) as response:
        status_code = response.getcode()

    if status_code >= 400:
        raise RuntimeError(f"Failed to notify RAPPI. Status code: {status_code}")

    return {"notified": True, "statusCode": status_code, "payload": payload}

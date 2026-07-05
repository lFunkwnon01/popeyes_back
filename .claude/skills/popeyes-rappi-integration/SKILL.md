---
name: popeyes-rappi-integration
description: Contract between the Rappi simulator (GCP) and the Popeyes backend (AWS). Covers auth via x-api-key, /orders/rappi request body, and the OrderStatusChanged webhook back to GCP. Use ONLY when wiring up the Rappi simulator or changing the external integration.
---

# Popeyes ↔ Rappi integration

The Popeyes backend **does NOT deploy anything in GCP**. It only defines the contract. The `simulacion_rappi` frontend lives in GCP (Firebase Hosting) and is the system that simulates the Rappi app.

## Flow

```
[Rappi simulator (GCP)]                  [Popeyes backend (AWS)]
   │                                              │
   │  POST /orders/rappi                          │
   │  Headers: x-api-key, X-Tenant-Id, X-Store-Id │
   │─────────────────────────────────────────────▶│
   │                                              │  validates x-api-key vs RAPPI_API_KEY
   │                                              │  persists order, starts Step Functions
   │  201 { orderId, status, createdAt, total }   │
   │◀─────────────────────────────────────────────│
   │                                              │
   │   …time passes, workers advance the order…   │
   │                                              │
   │                       (workers call          │
   │                       /tasks/{id}/complete)  │
   │                                              │  updateOrderStatus emits
   │                                              │  OrderStatusChanged to EventBridge
   │                                              │
   │                       notifyRappiStatus Lambda│
   │                       (EventBridge target)   │
   │                                              │  POSTs status to RAPPI_STATUS_API_URL
   │◀─────────────────────────────────────────────│  (the GCP webhook)
   │  200 OK                                       │
```

## Auth — `/orders/rappi`

- **Header required**: `x-api-key: <RAPPI_API_KEY>`
- **NO JWT**: the external system (Rappi) does not have Popeyes users, so the authorizer is bypassed and the API key is checked in the handler itself.
- The key is read from `headers.get("x-api-key") or headers.get("X-Api-Key")` — case-insensitive.
- A 401 is returned if it does not match `RAPPI_API_KEY`.

## Request body — `POST /orders/rappi`

```json
{
  "tenantId": "popeyes",
  "storeId": "store-001",
  "customerId": "rappi-customer-xyz",
  "customerName": "Lucía Vargas",
  "customerPhone": "+51 999 999 999",
  "items": [
    { "productId": "p-bucket-8", "name": "Bucket 8 piezas", "price": 64.9, "quantity": 1 }
  ],
  "total": 64.9,
  "deliveryAddress": "Av. Javier Prado 1234, San Isidro",
  "paymentMethod": "TARJETA",
  "origin": "RAPPI",
  "externalOrderId": "RAPPI-AB12CD"
}
```

- `externalOrderId` is **required** (400 if missing).
- `tenantId` and `storeId` fall back to `DEFAULT_TENANT_ID` and `DEFAULT_STORE_ID` from env if omitted.
- `customerId` falls back to `"rappi-customer"`.
- `origin` MUST be exactly `"RAPPI"` (the backend stores it verbatim).

## Response — 201 Created

```json
{
  "success": true,
  "data": {
    "orderId": "ord-lx9k2a-1234",
    "tenantId": "popeyes",
    "storeId": "store-001",
    "customerId": "rappi-customer-xyz",
    "customerName": "Lucía Vargas",
    "origin": "RAPPI",
    "externalOrderId": "RAPPI-AB12CD",
    "items": [...],
    "total": 64.9,
    "status": "ORDER_CREATED",
    "createdAt": "2026-06-27T16:00:00.000Z",
    "updatedAt": "2026-06-27T16:00:00.000Z",
    "completedAt": null
  }
}
```

## Status check — `GET /orders/{orderId}`

The Rappi simulator polls this endpoint to read the current status. Requires the same `x-api-key`. (The simulator currently calls `/orders/{orderId}/status` — update it to `/orders/{orderId}` to match the actual contract.)

Response: same shape as the 201 body above. The simulator watches the `status` field.

## Status webhook back to GCP

Every time `updateOrderStatus` runs (i.e. every worker advances a stage), the Lambda `notifyRappiStatus` is triggered by EventBridge (pattern: `source: popeyes.workflow`, `detail-type: OrderStatusChanged`). That Lambda POSTs to `RAPPI_STATUS_API_URL` with:

```json
{
  "orderId": "ord-...",
  "externalOrderId": "RAPPI-AB12CD",
  "status": "COOKED",
  "stepName": "COOK_ORDER",
  "completedBy": "Juan Cocina"
}
```

If `RAPPI_STATUS_API_URL` is empty, the Lambda **does nothing** (does not fail). This is intentional so local dev works without a GCP webhook receiver.

## Setting values in the Rappi simulator

After deploying the backend, get the API Gateway URL with `npx serverless info --stage dev` and the `RAPPI_API_KEY` from the deploy output (or from the `.env` you set before deploying). Configure both in the simulator's **Config** tab.

## What the backend does NOT do

- It does not authenticate `customerId` (Rappi passes it as-is).
- It does not verify that the items exist in the products table (it trusts the payload).
- It does not call back to GCP if the env var is empty.
- It does not retry failed status webhooks (one-shot; manual recovery needed).

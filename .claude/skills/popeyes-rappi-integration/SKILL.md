---
name: popeyes-rappi-integration
description: Contract between the Rappi simulator (GCP) and the Popeyes backend (AWS). Covers auth via x-api-key for order creation AND task completion, the /orders/rappi and /tasks/rappi + /tasks/{id}/complete request bodies, and the OrderStatusChanged webhook back to GCP. Use ONLY when wiring up the Rappi simulator or changing the external integration.
---

# Popeyes ↔ Rappi integration

The Popeyes backend (`popeyes_back` on GitHub, local dir `rappi/`) **does NOT deploy anything in GCP**. It only defines the contract. The Rappi simulator (`popeyes_frontend` on GitHub? — no: the GCP-side Rappi simulator is a separate project, not `rappi_frontend`; `rappi_frontend` is the Popeyes customer/worker web app) lives in GCP and is the system that simulates the Rappi app placing and tracking orders.

## Flow (now 3 touchpoints, not 2)

```
[Rappi simulator (GCP)]                       [Popeyes backend (AWS)]
   │                                                    │
   │  1. POST /orders/rappi (x-api-key)                 │
   │────────────────────────────────────────────────────▶│  creates order, starts workflow
   │  201 { orderId, status, ... }                        │
   │◀────────────────────────────────────────────────────│
   │                                                    │
   │        … workers advance the order through          │
   │        RECEIVE → COOK → PACK → DELIVER stages …      │
   │        (each UpdateStatus step fires                │
   │        notifyRappiStatus → RAPPI_STATUS_API_URL)      │
   │                                                    │
   │  2. GET /tasks/rappi?tenantId=&externalOrderId=     │  (x-api-key) discover pending taskId
   │────────────────────────────────────────────────────▶│  for the CONFIRM_RECEPTION stage
   │  200 [ { taskId, stepName: "CONFIRM_RECEPTION" } ]    │
   │◀────────────────────────────────────────────────────│
   │                                                    │
   │  3. POST /tasks/{taskId}/complete (x-api-key)        │  Rappi confirms delivery/reception
   │────────────────────────────────────────────────────▶│  on the customer's behalf
   │  200 { status: "COMPLETED" }                          │
   │◀────────────────────────────────────────────────────│
```

Step 2+3 are how Rappi (not a real Popeyes CLIENT user) completes the final `CONFIRM_RECEPTION` human-task stage of the workflow — see [[popeyes-workflow]] for the full state machine. Steps 2/3 can in principle be used for *any* stage's task if Rappi ever needs to act on behalf of a worker, but in practice the frontend's own workers complete stages 1–4.

## Auth — shared `x-api-key`, used on 3 endpoints now

- **Header required**: `x-api-key: <RAPPI_API_KEY>` on `POST /orders/rappi`, `GET /tasks/rappi`, and `POST /tasks/{taskId}/complete` (this last one also accepts a normal Popeyes JWT — see [[popeyes-workflow]] for the dual-auth logic).
- **NO JWT for the Rappi path**: the external system does not have Popeyes users, so these 3 routes have no `lambdaAuthorizer` in `serverless.yml`; the key is checked by hand in each handler.
- Read case-insensitively: `headers.get("x-api-key") or headers.get("X-Api-Key")`.
- A 401 is returned if it does not match `RAPPI_API_KEY`.
- **As of the last working session, `RAPPI_API_KEY` is still the placeholder default `change-this-rappi-key`** — it has not been synced with a real shared secret between AWS and the GCP `terraform.tfvars`.

## Request body — `POST /orders/rappi`

```json
{
  "tenantId": "popeyes-miraflores",
  "customerId": "rappi-customer-xyz",
  "customerName": "Lucía Vargas",
  "items": [
    { "productId": "prd-xxxx", "name": "Combo 2 piezas", "price": 23.9, "quantity": 1 }
  ],
  "total": 23.9,
  "deliveryAddress": "Av. Javier Prado 1234, San Isidro",
  "paymentMethod": "TARJETA",
  "externalOrderId": "RAPPI-AB12CD"
}
```

- **`tenantId` is now a sede, not a brand** — must be one of `popeyes-miraflores`, `popeyes-surco`, `popeyes-barranco` (see [[popeyes-backend]] for the multi-tenancy model). If omitted, falls back to `config.DEFAULT_TENANT_ID` (`popeyes-miraflores`).
- There is no `storeId` field anymore — it was retired along with the old "1 tenant = multiple stores" model.
- `externalOrderId` is **required** (400 if missing) — it's the only link Rappi has back to its own order after this call, since it never sees Popeyes's internal `orderId` again except in this response.
- `customerId` falls back to `"rappi-customer"`.
- `origin` is set to `"RAPPI"` server-side — not accepted from the payload.

## Response — 201 Created

```json
{
  "success": true,
  "data": {
    "orderId": "ord-lx9k2a-1234",
    "tenantId": "popeyes-miraflores",
    "customerId": "rappi-customer-xyz",
    "customerName": "Lucía Vargas",
    "origin": "RAPPI",
    "externalOrderId": "RAPPI-AB12CD",
    "items": [...],
    "total": 23.9,
    "status": "ORDER_CREATED",
    "deliveryAddress": "...",
    "paymentMethod": "TARJETA",
    "createdAt": "...",
    "updatedAt": "...",
    "completedAt": null
  }
}
```

## Status check — `GET /orders/{orderId}`

Requires the same `x-api-key`. Response: same shape as the 201 body above. `GET /tasks/rappi` (see the flow diagram) is the alternative/complementary way to check *task-level* progress rather than just order status.

## Status webhook back to GCP — `notifyRappiStatus`

Every time `updateOrderStatus` runs (a worker advances a stage, OR Rappi itself completes `CONFIRM_RECEPTION` via step 3 above), the Lambda `notifyRappiStatus` is triggered by EventBridge (pattern: `source: popeyes.workflow`, `detail-type: OrderStatusChanged`, bus `popeyes-orders-bus-${stage}`). That Lambda POSTs to `RAPPI_STATUS_API_URL` with:

```json
{
  "orderId": "ord-...",
  "externalOrderId": "RAPPI-AB12CD",
  "tenantId": "popeyes-miraflores",
  "status": "COOKED",
  "timestamp": "..."
}
```

If `RAPPI_STATUS_API_URL` is empty, the Lambda **does nothing** (does not fail). This is intentional so local/dev testing works without a live GCP webhook receiver. **As of the last session this env var is empty in the deployed stack** — the AWS→GCP direction of this integration is defined but not actually wired to a real GCP endpoint yet. No auth/secret is sent on this outbound call (`Content-Type: application/json` only) — whatever GCP endpoint eventually receives it needs its own protection scheme (shared secret in header/body, IP allowlist, etc.), since nothing here authenticates AWS to GCP.

## Setting values in the Rappi simulator

Get the API Gateway URL with `npx serverless info --stage dev3` (currently `https://lzlfyhmww8.execute-api.us-east-1.amazonaws.com`) and the `RAPPI_API_KEY` from `.env`. Configure both in the simulator's config, and configure `RAPPI_STATUS_API_URL` on the AWS side to point at whatever the GCP receiver's real URL is once it exists.

## What the backend does NOT do

- It does not authenticate `customerId` (Rappi passes it as-is).
- It does not verify that the items exist in the products table (it trusts the payload).
- It does not call back to GCP if `RAPPI_STATUS_API_URL` is empty.
- It does not retry failed status webhooks (one-shot; manual recovery needed).
- It does not restrict which stage Rappi can complete via `POST /tasks/{taskId}/complete` — the endpoint trusts the caller with a valid `x-api-key` to complete any pending task in the tenant, not just `CONFIRM_RECEPTION`.

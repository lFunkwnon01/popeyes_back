---
name: popeyes-backend
description: Backend serverless de Popeyes (AWS + Python 3.11 + FastAPI + Mangum + DynamoDB + EventBridge + Step Functions). Use ONLY when working on this repo's serverless.yml, src/functions/* Python handlers, or the AWS resources it creates.
---

# Popeyes Backend — serverless order management

Single Serverless Framework v3 service that deploys the entire Popeyes order management backend to AWS. No microservices, no separate stacks — one `serverless.yml` is the source of truth.

## Stack

- **Runtime**: Python 3.11 (Lambda). On the original dev machine this was mise-installed at `/home/lFunknown/.local/share/mise/installs/python/3.11/bin/python3.11` — on a new machine, point `pythonBin` at whatever local Python 3.11 install exists instead.
- **Plugin**: `serverless-python-requirements` with `pythonBin` pointing to that 3.11 path
- **HTTP layer**: AWS HTTP API (`httpApi:`) with custom Lambda authorizer (NOT Cognito)
- **Auth**: Custom JWT via PyJWT + bcrypt. Authorizer reads `request.scope["aws.event"]["requestContext"]["authorizer"]`. Do not switch to request `headers` only.
- **Persistence**: DynamoDB (6 tables, on-demand). Multi-tenant: `tenantId` is partition key for stores/products/orders/tasks/events.
- **Events**: EventBridge bus `popeyes-orders-bus-${stage}`. Detail-type `OrderStatusChanged` is what `notifyRappiStatus` listens to.
- **Workflow**: AWS Step Functions with `waitForTaskToken` pattern (5 human-task stages).
- **Storage**: S3 bucket `popeyes-assets-${stage}-${accountId}` for product images.

## Functions (12 total)

| Function | Trigger | Path |
|----------|---------|------|
| `authorizer` | HTTP API authorizer (JWT) | — |
| `health` | HTTP GET | `/health` |
| `auth` | HTTP | `/auth/register`, `/auth/login`, `/auth/me` |
| `catalog` | HTTP (JWT) | `/products`, `/stores` |
| `orders` | HTTP (JWT for `/orders`, x-api-key for `/orders/rappi`) | `/orders`, `/orders/rappi`, `/orders/{id}` |
| `tasks` | HTTP (JWT) | `/tasks`, `/tasks/{taskId}/complete` |
| `dashboard` | HTTP (JWT) | `/dashboard/summary` |
| `adminSeed` | HTTP (JWT, ADMIN only) | `/admin/seed` |
| `createHumanTask` | Step Functions (waitForTaskToken) | — |
| `updateOrderStatus` | Step Functions | — |
| `closeOrder` | Step Functions | — |
| `notifyRappiStatus` | EventBridge pattern `source=popeyes.workflow` + `detail-type=OrderStatusChanged` | — |

## Domain model (DynamoDB)

- `popeyes-users-{stage}` — PK: `userId`, GSI `email-index`
- `popeyes-stores-{stage}` — PK: `tenantId`, SK: `storeId`
- `popeyes-products-{stage}` — PK: `tenantId`, SK: `productId`
- `popeyes-orders-{stage}` — PK: `tenantId`, SK: `orderId`
- `popeyes-workflow-tasks-{stage}` — PK: `tenantId`, SK: `taskId`, GSI `orderId-index`
- `popeyes-order-events-{stage}` — PK: `tenantId`, SK: `eventId`, GSI `orderId-index`

## Key conventions

- **First-user-becomes-admin**: `/auth/register` honors the requested role only if no ADMIN exists. After that, public registration is forced to `CLIENT`.
- **Seed is manual**: After first deploy, create/login an ADMIN, then `POST /admin/seed` to populate the demo store, products, and example users.
- **Rappi is external-only**: This repo does NOT deploy GCP resources. It only defines the integration contract: `/orders/rappi` validates `x-api-key` against `RAPPI_API_KEY`, and `notifyRappiStatus` calls `RAPPI_STATUS_API_URL`.
- **`states:SendTaskSuccess` on `*`**: Intentional. Step Functions task-token callbacks cannot be scoped to a specific resource in a practical way.
- **Order origin values**: backend uses `"WEB_POPEYES"` and `"RAPPI"` (not `"WEB"`). Update frontend code accordingly.

## Common commands

```bash
# Validate + package without deploying
npx serverless package --stage dev

# Deploy (creates CloudFormation stack)
npx serverless deploy --stage dev

# Get deployed endpoints
npx serverless info --stage dev

# Tail logs
npx serverless logs -f orders --stage dev --tail

# Remove everything
npx serverless remove --stage dev
```

## Required env vars (`.env`)

```
STAGE=dev
REGION=us-east-1
JWT_SECRET=<32-byte hex>
RAPPI_API_KEY=<shared with Rappi simulator>
RAPPI_STATUS_API_URL=<GCP webhook URL, or empty for local>
```

## Gotchas

- Lambda Authorizer in HTTP API requires `enableSimpleResponses: true` and `resultTtlInSeconds: 0` for non-cached behavior.
- CORS in `httpApi.cors` is per-route in HTTP API (NOT API Gateway v1). The YAML config sets it globally but per-route overrides are possible.
- The Step Functions state machine is **inline** as a CloudFormation resource. Renaming a function (e.g. `closeOrder` → `closeOrderLambda`) breaks the state machine unless the logical reference is updated.
- Deploys run against an **AWS Academy Lab** account. The Lab session's STS credentials expire and CloudFormation access can be revoked mid-session — if `npx serverless deploy` starts failing with access-denied on `cloudformation:DescribeStacks`, it's the lab session, not the code. Wait for the lab to refresh and retry.

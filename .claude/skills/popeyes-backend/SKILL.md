---
name: popeyes-backend
description: Backend serverless de Popeyes (AWS Academy Lab + Python 3.11 + FastAPI + Mangum + DynamoDB + EventBridge + Step Functions). Use ONLY when working on this repo's serverless.yml, src/functions/* Python handlers, or the AWS resources it creates.
---

# Popeyes Backend — serverless order management

Single Serverless Framework v3 service that deploys the entire Popeyes order management backend to AWS. No microservices, no separate stacks — one `serverless.yml` is the source of truth.

## Stack

- **Runtime**: Python 3.11 (Lambda). `pythonBin` in `serverless.yml` points at `C:/Users/ayala/AppData/Local/Programs/Python/Python311/python.exe` (Windows dev machine). Packaging forces `pipCmdExtraArgs: --platform manylinux2014_x86_64 --only-binary=:all:` because packaging from Windows for a Linux Lambda runtime needs precompiled wheels (native extensions like `pydantic-core` won't cross-compile otherwise).
- **Plugin**: `serverless-python-requirements` with `dockerizePip: false`.
- **HTTP layer**: AWS HTTP API (`httpApi:`) with custom Lambda authorizer (NOT Cognito), named `lambdaAuthorizer`.
- **Auth**: Custom JWT via PyJWT. Passwords hashed with **PBKDF2-HMAC-SHA256, 200k iterations** (`src/shared/auth.py`) — NOT bcrypt (switched because Lambda's AL2/glibc build didn't play well with bcrypt's native extension when packaging from Windows). Authorizer reads `request.scope["aws.event"]["requestContext"]["authorizer"]`.
- **Persistence**: DynamoDB (6 tables, on-demand).
- **Events**: EventBridge bus `popeyes-orders-bus-${stage}`. Detail-type `OrderStatusChanged` is what `notifyRappiStatus` listens to.
- **Workflow**: AWS Step Functions with `waitForTaskToken` pattern (5 human-task stages).
- **Storage**: S3 bucket `popeyes-assets-${stage}-${accountId}` for product images.
- **IAM**: deploys against an **AWS Academy Lab** account (`227165337884`). The lab does NOT allow `iam:CreateRole`, so every resource that needs a role (Lambda execution, the Step Functions state machine, the EventBridge→StepFunctions target) reuses the pre-existing `arn:aws:iam::227165337884:role/LabRole` instead of a custom role. Do not add `iam.role` statements expecting CloudFormation to create a role — it will fail.

## Multi-tenancy model: one tenant = one sede (IMPORTANT — changed from earlier versions)

`tenantId` **is** the restaurant location, not a franchise/brand. Valid values live in `config.TENANT_IDS`:

```python
TENANT_IDS = ["popeyes-miraflores", "popeyes-surco", "popeyes-barranco"]
DEFAULT_TENANT_ID = "popeyes-miraflores"
```

`storeId` is **no longer a business concept** — it was retired when the project moved from "1 tenant (brand) + N stores" to "1 tenant = 1 sede". It only survives as the *physical* DynamoDB sort key name on 2 tables (`storeId` on Stores, `storeIdProductId` on Products), always set equal to `tenantId` or `productId` respectively, just to satisfy the existing key schema without a migration. Never treat it as meaningful — always filter/scope by `tenantId` (the partition key).

**Tenant resolution rules** (`src/shared/permissions.py::resolve_tenant_id`):
- **ADMIN / RESTAURANT_WORKER / COOK / DISPATCHER / DELIVERY_DRIVER**: always have a fixed `tenantId` baked into their JWT (assigned at creation, one sede). Every scoped endpoint uses that — ignoring/rejecting a different `tenantId` if the caller tries to pass one (403).
- **CLIENT**: has **no fixed tenantId** — clients are global and pick a sede in the frontend. Every CLIENT-facing scoped endpoint (`GET /orders`, `GET /tasks`, `GET /products`) requires `tenantId` as a query param; there's no ambiguity resolution beyond that.
- **Anonymous / public browsing** (`get_current_user_or_anonymous`): used only by `GET /products` and `GET /stores` so unauthenticated users can browse a sede's menu before logging in.
- **`GET /stores`** is the one deliberate exception that scans **across all tenants** — it's the sede-picker screen, so by definition it can't be scoped to a single tenant yet.

## Functions (12 total)

| Function | Trigger | Path |
|----------|---------|------|
| `authorizer` | HTTP API authorizer (JWT) | — |
| `health` | HTTP GET | `/health` |
| `auth` | HTTP | `/auth/register`, `/auth/login`, `/auth/me` |
| `catalog` | HTTP (JWT for writes, public/anonymous for reads) | `/products` (GET/POST), `/products/{productId}` (PUT/DELETE), `/stores` (GET/POST), `/upload-url` (POST) |
| `orders` | HTTP (JWT for `/orders`, x-api-key for `/orders/rappi`) | `/orders`, `/orders/rappi`, `/orders/{id}` |
| `tasks` | HTTP (JWT for `/tasks`; dual auth — x-api-key OR JWT, checked manually — for `/complete` and `/rappi`) | `/tasks`, `/tasks/{taskId}/complete`, `/tasks/rappi` |
| `dashboard` | HTTP (JWT) | `/dashboard/summary` |
| `adminSeed` | HTTP (JWT, ADMIN only) | `/admin/seed`, `/admin/users` |
| `createHumanTask` | Step Functions (waitForTaskToken) | — |
| `updateOrderStatus` | Step Functions | — |
| `closeOrder` | Step Functions | — |
| `notifyRappiStatus` | EventBridge pattern `source=popeyes.workflow` + `detail-type=OrderStatusChanged` | — |

Note: `/tasks/{taskId}/complete` and `/tasks/rappi` do **not** have `lambdaAuthorizer` attached in `serverless.yml` — auth is validated by hand inside `tasks/handler.py` so the route can accept either a Popeyes-worker JWT or Rappi's `x-api-key`. See [[popeyes-workflow]].

## Domain model (DynamoDB)

- `popeyes-users-{stage}` — PK: `userId`, GSI `email-index`. `tenantId` field: fixed sede for non-CLIENT roles, `""` for CLIENT (global).
- `popeyes-stores-{stage}` — PK: `tenantId`, SK: `storeId` (== tenantId, vestigial).
- `popeyes-products-{stage}` — PK: `tenantId`, SK: `storeIdProductId` (== productId, vestigial).
- `popeyes-orders-{stage}` — PK: `tenantId`, SK: `orderId`.
- `popeyes-workflow-tasks-{stage}` — PK: `tenantId`, SK: `taskId`, GSI `orderId-index`.
- `popeyes-order-events-{stage}` — PK: `tenantId`, SK: `eventId`, GSI `orderId-index`.

All numeric fields (`price`, `total`) are stored as `Decimal`, never `float` — DynamoDB's boto3 client rejects native floats. Convert with the `_to_decimal` helpers already present in each handler; `response.py`'s `success_response_safe` handles serializing `Decimal` back out for JSON responses.

## Product image uploads (S3 presigned URLs)

`POST /upload-url` (ADMIN-only, JWT) generates a presigned S3 PUT URL so the frontend uploads image binaries directly to S3, bypassing Lambda. Flow: `POST /upload-url` → browser `PUT`s the file straight to the returned `uploadUrl` → `POST /products` with `imageUrl` set to the returned `publicUrl`.

- `object_key` is `assets/{tenantId}/{uuid}.{ext}` — scoped per sede, matching the bucket policy's `assets/*` prefix.
- The presigned URL is generated with a fixed `ContentType` param — the client's `PUT` request **must** send the exact same `Content-Type` header or S3 will reject it (SignatureDoesNotMatch).
- `AssetsBucket` has `BlockPublicPolicy: false` / `RestrictPublicBuckets: false` and a `AssetsBucketPublicReadPolicy` bucket policy granting anonymous `s3:GetObject` — but **only** under `assets/*`. `BlockPublicAcls`/`IgnorePublicAcls` stay `true`, so nothing can be made public via object ACLs, only via that one bucket policy prefix. Don't widen the `Resource` in that policy to the whole bucket.
- No IAM statement was added for `s3:PutObject`/`s3:GetObject` on `LabRole` — verified empirically (direct `boto3` calls against the bucket) that the lab's existing policies already grant broad S3 access. Also, since `provider.iam.role` in this file is a plain ARN string (externally-managed role), any sibling `iam.statements` block would be silently ineffective in Serverless Framework v3 — that syntax only applies when Serverless creates the role itself.

## Key conventions

- **First-user-becomes-admin**: `/auth/register` honors the requested role only if no ADMIN exists globally (scans all tenants). After that, public registration is forced to `CLIENT`.
- **Seed is manual and multi-tenant**: `POST /admin/seed` (any ADMIN, any sede) creates all 3 sedes, their products, and ~16 demo users (3 admins + 12 workers + 1 global client) in one idempotent call — it is a global bootstrap, not scoped to the caller's tenant.
- **`POST /admin/users`**: lets an ADMIN create a user (any role, including another ADMIN) inside their own sede. CLIENT users created this way get `tenantId: ""` (global) regardless of who creates them.
- **Rappi is external-only**: This repo does NOT deploy GCP resources. It only defines the integration contract. See [[popeyes-rappi-integration]].
- **Order origin values**: `"WEB_POPEYES"` and `"RAPPI"` (not `"WEB"`).
- **`states:SendTaskSuccess` on `*`**: intentional — task-token callbacks aren't practically resource-scopable.

## Common commands

```bash
# Validate + package without deploying
npx serverless package --stage dev3

# Deploy (creates CloudFormation stack)
npx serverless deploy --stage dev3

# Get deployed endpoints
npx serverless info --stage dev3

# Tail logs
npx serverless logs -f orders --stage dev3 --tail

# Remove everything
npx serverless remove --stage dev3
```

The active deployed stage is `dev3` (API Gateway: `https://lzlfyhmww8.execute-api.us-east-1.amazonaws.com`). `dev2` and `dev` are stale/obsolete stages from earlier iterations — don't assume they're current.

## Required env vars (`.env`)

```
STAGE=dev3
REGION=us-east-1
JWT_SECRET=<32-byte hex>
RAPPI_API_KEY=<shared with Rappi simulator>
RAPPI_STATUS_API_URL=<GCP webhook URL, or empty for local>
```

`RAPPI_API_KEY` is still the placeholder default (`change-this-rappi-key`) and `RAPPI_STATUS_API_URL` is empty as of the last session — the GCP side of the integration isn't wired up with real values yet.

## Gotchas

- Lambda Authorizer in HTTP API requires `enableSimpleResponses: true` and `resultTtlInSeconds: 0` for non-cached behavior.
- CORS in `httpApi.cors` is global for this service (not per-route) — allowed methods include `PUT`/`DELETE` (added when product edit/delete and task-complete-by-Rappi routes were introduced; forgetting to add a new HTTP verb here silently breaks the browser preflight while curl/Postman still work).
- The Step Functions state machine is **inline** as a CloudFormation resource. Renaming a function (e.g. `closeOrder` → `closeOrderLambda`) breaks the state machine unless the logical reference (`${CloseOrderLambdaFunction.Arn}`) is updated.
- **Removing an authorizer from a route in `serverless.yml` and redeploying can silently not take effect** — CloudFormation may report success without actually detaching the authorizer from the HTTP API route. If a route that should now accept `x-api-key`-only calls still 401s after deploy, check the actual route config via `apigatewayv2` (`get-routes`) and patch it directly (`update-route`) rather than assuming the YAML change was applied.
- Deploys run against an **AWS Academy Lab** account. The Lab session's STS credentials expire and CloudFormation/IAM access can be revoked mid-session — if `npx serverless deploy` starts failing with access-denied on `cloudformation:DescribeStacks` or similar, it's the lab session, not the code. Get fresh temporary credentials and retry.
- Do not try to create custom IAM roles/policies — the Lab blocks `iam:CreateRole`. Always reuse `LabRole`.

---
name: popeyes-workflow
description: Step Functions state machine for Popeyes order workflow (5-stage human-task pattern with waitForTaskToken), plus how Rappi (external, no JWT) completes tasks via x-api-key. Use ONLY when modifying the OrderWorkflowStateMachine in serverless.yml or the workflow/tasks Lambda handlers.
---

# Popeyes Order Workflow

The order lifecycle is a Step Functions state machine with 5 human-task stages. Each stage uses the **Wait for Callback with Task Token** pattern: a Lambda creates a pending task in DynamoDB and pauses; someone completes the task via `POST /tasks/{taskId}/complete` which calls `states:SendTaskSuccess` to resume the state machine.

## Stages (in order)

| # | Step name | Required role | Status emitted |
|---|-----------|---------------|-----------------|
| 1 | `RECEIVE_ORDER` | `RESTAURANT_WORKER` | `ORDER_RECEIVED` |
| 2 | `COOK_ORDER` | `COOK` | `COOKED` |
| 3 | `PACK_ORDER` | `DISPATCHER` | `PACKED` |
| 4 | `DELIVER_ORDER` | `DELIVERY_DRIVER` | `DELIVERED` |
| 5 | `CONFIRM_RECEPTION` | `CLIENT` | `COMPLETED` |

After `COMPLETED`, `CloseOrder` registers `completedAt` on the order.

## State machine shape (in `serverless.yml`)

For each stage there are **two states**:
1. `CreateTaskXxxOrder` — Task with `Resource: arn:aws:states:::lambda:invoke.waitForTaskToken` that calls `createHumanTask`
2. `UpdateStatusXxx` — Task with `Resource: arn:aws:states:::lambda:invoke` that calls `updateOrderStatus`

After `CloseOrder`, the execution ends (`"End": true`).

**IAM**: the state machine's `RoleArn` and the EventBridge rule's target `RoleArn` are both `arn:aws:iam::227165337884:role/LabRole` — reused, not created, because this deploys to an AWS Academy Lab account that blocks `iam:CreateRole`. See [[popeyes-backend]] for the full IAM story.

## How the wait-for-callback works

1. `orders` Lambda puts a new order in DynamoDB with `status: ORDER_CREATED` and emits `OrderCreated` to EventBridge (bus `popeyes-orders-bus-${stage}`).
2. `StartOrderWorkflowRule` (pattern: `source: popeyes.orders`, `detail-type: OrderCreated`) triggers `OrderWorkflowStateMachine`, with `InputPath: $.detail` so the execution input is just the event detail (`tenantId`, `orderId`, `origin`, `externalOrderId`).
3. First state (`CreateTaskReceiveOrder`) invokes `createHumanTask` with the task token. The Lambda persists a `WorkflowTask` with `status: PENDING` and the `taskToken` field. The state machine PAUSES.
4. When someone calls `POST /tasks/{taskId}/complete`, the `tasks` Lambda calls `states:SendTaskSuccess` with the persisted token, **unblocking** the state machine.
5. State machine moves to `UpdateStatusOrderReceived`, which invokes `updateOrderStatus`. This writes the new status to the order, emits `OrderStatusChanged` to EventBridge, and writes an `OrderEvent` row.
6. Next stage repeats from step 3.
7. Final `CloseOrder` Lambda stamps `completedAt` and execution ends.

## Who can complete a task — two auth paths (important)

`POST /tasks/{taskId}/complete` and `GET /tasks/rappi` have **no `lambdaAuthorizer`** attached in `serverless.yml` (unlike `GET /tasks`, which is normal-JWT-protected). Auth is validated by hand inside `src/functions/tasks/handler.py` because the route must accept two very different callers:

1. **`x-api-key` header == `RAPPI_API_KEY`** → external call from the Rappi/GCP side. No JWT, no role check (there's no Popeyes user to check a role against). Requires an explicit `tenantId` in the body/query since there's no user to resolve it from. `completedBy` is recorded as the literal string `"rappi-integration"`.
2. **`Authorization: Bearer <JWT>`** → normal Popeyes worker/admin/client flow. Decoded manually with `decode_token()` (the route has no authorizer context to read from `request.scope`, unlike other JWT-protected routes) and goes through the usual `user_can_access_task` role check.

`GET /tasks/rappi?tenantId=...&externalOrderId=...` exists so Rappi can **discover** its pending `taskId` (it only knows its own `externalOrderId`, not the internal `taskId`) before calling `/complete`. It looks up the order by `externalOrderId` (query on `tenantId` partition key + filter in memory — no GSI on `externalOrderId`, deliberately, given the low order volume of this project) then queries `WorkflowTasksTable`'s `orderId-index` GSI.

## Handler responsibilities

- `create_human_task.py` (entry: `lambda_handler`): expects `{taskToken, tenantId, orderId, origin, externalOrderId, stepName, requiredRole}`. Stores a `WorkflowTask` with `status: PENDING` and the task token. Returns a JSON-serializable object (Step Functions does not accept `bytes`).
- `update_order_status.py`: expects `{tenantId, orderId, origin, externalOrderId, stepName, status}`. Updates the order status, emits an EventBridge event, appends an `OrderEvent`. **This is the function that triggers `notifyRappiStatus` downstream via EventBridge.**
- `close_order.py`: expects `{tenantId, orderId, origin, externalOrderId}`. Sets `completedAt` on the order.
- `tasks/handler.py` (HTTP): exposes `GET /tasks` (JWT-only), `GET /tasks/rappi` (x-api-key-only, discovery), `POST /tasks/{taskId}/complete` (dual auth, see above).

## Critical invariants

- The CloudFormation logical IDs of the three workflow Lambdas are referenced by `${CreateHumanTaskLambdaFunction.Arn}` etc. **Renaming the function in `functions:` block breaks this** — the logical IDs auto-generate from the function name, so use the existing names or update the references.
- `states:SendTaskSuccess` permission is `Resource: "*"` in `LabRole`'s policy. This is by design (task-token callbacks are not resource-scopable in the same way as table/bus permissions).
- If the order's `origin === "RAPPI"`, `notifyRappiStatus` will POST status changes to `RAPPI_STATUS_API_URL`. As of the last session that env var is **empty**, so this webhook is a no-op in the current deployment — nothing fails, it just silently doesn't notify GCP.
- **This whole state machine was once deleted from the codebase** (a prior iteration assumed it needed custom IAM roles incompatible with the AWS Academy Lab) and had to be restored by pointing every role reference at `LabRole` instead. If order creation succeeds but no `WorkflowTask` ever appears and the order status never advances past `ORDER_CREATED`, check first whether `OrderWorkflowStateMachine`, `StartOrderWorkflowRule`, and the 3 workflow Lambdas are actually present in `serverless.yml` and deployed — don't assume the wiring is intact.

## Where the execution starts

The state machine is started indirectly: `orders/handler.py` (`POST /orders` and `POST /orders/rappi`) emits an `OrderCreated` event to EventBridge; `StartOrderWorkflowRule` is what actually calls `start_execution`. (Earlier versions started the execution directly from the Lambda via `ORDER_WORKFLOW_ARN` — that env var was removed to avoid a CloudFormation circular dependency between the state machine and the Lambda's environment block; EventBridge decouples the two.)

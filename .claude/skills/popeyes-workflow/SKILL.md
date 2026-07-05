---
name: popeyes-workflow
description: Step Functions state machine for Popeyes order workflow (5-stage human-task pattern with waitForTaskToken). Use ONLY when modifying the OrderWorkflowStateMachine in serverless.yml or the workflow/* Lambda handlers.
---

# Popeyes Order Workflow

The order lifecycle is a Step Functions state machine with 5 human-task stages. Each stage uses the **Wait for Callback with Task Token** pattern: a Lambda creates a pending task in DynamoDB and pauses; a human completes the task via `POST /tasks/{taskId}/complete` which calls `states:SendTaskSuccess` to resume the state machine.

## Stages (in order)

| # | Step name | Required role | Status emitted |
|---|-----------|---------------|----------------|
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

After `CloseOrder`, the execution ends (no `End: true` needed; it is the final state).

## How the wait-for-callback works

1. `orders` Lambda puts a new order in DynamoDB with `status: ORDER_CREATED` and **starts a Step Functions execution** (the order payload IS the state machine input).
2. First state (`CreateTaskReceiveOrder`) invokes `createHumanTask` with the task token. The Lambda persists a `WorkflowTask` with `status: PENDING` and the `taskToken` field. The state machine PAUSES.
3. When a worker calls `POST /tasks/{taskId}/complete`, the `tasks` Lambda calls `states:SendTaskSuccess` with the persisted token, **unblocking** the state machine.
4. State machine moves to `UpdateStatusOrderReceived`, which invokes `updateOrderStatus`. This writes the new status to the order, emits `OrderStatusChanged` to EventBridge, and writes an `OrderEvent` row.
5. Next stage repeats from step 2.
6. Final `CloseOrder` Lambda stamps `completedAt` and execution ends.

## Handler responsibilities

- `create_human_task.py` (entry: `lambda_handler`): expects `{taskToken, tenantId, storeId, orderId, stepName, requiredRole, ...}`. Stores a `WorkflowTask` with `status: PENDING` and the task token. Returns a JSON-serializable object (Step Functions does not accept `bytes`).
- `update_order_status.py`: expects `{tenantId, storeId, orderId, stepName, status, ...}`. Updates the order status, emits an EventBridge event, appends an `OrderEvent`. **This is the function that triggers `notifyRappiStatus` downstream via EventBridge.**
- `close_order.py`: expects `{tenantId, storeId, orderId}`. Sets `completedAt` on the order.
- `tasks/handler.py` (HTTP): exposes `POST /tasks/{taskId}/complete` to workers. Validates role, fetches the task token from the persisted `WorkflowTask`, calls `states:SendTaskSuccess`, marks the task `COMPLETED`.

## Critical invariants

- The CloudFormation logical IDs of the three workflow Lambdas are referenced by `${CreateHumanTaskLambdaFunction.Arn}` etc. **Renaming the function in `functions:` block breaks this** — the logical IDs auto-generate from the function name, so use the existing names or update the references.
- `states:SendTaskSuccess` permission is `Resource: "*"` in the IAM role. This is by design (task-token callbacks are not resource-scopable in the same way as table/bus permissions).
- If the order's `origin === "RAPPI"`, `notifyRappiStatus` will POST status changes to `RAPPI_STATUS_API_URL`. Set this env var to a real GCP Cloud Function URL or leave empty during local testing.

## Where the execution starts

The state machine is started from `orders/handler.py` (the `POST /orders` and `POST /orders/rappi` handlers) by calling `start_execution` on the state machine ARN passed in `ORDER_WORKFLOW_ARN`. The execution input is the order document with extra fields `origin` and `externalOrderId` so the state machine can pass them through every step.

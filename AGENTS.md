# Repo Notes

- This repo is a single Serverless Framework service for the whole backend. Source of truth is `serverless.yml`; it defines the HTTP API, Lambda authorizer, DynamoDB tables, EventBridge bus/rules, S3 bucket, and Step Functions state machine inline.
- Runtime split matters: deploy tooling is Node-based (`package.json`), but all application code is Python (`requirements.txt`, `src/`). Use `npm install` for Serverless and plugin dependencies before any `serverless` command.
- HTTP endpoints are grouped by domain into separate FastAPI + Mangum handlers under `src/functions/*/handler.py`. Keep route additions inside the matching domain Lambda instead of creating a new service unless the boundary changes.
- Workflow Lambdas live under `src/functions/workflow/` and are invoked by the inline state machine resource in `serverless.yml`. If you rename those functions, update the CloudFormation logical references inside `OrderWorkflowStateMachine`.
- Protected routes rely on the custom HTTP API Lambda authorizer in `src/functions/authorizer/handler.py`. Handler code reads user claims from `request.scope["aws.event"]["requestContext"]["authorizer"]`; preserve that shape if you change authorizer mode.
- `POST /auth/register` is also the bootstrap path for the first non-client user: if no ADMIN exists yet, the requested role is honored. After an ADMIN exists, public registration is forced back to `CLIENT`.
- Seed data is not automatic. Deploy first, create/login an admin, then call `POST /admin/seed` to create the demo store, products, and example users.
- The Rappi integration is intentionally external-only. `/orders/rappi` validates `x-api-key` against `RAPPI_API_KEY`, and `notify_rappi_status.py` calls `RAPPI_STATUS_API_URL`; nothing in this repo deploys GCP resources.
- `states:SendTaskSuccess` is granted on `*` by design because Step Functions task-token callbacks are not resource-scopable in the same practical way as table or bus permissions.
- Fast verification available without installing Python deps: `python -m compileall src`. Full packaging validation depends on running `npm install` first so local `serverless` and the Python requirements plugin exist.

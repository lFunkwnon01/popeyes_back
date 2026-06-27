from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError

from src.shared.response import error_response


def create_app(title):
    app = FastAPI(title=title)

    @app.exception_handler(HTTPException)
    async def handle_http_exception(_, exc):
        return error_response(exc.detail, exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_exception(_, exc):
        first_error = exc.errors()[0] if exc.errors() else {"msg": "Invalid request"}
        return error_response(first_error.get("msg", "Invalid request"), 422)

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(_, exc):
        return error_response(str(exc), 500)

    @app.middleware("http")
    async def normalize_empty_json_body(request: Request, call_next):
        return await call_next(request)

    return app

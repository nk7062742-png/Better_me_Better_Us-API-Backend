import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import json
 
from app.core.telemetry import log_error, log_request
from fastapi.openapi.utils import get_openapi
from app.routes.admin import router as admin_router
from app.routes.chat import router as chat_router
from app.routes.ingestion import router as ingestion_router
 
app = FastAPI()
app.include_router(chat_router)
app.include_router(ingestion_router)
app.include_router(admin_router)
 
 
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Lightweight request logging with latency."""
    from time import time
 
    start = time()
    response = await call_next(request)
    duration_ms = (time() - start) * 1000
    log_request(
        "http_request",
        {
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "latency_ms": round(duration_ms, 1),
            "client": request.client.host if request.client else None,
        },
    )
    return response
 
 
@app.exception_handler(Exception)
async def handle_exception(_: Request, exc: Exception):
    log_error("unhandled_exception", str(exc))
    show_debug = os.getenv("SHOW_DEBUG_ERRORS", "false").lower() == "true"
    if show_debug:
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
 
 
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title="BetterMe Backend",
        version="1.0.0",
        routes=app.routes,
    )
    schema.setdefault("components", {}).setdefault("securitySchemes", {}).update(
        {
            "AdminKey": {
                "type": "apiKey",
                "in": "header",
                "name": "x-admin-key",
            }
        }
    )
    for path in schema.get("paths", {}).values():
        for method in path.values():
            method.setdefault("security", [{"AdminKey": []}])
    app.openapi_schema = schema
    return app.openapi_schema
 
 
app.openapi = custom_openapi

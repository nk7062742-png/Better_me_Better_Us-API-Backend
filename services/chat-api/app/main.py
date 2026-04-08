import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.telemetry import log_error, log_request
try:
    from app.core.request_context import reset_current_user_id, set_current_user_id
except ModuleNotFoundError:  # Backward-compatible for deployments missing request_context module.
    def set_current_user_id(_user_id):
        return None

    def reset_current_user_id(_token):
        return None
from fastapi.openapi.utils import get_openapi
from app.routes.admin import router as admin_router
from app.routes.chat import router as chat_router
from app.routes.ingestion import router as ingestion_router
 

def _allowed_origins() -> list[str]:
    """
    Resolve allowed origins from env only.
    Avoid wildcard when credentials are allowed.
    """
    raw = os.getenv("CORS_ALLOW_ORIGINS", "")
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins


app = FastAPI()
cors_origins = _allowed_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(chat_router)
app.include_router(ingestion_router)
app.include_router(admin_router)
 
 
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Lightweight request logging with latency."""
    from time import time
 
    start = time()
    token = set_current_user_id(None)
    try:
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
    finally:
        reset_current_user_id(token)
 
 
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
    for path, methods in schema.get("paths", {}).items():
        if not path.startswith("/admin"):
            continue
        for method in methods.values():
            method.setdefault("security", [{"AdminKey": []}])
    app.openapi_schema = schema
    return app.openapi_schema
 
 
app.openapi = custom_openapi

"""DBA Workspace local server and built React application host."""
import io
import sys
import threading
import time
import uuid
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.config import settings
from backend.database import run_startup_migrations
from backend.file_visual_preview import VIEWER_ORIGIN, router as preview_file_router
from backend.auth import PUBLIC_API_PATHS, load_session, verify_csrf
from backend.errors import (error_response, http_exception_handler, unhandled_exception_handler,
                            validation_exception_handler)
from backend.observability import (logger, record_audit, request_id_var)
from backend.routers import (articles, auth, customers, dashboard, export_import,
                             launcher, resources, scan, scripts, search,
                             tasks, vault)

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR / "frontend_dist"

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize new databases and reject incompatible schemas on every entry."""
    run_startup_migrations()
    yield


app = FastAPI(title="DBA 工作台 API", version="0.5", lifespan=lifespan)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=list(settings.allowed_hosts),
    www_redirect=False,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "If-Match", "X-CSRF-Token", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("Content-Security-Policy", (
        "default-src 'self'; "
        "base-uri 'none'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "form-action 'self'; "
        "img-src 'self' data:; "
        f"frame-src {VIEWER_ORIGIN}; "
        "object-src 'none'; "
        "script-src 'self' 'wasm-unsafe-eval'; style-src 'self'"
    ))
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.middleware("http")
async def request_context(request: Request, call_next):
    """Attach a request ID, emit metadata-only logs, and audit state changes."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    response = None
    try:
        if request.url.path.startswith("/api/") and request.method != "OPTIONS":
            if request.url.path not in PUBLIC_API_PATHS:
                session = load_session(request)
                if not session:
                    response = error_response(
                        request,
                        status_code=401,
                        message="Authentication required",
                    )
                    return response
                request.state.session = session
                if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                    if not verify_csrf(session, request.headers.get("X-CSRF-Token")):
                        response = error_response(
                            request,
                            status_code=403,
                            message="Invalid CSRF token",
                            code="CSRF_FAILED",
                        )
                        return response
            elif request.method in {"POST", "PUT", "PATCH", "DELETE"}:
                origin = request.headers.get("Origin")
                same_origin = f"{request.url.scheme}://{request.headers.get('host', '')}"
                if origin and origin != same_origin and origin not in settings.cors_origins:
                    response = error_response(
                        request,
                        status_code=403,
                        message="Untrusted request origin",
                        code="ORIGIN_REJECTED",
                    )
                    return response
        response = await call_next(request)
        return response
    finally:
        status_code = response.status_code if response is not None else 500
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "request completed",
            extra={
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": duration_ms,
            },
        )
        if response is not None:
            response.headers["X-Request-ID"] = request_id
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith("/api/"):
            parts = [part for part in request.url.path.split("/") if part]
            object_type = parts[1] if len(parts) > 1 else "api"
            object_id = next((part for part in parts[2:] if part.isdigit()), "")
            if status_code < 400:
                result = "success"
            elif status_code in {401, 403}:
                result = "denied"
            else:
                result = "failed"
            try:
                audit_session = getattr(request.state, "session", None)
                record_audit(
                    request_id=request_id,
                    action=request.method.lower(),
                    object_type=object_type,
                    object_id=object_id,
                    result=result,
                    source=request.client.host if request.client else "unknown",
                    actor=(
                        audit_session.get("username", "local-user")
                        if isinstance(audit_session, dict)
                        else "local-user"
                    ),
                )
            except Exception:
                logger.error(
                    "audit write failed",
                    extra={"event": "audit_error", "request_id": request_id},
                )
        request_id_var.reset(token)

# Register routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(scripts.router, prefix="/api/scripts", tags=["scripts"])
app.include_router(articles.router, prefix="/api/articles", tags=["articles"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(export_import.router, prefix="/api/export", tags=["export"])
app.include_router(customers.router, prefix="/api/customers", tags=["customers"])
app.include_router(resources.router, prefix="/api/resources", tags=["resources"])
app.include_router(vault.router, prefix="/api/vault", tags=["vault"])
app.include_router(launcher.router, prefix="/api/launcher", tags=["launcher"])
app.include_router(scan.router, prefix="/api/scan", tags=["scan"])
app.include_router(preview_file_router, prefix="/preview-file", tags=["file-preview"])


@app.get("/")
async def index():
    """Serve the built React application."""
    built_index = FRONTEND_DIR / "index.html"
    if built_index.exists():
        return Response(content=built_index.read_bytes(), media_type="text/html; charset=utf-8")
    return Response(
        content="Frontend build is missing. Run npm install and npm run build in frontend/.",
        status_code=503,
        media_type="text/plain; charset=utf-8",
    )


app.mount(
    "/app-assets",
    StaticFiles(directory=str(FRONTEND_DIR), check_dir=False),
    name="app-assets",
)


@app.get("/{frontend_path}")
async def frontend_fallback(frontend_path: str):
    """Let BrowserRouter handle the one-segment UI routes."""
    return await index()


def open_browser():
    time.sleep(1.5)
    webbrowser.open(f"http://localhost:{settings.port}")


if __name__ == "__main__":
    if sys.stdout is not None and hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if sys.stderr is not None and hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    print("=" * 50)
    print("  DBA Workspace Server v0.5")
    print(f"  Mode: {settings.mode}")
    print(f"  http://localhost:{settings.port}")
    print("  Press Ctrl+C to stop")
    print("=" * 50)

    if settings.open_browser:
        threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(
        "main:app" if settings.reload else app,
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level="info",
    )

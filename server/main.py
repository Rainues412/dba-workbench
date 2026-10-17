"""DBA Workspace Server - API backend for ops-workbench.html.

Run:  python main.py
API at http://localhost:8686 (serves this directory's ops-workbench.html at /)

The frontend is a single static HTML file; this server only provides the
REST API it talks to. UI lives in ../ops-workbench.html and is served as-is.
"""
import io
import sys
import threading
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.config import settings
from backend.database import run_startup_migrations
from backend.routers import (articles, customers, dashboard, export_import,
                             launcher, resources, scan, scripts, search,
                             tasks, vault)

BASE_DIR = Path(__file__).parent
HTML_FILE = BASE_DIR.parent / "ops-workbench.html"

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
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Content-Type"],
)

# Register routers
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


@app.get("/")
async def index():
    """Serve the single-file frontend.

    The file on disk (and in git, and published on workbuddy.link) stays
    byte-for-byte unchanged. Only when served by this API server do we
    append the bridge script that switches the page's data layer from
    localStorage to the REST API. Opening the file directly (or the
    published URL) keeps the original localStorage behaviour.
    """
    html = HTML_FILE.read_bytes()
    bridge = b'<script src="/static/workbench.js"></script>\n</body>'
    html = html.replace(b'</body>', bridge, 1)
    return Response(content=html, media_type="text/html; charset=utf-8")


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def open_browser():
    import time
    time.sleep(1.5)
    webbrowser.open(f"http://localhost:{settings.port}")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    print("=" * 50)
    print("  DBA Workspace Server v0.5")
    print(f"  Mode: {settings.mode}")
    print(f"  http://localhost:{settings.port}")
    print("  Press Ctrl+C to stop")
    print("=" * 50)

    if settings.open_browser:
        threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level="info",
    )

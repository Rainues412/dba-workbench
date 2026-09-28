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
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.database import init_db
from backend.routers import (articles, customers, dashboard, export_import,
                             launcher, resources, scan, scripts, search,
                             tasks, vault)

BASE_DIR = Path(__file__).parent
HTML_FILE = BASE_DIR.parent / "ops-workbench.html"

app = FastAPI(title="DBA 工作台 API", version="0.3")

# CORS：发布在 workbuddy 的桥接版页面需要从浏览器调用本机 API。
# 公网页实际以 iframe 形式加载，iframe 的 origin 是静态资源域
# workbuddy-space-static.codebuddy.work（不是 workbuddy.link），
# 三个 origin 都要放行，否则桥接脚本被 CORS 拦截、降级到空 localStorage。
# 仅放开 GET/POST/PUT/DELETE/OPTIONS 与 JSON 头；服务仍绑定 127.0.0.1，
# 外部设备不可达，因此该配置只影响"本机浏览器访问公网页"这一场景。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://workbuddy.link",
        "https://www.workbuddy.link",
        "https://www.workbuddy.cn",
        "https://workbuddy-space-static.codebuddy.work",
    ],
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
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

TLS_DIR = BASE_DIR / "tls"


@app.get("/trust")
def trust_cert():
    """Serve the self-signed localhost certificate for manual inspection/import."""
    return FileResponse(str(TLS_DIR / "localhost-cert.cer"),
                        media_type="application/pkix-cert")


@app.get("/trust-guide")
def trust_guide():
    return Response(content="""<html><body style="font-family:sans-serif;max-width:640px;margin:40px auto">
<h2>信任 localhost 自签证书</h2>
<p>公网发布页（workbuddy CSP 只放行 https）需要通过 <code>https://localhost:8687</code>
访问本机 API。证书已随服务生成，安装一次即可：</p>
<pre>powershell Import-Certificate -FilePath tls\\localhost-cert.cer -CertStoreLocation Cert:\\CurrentUser\\Root</pre>
<p>或直接下载 <a href="/trust">localhost-cert.cer</a> 后双击 → 安装到
「当前用户 → 受信任的根证书颁发机构」。</p>
<p>卸载：<code>powershell Get-ChildItem Cert:\\CurrentUser\\Root | Where Subject -eq 'CN=localhost' | Remove-Item</code></p>
</body></html>""", media_type="text/html; charset=utf-8")


def open_browser():
    import time
    time.sleep(1.5)
    webbrowser.open("http://localhost:8686")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    print("=" * 50)
    print("  DBA Workspace Server v0.4")
    print("  http://localhost:8686   (本地 / file:// 场景)")
    print("  https://localhost:8687  (公网发布页 iframe 场景，自签证书)")
    print("  Press Ctrl+C to stop")
    print("=" * 50)

    init_db()

    threading.Thread(target=open_browser, daemon=True).start()

    # HTTPS 实例：workbuddy 发布页的 CSP（connect-src 'self' blob: https:）
    # 禁止 https 页面请求明文 http，公网 iframe 里的桥接脚本必须走 https。
    cert, key = TLS_DIR / "localhost-cert.pem", TLS_DIR / "localhost-key.pem"
    if cert.exists() and key.exists():
        def run_tls():
            uvicorn.run(
                app, host="127.0.0.1", port=8687,
                ssl_certfile=str(cert), ssl_keyfile=str(key),
                log_level="warning",
            )
        threading.Thread(target=run_tls, daemon=True).start()
    else:
        print("  [warn] tls/ 证书缺失，跳过 https://localhost:8687")

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8686,
        reload=True,
        log_level="info",
    )

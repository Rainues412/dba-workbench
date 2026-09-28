"""Regenerate server/publish.html = 纯净 UI 壳 + 内联桥接脚本。

为什么要单独生成发布件：
- workbuddy 资料库只服务单个 HTML 文件，没有 /static 路由，
  所以发布版必须把 workbench.js **内联**（本地 :8686 版用 <script src> 注入）
- 桥接脚本在 https 上下文（公网 iframe）自动切到 https://localhost:8687，
  因为发布页的 CSP 是 connect-src 'self' blob: https:（平台固定），
  明文 http 的 localhost 会被拦

用法：
    python make_publish.py
然后按 README「修改与发布」导入并发布 publish.html（带 --node-block-id）。

注意：ops-workbench.html 本身保持纯净（不含桥接），是 UI/git 的唯一事实源。
"""
from pathlib import Path

BASE = Path(__file__).parent
html = (BASE.parent / "ops-workbench.html").read_bytes()
js = (BASE / "static" / "workbench.js").read_bytes()

assert b"</body>" in html, "ops-workbench.html 结构变化：找不到 </body>"
out = html.replace(b"</body>", b"<script>\n" + js + b"\n</script>\n</body>", 1)
(BASE / "publish.html").write_bytes(out)
print(f"publish.html written: {len(out)} bytes (html {len(html)} + bridge {len(js)})")

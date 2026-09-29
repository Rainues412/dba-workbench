# DBA 工作台

个人 DBA 运维工作台，单文件前端 + FastAPI 后端 + SQLite 数据层。
管理脚本库、知识库、安装包、任务排期、客户通讯录等运维资源。

- **GitHub**：https://github.com/Rainues412/dba-workbench （private，源码备份）
- **前端**：`ops-workbench.html`（CSS/JS 全内联，零外部依赖）

## 快速开始

```bash
# 1. 安装依赖
cd server
pip install -r requirements.txt

# 2. 启动服务（自动打开浏览器）
python main.py
```

服务启动后访问 http://localhost:8686

> **依赖**：Python 3.8+，`fastapi` / `uvicorn` / `cryptography`（见 `server/requirements.txt`）

## 项目架构

```
D:\coding\workspace\
├── ops-workbench.html            单文件前端（CSS/JS 全内联）
├── README.md
├── .gitignore / .gitattributes
├── server/                       FastAPI 后端
│   ├── main.py                   入口 :8686（绑 127.0.0.1）
│   ├── requirements.txt          Python 依赖
│   ├── workspace.db              SQLite 数据库（git 忽略）
│   ├── .workspace_secret         Fernet 密钥（git 忽略）
│   ├── static/
│   │   └── workbench.js          数据层桥接：劫持 gd()/sd()，读写走 REST API
│   └── backend/
│       ├── database.py           SQLite 建表 + 迁移 + 连接管理
│       └── routers/              11 个路由模块
│           ├── dashboard.py      统计/待办/收藏/最近文档
│           ├── scripts.py        脚本库 CRUD + 版本管理
│           ├── articles.py       知识库 CRUD + 浏览计数
│           ├── resources.py      安装包索引 CRUD
│           ├── tasks.py          任务排期 CRUD + 状态流转
│           ├── customers.py      客户/联系人/沟通记录
│           ├── vault.py          密码本（Fernet 加密）
│           ├── launcher.py       打开本地文件/目录/URL
│           ├── scan.py           扫描目录配置 + 文件入库
│           ├── search.py         全局搜索
│           └── export_import.py  JSON 导出导入
└── import_scripts.py             脚本批量导入工具
```

### 技术栈

| 层级 | 技术 | 说明 |
|---|---|---|
| 前端 | 原生 HTML/CSS/JS | 单文件，零构建，零外部依赖 |
| 数据桥接 | `workbench.js` | 劫持页面 gd()/sd()，读写改走 REST API |
| 后端 | FastAPI + Uvicorn | 11 个路由模块，JSON API |
| 存储 | SQLite (WAL) | 本地文件数据库，PRAGMA foreign_keys ON |
| 加密 | Fernet (AES-128-CBC + HMAC) | 密码本模块，密钥存 `.workspace_secret` |

### 数据流

```
页面 render*() ──读──> gd(key) ──> [API 模式] 内存 cache（pull 自 REST API）
                                └─> [回退模式] localStorage
页面 sd(key, data) ─写─> [API 模式] cache + 400ms 防抖 → 全量对账推送
                                （删服务端多余 + 逐条 upsert）→ SQLite
                        └─> [回退模式] localStorage
```

- 6 个集合中 5 个走 SQLite：scripts / knowledge / installers / tasks / contacts
- **accounts（账号保险箱）始终留在 localStorage**：明文密码不进 API、不上云

### API 路由一览（前缀 `/api`）

| 路由 | 用途 |
|---|---|
| `dashboard` | 统计数 / 待办 / 收藏 / 最近文档 |
| `scripts` | 脚本库 CRUD（支持 db_type + wb_type 二级筛选） |
| `articles` | 知识库 CRUD（支持 category 筛选） |
| `resources` | 安装包索引 CRUD |
| `tasks` | 任务排期 CRUD（支持状态流转、逾期检测） |
| `customers` | 客户通讯录（含联系人与沟通记录子表） |
| `vault` | 密码本（Fernet 加密，前端未启用） |
| `launcher` | 打开本地文件/目录/URL |
| `scan` | 扫描目录 + 文件分类入库 |
| `search` | 全局搜索（跨 6 个模块） |
| `export` | JSON 导出 / 导入（含外键 ID 重映射） |

### 脚本库三级导航

```
第一层：数据库类型（Oracle / MySQL / PostgreSQL / SQL Server / Linux / Redis / 其他）
  └─ 第二层：脚本类型（巡检 / 备份 / 部署 / 监控 / 性能 / 其他）
       └─ 第三层：脚本列表（名称可点击直接打开文件）
```

面包屑导航支持任意层级直接跳转，无需逐层返回。

## 部署方式

### 本地开发（推荐）

```bash
cd server
pip install -r requirements.txt
python main.py
```

服务绑定 `127.0.0.1:8686`，仅本机可访问。启动后自动打开浏览器。

### 独立服务器部署

```bash
# 1. 克隆仓库并安装依赖
git clone <repo-url> && cd dba-workbench/server
pip install -r requirements.txt

# 2. 用 uvicorn 生产模式启动
uvicorn main:app --host 0.0.0.0 --port 8686

# 3. （可选）配合 Nginx 反向代理
```

**Nginx 配置示例：**

```nginx
server {
    listen 80;
    server_name dba.your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8686;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**⚠️ 部署到公网前必须：**
- 添加 API 认证（当前 API 无鉴权，仅靠绑定 `127.0.0.1` 防护）
- 启用 HTTPS（Nginx + Let's Encrypt 或其他证书）
- 修改 `workbench.js` 中的 `API_BASE` 为相对路径或域名

### 纯前端模式（无需后端）

双击 `ops-workbench.html` 直接在浏览器中打开，数据存储在 localStorage。
此模式下无持久化存储，不支持打开文件、扫描入库等后端功能。

## 数据导入方式

### 方式一：JSON 导入（从旧版本迁移）

在页面右上角 **设置** → **导入恢复** → 选择 JSON 文件。

JSON 格式示例：

```json
{
  "scripts": [
    {"name": "脚本名", "type": "巡检", "db": "Oracle", "path": "D:/scripts/...", "desc": "说明", "tags": ["标签1"]}
  ],
  "knowledge": [...],
  "installers": [...],
  "tasks": [...],
  "contacts": [...],
  "accounts": [...]
}
```

### 方式二：API 批量导入

```python
import requests

API = "http://localhost:8686"

# 导入单个脚本
requests.post(f"{API}/api/scripts", json={
    "title": "脚本名称",
    "description": "脚本说明",
    "db_type": "Oracle",       # 数据库类型
    "wb_type": "巡检",          # 脚本类型：巡检/备份/部署/监控/性能/其他
    "tags": "巡检,Oracle",
    "file_path": "D:/scripts/oracle/check.sql",
    "content": ""              # 只记录路径时留空
})

# 导入知识库文档
requests.post(f"{API}/api/articles", json={
    "title": "文档名称",
    "summary": "摘要",
    "content": "",
    "category": "排障手册",
    "tags": "Oracle,故障",
    "file_path": "D:/docs/oracle/troubleshooting.md"
})

# 导入安装包
requests.post(f"{API}/api/resources", json={
    "name": "oracle-19c.zip",
    "kind": "安装包",
    "path": "D:/installers/oracle/",
    "version": "19.3.0",
    "size_mb": 2900
})
```

### 方式三：扫描入库

配置扫描目录后，自动发现并分类文件：

```python
# 添加扫描目录
requests.post(f"{API}/api/scan/dirs", json={"path": "D:/Database"})

# 执行扫描（返回建议入库的文件列表）
result = requests.post(f"{API}/api/scan/run", json={}).json()

# 确认入库
requests.post(f"{API}/api/scan/commit", json={"items": result["items"]})
```

扫描规则：
- **安装包**：`.msi` `.exe` `.zip` `.7z` `.iso` `.tar.gz` 等 → 入库为 resource
- **文档**：`.md` `.pdf` `.doc` `.docx` `.txt` `.html` 等 → 入库为 article
- **脚本**：`.sh` `.py` `.ps1` `.bat` `.cmd` `.sql` → 入库为 script（自动读取内容）
- 已入库的路径不会重复导入

### 方式四：脚本批量导入工具

仓库中提供了 `import_scripts.py`，可批量导入指定路径的脚本：

```bash
cd D:\coding\workspace
python import_scripts.py
```

修改脚本中的 `SCRIPTS_TO_IMPORT` 列表即可自定义导入内容。

### 数据库文件迁移

直接拷贝 `server/workspace.db`（和 `.workspace_secret`，若启用密码本）到新机器即可。

## 模块说明

| 模块 | 功能 |
|---|---|
| 仪表盘 | 统计总览、待办任务、数据库类型分布 |
| 脚本库 | 三级导航管理运维脚本（按数据库+类型分类） |
| 知识库 | 技术文档管理（排障/规范/架构/调优/迁移） |
| 安装包 | 软件/工具安装包索引 |
| 任务排期 | 任务管理（优先级/截止日期/逾期检测） |
| 客户通讯录 | 客户信息、联系人、沟通记录 |
| 账号保险箱 | 密码管理（localStorage，PIN 保护） |

## 安全说明

- API 仅绑定 `127.0.0.1`，无鉴权——**不要暴露到公网**
- 账号保险箱密码只在本机浏览器 localStorage，PIN 校验在前端
- `server/workspace.db` 和 `.workspace_secret` 均被 git 忽略
- 含真实密码的导出 JSON 勿外传

# DBA 工作台

本机单用户 DBA 运维工作台，用于管理脚本、知识文章、安装资源、任务、客户资料和客户端加密保险箱。前端采用 React + TypeScript，后端采用 FastAPI，数据保存在项目内的 SQLite 数据库。

> 当前版本只支持 Windows 本机回环访问（`127.0.0.1` / `localhost`），不是局域网或公网部署版本。

## 部署与启动

运行需要 Windows 10/11 x64 与 Python 3.12；仅重新构建前端时需要 Node.js。

以下命令均从仓库根目录执行，项目可以位于任意本地磁盘和任意目录，不要求固定为 `D:\coding\workspace`。

```powershell
# 1. 克隆后进入仓库；也可以直接复制完整项目目录
git clone https://github.com/Rainues412/dba-workbench.git
Set-Location .\dba-workbench

# 2. 创建项目内的 Python 环境并安装后端依赖
py -3.12 -m venv .runtime\.venv
.\.runtime\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.runtime\.venv\Scripts\python.exe -m pip install -r server\requirements.txt

# 3. 启动
.\.runtime\.venv\Scripts\python.exe server\main.py
```

访问 `http://127.0.0.1:8686/`。首次启动没有默认账号或密码，需要在页面创建第一个 Owner。数据库和保险箱恢复密钥会在首次使用相应功能时创建，均不会提交到 Git。

Windows 桌面启动方式：

```powershell
.\.runtime\.venv\Scripts\pythonw.exe tools\windows\launch_dba_workbench.py
```

启动器从自身位置定位项目，不依赖当前工作目录；日志默认写入 `.runtime\logs\server.log`。移动项目后，旧桌面快捷方式仍会指向旧位置，需要重新创建快捷方式。

### 重新构建前端

仅修改前端源码时需要 Node.js：

```powershell
Set-Location frontend
npm ci
npm run build
Set-Location ..
```

构建输出到 `server/frontend_dist`，由 FastAPI 与 API 同源提供。不要手工编辑构建后的 JS/CSS。

## 项目架构

```text
浏览器
  └─ React + TypeScript（frontend/src）
       └─ /api REST + Cookie/CSRF
            └─ FastAPI（server/main.py）
                 ├─ routers/               业务接口
                 ├─ auth.py                登录、会话、重新验证
                 ├─ local_capabilities.py  本机文件访问边界
                 ├─ migrations/            SQLite 前向迁移
                 ├─ admin.py               离线恢复命令
                 └─ workspace.db           本机业务数据
```

主要目录：

```text
frontend/                    React、TypeScript、Vite 源码与测试
server/frontend_dist/        已构建的生产前端
server/backend/              FastAPI 业务、安全与数据库代码
server/backend/routers/      按业务模块拆分的 REST API
server/backend/migrations/   有序 SQLite 迁移
server/tests/                后端与浏览器测试
tools/windows/               Windows 启动器
assets/                      桌面图标资源
.runtime/                    本机虚拟环境、日志和配置（Git 忽略）
```

列表接口统一分页；更新和删除通过 `revision` 检测并发冲突。启动时自动执行尚未应用的数据库迁移，高于程序支持版本的数据库会被拒绝打开。保险箱在浏览器端使用 Argon2id 与 AES-256-GCM 加解密，服务端只保存密文和密钥信封。

## 本机配置与可移植性

项目内部路径均由源码文件位置计算，部署目录不写死。Edge、编辑器和 Git Bash 通过环境变量或系统 `PATH` 查找：

| 环境变量 | 用途 |
| --- | --- |
| `DBA_HOST` / `DBA_PORT` | 监听地址和端口；地址只允许本机回环 |
| `DBA_OPEN_BROWSER` | 启动后是否自动打开浏览器 |
| `DBA_EDGE_PATH` | 可选，Edge 可执行文件路径 |
| `DBA_EDITOR` | 可选，首选编辑器命令或可执行文件路径 |
| `DBA_GIT_BASH` | 可选，执行获准 `.sh` 文件时使用的 Bash 路径 |
| `DBA_WORKBENCH_LOG_DIR` | Windows 启动器日志目录 |

脚本、知识文章和安装资源的原文件路径是业务数据，为防止越权访问，系统要求它们使用**绝对路径**。这类路径会随电脑和盘符变化：迁移到新电脑后，应复制原资料目录、更新允许根目录，并对失效记录重新扫描或编辑；程序不会擅自猜测或批量改写路径。

本机文件能力默认关闭。Windows 启动器可以读取不提交 Git 的 `.runtime\local-capabilities.json`：

```json
{
  "allowed_roots": ["X:\\DBA-Data", "X:\\DBA-Notes"],
  "allowed_actions": ["edit", "folder", "open", "scan", "pick-folder"]
}
```

请把示例盘符和目录替换成新电脑真实存在的绝对目录。不要加入 `run`，除非确实需要执行脚本并同时配置 `DBA_ALLOWED_RUN_EXTENSIONS`。UNC、相对路径、越界路径和符号链接逃逸会被拒绝。

## 数据迁移与备份

停止服务后迁移以下文件：

- `server/workspace.db`：业务数据、账号、会话元数据和保险箱密文。
- `server/.vault_recovery_private.pem` 与 `server/.vault_recovery_public.pem`：保险箱恢复密钥。
- 原脚本、知识文章和安装包目录：数据库只保存索引和路径，不会打包原文件。

恢复密钥备份目录必须是绝对路径，并且必须位于 `server` 数据目录之外：

```powershell
$backupDir = Read-Host "请输入项目 server 目录之外的绝对备份目录"
Push-Location server
..\.runtime\.venv\Scripts\python.exe -m backend.admin backup-recovery-key --output $backupDir
..\.runtime\.venv\Scripts\python.exe -m backend.admin verify-recovery-key
Pop-Location
```

恢复命令只能在服务器本机离线执行：

```powershell
$username = Read-Host "请输入用户名"
Push-Location server
..\.runtime\.venv\Scripts\python.exe -m backend.admin reset-login-password $username
..\.runtime\.venv\Scripts\python.exe -m backend.admin recover-vault $username
Pop-Location
```

数据库和恢复私钥同时遗失时，保险箱密文无法恢复。建议把恢复密钥副本与数据库分开存放，并使用操作系统磁盘加密保护。
迁移时不要复制旧电脑的 `.runtime\.venv` 或 `frontend\node_modules`，它们包含与原 Python、Node 和系统环境绑定的文件，应在新电脑按上述步骤重新创建。

## 验证

```powershell
.\.runtime\.venv\Scripts\python.exe -m pip install -r server\requirements-dev.txt
.\.runtime\.venv\Scripts\python.exe -m pytest

Set-Location frontend
npm ci
npm test -- --run
npm run build
```

测试使用项目内 `.runtime\pytest-temp` 和临时数据库，不读取或修改 `server/workspace.db`。

# DBA 工作台

本机单用户 DBA 运维工作台，用于管理脚本、知识文章、安装资源、任务、客户资料和客户端加密保险箱。前端采用 React + TypeScript，后端采用 FastAPI，数据保存在本机 SQLite 数据库。

> 当前版本只支持 Windows 本机回环访问（`127.0.0.1` / `localhost`），不是局域网或公网部署版本。

## 环境与版本要求

### 使用 EXE 安装程序（推荐）

[下载最新 Windows x64 安装版](https://github.com/Rainues412/dba-workbench/releases/latest)（安装程序仅作为 GitHub Release 附件发布，不存放在源码目录中）

| 依赖 | 要求 | 说明 |
| --- | --- | --- |
| 操作系统 | Windows 10/11 x64 | 打开本机文件、目录选择和桌面启动器依赖 Windows |
| Python | 不需要 | Python 运行时已编译进应用发行目录 |
| pip / venv | 不需要 | 仅从源码开发和重新打包时需要 |
| 浏览器 | Edge、Chrome 或其他现代浏览器 | Edge 可选，找不到时使用系统默认浏览器 |
| Node.js / npm | 不需要 | 仓库已包含 `server/frontend_dist` 生产前端 |

后端直接依赖已固定在 `server/requirements.txt`：

- FastAPI 0.115.0
- Uvicorn 0.30.6（含 standard 扩展）
- cryptography 43.0.1
- argon2-cffi 25.1.0
- Pillow 11.3.0
- pystray 0.19.5

将 `DBA工作台-安装程序-<版本>-x64.exe` 复制到新电脑并双击：

- 安装向导允许自行选择安装目录；默认安装到当前用户的 `%LOCALAPPDATA%\Programs\DBA 工作台`，不要求管理员权限。
- “创建桌面快捷方式”默认勾选，也可取消。
- 完成后可直接启动，目标机不需要安装 Python 或 Node.js。
- 运行期间会在 Windows 隐藏图标区域显示 DBA 工作台图标；关闭浏览器不会停止本机服务，需要右键托盘图标选择“退出”才能完整结束进程。
- 首次运行会在 `%LOCALAPPDATA%\DBA Workbench\data` 创建数据库和保险箱恢复密钥，日志位于同级 `logs` 目录；升级和卸载程序不会自动删除这些业务数据。
- 忘记保险箱主密码时，可在锁定页主密码框下点击“忘记密码”，使用登录密码和一次性本机验证码验证后重置。该流程依赖本机管理员恢复私钥；验证码用于限制自动化尝试，不等同于第二身份因素。
- 安装版使用“目录批量导入”时，点击“选择目录”会仅授权所选目录及其子目录；授权保存在同级 `local-capabilities.json`，重启后继续有效，不会开放整块磁盘或脚本执行权限。

安装程序目前没有商业代码签名证书，Windows SmartScreen 可能显示“未知发布者”。发布时应同时提供生成的 `.sha256` 文件用于完整性核验。Nuitka 编译能显著提高 Python 源码逆向成本，安装包不会包含 `.py`、`.ts`、`.tsx`、源码映射、Git 元数据、业务数据库或恢复密钥；浏览器端必须接收前端 JavaScript，因此不能承诺绝对不可逆。

### 从源码部署

从源码运行需要 Python **3.12.x x64**（当前验收版本 3.12.10）以及随 Python 安装的 pip/venv；目标机若只使用 EXE 安装程序则不需要这些依赖。

### 开发、测试或重新构建前端

| 依赖 | 要求 | 当前验收版本 |
| --- | --- | --- |
| Node.js | **22.12.0 以上**，推荐 24.x | 24.15.0 |
| npm | 随 Node.js 安装 | 11.12.1 |
| Python | 3.12.x x64 | 3.12.10 |

前端直接依赖版本由 `frontend/package.json` 与 `frontend/package-lock.json` 锁定：React 19.3.1、React Router 7.18.4、TanStack Query 5.104.4、Lucide React 1.59.0、hash-wasm 4.12.0；构建工具为 TypeScript 7.0.2、Vite 8.3.4、Vitest 5.0.5。测试依赖见 `server/requirements-dev.txt`：pytest 8.3.5、httpx 0.28.1、Playwright 1.48.0。

## 部署与启动

以下命令均从仓库根目录执行，项目可以位于任意本地磁盘和任意目录，不要求固定为 `D:\coding\workspace`。

```powershell
# 1. 克隆后进入仓库；也可以直接复制完整项目目录
git clone https://github.com/Rainues412/dba-workbench.git
Set-Location .\dba-workbench

# 2. 创建项目内的 Python 环境并安装后端依赖
py -3.12 -m venv .runtime\.venv
.\.runtime\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.runtime\.venv\Scripts\python.exe -m pip install -r server\requirements.txt

# 3. 以桌面模式启动（包含系统托盘图标与完整退出菜单）
.\.runtime\.venv\Scripts\pythonw.exe tools\windows\launch_dba_workbench.py
```

启动后会自动打开 `http://127.0.0.1:8686/`，并在 Windows 隐藏图标区域显示 DBA 工作台图标。关闭浏览器不会停止服务；右键托盘图标选择“退出”才会结束完整进程。首次启动没有默认账号或密码，需要在页面创建第一个 Owner。数据库和保险箱恢复密钥会在首次使用相应功能时创建，均不会提交到 Git。

`python server\main.py` 仅用于前台调试，不创建系统托盘图标。

### 生成 Windows 安装程序

构建机需要 Windows 10/11 x64、Python 3.12 x64 和网络连接。构建脚本固定使用 Nuitka 4.3.1，并从 Inno Setup 官方 GitHub Release 下载、校验和安装 Inno Setup 7.1.0 到源码目录之外。目标机不需要这些构建工具。

```powershell
.\packaging\windows\build-installer.ps1 -Version "1.0.4"
```

默认输出到仓库同级的 `DBA工作台-发布\installer`，最终只需分发其中的安装程序和同名 `.sha256` 文件；`.build` 是可删除的构建缓存。构建脚本拒绝把输出写进 Git 源码目录，并在打包前运行后端测试、扫描发行目录中的源码和业务数据。也可以通过 `-OutputDirectory` 指定其他源码目录之外的位置。

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
                 └─ workspace.db           本机业务数据（开发默认位置）
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
packaging/windows/           Nuitka 构建脚本与 Inno Setup 安装定义
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
| `DBA_DATA_DIR` | 可选，数据库和恢复密钥目录；安装版自动使用当前用户的 LocalAppData |
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

停止服务后迁移以下文件。源码模式默认位于 `server`，安装版默认位于 `%LOCALAPPDATA%\DBA Workbench\data`：

- `workspace.db`：业务数据、账号、会话元数据和保险箱密文。
- `.vault_recovery_private.pem` 与 `.vault_recovery_public.pem`：保险箱恢复密钥。
- 原脚本、知识文章和安装包目录：数据库只保存索引和路径，不会打包原文件。

恢复密钥备份目录必须是绝对路径，并且必须位于 `server` 数据目录之外：

```powershell
$backupDir = Read-Host "请输入项目 server 目录之外的绝对备份目录"
Push-Location server
..\.runtime\.venv\Scripts\python.exe -m backend.admin backup-recovery-key --output $backupDir
..\.runtime\.venv\Scripts\python.exe -m backend.admin verify-recovery-key
Pop-Location
```

保险箱锁定页已提供“忘记密码”入口；它会在后端使用本机管理员恢复私钥重新保护同一数据密钥，不会逐条解密或改写密码记录。登录密码、一次性验证码和恢复私钥缺一不可。管理员仍可在应用完全停止时使用以下离线命令应急恢复：

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

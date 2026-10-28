# DBA 工作台

本机单用户 DBA 运维工作台，用于管理脚本、知识文章、安装资源、任务、客户资料和客户端加密保险箱。前端采用 React + TypeScript，后端采用 FastAPI，数据保存在本机 SQLite 数据库。

> 当前版本只支持 Windows 本机回环访问（`127.0.0.1` / `localhost`），不是局域网或公网部署版本。

[下载最新版本](https://github.com/Rainues412/dba-workbench/releases/latest) · [更新日志](CHANGELOG.md) · [历史版本](https://github.com/Rainues412/dba-workbench/releases)

每个版本的新增、优化、修复和升级说明均在更新日志与对应 Release 中记录。下载时请选择 Windows x64 的 `DBA-Workbench-Setup-<版本>-x64.exe`，并用同名 `.sha256` 文件校验；GitHub 自动生成的 Source code 压缩包是源码，不能代替安装程序。

## 环境与版本要求

### 使用 EXE 安装程序（推荐）

[下载最新 Windows x64 安装版](https://github.com/Rainues412/dba-workbench/releases/latest)（安装程序仅作为 GitHub Release 附件发布，不存放在源码目录中）

| 依赖 | 要求 | 说明 |
| --- | --- | --- |
| 操作系统 | Windows 10/11 x64 | 打开本机文件、目录选择和桌面启动器依赖 Windows |
| Python | 不需要 | Python 运行时已编译进应用发行目录 |
| Java / Office | 不需要 | 安装包内置 Temurin JRE、kkFileView 和 LibreOffice Portable |
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
- 首次运行会在 `%LOCALAPPDATA%\DBA Workbench\data` 创建数据库和保险箱恢复密钥，日志位于同级 `logs` 目录。卸载 EXE 会询问是否同时删除全部应用数据，默认保留；只有明确选择“是”才会删除数据库、恢复密钥、日志和目录授权配置。
- 忘记保险箱主密码时，可在锁定页主密码框下点击“忘记密码”，使用登录密码和一次性本机验证码验证后重置。该流程依赖本机管理员恢复私钥；验证码用于限制自动化尝试，不等同于第二身份因素。
- 页面切回前台时自动同步会话及已过期的页面数据，已登录状态每分钟核对一次，不整页重载。保险箱刷新页面或闲置 5 分钟自动锁定，显示敏感操作验证倒计时，到期自动隐藏已展开的密码并提示重新验证；编辑窗口内可重新验证后继续保存，保留当前输入。
- 安装版使用“目录批量导入”时，点击“选择目录”会仅授权所选目录及其子目录；授权保存在同级 `local-capabilities.json`，重启后继续有效，不会开放整块磁盘或脚本执行权限。
- 知识库和脚本库的关联文件由内置 kkFileView 5.0.3 预览，覆盖 PDF、Office/WPS/ODF、图片、文本/代码、邮件、压缩包、音视频、CAD 等其支持的格式。Markdown 使用 Marked 与 DOMPurify 显示源文件中的图片及 GFM/HTML 表格。原文件只通过短时随机授权交给查看器；知识库仅展示源文件预览，已有文章正文保留在记录中。kkFileView 启动失败时，脚本库的文本类文件仍可使用原有只读正文回退。
- 本机安装 Microsoft Word 时，`.doc`、`.docx` 优先通过 Word 原生 PDF 导出保留图片、表格与分页；只读打开原文件、禁用宏及自动更新链接，结果保存在预览缓存。未安装 Word 时继续使用内置 LibreOffice。实现参考 [docx2pdf](https://github.com/AlJohri/docx2pdf) 的原生 Office 转换方式。

安装程序目前没有商业代码签名证书，Windows SmartScreen 可能显示“未知发布者”。发布时应同时提供生成的 `.sha256` 文件用于完整性核验。Nuitka 编译能显著提高 Python 源码逆向成本，安装包不会包含工作台的 `.py`、`.ts`、`.tsx`、源码映射、Git 元数据、业务数据库或恢复密钥；内置 LibreOffice 可能随其官方运行时携带脚本文件。浏览器端必须接收前端 JavaScript，因此不能承诺绝对不可逆。

### 从源码部署

从源码运行需要 Python **3.12.x x64**（当前验收版本 3.12.10）以及随 Python 安装的 pip/venv；目标机若只使用 EXE 安装程序则不需要这些依赖。

### 开发、测试或重新构建前端

| 依赖 | 要求 | 当前验收版本 |
| --- | --- | --- |
| Node.js | **22.12.0 以上**，推荐 24.x | 24.15.0 |
| npm | 随 Node.js 安装 | 11.12.1 |
| Python | 3.12.x x64 | 3.12.10 |

前端直接依赖版本由 `frontend/package.json` 与 `frontend/package-lock.json` 锁定：React 19.3.1、React Router 7.18.4、TanStack Query 5.104.4、Lucide React 1.59.0、hash-wasm 4.12.0、Marked 18.1.1、DOMPurify 3.4.17、react-resizable-panels 4.14.8、Screenfull 6.0.2、Tocbot 4.36.8、marked-gfm-heading-id 4.1.4、Motion 14.6.0、react-highlight-words 1.0.0、Downshift 9.4.0；构建工具为 TypeScript 7.0.2、Vite 8.3.4、Vitest 5.0.5。测试依赖见 `server/requirements-dev.txt`：pytest 8.3.5、httpx 0.28.1、Playwright 1.48.0。

## 部署与启动

以下命令均从仓库根目录执行，项目可以位于任意本地磁盘和任意目录，不要求固定为 `D:\coding\workspace`。

```powershell
# 1. 克隆后进入仓库；也可以直接复制完整项目目录
git clone --recurse-submodules https://github.com/Rainues412/dba-workbench.git
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

构建机需要 Windows 10/11 x64、Python 3.12 x64、已初始化的 Git 子模块和网络连接。构建脚本固定使用 Nuitka 4.3.1，并下载、校验固定版本的 Temurin 21、Maven 3.9.11 与 Inno Setup 7.1.0；kkFileView 固定为官方 v5.0.3 提交并从源码构建。目标机不需要这些构建工具。

```powershell
.\packaging\windows\build-installer.ps1 -Version "<major.minor.patch>"
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
                 ├─ file_visual_preview.py 文件短时授权与预览交接
                 └─ workspace.db           本机业务数据（开发默认位置）
       └─ kkFileView（独立回环侧车，LibreOffice 保留文档版式）
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
vendor/kkFileView/            官方 kkFileView v5.0.3 Git 子模块
assets/                      桌面图标资源
.runtime/                    本机虚拟环境、日志和配置（Git 忽略）
```

列表接口统一分页；更新和删除通过 `revision` 检测并发冲突。启动时自动执行尚未应用的数据库迁移，高于程序支持版本的数据库会被拒绝打开。保险箱在浏览器端使用 Argon2id 与 AES-256-GCM 加解密，服务端只保存密文和密钥信封。

## 任务保留与归档

任务管理中的已完成任务按创建时间从新到旧排列，同一创建时间按记录 ID 从大到小排列。未完成任务继续沿用逾期、状态、优先级和截止日期排序。

已完成任务自完成时间起保留 15 天，满 15 天后自动从普通列表移入“查看归档”中的独立列表，可以查看、编辑和恢复为待处理；通过“返回任务列表”回到普通列表。普通状态筛选只包含待处理、进行中、已完成。归档保留数据库中的完整记录，普通数据备份也包含归档任务。编辑任务不会重新计算保留期；恢复后再次完成则重新计时。页面打开时每分钟刷新一次，重新打开程序或切回窗口时也会重新读取归档结果。

升级会为缺少有效完成时间的历史已完成任务补记升级时间，让其保留完整 15 天。迁移只补记完成时间并递增这些记录的 revision，不改写正文、创建时间或状态。升级前请保留 SQLite 一致性备份；若需回退旧版本，应先停止应用并还原升级前数据库，旧版本会拒绝打开较新迁移版本的数据库。

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
| `DBA_FILE_VIEWER_PORT` | 内置文件查看器回环端口，安装版默认 `8012` |
| `DBA_FILE_VIEWER_HOME` | 源码调试时可选，指向已构建的 `file-viewer` 分发目录 |
| `DBA_FILE_VIEWER_DISABLED` | 可选，设为 `true` 时禁用 kkFileView，Markdown 预览和脚本文本回退仍可用 |

脚本、知识文章和安装资源的原文件路径是业务数据，为防止越权访问，系统要求它们使用**绝对路径**。这类路径会随电脑和盘符变化：迁移到新电脑后，应复制原资料目录、更新允许根目录，并对失效记录重新扫描或编辑；程序不会擅自猜测或批量改写路径。

本机文件能力默认关闭。Windows 启动器可以读取不提交 Git 的 `.runtime\local-capabilities.json`：

```json
{
  "allowed_roots": ["X:\\DBA-Data", "X:\\DBA-Notes"],
  "allowed_actions": ["edit", "folder", "open", "scan", "pick-folder"]
}
```

请把示例盘符和目录替换成新电脑真实存在的绝对目录。不要加入 `run`，除非确实需要执行脚本并同时配置 `DBA_ALLOWED_RUN_EXTENSIONS`。UNC、相对路径、越界路径和符号链接逃逸会被拒绝。

## 内置文件预览

知识库和脚本库在宽屏（至少 1400 CSS 像素）使用 [react-resizable-panels](https://github.com/bvaughn/react-resizable-panels)（MIT）调整文件列表与预览的宽度：拖动两栏之间的分隔条，或聚焦后按方向键微调，双击恢复均分。点击同一标题可展开或收起预览，点击其他标题直接切换文件；展开和收起使用约220毫秒过渡，再次展开恢复列表与预览各50%的默认比例，拖拽时即时调整，并遵循系统的减少动态效果设置。列表和预览分别保留 280px、340px 最小宽度；列表中的标题、操作按钮、标签和时间按实际栏宽排布。分类浏览独立收起或展开，宽度固定为 44px 或 176px，不参与拖拽。各模块在当前浏览器分别记住分类栏状态，筛选仍保留在 URL。切换数据库、分类、分页、搜索和收藏筛选只更新列表，保持当前预览及阅读位置；即使记录不在筛选结果中也可继续阅读。窄屏继续使用预览抽屉。打开原文件、打开所在目录和复制路径功能保留。

预览顶部使用紧凑工具区，文件内容占用剩余高度。通过 [Screenfull](https://github.com/sindresorhus/screenfull)（MIT）进入浏览器原生大屏阅读，按 Esc 或退出按钮返回，保持分栏比例、列表筛选与选中记录；切换大屏不重新加载已打开的文件。Markdown 正文在普通预览使用16px、大屏使用17px（窄屏16px），由 [Tocbot](https://github.com/tscanlin/tocbot)（MIT）生成分层目录、跟随阅读位置高亮。预览内容区实际宽度达到800px且文章有标题时，右侧自动显示220px目录栏；缩窄后隐藏，无标题时不占目录空间，普通分栏和大屏遵循相同规则；目录也可手动收起。章节锚点由 Marked 官方 [marked-gfm-heading-id](https://github.com/markedjs/marked-gfm-heading-id) 扩展生成，支持中文及重复标题；点击目录不改写模块筛选URL。Word/PDF继续使用内置查看器已有的文档目录/书签能力，没有源标题或书签时不自动识别或虚构章节。

知识库和脚本库不会自行解析或重绘 Office、PDF 等格式。安装包集成成熟开源项目 [kkFileView](https://github.com/kekingcn/kkFileView) v5.0.3（Apache-2.0），由它调用 LibreOffice Portable、PDF.js 和浏览器能力显示原文件。预览服务只监听 `127.0.0.1`，仅信任工作台回环来源，关闭上传、脚本预览和外部重定向，并使用每次启动随机生成的访问密钥。业务服务发出的文件地址带 30 分钟随机令牌，且每次读取都会重新检查允许目录和文件边界。

源码模式默认没有预编译的第三方运行包，因此可视化预览会提示查看器未启动。源码桌面启动器自动查找 `.runtime/file-viewer`，也可以通过 `DBA_FILE_VIEWER_HOME` 指向源码目录之外的运行包。`packaging/windows/build-file-viewer.ps1` 负责构建该运行包，安装构建脚本会把它一起打包。第三方许可和版本说明随安装目录的 `file-viewer` 一并交付。

PDF 预览默认收起缩略图侧栏，HTML 默认使用 kkFileView 自带的隔离沙箱显示版式。Word 文档在本机安装 Microsoft Word 时优先使用其原生只读 PDF 导出，其他情况通过内置 LibreOffice 转换；特殊字体、宏、加密文件和专有格式的效果取决于上游兼容性，快捷打开原文件和所在目录始终保留。

Markdown 复用 [Marked](https://github.com/markedjs/marked) 的 GFM 解析与 [DOMPurify](https://github.com/cure53/DOMPurify) 的 HTML 清理，支持管道表格、HTML 表格及 Typora 的 Markdown/HTML 图片引用，包括 JFIF 格式的 JPEG 图片。未编码空格的 Typora 图片路径通过 Marked 自带的兼容图片规则识别，表格与正文继续使用 GFM。独立的 `[TOC]` 目录标记由预览目录功能承接，不再作为正文显示；代码示例和正文中的标记照常保留。相对图片通过原文档的短时授权读取，仅允许文档目录及子目录中的图片，并逐次检查本机目录权限；不开放任意文件、父目录或网络路径。原 Markdown、图片和数据库正文均不会被重写；原图片已丢失或仍指向旧机器路径时，需要先恢复对应源文件。

`server/tests/test_visual_preview_browser.py` 是需要真实运行包的格式验收测试：将 `DBA_TEST_PREVIEW_SAMPLES` 指向包含 `sample.pdf/docx/pptx/txt/md/sql` 的验收样本目录后运行。它会自动启动隔离查看器，实际检查页面画布、正文和暗色窄屏截图；运行前先从托盘退出正式工作台，避免并行 LibreOffice 进程冲突。普通全量测试隔离外部查看器，不要求第三方运行包。

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

<div align="center">

<img src="assets/dba-workbench-icon.svg" alt="" width="72">

# DBA 工作台

面向数据库工程师的 Windows 本地工作台。

[下载安装](https://github.com/Rainues412/dba-workbench/releases/latest) · [功能概览](#功能概览) · [从源码运行](#从源码运行) · [问题反馈](https://github.com/Rainues412/dba-workbench/issues)

[![最新发布版本](https://img.shields.io/github/v/release/Rainues412/dba-workbench)](https://github.com/Rainues412/dba-workbench/releases/latest)
[![支持平台 Windows x64](https://img.shields.io/badge/platform-Windows%20x64-4c79c3)](#安装与使用)

</div>

## 为什么使用 DBA 工作台？

排障时经常要在脚本文件夹、交接文档和待办列表之间来回查找。DBA 工作台把运维脚本、技术资料、客户项目、任务和加密凭据集中到一个桌面应用，数据保存在本机 SQLite 数据库中。

## 界面预览

截图使用演示数据。

**工作台总览**可查看近期任务、资料统计和数据库类型分布。

![工作台总览，展示资产统计、近期任务和数据库类型分布](docs/screenshots/dashboard.png)

<details>
<summary>查看客户项目界面</summary>

![客户项目清单，展示群聊平台、多人负责人和职责标签](docs/screenshots/customer-projects.png)

</details>

## 功能概览

| 模块 | 可以做什么 |
| --- | --- |
| 脚本库 | 按数据库和用途整理运维脚本，筛选并预览脚本文本。 |
| 知识库 | 整理排障记录和技术文档，预览 PDF、Office 和 Markdown。Markdown 支持按目录跳转。 |
| 资源中心 | 集中管理安装包、工具和常用链接，支持从已授权的目录批量导入。 |
| 任务管理 | 设置截止日期和优先级，在工作台查看逾期与待办。已完成任务满 15 天后归档，可按需恢复。 |
| 客户项目 | 按客户展开项目，查看群聊及平台、负责人和职责标签。支持按客户名或项目名搜索，并在项目行直接编辑。 |
| 密码保险箱 | 用主密码解锁本地加密凭据，支持自动锁定、手动和自动备份，以及本机恢复和换机导入。 |

## 安装与使用

1. 从 [GitHub Releases](https://github.com/Rainues412/dba-workbench/releases/latest) 下载 `DBA-Workbench-Setup-<版本>-x64.exe` 及同名 `.sha256` 文件。用 PowerShell 的 `Get-FileHash -Algorithm SHA256` 核对安装包。
2. 在 Windows 10/11 x64 上双击 EXE 安装，安装包内置运行时和文件查看器。安装包未签名，Windows 可能提示发布者未知。
3. 从桌面快捷方式打开工作台。首次使用密码保险箱时，按页面提示设置主密码和密保问题。关闭窗口后默认可从桌面快捷方式或系统托盘重新打开。要停止服务，请在托盘菜单选择「退出」。

覆盖安装前先退出工作台并备份数据。卸载默认保留应用数据。安装版的功能以对应发布说明为准。

## 数据与隐私

- 工作台只通过本机地址访问。安装版的数据目录为 `%LOCALAPPDATA%\DBA Workbench\data`，源码运行默认使用 `server`。
- 凭据以加密形式保存。在「设置 → 密码库安全」可以管理主密码、闲置锁定和 Windows 本机自动解锁。忘记主密码时，可答对密保问题并通过本机恢复密钥重置。
- 如需备份整个工作台，先从托盘退出，再复制数据目录中的 `workspace.db`。已有的保险箱主密码恢复密钥 `.vault_recovery_private.pem` 和 `.vault_recovery_public.pem` 也需保管，私钥与数据库备份分开保存。换机后，请重新授权外部资料所在目录，并更新有变动的文件路径。

### 密码保险箱备份

在「设置 → 密码库安全 → 备份与恢复」管理加密备份。手动备份可直接执行，自动备份默认每 24 小时运行并保留最近 10 份自动备份。间隔和保留数量均可调整。修改主密码后，已有备份仍可恢复。

- **备份位置**：页面显示固定的备份目录，可点击旁边的按钮打开。源码版的备份位于项目根目录下的 `backups`，安装版位于数据目录下的 `backups`。列表中的名称对应实际文件，支持重命名、删除和恢复。
- **本机恢复**：在备份列表选择「恢复」，验证当前主密码后确认。工作台使用受 Windows 保护的本机密钥读取备份。已有条目会在覆盖前先备份。
- **换机导入**：从旧电脑复制任一 `.age` 备份及「密钥存放目录」中的对应 `.key` 文件。在新电脑设置主密码后，选择「导入」，验证新电脑的主密码，选择这两个文件并预览条目，再确认导入。请分开保管备份和恢复密钥。

## 从源码运行

需要 Windows x64 和 Python 3.12 x64。仓库包含生产前端，重新构建前端时需要 Node.js 22.12+（推荐 24.x）。

```powershell
git clone --recurse-submodules https://github.com/Rainues412/dba-workbench.git
Set-Location dba-workbench
py -3.12 -m venv .runtime\.venv
.\.runtime\.venv\Scripts\python.exe -m pip install -r server\requirements.txt
.\.runtime\.venv\Scripts\pythonw.exe tools\windows\launch_dba_workbench.py
```

源码启动器使用系统的 Microsoft Edge WebView2 Runtime，关闭窗口后仍可从系统托盘重新打开。WebView2 不可用时回退到浏览器。从启动器打开时会自动进入工作台。

设置中的「窗口与启动」提供开机启动、静默启动和关闭时最小化到托盘。开机启动在当前 Windows 用户登录后运行；静默启动可独立开启，控制手动启动和登录自启时是否只显示托盘图标，再次打开软件或选择托盘「打开工作台」可显示窗口。关闭开机启动不会改变静默启动设置。「关闭时最小化到托盘」默认开启，关闭后窗口的关闭按钮会退出工作台；浏览器回退模式请从托盘退出。源码版与安装版的启动项分别登记，源码版设置保存在 `.runtime/desktop-settings.json`，安装版保存在数据目录的 `desktop-settings.json`。源码启动器支持 `--show-window` 强制显示窗口。

如需在源码模式预览 Office、PDF 等文件，可通过 `DBA_FILE_VIEWER_HOME` 指向已构建的查看器目录。[查看器构建脚本](packaging/windows/build-file-viewer.ps1)

<details>
<summary>Tauri 桌面宿主开发预览</summary>

开发验收需要 Windows Rust MSVC 工具链和已安装的前端依赖。先运行 `cargo build --locked --manifest-path src-tauri/Cargo.toml`，再用项目 Python 环境启动预览。

```powershell
.\.runtime\.venv\Scripts\python.exe tools/windows/launch_dba_workbench_tauri.py --executable src-tauri/target/debug/dba-workbench-tauri.exe --work-dir '<现有测试目录>'
```

启动脚本创建独立的测试数据库和 WebView2 配置。仪表盘、任务管理、全局搜索、脚本库、知识库、客户项目、资源中心的记录管理，以及本机会话状态和保险箱配置读取由 Rust 执行。会话签发、保险箱解锁和恢复、旧数据库升级及本机文件操作沿用现有 FastAPI 服务和权限。页面完成首次渲染后才显示窗口。从托盘选择「退出」结束预览和两个测试服务。

Windows 源码快捷方式可以向 `launch_dba_workbench.py` 传入 `--tauri-host <EXE 路径>`，或在原桌面启动宿主的同一目录放置 `dba-workbench-tauri.exe`。现有数据库、WebView2 配置及启动偏好继续原位使用。

</details>

### 测试与构建

```powershell
.\.runtime\.venv\Scripts\python.exe -m pip install -r server\requirements-dev.txt
.\.runtime\.venv\Scripts\python.exe -m pytest

Push-Location frontend
npm ci
npm test -- --run
npm run build
Pop-Location
```

生产前端输出到 `server/frontend_dist`。初始化 Git 子模块后，可运行 `.\packaging\windows\build-installer.ps1 -Version "<major.minor.patch>"` 生成安装包。打包时会重新构建前端，「关于」、程序文件和安装包统一使用此版本号；普通源码构建显示「开发版」。

## 反馈与贡献

欢迎在 [GitHub Issues](https://github.com/Rainues412/dba-workbench/issues) 报告问题或提出建议，也欢迎提交 Pull Request。报告问题时可附上版本号、复现步骤和截图，请先移除凭据、密钥和客户数据。

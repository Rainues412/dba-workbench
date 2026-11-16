# DBA 工作台

面向 Windows 的本机单用户 DBA 运维工作台。用它管理脚本、知识文章、安装资源、待办任务、客户项目和加密密码保险箱。应用只通过本机地址访问，数据存储在本机 SQLite 数据库。

[下载 Windows x64 安装包](https://github.com/Rainues412/dba-workbench/releases/latest) · [更新日志](CHANGELOG.md)

## 安装与启动

1. 在 GitHub Release 下载 `DBA-Workbench-Setup-<版本>-x64.exe` 和同名 `.sha256` 文件。在 PowerShell 中用 `Get-FileHash -Algorithm SHA256` 计算 EXE 的哈希，并与校验文件核对。
2. 双击 EXE 安装。支持 Windows 10/11 x64，内置运行时和文件查看器，使用 Edge 或系统默认浏览器。
3. 启动后访问 `http://127.0.0.1:8686/`，按页面提示创建管理员账号。关闭浏览器后服务仍在运行，右键系统托盘图标选择「退出」可停止服务。

安装包未签名，Windows SmartScreen 可能显示「未知发布者」。升级时先从托盘退出，再运行新版安装程序。卸载默认保留应用数据。

## 主要功能

- **知识库与脚本库**可按数据库类型和分类筛选，支持 PDF、Office、Markdown 及脚本文本预览。宽屏可拖动分隔条调整预览宽度，双击均分，按 Esc 取消拖动。Markdown 可通过目录跳转章节。
- **资源中心与快捷入口**集中管理安装包、工具和常用链接。可通过「目录批量导入」授权选定目录及其子目录。
- **任务管理**支持中文截止日期选择器、优先级和逾期提示。已完成任务满 15 天后移入归档，可按需恢复。
- **客户项目**按客户归纳多个项目，客户与项目均可填写群聊名称和平台。项目负责人支持多人及自定义职责标签。点击项目行的编辑图标可直接修改该项目。模块搜索与全局搜索均支持客户名和项目名。
- **密码保险箱**在浏览器端加密。忘记主密码时，可通过锁定页的「忘记密码」入口验证身份并使用本机恢复密钥重置。

## 数据备份与迁移

安装版的数据目录是 `%LOCALAPPDATA%\DBA Workbench\data`，源码运行默认使用 `server`。备份前先从托盘退出工作台，再复制 `workspace.db` 和同目录下的保险箱恢复密钥文件 `.vault_recovery_private.pem`、`.vault_recovery_public.pem`。恢复私钥应与数据库备份分开保管。

数据库保存脚本、文章、安装资源的路径。迁移电脑时还需要复制原文件，重新授权所在目录，并在盘符或路径变化时重新扫描或更新记录。回退到旧版时使用升级前备份的数据库。

## 从源码运行

需要 Windows x64 和 Python 3.12 x64。仓库包含生产前端，修改前端时再安装 Node.js 22.12+（推荐 24.x）。

```powershell
git clone --recurse-submodules https://github.com/Rainues412/dba-workbench.git
Set-Location dba-workbench
py -3.12 -m venv .runtime\.venv
.\.runtime\.venv\Scripts\python.exe -m pip install -r server\requirements.txt
.\.runtime\.venv\Scripts\pythonw.exe tools\windows\launch_dba_workbench.py
```

源码模式可通过 `DBA_FILE_VIEWER_HOME` 指向已构建的查看器运行目录。查看器构建脚本位于 `packaging/windows/build-file-viewer.ps1`。

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

生产前端输出到 `server/frontend_dist`。Windows 安装包可在初始化 Git 子模块、构建生产前端之后运行 `.\packaging\windows\build-installer.ps1 -Version "<major.minor.patch>"` 生成。

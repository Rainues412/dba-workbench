# DBA 工作台代理指南

本文件适用于整个仓库。开始任何任务前先阅读本文件和 `README.md`，再依据实际代码、测试与运行状态工作；不要把历史对话中的进程号、测试数量、文件哈希或版本号当作当前事实。

## 1. 任务开始

1. 先确认用户目标、验收标准和授权范围，检查前提是否成立；区分已验证事实、推测和主观偏好。目标会实质改变方案且不明确时才提问。
2. 运行 `git status --short --branch`、查看最近提交和标签，保留用户已有改动，不覆盖无关文件。
3. 修改前先在 GitHub 查找成熟开源实现，优先官方文档或维护活跃的项目；只借鉴与需求直接相关的最小模式。
4. 检查实际路由、入口、配置和调用链，不根据页面文字猜测后端行为。
5. 大范围改动先做只读审计并给出可回滚、可独立验证的分阶段方案；小范围明确修复可直接实施。

## 2. 项目边界与架构

- 唯一源码目录：`D:\coding\workspace`。
- 技术栈：React + TypeScript + Vite，FastAPI，SQLite，Windows 桌面启动器。
- 页面数据流：`frontend/src` → `/api` REST/Cookie/CSRF → `server/main.py` → `server/backend` → SQLite。
- 安装版入口：`server/desktop.py`。它负责 Uvicorn、浏览器和 Windows 系统托盘生命周期。
- 源码桌面入口：`tools/windows/launch_dba_workbench.py`。不要用 `server/main.py` 替代桌面入口；后者只用于前台调试且没有托盘。
- 生产前端：`server/frontend_dist`，由 `frontend` 执行 `npm run build` 生成，不要手工编辑构建产物。
- 数据迁移：`server/backend/migrations`，必须连续编号、前向迁移并通过迁移测试。
- Windows 安装：`packaging/windows`；GitHub 标签触发 `.github/workflows/release-windows.yml`。

关键代码位置：

| 范围 | 位置 |
| --- | --- |
| 页面与组件 | `frontend/src/pages`、`frontend/src/components` |
| API 客户端与认证 | `frontend/src/api`、`frontend/src/auth` |
| 密码保险箱前端加密 | `frontend/src/vault`、`frontend/src/pages/Vault.tsx` |
| API 路由 | `server/backend/routers` |
| 登录、会话、敏感操作验证 | `server/backend/auth.py`、`server/backend/routers/auth.py` |
| 数据库与并发控制 | `server/backend/database.py`、`server/backend/concurrency.py` |
| 本机文件权限 | `server/backend/local_capabilities.py` |
| 保险箱恢复 | `server/backend/vault_recovery.py`、`server/backend/admin.py` |
| 自动化测试 | `frontend/src/test`、`server/tests` |

## 3. 不可破坏的约束

- 保留文章、脚本、资源、任务、客户、快捷入口、目录分类和保险箱数据。修改数据库或迁移前先证明兼容性和回滚方式。
- 源码模式默认数据库位于 `server/workspace.db`；安装版数据位于 `%LOCALAPPDATA%\DBA Workbench\data`。不得把真实数据、恢复私钥、凭据、日志或本机授权配置提交到 Git。
- 卸载默认保留应用数据；只有用户在卸载 EXE 中明确选择删除时，才可清理 `%LOCALAPPDATA%\DBA Workbench`。
- 保险箱采用浏览器端 Argon2id 与 AES-256-GCM；管理员恢复只能重包数据密钥，不得把明文密码写入日志、响应或持久化存储。主密码最低 9 位，敏感操作验证有效期 30 分钟。
- 服务仅绑定回环地址。未实现 HTTPS 与局域网加固前，不得开启 LAN 或公网访问。
- 本机文件能力必须使用明确目录白名单；不得扩大到整块磁盘、UNC 路径或脚本执行。
- 写操作保留 `revision` / `If-Match` 并发保护；列表保持服务端分页，摘要列表不得覆盖未返回的正文。
- 全局搜索和模块搜索只检索标题；任务管理不参与全局搜索，除非用户明确改变产品要求。
- 数据库类型图标沿用现有资产和视觉语义；不要用无关图片替换，MongoDB、MySQL 与“其他”需保持可区分。

## 4. 实现与界面规则

- 使用最小、直接、可维护的代码；复用现有组件和样式，不增加需求外的框架、配置或扩展能力。
- 修复根因并覆盖失败路径，不用硬编码特定机器的绝对路径。运行路径通过入口位置、环境变量或 Windows 已知目录解析。
- UI 改动同时检查浅色/深色、窄屏、文本溢出、键盘焦点、悬停说明和加载/空/错误状态。
- 表格与列表分页保持当前页不无故滚回顶部；截断标题必须提供完整名称悬停提示。
- 修改前端源码后必须执行 `npm run build` 并提交同步更新的 `server/frontend_dist`；仅类型或测试变化且产物未变化时不要制造无意义构建差异。
- 不直接编辑或提交发布 EXE。安装包只放在 GitHub Release 和 `D:\coding\DBA工作台-发布\installer`。
- 临时调研、截图和辅助文件放在 `D:\Software\AI\Codex`；不要在 C 盘创建项目文件。

## 5. 验证

从仓库根目录执行：

```powershell
# 后端全量测试
.\.runtime\.venv\Scripts\python.exe -m pytest -q

# 前端全量测试与生产构建
Set-Location frontend
npm test -- --run
npm run build
Set-Location ..

# 补充检查
git diff --check
git status --short
```

按风险增加针对性验证：

- API、迁移、认证或保险箱：先运行对应后端测试，再运行全量测试。
- UI 行为：增加 Vitest/Testing Library 测试，并在实际生产构建中检查。
- Windows 启动、目录选择、托盘或安装卸载：运行对应 Windows 测试，并使用真实 Inno Setup 编译；发布前构建完整安装包。
- 测试必须使用隔离数据库和临时目录，不得写入真实 `workspace.db` 或用户保险箱。

不要声称“已修复”或“已发布”，除非相应测试、提交、远端标签和 Release 资产已经核验。

## 6. Git 与提交

- 按用户每次提出的独立要求分次提交；不要把多个无关需求压成一个提交。
- 提交前检查 diff，避免包含缓存、数据库、密钥、日志、安装包或无关格式化。
- 提交信息使用简洁英文约定式前缀，例如 `fix:`、`feat:`、`docs:`、`build:`。
- 本项目所有代码改动完成验证并分次提交后，必须主动推送 `main` 同步到 GitHub，不再等待用户另行要求。GitHub 仓库操作优先使用 GitHub MCP；推送已有本地提交使用 Git，不用浏览器自动化。
- 不重写已发布标签，不强推，不使用破坏性 Git 命令。

## 7. 构建与发布

发布物目录不属于 Git 源码：

```powershell
.\packaging\windows\build-installer.ps1 `
  -OutputDirectory 'D:\coding\DBA工作台-发布' `
  -Version '<major.minor.patch>'
```

发布规则：

1. 只有用户可见行为、安装逻辑、缺陷修复、依赖或数据迁移发生变化，并且用户要求发布时，才递增版本。纯 `AGENTS.md`、README 或注释更新不单独发布应用版本。
2. 从远端最新标签确定下一个语义化版本，不在多个文件中硬编码“当前版本”。
3. 发布前要求工作区干净、前后端全量测试通过、本地完整安装包构建成功且 SHA-256 文件存在。
4. 安装包必须位于 `D:\coding\DBA工作台-发布\installer`，源码仓库内不得出现 `.exe`。
5. 分次提交并推送 `main` 后创建带注释标签 `v<version>`，再推送标签触发 GitHub Actions。
6. 使用 GitHub MCP 核验 Release 非草稿、非预发布，并确认同时存在安装 EXE 与 `.sha256` 资产；记录云端资产 SHA-256。
7. 本地构建与云端构建因编译环境不同，哈希可以不同；各自必须与同目录校验文件一致。

发布完成的最低交付信息：版本、提交、测试结果、本地安装包路径及哈希、GitHub Release 链接、云端安装包链接及哈希。

## 8. 结束任务

- 再次运行 `git status --short --branch`，确认没有遗漏或意外文件。
- 明确说明已完成、未完成、风险和用户需要执行的动作。
- 如果只完成源码而未重新构建安装包，要明确指出旧安装包不包含该变更。
- 不把推测写成事实；时间敏感的版本、发布状态和哈希必须实时核验。

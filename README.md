# DBA 工作台

本机运行的 DBA 运维工作台，使用 React + TypeScript 前端、FastAPI 后端和 SQLite 数据库，管理脚本、知识、资源、任务、客户资料与加密保险箱。

## 快速开始

```powershell
Set-Location D:\coding\workspace

# 后端依赖统一安装到项目运行目录
python -m venv .runtime/.venv
.runtime/.venv/Scripts/python.exe -m pip install -r server/requirements.txt

# 仅在修改前端后需要重新构建
cd frontend
npm ci
npm run build

# 启动（仓库根目录）
cd ..
.runtime/.venv/Scripts/python.exe server/main.py
```

浏览器访问 `http://localhost:8686`。首次启动没有默认账号或默认密码，必须在页面创建第一个所有者账号。

也可以使用 Windows 启动器：

```powershell
.runtime/.venv/Scripts/pythonw.exe tools/windows/launch_dba_workbench.py
```

启动器从自身位置定位仓库，优先使用 `.runtime/.venv` 的 Python，默认在 Microsoft Edge 中打开；没有 Edge 时使用系统默认浏览器。启动日志位于 `.runtime/logs/server.log`。桌面快捷方式也直接指向此启动器，项目不再依赖仓库外的另一份启动代码。

服务默认仅监听 `127.0.0.1`，不支持局域网或公网部署。生产前端构建产物位于 `server/frontend_dist`，与源码一起提交，因此仅运行项目时不需要安装 Node.js。旧单文件页面和桥接脚本已移除，所有界面统一由 React 提供。

## 验证

```powershell
.runtime/.venv/Scripts/python.exe -m pip install -r server/requirements-dev.txt
.runtime/.venv/Scripts/python.exe -m pytest

cd frontend
npm test -- --run
npm run build
```

测试使用临时数据库和随机本机端口，不访问 `server/workspace.db`。浏览器测试优先调用本机 Microsoft Edge；不可用时会明确标记为跳过。2026-10-19 复核修复最终验证：后端/Edge 96 项、前端 60 项通过，生产构建成功。

## 架构

```text
frontend/                    React、TypeScript、Vite 源码
server/frontend_dist/        已构建的生产前端
server/main.py               FastAPI 入口
server/backend/auth.py       登录会话、CSRF、Argon2id
server/backend/migrations/   有序、前向、逐版本事务迁移
server/backend/routers/      类型化 REST API
server/backend/admin.py      仅离线可用的管理员恢复命令
server/workspace.db          SQLite 数据库（Git 忽略）
tools/windows/              唯一 Windows 启动器
assets/                     桌面图标及源 SVG
.runtime/.venv/             项目 Python 环境（Git 忽略）
.runtime/logs/              本机启动日志（Git 忽略）
```

所有业务模块都通过统一 API 客户端访问后端。列表接口统一分页；更新使用 `revision` 做并发冲突检测。数据库启动时自动检查版本并执行尚未应用的 SQL 迁移，高版本数据库会被拒绝打开。

数据库类型分布合并统计脚本与知识文章，保留 Oracle、MySQL、PostgreSQL、SQL Server、Linux、Redis 和其他类型。图标使用项目内 SVG，颜色与对应标签和进度条一致。首页未完成任务按高、中、低优先级呈现不同颜色。

脚本库支持“数据库 → 脚本类型”，知识库支持“数据库 → 文档分类”，资源中心支持按数据库分类浏览。分类名称及计数从全部记录聚合读取，原有自定义分类也会显示。搜索与当前分类共同生效，切换分类会回到第一页；新增记录默认带上当前选中的分类，分类输入框同时支持已有值建议和自定义名称。

列表右下角采用数字分页：每页条数选择、总条数、上一页/下一页、首尾页及当前页附近的页码。默认 10 条/页，可选 20、50、100、200 条/页；当前页以蓝底高亮，点击省略号可向前或向后跨 5 页。调整每页条数时保留分类及搜索条件并回到第一页；删除末页最后一条记录后会自动回到有效页码。

翻页请求期间保留当前列表及分页栏，避免加载状态导致页面高度骤变。新页加载后保持分页栏在视口中的位置，访问缓存页或记录较少的末页时也无需重新滚动到底部。

脚本库中点击名称会用本机编辑器打开脚本，不会执行脚本；知识库和本地资源点击名称会用系统默认程序打开。点击名称下方的路径可打开所在文件夹并选中文件，旁边可复制完整路径。网址资源仅允许打开 HTTP/HTTPS 链接。打开失败会显示原因，不会自动回退为执行。

## 本机目录与维护

唯一源码目录为 `D:\coding\workspace`，对应 GitHub 仓库 [Rainues412/dba-workbench](https://github.com/Rainues412/dba-workbench)。原 `D:\Software\AI\Codex\DBA工作台` 中的有效启动逻辑和运行依赖已归并至本仓库；旧目录不再作为运行入口。

2026-10-19 合并前的 Git 历史、源码快照、数据库快照、旧启动器及历史备份保存在 `D:\Software\AI\Codex\DBA工作台合并备份\20261019`，不提交到 GitHub。旧位图和旧单文件页面可从源码快照或 Git 历史恢复；当前界面仅使用 `frontend/src/assets/database` 中的 SVG。

更新前端后在 `frontend` 执行 `npm run build`，再一并提交源码、锁文件及 `server/frontend_dist`。不要手工编辑打包后的 JS/CSS。`.runtime`、`frontend/node_modules` 和 Python 缓存不属于源码；删除这些目录后可按快速开始重新安装依赖。数据库、恢复私钥和备份应单独保留，不能作为缓存清理。

## 保险箱安全模型

- 主密码与登录密码分离，不保存主密码。
- 浏览器以 Argon2id 派生密钥，并用 AES-256-GCM 在客户端加解密；服务端只保存密文、随机 nonce、AAD 和密钥信封。
- 查看、复制、编辑、删除、迁移、备份和恢复前需要近期重新验证登录密码。
- 保险箱默认锁定，闲置五分钟后自动清除内存密钥；短暂切换窗口不会立即锁定，回到页面时会检查闲置期限，刷新、关闭页面或离开保险箱仍需重新解锁。复制到剪贴板的密码会在 30 秒后尽力清除。
- 解锁后可通过“导入 Edge 密码”选择 Edge 导出的 UTF-8 CSV；仅在浏览器内解析、加密并回读校验，服务器只接收密文。相同网址、账号和密码跳过，密码不同另存、不覆盖；导入后分类为“Edge 导入”。核对成功后请自行删除明文 CSV，不要提交到 Git 或聊天。
- 管理员恢复只允许在服务器本机离线执行，不存在 HTTP 解密或绕过接口。
- 普通 JSON 导出不包含保险箱；保险箱使用独立的加密备份与摘要校验。

保险箱创建后，应立即将恢复密钥备份到 `D:\Software\AI\Codex` 下，并将副本与数据库分开保存：

```powershell
cd server
../.runtime/.venv/Scripts/python.exe -m backend.admin backup-recovery-key --output D:\Software\AI\Codex\dba-vault-recovery
../.runtime/.venv/Scripts/python.exe -m backend.admin verify-recovery-key
```

遗忘保险箱主密码时，停止服务后在 `server` 目录执行：

```powershell
../.runtime/.venv/Scripts/python.exe -m backend.admin recover-vault <用户名>
```

该命令使用本机恢复私钥重新包裹同一数据密钥，不会逐条重加密业务数据，并会撤销该用户全部登录会话。若恢复私钥和数据库同时遗失，保险箱密文无法恢复。

遗忘登录密码时：

```powershell
../.runtime/.venv/Scripts/python.exe -m backend.admin reset-login-password <用户名>
```

## 数据与升级

数据库文件是 `server/workspace.db`。升级或迁移机器前应在服务停止状态下复制数据库和恢复密钥备份。旧 Fernet 密码记录与浏览器 localStorage 记录通过新界面的迁移入口一次性转换；迁移确认成功前不会删除旧数据。

常规 JSON 导入导出覆盖脚本、知识、资源、任务和客户资料，不包含认证数据、会话、恢复私钥或保险箱密文。

右上角备份图标打开普通模块 JSON 导出/导入。导入保留分类、联系人、文本版本号、完成时间与父子关系，重新分配 ID/revision；采用追加而非覆盖，重复导入会增加重复记录。任一行失败时整份导入回滚，界面明确显示错误，不会留下部分成功的恢复。JSON 包含已存入数据库的正文，但不打包原路径文件，原文件应另行备份。

顶部搜索按钮或 `Ctrl+K` 可跨脚本、知识、资源、任务和客户搜索，选中结果直接打开对应详情；保险箱只在解锁后单独搜索。编辑详情加载失败时只允许重试/关闭，不会切换成新增或允许误保存。

任务页提供状态/优先级筛选、完成/恢复按钮。“旧任务归档”仅从当前浏览器当前地址的 `wb_dba_workbench_tasks_archive` 显式追加迁移为已完成任务，原数据保留；同一数据库的迁移回执使重试不会重复导入，已导入后删除的记录也不会被重试复活。localhost 与 127.0.0.1 的浏览器本地存储互不相通，请在原地址和原浏览器进行迁移。

脚本、知识、资源支持收藏筛选与切换，知识支持置顶；脚本详情支持读取历史正文并通过 revision 校验恢复，当前正文会保留为历史。客户详情提供关联联系人的新增/编辑/删除、沟通记录新增/删除及关联任务跳转，沟通列表显示最近 50 条。

保险箱遍历所有密文分页后在内存解密、搜索，并用数字页码展示结果，不再只显示前 200 条；支持收藏编辑/筛选，锁定后清除解密结果。大保险箱首次解锁会多次请求并占用与总记录量相关的内存。

条目默认按名称进行中文、英文和数字自然排序；卡片可直接收藏或取消收藏，密码可通过“查看 / 隐藏”切换。支持单项勾选、全选当前页、取消选择和删除所选；翻页或更改筛选时清空勾选。删除前会提示数量和不可撤销风险；逐条携带版本号删除，遇到冲突、授权过期或请求失败立即停止，并提示已确认删除数量，不自动强制重试。建议操作前保存加密备份。

## 本机能力

打开文件、编辑文件、扫描目录和执行脚本默认关闭。确需使用时必须启用总开关并明确允许根目录：

Windows 启动器支持本机专用的 `.runtime/local-capabilities.json`（不提交 Git）：

```json
{
  "allowed_roots": ["D:\\Database", "D:\\Note\\Typora"],
  "allowed_actions": ["edit", "folder", "open", "scan", "pick-folder"]
}
```

存在此文件而未配置 `allowed_actions` 时，启动器仅默认启用 `edit,folder,open`；扫描和目录选择必须另外明确配置。此配置文件不接受 `run`，环境变量仍可覆盖默认值。修改配置后需重启服务。当前桌面安装经用户确认，仅对上述两个目录启用示例中的五个动作，未开启脚本执行。三个资料库的“目录批量导入”支持显式目录、预览、勾选与重复路径跳过，不移动原文件。直接运行 `server/main.py` 不会读取此文件，仍需显式设置环境变量：

```powershell
$env:DBA_LOCAL_CAPABILITIES = "true"
$env:DBA_ALLOWED_ROOTS = "D:\Database;D:\scripts"
$env:DBA_ALLOWED_LOCAL_ACTIONS = "check,edit,folder,open,pick-folder,scan"
.runtime/.venv/Scripts/python.exe server/main.py
```

脚本执行还需把 `run` 加入动作白名单，并通过 `DBA_ALLOWED_RUN_EXTENSIONS` 指定允许的扩展名。UNC、相对路径、越界路径和符号链接逃逸会被拒绝。

## 功能复核状态（2026-10-19）

本次复核报告 R-01 至 R-09 已按现有业务能力修复并补齐入口：普通备份字段完整往返及事务回滚、详情失败保护、保险箱全量分页搜索与收藏、普通备份入口、全局搜索、受限目录导入、任务筛选/快捷状态/旧归档迁移、脚本历史及客户关联信息。原分类、数字分页、滚动位置保持和本机快捷打开继续保留。数据库版本 5 仅新增旧任务归档迁移回执表，原业务记录不迁移或清理。

报告、验收记录、截图和升级前数据库快照保存在 `D:\Software\AI\Codex`，不提交真实业务数据。测试覆盖不等于完整安全审计，也不保证不存在其他缺陷；阶段五局域网多人能力仍未实施。

## 安全边界

- 仅支持本机回环地址；`DBA_MODE=lan` 会拒绝启动。
- 登录密码使用 Argon2id；会话 Cookie 为 HttpOnly、SameSite=Strict，状态修改要求 CSRF 令牌。
- Host、Origin 和 CORS 使用明确白名单，不接受 `*`。
- `server/workspace.db`、恢复私钥和旧 Fernet 密钥均被 Git 忽略。
- 本机管理员与能够读取数据库和恢复私钥的人仍属于信任边界；请使用操作系统磁盘加密和账户权限保护这些文件。

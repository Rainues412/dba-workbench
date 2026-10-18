# DBA 工作台

本机运行的 DBA 运维工作台，使用 React + TypeScript 前端、FastAPI 后端和 SQLite 数据库，管理脚本、知识、资源、任务、客户资料与加密保险箱。

## 快速开始

```powershell
# 后端依赖
python -m pip install -r server/requirements.txt

# 仅在修改前端后需要重新构建
cd frontend
npm ci
npm run build

# 启动（仓库根目录）
cd ..
python server/main.py
```

浏览器访问 `http://localhost:8686`。首次启动没有默认账号或默认密码，必须在页面创建第一个所有者账号。

也可以使用 Windows 启动器：

```powershell
python tools/windows/launch_dba_workbench.py
```

服务默认仅监听 `127.0.0.1`，不支持局域网或公网部署。生产前端构建产物位于 `server/frontend_dist`；旧单文件页面仅作为短期回退入口保留在 `/legacy`，其 API 同样受登录保护。

## 验证

```powershell
python -m pip install -r server/requirements-dev.txt
python -m pytest

cd frontend
npm test -- --run
npm run build
```

测试使用临时数据库和随机本机端口，不访问 `server/workspace.db`。浏览器测试优先调用本机 Microsoft Edge；不可用时会明确标记为跳过。

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
ops-workbench.html           旧界面回退页
```

所有业务模块都通过统一 API 客户端访问后端。列表接口统一分页；更新使用 `revision` 做并发冲突检测。数据库启动时自动检查版本并执行尚未应用的 SQL 迁移，高版本数据库会被拒绝打开。

## 保险箱安全模型

- 主密码与登录密码分离，不保存主密码。
- 浏览器以 Argon2id 派生密钥，并用 AES-256-GCM 在客户端加解密；服务端只保存密文、随机 nonce、AAD 和密钥信封。
- 查看、复制、编辑、删除、迁移、备份和恢复前需要近期重新验证登录密码。
- 保险箱默认锁定，闲置五分钟或页面隐藏时自动清除内存密钥；复制到剪贴板的密码会在 30 秒后尽力清除。
- 管理员恢复只允许在服务器本机离线执行，不存在 HTTP 解密或绕过接口。
- 普通 JSON 导出不包含保险箱；保险箱使用独立的加密备份与摘要校验。

保险箱创建后，应立即将恢复密钥备份到 `D:\Software\AI\Codex` 下，并将副本与数据库分开保存：

```powershell
cd server
python -m backend.admin backup-recovery-key --output D:\Software\AI\Codex\dba-vault-recovery
python -m backend.admin verify-recovery-key
```

遗忘保险箱主密码时，停止服务后在 `server` 目录执行：

```powershell
python -m backend.admin recover-vault <用户名>
```

该命令使用本机恢复私钥重新包裹同一数据密钥，不会逐条重加密业务数据，并会撤销该用户全部登录会话。若恢复私钥和数据库同时遗失，保险箱密文无法恢复。

遗忘登录密码时：

```powershell
python -m backend.admin reset-login-password <用户名>
```

## 数据与升级

数据库文件是 `server/workspace.db`。升级或迁移机器前应在服务停止状态下复制数据库和恢复密钥备份。旧 Fernet 密码记录与浏览器 localStorage 记录通过新界面的迁移入口一次性转换；迁移确认成功前不会删除旧数据。

常规 JSON 导入导出覆盖脚本、知识、资源、任务和客户资料，不包含认证数据、会话、恢复私钥或保险箱密文。

## 本机能力

打开文件、编辑文件、扫描目录和执行脚本默认关闭。确需使用时必须启用总开关并明确允许根目录：

```powershell
$env:DBA_LOCAL_CAPABILITIES = "true"
$env:DBA_ALLOWED_ROOTS = "D:\Database;D:\scripts"
$env:DBA_ALLOWED_LOCAL_ACTIONS = "check,edit,folder,open,pick-folder,scan"
python server/main.py
```

脚本执行还需把 `run` 加入动作白名单，并通过 `DBA_ALLOWED_RUN_EXTENSIONS` 指定允许的扩展名。UNC、相对路径、越界路径和符号链接逃逸会被拒绝。

## 安全边界

- 仅支持本机回环地址；`DBA_MODE=lan` 会拒绝启动。
- 登录密码使用 Argon2id；会话 Cookie 为 HttpOnly、SameSite=Strict，状态修改要求 CSRF 令牌。
- Host、Origin 和 CORS 使用明确白名单，不接受 `*`。
- `server/workspace.db`、恢复私钥和旧 Fernet 密钥均被 Git 忽略。
- 本机管理员与能够读取数据库和恢复私钥的人仍属于信任边界；请使用操作系统磁盘加密和账户权限保护这些文件。

# DBA 工作台

个人 DBA 工作台。**合并版架构**：workbuddy 的单文件 UI 壳 + FastAPI 后端与
SQLite 数据层。UI 与 `ops-workbench.html` 保持逐字节不变，数据层按访问方式切换。

- **本地工作台（真数据）**：http://localhost:8686 （`server/main.py`）
- **GitHub**：https://github.com/Rainues412/dba-workbench （private，源码备份）
- **公网发布**：已于 2026-09-28 下线（`unpublish_page.py`）。页面仍保留在
  workbuddy 资料库（节点 `yKeXCdqf9JT4DJ2JmpmBpY`，编辑态
  https://www.workbuddy.cn/space/d/yKeXCdqf9JT4DJ2JmpmBpY ），
  计划日后在独立服务器上重新发布，见「修改与发布」
- 前端主文件：`ops-workbench.html`（CSS/JS 全内联，零外部依赖）

## 快速开始

```bash
cd server && python main.py     # 自动开浏览器 http://localhost:8686
```

依赖：`server/requirements.txt`（fastapi / uvicorn / cryptography）。
侧栏标题下方徽章显示当前数据模式：**已连接服务器**（API/SQLite）或
**本地模式**（回退 localStorage）。

## 项目架构

```
D:\coding\workspace\
├── ops-workbench.html        单文件前端（workbuddy UI 壳，磁盘/git/线上逐字节一致）
├── *-icon.png ×6             数据库官方 logo 图标源文件（base64 已内嵌进 HTML）
├── README.md / .gitignore / .gitattributes
├── .workbuddy/memory/        workbuddy 工作记忆与偏好（纳入版本控制）
└── server\                   FastAPI 后端（合并自 dba-workspace 项目）
    ├── main.py               入口 :8686（仅绑 127.0.0.1）；GET / 返回 HTML 时
    │                         仅在响应中追加 <script src="/static/workbench.js">
    │                         （不改磁盘文件）
    ├── static/workbench.js   数据层桥接：劫持页面 gd()/sd()，读写改走 REST API；
    │                         服务器不可用时自动回退 localStorage
    ├── backend/
    │   ├── database.py       SQLite 建表 + 迁移（含 wb_type/wb_db/wb_person 等桥接列）
    │   └── routers/          11 个路由模块（见下「API 一览」）
    ├── migrate_from_dba_workspace.py
    │                         一次性幂等迁移：旧库 → 本库（09-24 已执行）
    ├── requirements.txt
    ├── workspace.db          SQLite 真数据（git 忽略；583 行）
    └── .workspace_secret     密码本 Fernet 密钥（git 忽略，勿外传；当前未启用见下）
```

### 两种访问形态

| 访问方式 | 数据源 | 打开/定位/扫描入库 |
|---|---|---|
| `localhost:8686`（本服务器） | SQLite 真数据 | ✅ |
| 双击 `ops-workbench.html` 直接打开 | 该浏览器 localStorage（空库时为内置示例数据） | ❌（无 API） |

服务绑定 `127.0.0.1`，外部设备不可达。公网形态已下线；日后在独立服务器
发布时，前端与 API 同域部署即可天然避开跨域与 CSP 问题（见「修改与发布」）。

### 数据流

```
页面 render*() ──读──> gd(key) ──> [API 模式] 内存 cache（pull 自 REST API）
                                └─> [回退模式] localStorage
页面 sd(key, data) ─写─> [API 模式] cache + 400ms 防抖 → 全量对账推送
                                （删服务端多余 + 逐条 upsert）→ SQLite
                        └─> [回退模式] localStorage
每次 pull 镜像回 localStorage：服务器宕机时回退看到的是真实数据而非示例种子
```

- 6 个集合中 5 个走 SQLite：scripts / knowledge / installers / tasks / contacts
- **accounts（账号保险箱）始终留在 localStorage**：明文密码不进 API、不进 git、不上云
- 字段映射在 `workbench.js` 的 `M` 表：P0/P1/P2 ↔ 高/中/低；
  scripts.type ↔ `scripts.wb_type`；knowledge.db ↔ `articles.wb_db`；
  contacts 的负责人/联系方式 ↔ `customers.wb_person` / `wb_contact`
- 密码本模块（vault 路由，Fernet 加密）后端保留但前端未接线——
  当前 UI 的账号保险箱按用户偏好走 localStorage；`.workspace_secret` 暂为闲置

### API 一览（前缀 `/api`）

| 路由 | 用途 |
|---|---|
| `dashboard` | 统计数 / 待办 / 收藏 / 最近文档 |
| `scripts` / `articles` | 脚本库 / 知识库（对应 UI 的 scripts / knowledge） |
| `resources` | 安装包索引（对应 UI 的 installers） |
| `tasks` / `customers` | 任务排期 / 客户通讯录（含联系人与沟通记录子表） |
| `vault` | 密码本（Fernet 加密；前端未启用） |
| `launcher` | 打开本地文件/目录/URL（`os.startfile` / `explorer /select` / 浏览器） |
| `scan` | 扫描目录配置 + 扫描 + 入库（只记路径，不移动文件） |
| `search` / `export` | 全局搜索 / JSON 导出导入 |

### 合并带来的增强（不改 UI，仅运行时注入）

- 脚本/知识库/安装包表格中**有路径的行**行首注入「打开」「定位」按钮
- 设置弹窗注入「扫描入库」区块；控制台另有
  `wbAddScanDir("D:\...")` / `wbScan()` / `wbListScanDirs()`

## 模块

仪表盘 / 脚本库 / 知识库 / 安装包 / 任务排期 / 客户通讯录 / 账号保险箱

仪表盘左侧为「处理中的故障」+「我的当前工作」，右侧为「数据库类型分布」
（7 类两列卡片，每张含图标胶囊 + 进度条 + 数量）。
注意：分布图计数写死在 HTML 的 `dbData` 中，不随 SQLite 数据变化。

## 修改与发布

**当前状态：公网已下线（2026-09-28 unpublish）**。页面仍保留在 workbuddy
资料库（节点 `yKeXCdqf9JT4DJ2JmpmBpY`），链接 `workbuddy.link/p/...` 不再可访问。
计划日后在独立服务器上重新发布本项目。

### 将来在独立服务器发布的要点

- 前端与 API **同域部署**（如 `https://your.host/` 出页面、`https://your.host/api`
  出接口），天然避开跨域与 workbuddy 那类平台 CSP 限制，无需自签证书/https 双端口
- `workbench.js` 的 `API_BASE` 目前是写死的 `http://localhost:8686`，
  同域部署时改为相对路径（如 `/api` 前缀）或按 `location.origin` 拼接
- 数据从本机迁出：设置页导出 JSON，或直接拷贝 `server/workspace.db`
  （含 `.workspace_secret` 若启用密码本）
- 绑定地址需从 `127.0.0.1` 改为对外网卡，并**务必加认证**（当前 API 无任何鉴权，
  仅靠"只绑回环"这一条防线）

### workbuddy 资料库（历史通道，保留备查）

若仍要向 workbuddy 发布（仅 localStorage 展示态，无真数据）：

```bash
python3 "<library-skill>/page/import_html.py" ops-workbench.html \
        --node-block-id yKeXCdqf9JT4DJ2JmpmBpY
python3 "<library-skill>/page/publish_page.py" --node-id yKeXCdqf9JT4DJ2JmpmBpY
```

**必须带 `--node-block-id`**，否则会新建一个页面、链接随之改变。
查线上产物必须用接口返回的 `artifacts[].path`（产物名可能是 `public.html`），
沿用旧文件名会拿到 NoSuchKey 错误页并误判线上被破坏。

## 数据库图标

「数据库类型分布」的 7 个图标中，6 个来自官方 logo（Oracle / MySQL /
PostgreSQL / SQL Server / Linux / 其他），Redis 为手绘线性 SVG。

图标处理**必须复用 user-level skill `db-icon-recolor`**
（`~/.workbuddy/skills/db-icon-recolor/`），不要重写逻辑。该 skill 在本仓库之外
（仓库曾有的 `db-icon-recolor.zip` 打包快照已于 2026-09-28 清理）。

关键约定：

- 图标色必须等于该条目 `dbData[i].color`（它同时驱动进度条与图标底框 `color+'15'`）
- 新增条目须同步补 `darkColors[name]`；带空格的键（`'SQL Server'`）要加引号
- 7 个图标已**统一视觉尺寸**：6 个 PNG 为 256×256 画布 + 205px 图形（80%），
  最长边均 16.02px；Redis 用 `viewBox="2 1 20 20"` + `stroke-width="1.25"` 匹配同一比例
- 尺寸只有相对兄弟图标才有意义——**必须整组一起归一化**，且 `--glyph` 取值一致，
  单独改一个会让它成为新的异类
- 处理模式**不可按条目名缓存**：「其他」曾是 light_bg 光底 RGB（transparent），
  后换成 alpha-mask 调色板图（keepalpha）。每次都要从当前源文件重新推导
- 改了检测/管线逻辑后必须跑 `regenerate_all.py`（需带 `--python <venv>`）做全量
  逐字节比对，确认已发布图标没有停留在旧代参数上

环境：系统 Python 无 PIL；隔离 venv 在
`C:/Users/76879/.workbuddy/binaries/python/envs/default`（已装 Pillow，用于 WebP /
调色板 PNG / 灰度图转 RGBA，以及 `normalize_icon.py` 的 LANCZOS 重采样）。

## 版本控制约定

`.gitignore` 排除内容：

| 排除项 | 原因 |
|---|---|
| `ops-workbench.backup-before-*.html` | 每个状态都已作为一次提交的 `ops-workbench.html` 记录。**文件已于 2026-09-28 删除**（删除前逐一与对应提交 blob 校验 sha256 一致），规则保留作安全网 |
| `nb64_*.txt` / `b64_*.txt` / `rc-*.png` / `*-norm.png` | 可由「源 PNG + skill」再生；base64 已内嵌进 HTML（文件已清理） |
| `db-icon-recolor.zip` | 构建产物，源在仓库外的 skill 目录（文件已清理） |
| `server/workspace.db*` / `server/.workspace_secret` / `server/public.html` | 真数据 / 密钥 / 可再生发布产物，不入库 |
| `__pycache__/` / `*.pyc` 及一次性诊断脚本 | 临时产物 |

**备份文件 → 提交映射**（历史存档；备份是各轮「改动前」快照，内容等于上一轮最终状态）：

| 备份文件（已删） | 提交 | 内容 |
|---|---|---|
| `backup-before-pg.html` | `548c5e1` | 1：DBA 工作台基线（MySQL 绿 PNG + PG 120px 透明底 PNG，余为手绘 SVG） |
| `backup-before-oracle.html` | `30930fc` | 2：PostgreSQL 换用 300x300 白底版官方图标 |
| `backup-before-mssql-other.html` | `41551b9` | 3：Oracle 改用官方 logo 图标 |
| `backup-before-other-linux.html` | `aff09f0` | 4：SQL Server 与「其他」改用官方 logo 图标 |
| `backup-before-normalize.html` | `6aeed64` | 5：「其他」与 Linux 改用官方图标（alpha mask） |
| （当前文件） | `9ff0cc3` | 6：统一 7 个图标的视觉尺寸 |

工作记忆与偏好记录在 `.workbuddy/memory/`（已纳入版本控制）。

## GitHub 同步

- 仓库：`git@github.com:Rainues412/dba-workbench.git`（**private**），推送 `git push origin main`
- **入库**：UI 壳、图标源 PNG、`server/` 后端与桥接层、`.workbuddy/memory/`、README
- **不入库**（.gitignore）：`server/workspace.db*`（583 行真数据）、
  `server/.workspace_secret`、`server/public.html`、`__pycache__/`
- 因此 GitHub 副本**不含真实业务数据**，只是源码备份；换机器后
  克隆仓库 + 恢复 `workspace.db` 备份（或设置页导入 JSON）即可复原
- 安全提示：`ops-workbench.html` 的 `SD` 种子数据含 5 条示例账号密码字符串
  （workbuddy 生成的 DBA 场景示例，非真实凭据）；若日后把其中任何一条换成
  真实密码，请先从种子中移除再提交。仓库设为 private 即为此类内容兜底
- 公网形态已于 2026-09-28 下线；workbuddy 资料库节点保留，见「修改与发布」

## 行尾策略（重要，勿改）

`ops-workbench.html` 是纯 CRLF 文件且已发布到线上，`.gitattributes` 用
`* -text` 禁止任何行尾转换。若允许转换，`git checkout` 得到的副本将不再与
线上发布件逐字节一致，`regenerate_all.py` 的哈希比对也会失效。
仓库级另设 `core.autocrlf=false`，但本地 config 不随克隆传播，
**以 `.gitattributes` 为准**。

## 历史时间线

| 日期 | 事件 | 提交 |
|---|---|---|
| 09-24 | 建库基线 + 6 轮图标迭代 | `548c5e1`…`9ff0cc3` |
| 09-24 | 合并 dba-workspace 后端（FastAPI + SQLite + 桥接层），迁移 583 行真数据 | `0618297`（feat/server-merge） |
| 09-28 | workbuddy 会话误回滚（checkout main），留下僵尸进程与线上桥接版不同步 | `1108853`（记录） |
| 09-28 | 用户确认要合并模式：合回 main、补 CORS、清理备份与可再生产物 | `3854c96` / `bcb3d85` |
| 09-28 | 推送 GitHub private 仓库 | `5ee9477` |
| 09-28 | 排查公网页拿不到真数据：CORS origin + 平台 CSP 拦明文 http；上 https:8687 双端口方案并发布 | `9da0354` |
| 09-28 | 用户决定取消公网形态（日后独立服务器发布）：unpublish、拆掉 https/CORS/证书/发布件 | 本次提交 |

## 安全说明

- 账号保险箱密码只在本机浏览器 localStorage，PIN 校验在前端（源码可见），
  属"防顺手翻看"级别，不是加密存储；含真实密码的导出 JSON 勿外传
- `server/workspace.db` 与 `.workspace_secret` 均被 git 忽略；备份数据库时两者要同存同备
- API 仅绑定 127.0.0.1 且无鉴权——**不要把它暴露到公网**；将来服务器发布前必须加认证

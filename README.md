# DBA 工作台

个人 DBA 工作台，单文件 HTML（CSS/JS 全内联，零外部依赖），已部署为在线页面。

- **在线访问**：https://workbuddy.link/p/yKeXCdqf9JT4DJ2JmpmBpY
- **编辑态**：https://www.workbuddy.cn/space/d/yKeXCdqf9JT4DJ2JmpmBpY
- 主文件：`ops-workbench.html`

## 模块

仪表盘 / 脚本库 / 知识库 / 安装包 / 任务排期 / 客户通讯录 / 账号保险箱

仪表盘左侧为「处理中的故障」+「我的当前工作」，右侧为「数据库类型分布」
（7 类两列卡片，每张含图标胶囊 + 进度条 + 数量）。

账号密码仅存本机浏览器 localStorage，不上云。

## 修改与发布

本地改动不会自动上线，必须重新导入并发布。**必须带 `--node-block-id`**，
否则会新建一个页面、链接随之改变：

```bash
python3 "<library-skill>/page/import_html.py" ops-workbench.html \
        --node-block-id yKeXCdqf9JT4DJ2JmpmBpY
python3 "<library-skill>/page/publish_page.py" --node-id yKeXCdqf9JT4DJ2JmpmBpY
```

## 数据库图标

「数据库类型分布」的 7 个图标中，6 个来自官方 logo（Oracle / MySQL /
PostgreSQL / SQL Server / Linux / 其他），Redis 为手绘线性 SVG。

图标处理**必须复用 user-level skill `db-icon-recolor`**
（`~/.workbuddy/skills/db-icon-recolor/`），不要重写逻辑。该 skill 在本仓库之外，
仓库里的 `db-icon-recolor.zip` 只是它的打包快照。

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

`.gitignore` 排除三类内容：

| 排除项 | 原因 |
|---|---|
| `ops-workbench.backup-before-*.html` | 每个状态都已作为一次提交的 `ops-workbench.html` 记录，再纳入即重复 |
| `nb64_*.txt` / `rc-*.png` / `*-norm.png` | 可由「源 PNG + skill」再生；base64 已内嵌进 HTML |
| `db-icon-recolor.zip` | 构建产物，源在仓库外的 skill 目录 |

**备份文件 → 提交映射**（备份是各轮「改动前」快照，因此其内容等于上一轮的最终状态）：

| 备份文件 | 对应提交内容 |
|---|---|
| `backup-before-pg.html` | 提交 1：DBA 工作台基线 |
| `backup-before-oracle.html` | 提交 2：新增 PostgreSQL、MySQL 改绿 |
| `backup-before-mssql-other.html` | 提交 3：Oracle 官方图标 |
| `backup-before-other-linux.html` | 提交 4：SQL Server +「其他」官方图标 |
| `backup-before-normalize.html` | 提交 5：「其他」+ Linux（alpha mask） |
| （当前文件） | 提交 6：统一图标视觉尺寸 |

工作记忆与偏好记录在 `.workbuddy/memory/`（已纳入版本控制）。

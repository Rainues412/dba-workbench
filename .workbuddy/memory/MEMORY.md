# 项目长期记忆

## DBA 工作台

用户是一名 **DBA**，本工作区维护其个人「DBA 工作台」。

- 主文件：`ops-workbench.html`（单文件，CSS/JS 全内联，零外部依赖）
- 资料库页面节点：`yKeXCdqf9JT4DJ2JmpmBpY`
  - 编辑态：https://www.workbuddy.cn/space/d/yKeXCdqf9JT4DJ2JmpmBpY
  - 发布态：https://workbuddy.link/p/yKeXCdqf9JT4DJ2JmpmBpY
  - 改动后须用 `import_html.py --node-block-id <节点ID>` 覆盖导入 + `publish_page.py` 发布，**链接保持不变**
- 模块：仪表盘 / 脚本库 / 知识库 / 安装包 / 任务排期 / 客户通讯录 / 账号保险箱
- 仪表盘布局：左侧「处理中的故障」+「我的当前工作」，右侧「数据库类型分布」
- 数据库类型分布：7 类两列卡片，每张含图标胶囊（图标 + 名称）+ 进度条 + 数量

## 用户偏好（重要）

- **UI 参照**用户提供的 DBA 工作台截图：深色侧边栏 `#1e293b`、顶部搜索（Ctrl+K）、统计卡片行、圆角卡片、浅色内容区 `#f0f2f5`
- **脚本库 / 知识库 / 安装包分开**为三个独立模块，不要合并成"资源库"
- **图标用官方 logo 原图**，不用手绘替代品；用户会自己提供 PNG 文件
  - 已知取舍：Oracle 用的是文字 logo，20px 下不可辨，已向用户说明并**获得确认照原样使用**——不要再主动提议换成手绘图标
- **颜色是用户偏好，不是品牌色**：MySQL 被用户指定为绿色 `#16a34a`（非品牌蓝），PostgreSQL 用蓝 `#2563eb`。不要"纠正"回官方品牌色
- 每次改动前先读取 HTML 里的实际 `dbData[i].color`，不要凭记忆假设

## 图标处理

复用 user-level skill **`db-icon-recolor`**（`~/.workbuddy/skills/db-icon-recolor/`），
含 `recolor_icon.py` / `normalize_icon.py` / `inject_icon.py` / `verify_icon.py` / `regenerate_all.py` 五个脚本与 19 条踩坑记录。
处理任何数据库图标前先加载该 skill，不要重写逻辑。

关键约定：图标色必须等于该条目的 `color`（它同时驱动进度条和图标底框 `color+'15'`）；
新增条目须同步补 `darkColors[name]`（带空格的键如 `'SQL Server'` 要加引号）。

当前状态：7 类中 **6 类用官方 PNG 图标**（Oracle / MySQL / PostgreSQL / SQL Server / Linux / 其他），仅 **Redis** 是手绘线性 SVG。

**已统一视觉尺寸**：6 个 PNG 归一化为 256×256 画布 + 205px 图形（80%），最长边均为 16.02px；Redis SVG 用 `viewBox="2 1 20 20"` + `stroke-width="1.25"` 匹配同一比例。**不要单独归一化某一个图标**——尺寸只有相对兄弟图标才有意义，改一个会让它成为新的异类；必须整组一起处理，且 `--glyph` 取值一致。

`normalize_icon.py` 需要 **Pillow**（venv 解释器），其余四个脚本是纯标准库。

**处理模式不可按条目名缓存**——同一入口在不同轮次会切换：「其他」曾是 light_bg 光底 RGB（transparent），后换成 alpha-mask 调色板图（keepalpha）。每次都要从当前源文件重新推导。

**改了检测/管线逻辑后必须跑 `regenerate_all.py`** 全量逐字节比对（不是只重跑在调试的那张），确认已发布图标没有变成旧代参数。注意它需带 `--python <venv>`，因为它复现的是 recolor + normalize 完整管线。

**重采样会使上游验收失效**：recolor 后验过的图，经 normalize 的裁切/缩放/重贴可能重新引入同类缺陷，必须对最终进 base64 的文件重跑 `verify_icon.py`。

## 环境

- 系统 Python **无 PIL**；隔离 venv 在 `C:/Users/76879/.workbuddy/binaries/python/envs/default`，已装 Pillow 12.3.0（支持 WebP 解码、调色板 PNG 转 RGBA）
- Windows `C:\Windows\System32\convert` 是 **NTFS 工具，不是 ImageMagick**，禁止用于图片
- PowerShell `Add-Type`（WinRT 位图解码）被沙箱策略拦截，不要尝试
- bash 陷阱：Windows 绝对路径含 `C:` 冒号会破坏 `${f%%:*}` 参数展开，for 循环里别用冒号作分隔符
- `sha256sum` 对二进制模式文件会加 `\` 前缀，直接字符串比较会误判 FAIL；比对哈希改用 Python 读字节

## 版本控制

项目已建本地 git 仓库（`D:/coding/workspace/.git`，分支 `main`）。

- **`.gitattributes` 用 `* -text` 禁止行尾转换**，不可删改：`ops-workbench.html` 是纯 CRLF 且已发布线上，转换会让 checkout 副本与发布件不再逐字节一致，也会破坏 `regenerate_all.py` 的哈希比对。仓库级另设 `core.autocrlf=false`（但本地 config 不随克隆传播，以 `.gitattributes` 为准）
- 6 个源 PNG 已全部入库（含 `postgresql-icon.png`，此前只在桌面），仓库自包含，可直接跑 `regenerate_all.py`
- `.gitignore` 排除：`ops-workbench.backup-before-*.html`（内容已作为历史提交存在）、`nb64_*.txt` / `rc-*.png` / `*-norm.png`（可再生）、`db-icon-recolor.zip`（构建产物，源在仓库外的 skill 目录）
- **改完 `ops-workbench.html` 或 memory 后要提交**；提交前用 `git diff --stat` 确认改动范围符合预期
- 备份快照 → 提交的映射表记在 `README.md`，忽略备份后仍可追溯历史

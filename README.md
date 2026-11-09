# PushAll 消息中心

> **取数 → 模板 → 推送**
> 把 SQL / HTTP / 静态数据格式化后，推送到钉钉群、邮箱或任意 Webhook。

本地单机 · 插件化 · 系统托盘常驻 · GitHub Releases 自动更新

**当前版本：v0.1.9** ｜ Windows x64 便携版 ｜ Python 3.13 + FastAPI + Vue 3 + pywebview

---

## 目录

- [功能一览](#功能一览)
- [最近更新](#最近更新)
- [快速开始（Windows）](#快速开始windows)
- [桌面常驻模式](#桌面常驻模式推荐)
- [Windows 便携版](#windows-便携版解压即用)
- [自动更新](#自动更新)
- [使用流程](#使用流程)
- [模板](#模板)
- [内置插件](#内置插件)
- [开发插件](#开发插件)
- [HTTP 接口](#http-接口)
- [配置](#配置env)
- [安全与隐私](#安全与隐私)
- [推送前检查](#推送前检查)
- [测试](#测试)
- [目录结构](#目录结构)
- [发布新版本](#发布新版本)
- [维护节奏](#维护节奏)
- [路线图](#路线图)

---

## 功能一览

| 模块 | 能力 |
|---|---|
| 消息场景 | 数据源 + 模板 + 多个渠道 + 触发方式（手动 / cron / 外部 Webhook） |
| 数据源 | Oracle / MySQL / PostgreSQL / SQLite、HTTP 接口、静态 JSON，可保存复用 |
| 模板 | Jinja2 + Markdown，支持表格、计数、时间等；样例数据实时预览 |
| 下游 | 钉钉群机器人（加签、@成员）、SMTP 邮件、通用 Webhook |
| 调度 | APScheduler cron（5 段表达式，Asia/Shanghai）、立即运行、外部 POST 触发 |
| 可观测 | 每次执行记录取数 / 渲染 / 每个渠道的耗时与响应，支持查看与重发 |
| 插件化 | 数据源与下游均为插件，配置表单由 `schema.json` 自动生成 |
| 桌面端 | 窗口 + 系统托盘，关闭/最小化收进托盘，单实例，自动更新 |
| 本地优先 | 配置存本地 SQLite，敏感字段可加密，不依赖任何外部服务 |

---

## 最近更新

### v0.1.9
- 修复安装目录含中文时自动更新不生效（cmd/robocopy 编码问题）
- 更新改为新版本 exe 的 Python 更新模式，兼容中文路径

### v0.1.8
- 修复更新自动重启后插件列表为空的问题
- 窗口启动前等待本版本服务就绪；前端加载失败自动重试

### v0.1.7
- 修复打包版 Oracle 数据源提示 `No module named 'oracledb'`
- 内置 Oracle / MySQL / PostgreSQL 驱动（oracledb / pymysql / psycopg）

### v0.1.6
- 修复更新后旧进程未退出，导致仍显示旧版本 / 反复更新的问题
- 新版本会自动接管被旧实例占用的端口；服务启动失败会自动重试
- 退出流程增加强制结束兜底

### v0.1.5
- 更新代理开关切换时自动保存；测试连接成功后也会自动保存
- 启动日志记录更新代理状态，升级后可在 `logs/desktop.log` 核对

### v0.1.4
- 修复弹窗内按住鼠标拖选文字时，弹窗被误关闭的问题
- 点击遮罩关闭、取消按钮、右上角关闭保持原有行为

### v0.1.3
- 设置页新增「更新代理」：支持 HTTP / HTTPS / SOCKS5
- 代理仅用于检查与下载新版本，不影响数据源、钉钉、邮件等业务请求
- 支持用户名/密码、测试连接；密码不回显

### v0.1.2
- 检测到新版本时，更新弹窗直接展示该 Release 的更新说明（Markdown 自动转纯文本）
- 设置页「版本与更新」同步展示完整说明
- 修复打包配置 `packaging/PushAll.spec` 未被纳入版本库的问题

### v0.1.1
- 启动自动检查 GitHub Releases，托盘/设置页可手动检查
- 下载后 SHA256 校验，替换时保留 `data`、`plugins`、`logs` 并自动重启
- 支持本地安装包（`data/updates/`）与镜像（`PUSHALL_UPDATE_MIRROR`）

### v0.1.0
- 首个可用版本：场景、数据源、模板、钉钉/邮件渠道、cron、运行记录、插件体系
- Windows 便携版（内置 Python 运行时）+ 系统托盘常驻

---

## 快速开始（Windows）

```powershell
# 1. 创建虚拟环境并安装依赖
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. 开发调试启动
.\run.ps1
# 浏览器打开 http://127.0.0.1:8765
```

需要 Oracle / MySQL / PostgreSQL 时再安装驱动：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-db.txt
```

日常使用建议直接用桌面端，见下一节。

---

## 桌面常驻模式（推荐）

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\创建桌面快捷方式.ps1   # 生成桌面图标（只需一次）
```

之后双击桌面 `PushAll` 图标，或项目里的 `启动 PushAll.vbs`。

| 操作 | 效果 |
|---|---|
| 双击图标 | 启动并打开主界面；已运行时只唤回已有窗口 |
| 关闭窗口 / 最小化 | 收进系统托盘，程序继续运行 |
| 双击托盘图标 | 重新打开主界面 |
| 托盘右键 → 检查更新 | 手动检查 GitHub Releases |
| 托盘右键 → 重启服务 | 重启本地服务并刷新窗口 |
| 托盘右键 → 退出 | 停止服务并退出程序 |

日志：`logs\desktop.log`。托盘不可用时关闭窗口会直接退出，不会把程序“藏”起来。

---

## Windows 便携版（解压即用）

```powershell
.\packaging\build.ps1
```

产物：

- `dist\PushAll\`：可直接运行
- `dist\PushAll-<版本>-win64.zip`：拷到其他电脑解压即用
- `dist\PushAll-<版本>-win64.zip.sha256`：发布校验文件

内置 Python 运行时与数据库驱动（Oracle / MySQL / PostgreSQL），目标机器**不需要安装 Python**。`data\`（配置与运行记录）、`logs\`、`plugins\` 均在 exe 同目录，整个文件夹可随意搬移；退出托盘程序后删除文件夹即完成卸载。

> 首次运行 Windows 可能提示“未知发布者”，选择“更多信息 → 仍要运行”。目标机器缺少 WebView2 时会自动改用默认浏览器，托盘功能不受影响。

---

## 自动更新

- 启动 3 秒后自动检查 GitHub Releases（仓库公开，无需令牌）。
- 发现新版本时，弹窗展示 **版本号 + 该 Release 的更新说明**。
- 确认后下载 zip → 校验大小与 SHA256 → 退出并替换程序文件 → 自动重启。
- 只替换程序文件，`data`、`plugins`、`logs`、`.env` 原样保留。
- 托盘「检查更新」、设置页「版本与更新」可手动触发。
- 设置页「更新代理」可配置 HTTP / HTTPS / SOCKS5，仅作用于更新检查与下载；业务请求不受影响。

相关配置（`.env`）：

| 变量 | 默认 | 说明 |
|---|---|---|
| `PUSHALL_UPDATE_REPO` | `mryangguang/PushAll` | 更新来源仓库 |
| `PUSHALL_UPDATE_MIRROR` | 空 | 下载镜像，支持前缀或 `{url}` 模板 |
| `PUSHALL_UPDATE_DISABLED` | 空 | 设为 `1` 关闭启动自动检查 |

**网络受限时（GitHub 下载慢/超时）**：

1. 用浏览器手动下载 `PushAll-<版本>-win64.zip`；
2. 放到程序目录的 `data\updates\` 下（文件名与 Release 资产一致）；
3. 设置页点「下载并更新」，程序优先使用本地包并做 SHA256 校验。

---

## 使用流程

1. **数据源**：新建连接 → 填 SQL / 接口 → 点「测试取数」确认能取到数据。
2. **模板**：新建模板 → 写标题与 Markdown 正文 → 用示例数据预览。
3. **渠道**：新建钉钉机器人或邮箱 → 点「测试发送」确认能收到。
4. **场景**：选择数据源 / 模板 / 渠道，设置触发方式 → 保存 → 「预览」或「立即运行」。
5. **运行记录**：查看每一步耗时与响应；失败可一键重发。

---

## 模板

### 可用变量

| 变量 | 说明 |
|---|---|
| `{{ count }}` | 本次数据行数 |
| `{{ rows }}` | 数据列表（`list[dict]`） |
| `{{ rows \| md_table }}` | 渲染成 Markdown 表格 |
| `{{ scenario.name }}` | 场景名称 |
| `{{ run.started_at }}` | 开始时间 |
| `{{ run.trigger }}` | 触发方式 |
| `{{ payload }}` | 外部 Webhook 传入的 JSON |
| `{{ now() }}` | 当前时间（可接 `.strftime()`） |

常用过滤器：`md_table`、`kv_table`、`num`、`pct`、`date`、`tojson`、`truncate`。

### 示例

```jinja
### 库存预警
> {{ run.started_at }} · 共 {{ count }} 条

{{ rows | md_table }}

以上请及时处理。
```

---

## 内置插件

| ID | 类型 | 说明 | 权限 |
|---|---|---|---|
| `source.sql` | 数据源 | Oracle / MySQL / PostgreSQL / SQLite | database |
| `source.http` | 数据源 | REST 接口，支持请求头/参数/取值路径 | network |
| `source.static` | 数据源 | 内置 JSON，用于调试 | 无 |
| `sink.dingtalk` | 下游 | 钉钉群机器人（Markdown + 加签 + @） | network |
| `sink.email` | 下游 | SMTP 邮件（纯文本 + HTML） | network |
| `sink.webhook` | 下游 | 通用 Webhook，请求体支持模板 | network |

内置插件位于 `app/plugins/builtin/`，可在「插件」页禁用，不能删除。

---

## 开发插件

一个插件就是一个目录：

```
plugins/source_csv/
  manifest.json     # 元信息 + 入口 + 权限
  schema.json       # 配置表单（JSON Schema 子集）
  plugin.py         # 实现类
```

`manifest.json`：

```json
{
  "id": "source.csv",
  "type": "source",
  "name": "CSV 文件",
  "description": "读取本地 CSV",
  "version": "1.0.0",
  "entry": "plugin.py:CsvSource",
  "config_schema": "schema.json",
  "permissions": ["filesystem"]
}
```

`plugin.py`：

```python
from app.plugins.base import SourcePlugin, TestResult, RunContext

class CsvSource(SourcePlugin):
    id = "source.csv"

    def test(self, config: dict) -> TestResult:
        rows = self.fetch(config, RunContext())
        return TestResult(ok=True, message=f"{len(rows)} 行", rows=rows[:5], columns=list(rows[0].keys()))

    def fetch(self, config: dict, ctx: RunContext) -> list[dict]:
        ...
```

- 数据源实现 `fetch()`，返回 `list[dict]`；下游实现 `send(message, config, ctx)`。
- 表单由 `schema.json` 自动生成，支持 `string / integer / number / boolean / enum / code / password`。
- 密钥字段加 `"x-ui": {"secret": true}`，落库时会加密。
- 完整示例：`examples/plugin-csv/`，复制到 `plugins/` 刷新即可；也可在插件页上传 zip 安装。

---

## HTTP 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/meta` | 版本、时区、数据目录、调度任务 |
| GET | `/api/plugins` | 插件列表（含 schema） |
| POST | `/api/plugins/install` | 上传 zip 安装插件 |
| POST | `/api/plugins/{id}/enabled` | 启用/禁用 |
| GET/POST/PUT/DELETE | `/api/sources` | 数据源 CRUD |
| POST | `/api/sources/test` | 测试取数 |
| GET/POST/PUT/DELETE | `/api/channels` | 渠道 CRUD |
| POST | `/api/channels/test` | 测试发送 |
| GET/POST/PUT/DELETE | `/api/templates` | 模板 CRUD |
| POST | `/api/templates/preview` | 用样例数据渲染 |
| GET/POST/PUT/DELETE | `/api/scenarios` | 场景 CRUD |
| POST | `/api/scenarios/{id}/preview` | 只看不发的渲染 |
| POST | `/api/scenarios/{id}/run` | 立即执行 |
| POST | `/api/hooks/{id}` | 外部触发（JSON 作为 payload） |
| GET | `/api/runs` / `/api/runs/{id}` | 运行记录与步骤 |
| GET | `/api/cron/next?expr=` | 计算下次触发时间 |
| GET | `/api/update/check` | 查询最新 Release |
| GET/PUT | `/api/settings/update-proxy` | 读取/保存更新代理 |
| POST | `/api/settings/update-proxy/test` | 测试更新代理 |
| POST | `/api/update/install` | 桌面端触发下载安装 |
| POST | `/api/app/show` | 唤回已有桌面窗口 |
| GET | `/api/export` / POST `/api/import` | 配置导出/导入 |
| POST/GET | `/api/dev/echo` | 联调接收器（仅本地） |

设置 `PUSHALL_TOKEN` 后，所有 `/api` 请求需带 `X-Auth-Token` 或 `?token=`。

> 调度器与 SQLite 都在进程内，必须单进程运行，不要使用 `--workers` 多开。

---

## 配置（.env）

复制 `.env.example` 为 `.env`：

| 变量 | 默认 | 说明 |
|---|---|---|
| `PUSHALL_TZ` | Asia/Shanghai | 时区，影响 cron 与日志 |
| `PUSHALL_DATA_DIR` | ./data | SQLite 数据目录 |
| `PUSHALL_PLUGIN_DIR` | ./plugins | 用户插件目录 |
| `PUSHALL_MAX_ROWS` | 500 | 单次最大行数 |
| `PUSHALL_LOG_KEEP_DAYS` | 90 | 运行记录保留天数 |
| `PUSHALL_HTTP_TIMEOUT` | 20 | 内置 HTTP 默认超时 |
| `PUSHALL_TOKEN` | 空 | 访问令牌，空表示不校验 |
| `PUSHALL_SECRET_KEY` | 空 | 敏感字段加密密钥，设置后不可随意更换 |
| `PUSHALL_UPDATE_REPO` | mryangguang/PushAll | 更新来源仓库 |
| `PUSHALL_UPDATE_MIRROR` | 空 | 下载镜像 |
| `PUSHALL_UPDATE_DISABLED` | 空 | 设为 1 关闭启动检查 |

---

## 安全与隐私

- **本仓库是公开仓库**：只包含源代码、示例和文档，不包含任何真实业务数据、密钥或运行配置。
- 运行时数据（`data/`）、日志（`logs/`）、构建产物（`dist/`、`build/`）、用户插件（`plugins/*`）、`.env` 均在 `.gitignore` 中排除。
- 配置与运行记录只存在本机 SQLite；程序默认只监听 `127.0.0.1`，不对局域网/公网开放。
- 设置 `PUSHALL_SECRET_KEY` 后，webhook、密码等字段加密落库。
- 「导出配置」包含明文密钥，请妥善保管，不要提交到任何仓库。
- 插件在同进程运行，只安装可信来源的插件。
- 自动更新只从 GitHub Releases 下载，并做 SHA256 校验；也可用本地安装包离线更新。
- 更新代理的密码保存在本地 SQLite（设置 `PUSHALL_SECRET_KEY` 时加密），接口不会回显密码。

---

## 推送前检查

仓库自带两层检查，避免把敏感文件推到公开仓库：

**本地 pre-push 钩子**（每次 `git push` 自动运行）：

```powershell
.\tools\install_hooks.ps1   # 启用 .githooks/pre-push，只需一次
```

检查内容：

- 禁止目录：`.venv`、`data`、`logs`、`dist`、`build`、`__pycache__` 等
- 禁止类型：数据库、日志、压缩包、密钥、证书、Excel/CSV/PDF/Word 等
- 禁止文件名：`.env`、`id_rsa`、`credentials.*`、`secrets.*` 等
- 疑似密钥：钉钉 webhook token、私钥块、AWS/GitHub/OpenAI 风格密钥、硬编码密码
- 单文件超过 5 MB
- `--history` 额外扫描全部 git 历史

手动执行：

```powershell
.\.venv\Scripts\python.exe tools\security_check.py --history
```

**GitHub Actions**：`.github/workflows/security-check.yml` 在每次 push / PR 时再跑一遍（含历史扫描）。

---

## 测试

```powershell
# 端到端冒烟：插件 → 取数 → 渲染 → 推送 → 记录 → cron
.\.venv\Scripts\python.exe tools\smoke.py

# 更新流程：版本比较、Release 查询、SHA256、替换与数据保留
.\.venv\Scripts\python.exe tools\test_update.py --apply

# 敏感信息检查
.\.venv\Scripts\python.exe tools\security_check.py --history
```

`smoke.py` 会在临时目录启动隔离实例，不影响正式数据。

---

## 目录结构

```
PushAll/
├─ app/
│  ├─ main.py              # FastAPI 接口
│  ├─ runner.py            # 取数 → 渲染 → 推送
│  ├─ scheduler.py         # cron 调度
│  ├─ templating.py        # Jinja2 与过滤器
│  ├─ updater.py           # GitHub Releases 自动更新
│  ├─ db.py / crypto.py    # 存储与加密
│  ├─ plugins/             # 插件宿主 + 内置插件
│  └─ web/                 # 前端（Vue 3，免构建）
├─ plugins/                # 用户插件
├─ examples/plugin-csv/    # 插件示例
├─ packaging/              # PyInstaller 配置、构建与发布脚本
├─ tools/                  # 冒烟、更新、安全检查、钩子安装
├─ .githooks/pre-push      # 推送前安全检查
├─ .github/workflows/      # GitHub Actions
├─ desktop.py              # 桌面端：窗口 + 托盘 + 单实例
├─ 启动 PushAll.vbs        # 双击启动（无控制台）
├─ 创建桌面快捷方式.ps1     # 生成桌面图标
├─ run.ps1 / run.sh        # 命令行启动
└─ docs/DESIGN.md          # 完整设计稿
```

---

## 发布新版本

1. 修改 `app/settings.py` 中的 `VERSION`；
2. 运行 `.\packaging\release.ps1`（自动打包、打 tag、创建/更新 GitHub Release，并上传 zip 与 sha256）。

Release 标题统一为 `PushAll vX.Y.Z`（英文，不加“便携版”等后缀），正文默认中文；可用 `-NotesFile` 指定说明文件，`-DryRun` 只预览不发布。

预览将要发布的内容：

```powershell
.\packaging\release.ps1 -DryRun
```

---

## 维护节奏

每累计约 **10 次提交**，按最新内容整理一次 GitHub About 与 README：

```powershell
.\.venv\Scripts\python.exe tools\readme_status.py
```

- 计数配置：`.github/project-meta.json` 的 `last_readme_refresh`
- pre-push 钩子会自动提示（不阻塞推送）
- 整理内容：版本号、最近更新、功能清单、安全说明、目录结构、路线图

---

## 路线图

- 企业微信 / 飞书 / 钉钉工作通知插件
- 条件路由与渠道组、失败队列与补发
- 流程画布（节点式编排）
- 多用户与权限
- 消息去重与限流
- macOS / Linux 打包








# PushAll 消息中心

> 本地单机版 · 取数 → 模板 → 推送
> 一个把 SQL / HTTP 数据格式化后送到钉钉群、邮箱的工具，来源与下游均可通过插件扩展。

---

## 功能一览

- **消息场景**：一个场景 = 一个数据源 + 一个模板 + 若干推送渠道 + 一种触发方式（手动 / cron / 外部 Webhook）。
- **数据源**：Oracle / MySQL / PostgreSQL / SQLite / HTTP 接口 / 静态数据，可保存复用。
- **模板**：Jinja2 语法 + Markdown 正文，支持表格、计数、时间等；带样例数据实时预览。
- **下游**：钉钉群机器人（支持加签、@成员）、SMTP 邮件；另带通用 Webhook 便于联调与对接自建系统。
- **调度**：APScheduler cron（5 段表达式，时区 Asia/Shanghai），支持立即运行与外部 POST 触发。
- **可观测**：每次执行记录取数、渲染、每个渠道的耗时与响应原文，支持查看与重发。
- **插件化**：数据源与下游都是插件；插件自带 `manifest.json` + `schema.json` + `plugin.py`，配置表单由 schema 自动生成，新增插件不用改主程序。
- **本地优先**：配置存本地 SQLite；可选用系统密钥加密敏感字段；不依赖任何外部服务。

---

## 快速开始（Windows）

```powershell
# 1. 安装依赖
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. 启动（开发调试用）
.\run.ps1
# 浏览器打开 http://127.0.0.1:8765

# 日常使用：双击桌面图标的 PushAll（见「桌面常驻模式」）
```

需要 Oracle / MySQL / PostgreSQL 时再安装驱动：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-db.txt
```

### 桌面常驻模式（推荐）

安装一次桌面依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
```

然后任选一种方式启动：

- **双击桌面图标 `PushAll`**（首次可运行 `.\创建桌面快捷方式.ps1` 生成）
- **双击项目里的 `启动 PushAll.vbs`**（无控制台窗口）

运行行为：

| 操作 | 效果 |
|---|---|
| 双击图标 | 启动并打开主界面；已运行时只唤回已有窗口 |
| 关闭窗口 / 最小化 | 收进系统托盘，程序继续运行 |
| 双击托盘图标 | 重新打开主界面 |
| 托盘右键 → 打开主界面 | 重新打开主界面 |
| 托盘右键 → 重启服务 | 重启本地服务并刷新窗口 |
| 托盘右键 → 退出 | 停止服务并退出程序 |

日志：`logs\desktop.log`。如果托盘启动失败，关闭窗口会直接退出，不会把程序"藏"起来。

### Windows 便携版（解压即用）

```powershell
.\packaging\build.ps1
```

产物：

- `dist\PushAll\`：可直接运行
- `dist\PushAll-<版本>-win64.zip`：拷到其他电脑解压即用

内置 Python 运行时，目标机器**不需要安装 Python**。`data\`（配置与运行记录）、`logs\`、`plugins\` 都在 exe 同目录，整个文件夹可随意搬移；退出托盘程序后删除文件夹即完成卸载。

> 首次运行 Windows 可能提示“未知发布者”，选择“更多信息 → 仍要运行”。若目标机器缺少 WebView2，程序会自动改用默认浏览器打开，托盘功能不受影响。
### 自动更新

- 启动 3 秒后自动检查 GitHub Releases（仓库公开，无需令牌），托盘和设置页也可手动「检查更新」。
- 发现新版本会弹窗询问 → 下载 zip → SHA256 校验 → 退出并替换程序文件 → 自动重启。
- 只替换程序文件，`data`、`plugins`、`logs` 原样保留。
- 可在 `.env` 设置 `PUSHALL_UPDATE_REPO`（默认 `mryangguang/PushAll`）、`PUSHALL_UPDATE_MIRROR`（下载镜像）、`PUSHALL_UPDATE_DISABLED=1`（关闭自动检查）。

**网络受限时（GitHub 下载慢/超时）**：

1. 用浏览器手动下载 `PushAll-<版本>-win64.zip`；
2. 放到程序目录的 `data\updates\` 下（文件名与 Release 资产一致）；
3. 打开设置页点「下载并更新」，程序会优先使用本地安装包并做 SHA256 校验。

### macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./run.sh
```

---

## 使用流程

1. **数据源**：新建连接 → 填 SQL / 接口 → 点「测试取数」确认能取到数据。
2. **模板**：新建模板 → 写标题与 Markdown 正文 → 用示例数据预览。
3. **渠道**：新建钉钉机器人或邮箱 → 点「测试发送」确认能收到。
4. **场景**：选择数据源/模板/渠道，设置触发方式 → 保存 → 「预览」或「立即运行」。
5. **运行记录**：查看每一步耗时与响应；失败可一键重发。

### 模板可用变量

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

示例：

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

插件就是一个目录：

```
plugins/source_csv/
  manifest.json     # 元信息 + 入口
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

- 数据源实现 `fetch()`，返回 `list[dict]`。
- 下游实现 `send(message, config, ctx)`，返回 `SendResult(ok=..., message=...)`。
- 表单由 `schema.json` 自动生成，支持 `string / integer / number / boolean / enum / code / password`，密钥字段加 `"x-ui": {"secret": true}`。
- 完整可运行示例见 `examples/plugin-csv/`，复制到 `plugins/` 下刷新即可。
- 也可以把插件目录打成 zip，在「插件」页点「安装插件」上传。

---

## HTTP 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/meta` | 版本、时区、调度任务 |
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
| GET | `/api/export` / POST `/api/import` | 配置导出/导入 |
| POST/GET | `/api/dev/echo` | 联调接收器（仅本地使用） |

设置 `PUSHALL_TOKEN` 后，所有 `/api` 请求需带 `X-Auth-Token` 或 `?token=`。

> 注意：调度器与 SQLite 都在进程内，必须单进程运行，不要使用 `--workers` 多开。

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

---

## 安全说明

- 默认只监听 `127.0.0.1`，不对外网开放。
- 设置 `PUSHALL_SECRET_KEY` 后，webhook、密码等字段会加密写入 SQLite。
- 「导出配置」包含明文密钥，请妥善保管。
- 插件在同进程运行，只应安装可信来源的插件；生产环境建议只启用必要插件。

---

## 测试

```powershell
.\.venv\Scripts\python.exe tools\smoke.py
```

会在临时目录启动一个隔离实例，验证：插件加载 → SQL 取数 → 模板渲染 → Webhook 推送 → 运行记录 → cron 计算。

---

## 目录结构

```
PushAll/
├─ app/
│  ├─ main.py              # FastAPI 接口
│  ├─ runner.py            # 取数 → 渲染 → 推送
│  ├─ scheduler.py         # cron 调度
│  ├─ templating.py        # Jinja2 与过滤器
│  ├─ db.py / crypto.py    # 存储与加密
│  ├─ plugins/             # 插件宿主 + 内置插件
│  └─ web/                 # 前端（Vue 3，免构建）
├─ plugins/                # 用户插件
├─ examples/plugin-csv/    # 插件示例
├─ tools/smoke.py          # 冒烟测试
├─ packaging/              # PyInstaller 打包配置与构建脚本
├─ desktop.py              # 桌面端：窗口 + 托盘 + 单实例
├─ 启动 PushAll.vbs        # 双击启动（无控制台窗口）
├─ 创建桌面快捷方式.ps1     # 生成带图标的桌面快捷方式
├─ run.ps1 / run.sh        # 命令行启动脚本
└─ docs/DESIGN.md          # 完整设计稿
```

---

## 当前范围与后续

**v0.1（当前）**：单机、钉钉群机器人 + 邮件、6 个内置插件、cron/手动/Webhook 触发、完整运行记录、配置导出导入。

**后续可加**：

- 企业微信 / 飞书 / 钉钉工作通知插件
- 条件路由与渠道组、失败队列与补发
- 流程画布（节点式编排）
- 多用户与权限
- 消息去重与限流
- 打包为 Windows / macOS / Linux 安装包


---

## 打包为桌面应用

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
pyinstaller --noconfirm --windowed --name PushAll `
  --add-data "app/web;app/web" `
  --add-data "app/plugins/builtin;app/plugins/builtin" `
  desktop.py
```

- macOS / Linux 把 `--add-data` 的分号改成冒号（`app/web:app/web`）。
- 首次打包后建议在无 Python 环境的机器上验证一遍；`plugins/` 与 `data/` 会生成在可执行文件旁。
- 数据库驱动（oracledb / pymysql / psycopg）需按目标环境一起打包或在插件中延迟导入。






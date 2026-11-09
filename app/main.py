"""PushAll 消息中心 · HTTP 接口与静态界面。"""

from __future__ import annotations

import json
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime
from threading import Lock

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import crypto, db, runner, scheduler, settings, templating
from .plugins import loader
from .plugins.loader import PluginError

WEB_DIR = settings.WEB_DIR

_echo_lock = Lock()
_echo_log: deque = deque(maxlen=50)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    db.init_db()
    loader.all_plugins(force=True)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if settings.API_TOKEN and request.url.path.startswith("/api"):
        token = request.headers.get("x-auth-token") or request.query_params.get("token")
        if token != settings.API_TOKEN:
            return JSONResponse({"detail": "未授权：缺少或错误的访问令牌"}, status_code=401)
    return await call_next(request)


# ---------------- 模型 ----------------

class SourceIn(BaseModel):
    name: str = Field(min_length=1)
    plugin_id: str
    config: dict = Field(default_factory=dict)


class ChannelIn(BaseModel):
    name: str = Field(min_length=1)
    plugin_id: str
    config: dict = Field(default_factory=dict)


class TemplateIn(BaseModel):
    name: str = Field(min_length=1)
    title_tpl: str = ""
    body_tpl: str = ""


class ScenarioIn(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    enabled: bool = True
    source_id: int | None = None
    template_id: int | None = None
    channel_ids: list[int] = Field(default_factory=list)
    schedule_mode: str = "manual"
    cron: str = ""
    options: dict = Field(default_factory=dict)


class ConfigTestIn(BaseModel):
    plugin_id: str
    config: dict = Field(default_factory=dict)


class EnabledIn(BaseModel):
    enabled: bool


# ---------------- 序列化 ----------------

def _loads(raw: str | None, default):
    try:
        return json.loads(raw) if raw else default
    except json.JSONDecodeError:
        return default


def _source_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "plugin_id": row["plugin_id"],
        "config": crypto.loads(row.get("config_json")),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _channel_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "plugin_id": row["plugin_id"],
        "config": crypto.loads(row.get("config_json")),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _template_out(row: dict) -> dict:
    return dict(row)


def _scenario_out(row: dict, sources: dict, templates: dict, channels: dict) -> dict:
    channel_ids = _loads(row.get("channel_ids"), [])
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "enabled": bool(row["enabled"]),
        "source_id": row["source_id"],
        "template_id": row["template_id"],
        "channel_ids": channel_ids,
        "schedule_mode": row["schedule_mode"],
        "cron": row["cron"],
        "options": _loads(row.get("options_json"), {}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_run_at": row["last_run_at"],
        "last_status": row["last_status"],
        "source_name": (sources.get(row["source_id"]) or {}).get("name", ""),
        "template_name": (templates.get(row["template_id"]) or {}).get("name", ""),
        "channel_names": [(channels.get(cid) or {}).get("name", f"#{cid}") for cid in channel_ids],
    }


def _row_or_404(table: str, row_id: int) -> dict:
    row = db.fetch_one(table, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    return row


def _check_plugin(plugin_id: str, expected_type: str) -> loader.Plugin:
    plugin = loader.get_plugin(plugin_id)
    if not plugin:
        raise HTTPException(status_code=400, detail=f"插件不存在：{plugin_id}")
    if plugin.error:
        raise HTTPException(status_code=400, detail=f"插件不可用：{plugin.error}")
    if plugin.type != expected_type:
        raise HTTPException(status_code=400, detail=f"插件类型不匹配，需要 {expected_type}")
    return plugin


def _validate_config(plugin_id: str, config: dict) -> None:
    try:
        loader.check_config(plugin_id, config)
    except PluginError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _validate_cron(expr: str) -> None:
    error = scheduler.validate(expr)
    if error:
        raise HTTPException(status_code=400, detail=f"cron 表达式不合法：{error}")


# ---------------- 元信息 ----------------

@app.get("/api/health")
def health():
    return {"ok": True, "app": settings.APP_NAME, "version": settings.VERSION}


@app.post("/api/app/show")
def app_show():
    """桌面端单实例：把已运行的窗口唤到前台。服务模式返回 409。"""
    callback = getattr(app.state, "show_window", None)
    if not callback:
        raise HTTPException(status_code=409, detail="当前为服务模式，没有桌面窗口")
    callback()
    return {"ok": True}


@app.get("/api/update/check")
def update_check():
    from . import updater

    return updater.check_latest()


@app.post("/api/update/install")
def update_install():
    """桌面端：触发下载并安装更新（会有原生确认弹窗）。"""
    callback = getattr(app.state, "update_now", None)
    if not callback:
        raise HTTPException(status_code=409, detail="当前为服务模式，请在桌面端检查更新")
    callback()
    return {"ok": True}


@app.get("/api/meta")
def meta():
    jobs = []
    if scheduler._scheduler:
        for job in scheduler._scheduler.get_jobs():
            if job.id.startswith("scenario:"):
                jobs.append(
                    {
                        "scenario_id": int(job.id.split(":", 1)[1]),
                        "next_run": job.next_run_time.strftime("%Y-%m-%d %H:%M:%S") if job.next_run_time else "",
                    }
                )
    return {
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "timezone": settings.TIMEZONE,
        "data_dir": str(settings.DATA_DIR),
        "plugin_dir": str(settings.PLUGIN_DIR),
        "secret_enabled": crypto.enabled(),
        "frozen": settings.FROZEN,
        "jobs": jobs,
    }


@app.get("/api/cron/next")
def cron_next(expr: str):
    error = scheduler.validate(expr)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return {"next": scheduler.next_runs(expr, 3)}


# ---------------- 插件 ----------------

@app.get("/api/plugins")
def plugins():
    return loader.list_public()


@app.post("/api/plugins/install")
async def install_plugin(file: UploadFile = File(...)):
    data = await file.read()
    try:
        manifest = loader.install_zip(data)
    except PluginError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "manifest": manifest}


@app.post("/api/plugins/{plugin_id}/enabled")
def enable_plugin(plugin_id: str, body: EnabledIn):
    if not loader.get_plugin(plugin_id):
        raise HTTPException(status_code=404, detail="插件不存在")
    db.set_plugin_enabled(plugin_id, body.enabled)
    return {"ok": True}


@app.delete("/api/plugins/{plugin_id}")
def remove_plugin(plugin_id: str):
    sources = [r for r in db.fetch_all("source") if r["plugin_id"] == plugin_id]
    channels = [r for r in db.fetch_all("channel") if r["plugin_id"] == plugin_id]
    used = [r["name"] for r in sources + channels]
    if used:
        raise HTTPException(status_code=400, detail=f"插件仍被使用：{'、'.join(used)}")
    try:
        loader.delete_plugin(plugin_id)
    except PluginError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


# ---------------- 数据源 ----------------

@app.get("/api/sources")
def list_sources():
    return [_source_out(row) for row in db.fetch_all("source")]


@app.post("/api/sources")
def create_source(body: SourceIn):
    _check_plugin(body.plugin_id, "source")
    _validate_config(body.plugin_id, body.config)
    now = db.now_text()
    row_id = db.insert(
        "source",
        {
            "name": body.name.strip(),
            "plugin_id": body.plugin_id,
            "config_json": crypto.dumps(body.config),
            "created_at": now,
            "updated_at": now,
        },
    )
    return _source_out(_row_or_404("source", row_id))


@app.put("/api/sources/{source_id}")
def update_source(source_id: int, body: SourceIn):
    _row_or_404("source", source_id)
    _check_plugin(body.plugin_id, "source")
    _validate_config(body.plugin_id, body.config)
    db.update(
        "source",
        source_id,
        {
            "name": body.name.strip(),
            "plugin_id": body.plugin_id,
            "config_json": crypto.dumps(body.config),
            "updated_at": db.now_text(),
        },
    )
    return _source_out(_row_or_404("source", source_id))


@app.delete("/api/sources/{source_id}")
def delete_source(source_id: int):
    _row_or_404("source", source_id)
    used = db.source_usage(source_id)
    if used:
        raise HTTPException(status_code=400, detail=f"该数据源被以下场景使用：{'、'.join(used)}")
    db.delete("source", source_id)
    return {"ok": True}


@app.post("/api/sources/test")
def test_source(body: ConfigTestIn):
    plugin = _check_plugin(body.plugin_id, "source")
    try:
        result = plugin.instance.test(body.config)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
    return {
        "ok": result.ok,
        "message": result.message,
        "rows": result.rows or [],
        "columns": result.columns or [],
        "detail": result.detail or {},
    }


# ---------------- 渠道 ----------------

@app.get("/api/channels")
def list_channels():
    return [_channel_out(row) for row in db.fetch_all("channel")]


@app.post("/api/channels")
def create_channel(body: ChannelIn):
    _check_plugin(body.plugin_id, "sink")
    _validate_config(body.plugin_id, body.config)
    now = db.now_text()
    row_id = db.insert(
        "channel",
        {
            "name": body.name.strip(),
            "plugin_id": body.plugin_id,
            "config_json": crypto.dumps(body.config),
            "created_at": now,
            "updated_at": now,
        },
    )
    return _channel_out(_row_or_404("channel", row_id))


@app.put("/api/channels/{channel_id}")
def update_channel(channel_id: int, body: ChannelIn):
    _row_or_404("channel", channel_id)
    _check_plugin(body.plugin_id, "sink")
    _validate_config(body.plugin_id, body.config)
    db.update(
        "channel",
        channel_id,
        {
            "name": body.name.strip(),
            "plugin_id": body.plugin_id,
            "config_json": crypto.dumps(body.config),
            "updated_at": db.now_text(),
        },
    )
    return _channel_out(_row_or_404("channel", channel_id))


@app.delete("/api/channels/{channel_id}")
def delete_channel(channel_id: int):
    _row_or_404("channel", channel_id)
    used = db.channel_usage(channel_id)
    if used:
        raise HTTPException(status_code=400, detail=f"该渠道被以下场景使用：{'、'.join(used)}")
    db.delete("channel", channel_id)
    return {"ok": True}


@app.post("/api/channels/test")
def test_channel(body: ConfigTestIn):
    plugin = _check_plugin(body.plugin_id, "sink")
    _validate_config(body.plugin_id, body.config)
    try:
        result = plugin.instance.test(body.config)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"{type(exc).__name__}: {exc}"}
    return {"ok": result.ok, "message": result.message, "detail": result.detail or {}}


# ---------------- 模板 ----------------

@app.get("/api/templates")
def list_templates():
    return [_template_out(row) for row in db.fetch_all("template")]


@app.post("/api/templates")
def create_template(body: TemplateIn):
    now = db.now_text()
    row_id = db.insert(
        "template",
        {
            "name": body.name.strip(),
            "title_tpl": body.title_tpl,
            "body_tpl": body.body_tpl,
            "created_at": now,
            "updated_at": now,
        },
    )
    return _row_or_404("template", row_id)


@app.put("/api/templates/{template_id}")
def update_template(template_id: int, body: TemplateIn):
    _row_or_404("template", template_id)
    db.update(
        "template",
        template_id,
        {
            "name": body.name.strip(),
            "title_tpl": body.title_tpl,
            "body_tpl": body.body_tpl,
            "updated_at": db.now_text(),
        },
    )
    return _row_or_404("template", template_id)


@app.delete("/api/templates/{template_id}")
def delete_template(template_id: int):
    _row_or_404("template", template_id)
    used = db.template_usage(template_id)
    if used:
        raise HTTPException(status_code=400, detail=f"该模板被以下场景使用：{'、'.join(used)}")
    db.delete("template", template_id)
    return {"ok": True}


class TemplatePreviewIn(BaseModel):
    title_tpl: str = ""
    body_tpl: str = ""
    rows: list[dict] = Field(default_factory=list)


@app.post("/api/templates/preview")
def preview_template(body: TemplatePreviewIn):
    scenario = {"id": 0, "name": "示例场景", "description": ""}
    ctx = templating.build_context(body.rows, scenario, "preview", {})
    title = templating.render(body.title_tpl or templating.DEFAULT_TITLE, ctx).strip()
    content = templating.render(body.body_tpl or templating.DEFAULT_BODY, ctx).strip()
    return {"title": title, "content": content, "count": len(body.rows)}


# ---------------- 场景 ----------------

def _scenario_list() -> list[dict]:
    sources = {row["id"]: row for row in db.fetch_all("source")}
    templates = {row["id"]: row for row in db.fetch_all("template")}
    channels = {row["id"]: row for row in db.fetch_all("channel")}
    return [_scenario_out(row, sources, templates, channels) for row in db.fetch_all("scenario")]


@app.get("/api/scenarios")
def list_scenarios():
    return _scenario_list()


@app.get("/api/scenarios/{scenario_id}")
def get_scenario(scenario_id: int):
    for item in _scenario_list():
        if item["id"] == scenario_id:
            return item
    raise HTTPException(status_code=404, detail="场景不存在")


@app.post("/api/scenarios")
def create_scenario(body: ScenarioIn):
    _validate_scenario(body)
    now = db.now_text()
    row_id = db.insert(
        "scenario",
        {
            "name": body.name.strip(),
            "description": body.description,
            "enabled": 1 if body.enabled else 0,
            "source_id": body.source_id,
            "template_id": body.template_id,
            "channel_ids": json.dumps(body.channel_ids),
            "schedule_mode": body.schedule_mode,
            "cron": body.cron.strip(),
            "options_json": json.dumps(body.options, ensure_ascii=False),
            "created_at": now,
            "updated_at": now,
        },
    )
    scheduler.sync()
    return get_scenario(row_id)


@app.put("/api/scenarios/{scenario_id}")
def update_scenario(scenario_id: int, body: ScenarioIn):
    _row_or_404("scenario", scenario_id)
    _validate_scenario(body)
    db.update(
        "scenario",
        scenario_id,
        {
            "name": body.name.strip(),
            "description": body.description,
            "enabled": 1 if body.enabled else 0,
            "source_id": body.source_id,
            "template_id": body.template_id,
            "channel_ids": json.dumps(body.channel_ids),
            "schedule_mode": body.schedule_mode,
            "cron": body.cron.strip(),
            "options_json": json.dumps(body.options, ensure_ascii=False),
            "updated_at": db.now_text(),
        },
    )
    scheduler.sync()
    return get_scenario(scenario_id)


@app.delete("/api/scenarios/{scenario_id}")
def delete_scenario(scenario_id: int):
    _row_or_404("scenario", scenario_id)
    db.delete_scenario(scenario_id)
    scheduler.sync()
    return {"ok": True}


@app.post("/api/scenarios/{scenario_id}/duplicate")
def duplicate_scenario(scenario_id: int):
    row = _row_or_404("scenario", scenario_id)
    body = ScenarioIn(
        name=f"{row['name']} 副本",
        description=row["description"],
        enabled=False,
        source_id=row["source_id"],
        template_id=row["template_id"],
        channel_ids=_loads(row["channel_ids"], []),
        schedule_mode=row["schedule_mode"],
        cron=row["cron"],
        options=_loads(row["options_json"], {}),
    )
    return create_scenario(body)


def _validate_scenario(body: ScenarioIn) -> None:
    if body.source_id is not None:
        _row_or_404("source", body.source_id)
    if body.template_id is not None:
        _row_or_404("template", body.template_id)
    for channel_id in body.channel_ids:
        _row_or_404("channel", channel_id)
    if body.schedule_mode not in ("manual", "cron", "webhook"):
        raise HTTPException(status_code=400, detail="调度方式不合法")
    if body.schedule_mode == "cron":
        if not body.cron.strip():
            raise HTTPException(status_code=400, detail="定时模式需要填写 cron 表达式")
        _validate_cron(body.cron)


@app.post("/api/scenarios/{scenario_id}/preview")
async def preview_scenario(scenario_id: int, request: Request):
    payload = {}
    try:
        raw = await request.body()
        if raw:
            payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {}
    try:
        return runner.preview(scenario_id, payload)
    except runner.ScenarioError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/scenarios/{scenario_id}/run")
def run_scenario(scenario_id: int):
    try:
        return runner.run(scenario_id, trigger="manual")
    except runner.ScenarioError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/hooks/{scenario_id}")
async def webhook_trigger(scenario_id: int, request: Request):
    scenario = _row_or_404("scenario", scenario_id)
    if not scenario["enabled"]:
        raise HTTPException(status_code=400, detail="场景已停用")
    payload = {}
    raw = await request.body()
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw.decode("utf-8", errors="ignore")}
    return runner.run(scenario_id, trigger="webhook", payload=payload if isinstance(payload, dict) else {"data": payload})


# ---------------- 运行记录 ----------------

@app.get("/api/runs")
def list_runs(scenario_id: int | None = None, limit: int = 50, offset: int = 0):
    limit = max(1, min(limit, 200))
    return db.list_runs(scenario_id, limit, offset)


@app.get("/api/runs/{run_id}")
def get_run(run_id: int):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="运行记录不存在")
    run["steps"] = db.get_steps(run_id)
    return run


# ---------------- 导入导出 ----------------

def _scenario_export(row: dict) -> dict:
    return {
        "name": row["name"],
        "description": row["description"],
        "enabled": bool(row["enabled"]),
        "source_id": row["source_id"],
        "template_id": row["template_id"],
        "channel_ids": _loads(row["channel_ids"], []),
        "schedule_mode": row["schedule_mode"],
        "cron": row["cron"],
        "options": _loads(row["options_json"], {}),
    }


@app.get("/api/export")
def export_data():
    return {
        "version": settings.VERSION,
        "exported_at": db.now_text(),
        "sources": [_source_out(row) for row in db.fetch_all("source")],
        "channels": [_channel_out(row) for row in db.fetch_all("channel")],
        "templates": [dict(row) for row in db.fetch_all("template")],
        "scenarios": [_scenario_export(row) for row in db.fetch_all("scenario")],
    }


@app.post("/api/import")
def import_data(data: dict):
    source_map: dict[int, int] = {}
    template_map: dict[int, int] = {}
    channel_map: dict[int, int] = {}
    now = db.now_text()
    try:
        for item in data.get("sources", []):
            new_id = db.insert(
                "source",
                {
                    "name": item.get("name", "导入的数据源"),
                    "plugin_id": item.get("plugin_id", ""),
                    "config_json": crypto.dumps(item.get("config", {})),
                    "created_at": now,
                    "updated_at": now,
                },
            )
            source_map[item.get("id")] = new_id
        for item in data.get("channels", []):
            new_id = db.insert(
                "channel",
                {
                    "name": item.get("name", "导入的渠道"),
                    "plugin_id": item.get("plugin_id", ""),
                    "config_json": crypto.dumps(item.get("config", {})),
                    "created_at": now,
                    "updated_at": now,
                },
            )
            channel_map[item.get("id")] = new_id
        for item in data.get("templates", []):
            new_id = db.insert(
                "template",
                {
                    "name": item.get("name", "导入的模板"),
                    "title_tpl": item.get("title_tpl", ""),
                    "body_tpl": item.get("body_tpl", ""),
                    "created_at": now,
                    "updated_at": now,
                },
            )
            template_map[item.get("id")] = new_id
        for item in data.get("scenarios", []):
            db.insert(
                "scenario",
                {
                    "name": item.get("name", "导入的场景"),
                    "description": item.get("description", ""),
                    "enabled": 0,
                    "source_id": source_map.get(item.get("source_id")),
                    "template_id": template_map.get(item.get("template_id")),
                    "channel_ids": json.dumps([channel_map[c] for c in item.get("channel_ids", []) if c in channel_map]),
                    "schedule_mode": item.get("schedule_mode", "manual"),
                    "cron": item.get("cron", ""),
                    "options_json": json.dumps(item.get("options", {}), ensure_ascii=False),
                    "created_at": now,
                    "updated_at": now,
                },
            )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"导入失败：{exc}") from exc
    scheduler.sync()
    return {"ok": True, "scenarios": len(data.get("scenarios", []))}


# ---------------- 联调辅助 ----------------

@app.post("/api/dev/echo")
async def dev_echo(request: Request):
    raw = await request.body()
    try:
        body = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        body = raw.decode("utf-8", errors="ignore")
    item = {
        "received_at": db.now_text(),
        "content_type": request.headers.get("content-type", ""),
        "headers": dict(request.headers),
        "body": body,
    }
    with _echo_lock:
        _echo_log.appendleft(item)
    return {"ok": True, "received": len(_echo_log)}


@app.get("/api/dev/echo")
def dev_echo_list():
    with _echo_lock:
        return list(_echo_log)


# ---------------- 静态界面 ----------------

if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/")
def index():
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse({"detail": "前端文件缺失"}, status_code=500)






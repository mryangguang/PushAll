"""场景执行器：取数 → 渲染 → 推送 → 记录。"""

from __future__ import annotations

import json
import threading
import time
import traceback
from typing import Any

from . import crypto, db, templating
from .plugins import loader
from .plugins.base import RunContext, SendResult


class ScenarioError(Exception):
    pass


_locks: dict[int, threading.Lock] = {}
_guard = threading.Lock()


def _lock_for(scenario_id: int) -> threading.Lock:
    with _guard:
        if scenario_id not in _locks:
            _locks[scenario_id] = threading.Lock()
        return _locks[scenario_id]


def _json(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _build_message(scenario: dict, rows: list[dict], trigger: str, payload: dict | None):
    template_row = db.fetch_one("template", scenario.get("template_id") or 0)
    context = templating.build_context(rows, scenario, trigger, payload)

    title_tpl = (template_row or {}).get("title_tpl") or templating.DEFAULT_TITLE
    body_tpl = (template_row or {}).get("body_tpl") or templating.DEFAULT_BODY

    title = templating.render(title_tpl, context).strip() or scenario.get("name", "PushAll 通知")
    content = templating.render(body_tpl, context).strip()
    return title, content, context, template_row


def _load_source(scenario: dict) -> tuple[dict, Any, dict]:
    source = db.fetch_one("source", scenario.get("source_id") or 0)
    if not source:
        raise ScenarioError("场景未配置数据源，或数据源已被删除")
    plugin = loader.get_plugin(source["plugin_id"])
    if not plugin or not plugin.ok:
        raise ScenarioError(f"数据源插件不可用：{source['plugin_id']} {getattr(plugin, 'error', '')}")
    if plugin.id in db.disabled_plugin_ids():
        raise ScenarioError(f"数据源插件已禁用：{plugin.name}")
    config = crypto.loads(source.get("config_json"))
    return source, plugin, config


def _load_channels(scenario: dict) -> list[tuple[dict, Any, dict]]:
    ids = _json(scenario.get("channel_ids"), [])
    result = []
    for channel_id in ids:
        channel = db.fetch_one("channel", int(channel_id))
        if not channel:
            continue
        plugin = loader.get_plugin(channel["plugin_id"])
        config = crypto.loads(channel.get("config_json"))
        result.append((channel, plugin, config))
    return result


def fetch_rows(scenario: dict, trigger: str = "manual") -> tuple[list[dict], int, dict]:
    source, plugin, config = _load_source(scenario)
    ctx = RunContext(scenario=scenario, trigger=trigger)
    started = time.perf_counter()
    rows = plugin.instance.fetch(config, ctx)
    if not isinstance(rows, list):
        raise ScenarioError("数据源插件返回值不是数据列表")
    duration = int((time.perf_counter() - started) * 1000)
    meta = {"source": source["name"], "plugin": plugin.id, "duration_ms": duration}
    return rows, duration, meta


def preview(scenario_id: int, payload: dict | None = None) -> dict:
    scenario = db.fetch_one("scenario", scenario_id)
    if not scenario:
        raise ScenarioError("场景不存在")

    steps: list[dict] = []
    started = time.perf_counter()

    try:
        rows, duration, meta = fetch_rows(scenario)
    except Exception as exc:  # noqa: BLE001
        raise ScenarioError(str(exc)) from exc
    steps.append(
        {
            "seq": 1,
            "step": "fetch",
            "name": f"取数 · {meta['source']}",
            "status": "success",
            "duration_ms": duration,
            "detail": {"rows": len(rows), "plugin": meta["plugin"]},
        }
    )

    t0 = time.perf_counter()
    title, content, _, template_row = _build_message(scenario, rows, "preview", payload)
    steps.append(
        {
            "seq": 2,
            "step": "render",
            "name": "渲染模板",
            "status": "success",
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "detail": {"title": title, "length": len(content), "template": (template_row or {}).get("name", "")},
        }
    )

    return {
        "ok": True,
        "row_count": len(rows),
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "title": title,
        "content": content,
        "rows": rows[:20],
        "columns": list(rows[0].keys()) if rows else [],
        "steps": steps,
    }


def run(scenario_id: int, trigger: str = "manual", payload: dict | None = None) -> dict:
    lock = _lock_for(scenario_id)
    if not lock.acquire(blocking=False):
        return {"ok": False, "status": "busy", "message": "该场景正在运行，请稍后再试"}
    try:
        return _run_locked(scenario_id, trigger, payload)
    finally:
        lock.release()


def _run_locked(scenario_id: int, trigger: str, payload: dict | None) -> dict:
    scenario = db.fetch_one("scenario", scenario_id)
    if not scenario:
        raise ScenarioError("场景不存在")

    started_at = db.now_text()
    t_start = time.perf_counter()
    steps: list[dict] = []
    status = "failed"
    message = ""
    title = ""
    content = ""
    row_count = 0
    run_id: int | None = None

    try:
        rows, duration, meta = fetch_rows(scenario, trigger)
        row_count = len(rows)
        steps.append(
            {
                "seq": 1,
                "step": "fetch",
                "name": f"取数 · {meta['source']}",
                "status": "success",
                "duration_ms": duration,
                "detail": {"rows": row_count, "plugin": meta["plugin"]},
            }
        )

        options = _json(scenario.get("options_json"), {})
        send_when_empty = bool(options.get("send_when_empty", False))
        if row_count == 0 and not send_when_empty:
            status = "skipped"
            message = "本次没有查到数据，按配置跳过推送"
            return _finish(scenario, trigger, status, message, row_count, title, content, steps, started_at, t_start)

        t0 = time.perf_counter()
        title, content, _, template_row = _build_message(scenario, rows, trigger, payload)
        steps.append(
            {
                "seq": 2,
                "step": "render",
                "name": "渲染模板",
                "status": "success",
                "duration_ms": int((time.perf_counter() - t0) * 1000),
                "detail": {"title": title, "length": len(content), "template": (template_row or {}).get("name", "")},
            }
        )

        channels = _load_channels(scenario)
        if not channels:
            status = "failed"
            message = "场景未配置推送渠道"
            return _finish(scenario, trigger, status, message, row_count, title, content, steps, started_at, t_start)

        retry_times = int(options.get("retry", 1) or 0)
        message_obj = {"title": title, "content": content, "level": "info", "data": rows, "scenario": scenario}
        ctx = RunContext(scenario=scenario, trigger=trigger)

        ok_count = 0
        failures: list[str] = []
        for channel, plugin, config in channels:
            seq = len(steps) + 1
            step_name = f"推送 · {channel['name']}"
            if not plugin or not plugin.ok:
                steps.append(
                    {
                        "seq": seq,
                        "step": "send",
                        "name": step_name,
                        "status": "failed",
                        "duration_ms": 0,
                        "detail": {"error": f"插件不可用：{getattr(plugin, 'error', '未找到')}"},
                    }
                )
                failures.append(f"{channel['name']}：插件不可用")
                continue

            t0 = time.perf_counter()
            result: SendResult
            attempts = 0
            while True:
                attempts += 1
                try:
                    result = plugin.instance.send(message_obj, config, ctx)
                except Exception as exc:  # noqa: BLE001
                    result = SendResult(ok=False, message=f"插件异常：{exc}", retryable=True)
                if result.ok or not result.retryable or attempts > retry_times:
                    break
                time.sleep(0.8 * attempts)

            duration_ms = int((time.perf_counter() - t0) * 1000)
            steps.append(
                {
                    "seq": seq,
                    "step": "send",
                    "name": step_name,
                    "status": "success" if result.ok else "failed",
                    "duration_ms": duration_ms,
                    "detail": {"message": result.message, "attempts": attempts, "response": result.detail or {}},
                }
            )
            if result.ok:
                ok_count += 1
            else:
                failures.append(f"{channel['name']}：{result.message}")

        if ok_count == len(channels):
            status = "success"
            message = f"已推送到 {ok_count} 个渠道"
        elif ok_count > 0:
            status = "partial"
            message = f"部分成功（{ok_count}/{len(channels)}）：" + "；".join(failures)
        else:
            status = "failed"
            message = "推送失败：" + "；".join(failures)

        return _finish(scenario, trigger, status, message, row_count, title, content, steps, started_at, t_start)

    except Exception as exc:  # noqa: BLE001
        status = "failed"
        message = f"{type(exc).__name__}: {exc}"
        steps.append(
            {
                "seq": len(steps) + 1,
                "step": "error",
                "name": "执行异常",
                "status": "failed",
                "duration_ms": 0,
                "detail": {"traceback": traceback.format_exc()[-2000:]},
            }
        )
        return _finish(scenario, trigger, status, message, row_count, title, content, steps, started_at, t_start)


def _finish(
    scenario: dict,
    trigger: str,
    status: str,
    message: str,
    row_count: int,
    title: str,
    content: str,
    steps: list[dict],
    started_at: str,
    t_start: float,
) -> dict:
    duration_ms = int((time.perf_counter() - t_start) * 1000)
    run_id = db.add_run(
        {
            "scenario_id": scenario["id"],
            "scenario_name": scenario["name"],
            "trigger": trigger,
            "status": status,
            "row_count": row_count,
            "duration_ms": duration_ms,
            "message": message,
            "title": title,
            "content": content,
            "created_at": started_at,
        }
    )
    for step in steps:
        db.add_step(
            {
                "run_id": run_id,
                "seq": step["seq"],
                "step": step["step"],
                "name": step["name"],
                "status": step["status"],
                "duration_ms": step["duration_ms"],
                "detail": json.dumps(step["detail"], ensure_ascii=False),
            }
        )
    db.update(
        "scenario",
        scenario["id"],
        {"last_run_at": started_at, "last_status": status, "updated_at": db.now_text()},
    )

    return {
        "ok": status in ("success", "skipped"),
        "status": status,
        "run_id": run_id,
        "row_count": row_count,
        "duration_ms": duration_ms,
        "message": message,
        "title": title,
        "content": content,
        "steps": steps,
    }

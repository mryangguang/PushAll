"""模板渲染：Jinja2 沙箱 + 消息场景常用过滤器。"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from jinja2.sandbox import SandboxedEnvironment

from . import settings

ENV = SandboxedEnvironment(autoescape=False)


def _cell(value, empty: str) -> str:
    if value is None:
        return empty
    text = str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|")
    return text.strip() or empty


def md_table(rows, columns=None, empty: str = "-", max_width: int = 40) -> str:
    """把 list[dict] 渲染成 Markdown 表格。"""
    if not rows:
        return "（无数据）"
    if isinstance(columns, str):
        columns = [c.strip() for c in columns.split(",") if c.strip()]
    keys = list(columns) if columns else list(rows[0].keys())

    def clip(value):
        text = _cell(value, empty)
        return text if len(text) <= max_width else text[: max_width - 1] + "…"

    lines = ["| " + " | ".join(str(k) for k in keys) + " |"]
    lines.append("| " + " | ".join("---" for _ in keys) + " |")
    for row in rows:
        lines.append("| " + " | ".join(clip(row.get(k)) for k in keys) + " |")
    return "\n".join(lines)


def kv_table(mapping: dict, empty: str = "-") -> str:
    if not mapping:
        return "（无数据）"
    lines = ["| 项目 | 值 |", "| --- | --- |"]
    for key, value in mapping.items():
        lines.append(f"| {_cell(key, empty)} | {_cell(value, empty)} |")
    return "\n".join(lines)


def num(value, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if digits <= 0:
        return f"{number:,.0f}"
    return f"{number:,.{digits}f}"


def pct(value, digits: int = 1) -> str:
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return str(value)


def datefmt(value, fmt: str = "%Y-%m-%d %H:%M") -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (dt.datetime, dt.date)):
        return value.strftime(fmt)
    return str(value)


ENV.filters.update(
    {
        "md_table": md_table,
        "kv_table": kv_table,
        "num": num,
        "pct": pct,
        "date": datefmt,
    }
)


def now() -> dt.datetime:
    return dt.datetime.now(ZoneInfo(settings.TIMEZONE))


ENV.globals["now"] = now
ENV.globals["today"] = lambda: now().date()


def render(text: str, context: dict) -> str:
    template = ENV.from_string(text or "")
    return template.render(**context)


def build_context(rows: list[dict], scenario: dict, trigger: str, payload: dict | None = None) -> dict:
    started = now()
    return {
        "rows": rows,
        "count": len(rows),
        "scenario": {
            "id": scenario.get("id"),
            "name": scenario.get("name", ""),
            "description": scenario.get("description", ""),
        },
        "run": {
            "trigger": trigger,
            "started_at": started.strftime("%Y-%m-%d %H:%M:%S"),
            "date": started.strftime("%Y-%m-%d"),
        },
        "payload": payload or {},
        "now": now,
    }


DEFAULT_BODY = """### {{ scenario.name }}
> {{ run.started_at }} · 共 {{ count }} 条

{{ rows | md_table }}
"""

DEFAULT_TITLE = "{{ scenario.name }}（{{ count }} 条）"

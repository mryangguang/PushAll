"""SQLite 存储层。"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from . import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS source (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    plugin_id   TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS channel (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    plugin_id   TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS template (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    title_tpl   TEXT NOT NULL DEFAULT '',
    body_tpl    TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS scenario (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    enabled        INTEGER NOT NULL DEFAULT 1,
    source_id      INTEGER,
    template_id    INTEGER,
    channel_ids    TEXT NOT NULL DEFAULT '[]',
    schedule_mode  TEXT NOT NULL DEFAULT 'manual',
    cron           TEXT NOT NULL DEFAULT '',
    options_json   TEXT NOT NULL DEFAULT '{}',
    created_at     TEXT NOT NULL DEFAULT '',
    updated_at     TEXT NOT NULL DEFAULT '',
    last_run_at    TEXT NOT NULL DEFAULT '',
    last_status    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS run (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario_id   INTEGER,
    scenario_name TEXT NOT NULL DEFAULT '',
    trigger       TEXT NOT NULL DEFAULT 'manual',
    status        TEXT NOT NULL DEFAULT '',
    row_count     INTEGER NOT NULL DEFAULT 0,
    duration_ms   INTEGER NOT NULL DEFAULT 0,
    message       TEXT NOT NULL DEFAULT '',
    title         TEXT NOT NULL DEFAULT '',
    content       TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS run_step (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL,
    seq         INTEGER NOT NULL DEFAULT 0,
    step        TEXT NOT NULL DEFAULT '',
    name        TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT '',
    duration_ms INTEGER NOT NULL DEFAULT 0,
    detail      TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS app_setting (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS plugin_state (
    plugin_id    TEXT PRIMARY KEY,
    enabled      INTEGER NOT NULL DEFAULT 1,
    installed_at TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_run_scenario ON run(scenario_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_run_created ON run(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_step_run ON run_step(run_id, seq);
"""

TABLES = {"source", "channel", "template", "scenario"}


def now_text() -> str:
    return datetime.now(ZoneInfo(settings.TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def connect():
    settings.ensure_dirs()
    conn = sqlite3.connect(settings.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def _check(table: str) -> None:
    if table not in TABLES:
        raise ValueError(f"非法表名: {table}")


def fetch_all(table: str) -> list[dict]:
    _check(table)
    with connect() as conn:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")]


def fetch_one(table: str, row_id: int) -> dict | None:
    _check(table)
    with connect() as conn:
        row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
        return dict(row) if row else None


def insert(table: str, values: dict) -> int:
    _check(table)
    columns = ", ".join(values.keys())
    marks = ", ".join("?" for _ in values)
    with connect() as conn:
        cur = conn.execute(f"INSERT INTO {table} ({columns}) VALUES ({marks})", list(values.values()))
        return int(cur.lastrowid)


def update(table: str, row_id: int, values: dict) -> None:
    _check(table)
    if not values:
        return
    assignments = ", ".join(f"{key} = ?" for key in values)
    with connect() as conn:
        conn.execute(f"UPDATE {table} SET {assignments} WHERE id = ?", [*values.values(), row_id])


def delete(table: str, row_id: int) -> None:
    _check(table)
    with connect() as conn:
        conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))


# ---------- 运行记录 ----------

def add_run(values: dict) -> int:
    columns = ", ".join(values.keys())
    marks = ", ".join("?" for _ in values)
    with connect() as conn:
        cur = conn.execute(f"INSERT INTO run ({columns}) VALUES ({marks})", list(values.values()))
        return int(cur.lastrowid)


def add_step(values: dict) -> None:
    columns = ", ".join(values.keys())
    marks = ", ".join("?" for _ in values)
    with connect() as conn:
        conn.execute(f"INSERT INTO run_step ({columns}) VALUES ({marks})", list(values.values()))


def list_runs(scenario_id: int | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
    sql = "SELECT * FROM run"
    args: list = []
    if scenario_id:
        sql += " WHERE scenario_id = ?"
        args.append(scenario_id)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    args.extend([limit, offset])
    with connect() as conn:
        return [dict(row) for row in conn.execute(sql, args)]


def get_run(run_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM run WHERE id = ?", (run_id,)).fetchone()
        return dict(row) if row else None


def get_steps(run_id: int) -> list[dict]:
    with connect() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM run_step WHERE run_id = ? ORDER BY seq", (run_id,))]


def purge_old_runs(days: int) -> int:
    if days <= 0:
        return 0
    cutoff = datetime.now(ZoneInfo(settings.TIMEZONE)).timestamp() - days * 86400
    cutoff_text = datetime.fromtimestamp(cutoff, ZoneInfo(settings.TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")
    with connect() as conn:
        ids = [row["id"] for row in conn.execute("SELECT id FROM run WHERE created_at < ?", (cutoff_text,))]
        if ids:
            marks = ",".join("?" for _ in ids)
            conn.execute(f"DELETE FROM run_step WHERE run_id IN ({marks})", ids)
        cur = conn.execute("DELETE FROM run WHERE created_at < ?", (cutoff_text,))
        return cur.rowcount or 0


def delete_scenario(scenario_id: int) -> None:
    with connect() as conn:
        ids = [row["id"] for row in conn.execute("SELECT id FROM run WHERE scenario_id = ?", (scenario_id,))]
        if ids:
            marks = ",".join("?" for _ in ids)
            conn.execute(f"DELETE FROM run_step WHERE run_id IN ({marks})", ids)
        conn.execute("DELETE FROM run WHERE scenario_id = ?", (scenario_id,))
        conn.execute("DELETE FROM scenario WHERE id = ?", (scenario_id,))


# ---------- 插件状态 ----------

def disabled_plugin_ids() -> set[str]:
    with connect() as conn:
        rows = conn.execute("SELECT plugin_id FROM plugin_state WHERE enabled = 0").fetchall()
        return {row["plugin_id"] for row in rows}


def set_plugin_enabled(plugin_id: str, enabled: bool) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO plugin_state (plugin_id, enabled, installed_at) VALUES (?, ?, ?) "
            "ON CONFLICT(plugin_id) DO UPDATE SET enabled = excluded.enabled",
            (plugin_id, 1 if enabled else 0, now_text()),
        )


def source_usage(source_id: int) -> list[str]:
    with connect() as conn:
        rows = conn.execute("SELECT name FROM scenario WHERE source_id = ?", (source_id,)).fetchall()
        return [row["name"] for row in rows]


def template_usage(template_id: int) -> list[str]:
    with connect() as conn:
        rows = conn.execute("SELECT name FROM scenario WHERE template_id = ?", (template_id,)).fetchall()
        return [row["name"] for row in rows]


def channel_usage(channel_id: int) -> list[str]:
    names: list[str] = []
    with connect() as conn:
        rows = conn.execute("SELECT name, channel_ids FROM scenario").fetchall()
    for row in rows:
        try:
            ids = json.loads(row["channel_ids"] or "[]")
        except json.JSONDecodeError:
            continue
        if channel_id in ids:
            names.append(row["name"])
    return names



# ---------- 应用设置 ----------

def get_setting(key: str, default: str = "") -> str:
    with connect() as conn:
        row = conn.execute("SELECT value FROM app_setting WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO app_setting (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, value, now_text()),
        )

"""Oracle / MySQL / PostgreSQL / SQLite 数据源。"""

from __future__ import annotations

import base64
import datetime as dt
import decimal
import json
import sqlite3
from typing import Any

from app.plugins.base import RunContext, SourcePlugin, TestResult


def _jsonable(value: Any) -> Any:
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat(sep=" ") if isinstance(value, dt.datetime) else value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray)):
        return base64.b64encode(bytes(value)).decode("ascii")
    if isinstance(value, dt.timedelta):
        return str(value)
    return value


def _parse_json(raw: Any) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(str(raw))
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError as exc:
        raise ValueError(f"绑定参数不是合法 JSON：{exc}") from exc


class SqlSource(SourcePlugin):
    id = "source.sql"

    def test(self, config: dict) -> TestResult:
        try:
            rows = self.fetch({**config, "max_rows": 5}, RunContext())
        except Exception as exc:  # noqa: BLE001
            return TestResult(ok=False, message=f"连接或查询失败：{exc}")
        columns = list(rows[0].keys()) if rows else []
        return TestResult(
            ok=True,
            message=f"查询成功，返回 {len(rows)} 行（测试最多取 5 行）",
            rows=rows,
            columns=columns,
            detail={"row_count": len(rows)},
        )

    def fetch(self, config: dict, ctx: RunContext) -> list[dict]:
        driver = str(config.get("driver") or "oracle").lower()
        query = str(config.get("query") or "").strip()
        if not query:
            raise ValueError("SQL 不能为空")
        params = _parse_json(config.get("params"))
        max_rows = int(config.get("max_rows") or 500)
        lower_keys = bool(config.get("lower_keys", True))

        if driver == "oracle":
            rows = self._oracle(config, query, params)
        elif driver == "mysql":
            rows = self._mysql(config, query, params)
        elif driver in ("postgres", "postgresql", "pg"):
            rows = self._postgres(config, query, params)
        elif driver == "sqlite":
            rows = self._sqlite(config, query, params)
        else:
            raise ValueError(f"不支持的数据库类型：{driver}")

        if max_rows > 0:
            rows = rows[:max_rows]
        if lower_keys:
            rows = [{str(k).lower(): v for k, v in row.items()} for row in rows]
        return [{k: _jsonable(v) for k, v in row.items()} for row in rows]

    @staticmethod
    def _oracle(config: dict, query: str, params: dict) -> list[dict]:
        import oracledb

        if str(config.get("mode") or "thin").lower() == "thick":
            lib_dir = str(config.get("lib_dir") or "").strip()
            try:
                oracledb.init_oracle_client(lib_dir=lib_dir or None)
            except oracledb.ProgrammingError:
                pass  # 已初始化

        dsn = str(config.get("dsn") or "").strip()
        if not dsn:
            host = config.get("host") or "127.0.0.1"
            port = config.get("port") or 1521
            service = config.get("database") or ""
            dsn = f"{host}:{port}/{service}" if service else f"{host}:{port}"
        conn = oracledb.connect(user=str(config.get("user") or ""), password=str(config.get("password") or ""), dsn=dsn)
        try:
            cur = conn.cursor()
            cur.execute(query, params or None)
            columns = [desc[0] for desc in cur.description or []]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
        finally:
            conn.close()

    @staticmethod
    def _mysql(config: dict, query: str, params: dict) -> list[dict]:
        import pymysql
        from pymysql.cursors import DictCursor

        conn = pymysql.connect(
            host=str(config.get("host") or "127.0.0.1"),
            port=int(config.get("port") or 3306),
            user=str(config.get("user") or ""),
            password=str(config.get("password") or ""),
            database=str(config.get("database") or "") or None,
            charset="utf8mb4",
            cursorclass=DictCursor,
            connect_timeout=10,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(query, params or None)
                return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()

    @staticmethod
    def _postgres(config: dict, query: str, params: dict) -> list[dict]:
        import psycopg
        from psycopg.rows import dict_row

        dsn = str(config.get("dsn") or "").strip()
        if not dsn:
            dsn = (
                f"host={config.get('host') or '127.0.0.1'} port={config.get('port') or 5432} "
                f"dbname={config.get('database') or 'postgres'} user={config.get('user') or ''} "
                f"password={config.get('password') or ''}"
            )
        with psycopg.connect(dsn, row_factory=dict_row, connect_timeout=10) as conn:
            with conn.cursor() as cur:
                cur.execute(query, params or None)
                return [dict(row) for row in cur.fetchall()]

    @staticmethod
    def _sqlite(config: dict, query: str, params: dict) -> list[dict]:
        path = str(config.get("dsn") or config.get("database") or "").strip()
        if not path:
            raise ValueError("SQLite 需要填写数据库文件路径（dsn 字段）")
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(query, params or {})
            return [dict(row) for row in cur.fetchall()]
        finally:
            conn.close()


"""Oracle / MySQL / PostgreSQL / SQLite 数据源。"""

from __future__ import annotations

import base64
import datetime as dt
import decimal
import json
import os
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


def _normalize_query(sql: str) -> str:
    """去掉首尾空白与结尾分号，兼容从 SQL Developer / PLSQL Developer 直接粘贴。"""
    text = str(sql or "").strip()
    while text.endswith(";"):
        text = text[:-1].rstrip()
    return text


def _friendly_error(exc: Exception) -> str:
    text = str(exc)
    if "ORA-00911" in text:
        return (
            "SQL 中有非法字符：最常见是结尾多了英文分号（;），请删除后再试；"
            "也请检查是否混入了中文标点（，；：（）等）。"
        )
    if "DPY-3010" in text:
        return (
            "Oracle 数据库版本较旧（如 11g），python-oracledb 的 thin 模式不支持。"
            "请安装 Oracle Instant Client（19c/21c x64），在数据源中选择 thick 模式并填写 Instant Client 目录。"
        )
    if "DPY-4027" in text:
        return (
            "DSN 使用了 TNS 别名，但未指定配置目录。"
            "请填写 tnsnames.ora 所在目录（TNS 配置目录），或把 DSN 改成 host:port/service。"
        )
    if "DPY-4011" in text or "DPI-1047" in text:
        return (
            "未找到 Oracle Client 库。请安装 Oracle Instant Client（19c/21c x64），"
            "并在数据源中填写 Instant Client 目录。"
        )
    if "DPY-6001" in text:
        return "服务名不正确：监听器上没有该 Service，请核对 DSN 中的 service name。"
    if "DPY-6003" in text:
        return "SID 不正确：监听器上没有该 SID，请改用 service name。"
    return text


class SqlSource(SourcePlugin):
    id = "source.sql"

    def test(self, config: dict) -> TestResult:
        try:
            rows = self.fetch({**config, "max_rows": 5}, RunContext())
        except Exception as exc:  # noqa: BLE001
            return TestResult(ok=False, message=f"连接或查询失败：{_friendly_error(exc)}")
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
        query = _normalize_query(config.get("query"))
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

        mode = str(config.get("mode") or "thin").lower()
        lib_dir = str(config.get("lib_dir") or "").strip()
        config_dir = str(config.get("config_dir") or "").strip()

        if mode == "thick":
            # PyInstaller 冻结环境下直接传 lib_dir 可能触发 DPI-1072；
            # 先把客户端目录加入 PATH，再让 oracledb 从 PATH 加载。
            if lib_dir:
                os.environ["PATH"] = lib_dir + os.pathsep + os.environ.get("PATH", "")
            try:
                oracledb.init_oracle_client(lib_dir=None, config_dir=config_dir or None)
            except oracledb.ProgrammingError:
                pass  # 已初始化
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"Oracle Client 初始化失败：{_friendly_error(exc)}") from exc

        host = str(config.get("host") or "").strip()
        port = config.get("port") or 1521
        service = str(config.get("database") or "").strip()
        dsn_raw = str(config.get("dsn") or "").strip()

        if dsn_raw:
            # 纯名字 + 主机：按 service name 拼 Easy Connect（如 dsn=tsoa）
            if config_dir or not host or ":" in dsn_raw or "/" in dsn_raw or dsn_raw.startswith("("):
                dsn = dsn_raw
            else:
                dsn = f"{host}:{port}/{dsn_raw}"
        else:
            dsn = f"{host or '127.0.0.1'}:{port}/{service}" if service else f"{host or '127.0.0.1'}:{port}"

        kwargs = {"user": str(config.get("user") or ""), "password": str(config.get("password") or ""), "dsn": dsn}
        if mode != "thick" and config_dir:
            kwargs["config_dir"] = config_dir
        conn = oracledb.connect(**kwargs)
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




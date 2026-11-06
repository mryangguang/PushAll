"""端到端冒烟测试：python tools/smoke.py

会在临时目录启动一个独立实例，不影响正式数据。
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_ready(client: httpx.Client, timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if client.get("/api/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError("服务启动超时")


def main() -> None:
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PUSHALL_DATA_DIR"] = str(root / "data")
    env["PUSHALL_LOG_DIR"] = str(root / "logs")
    env["PUSHALL_PLUGIN_DIR"] = str(root / "plugins")

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(ROOT),
        env=env,
    )
    try:
        with httpx.Client(base_url=base, timeout=30) as c:
            wait_ready(c)
            assert c.get("/api/health").json()["ok"] is True

            plugins = c.get("/api/plugins").json()
            assert len(plugins) >= 6, f"内置插件数量异常：{len(plugins)}"
            print(f"[1/6] 插件加载正常：{len(plugins)} 个")

            sqlite_path = root / "demo.db"
            conn = sqlite3.connect(sqlite_path)
            conn.execute("CREATE TABLE shop (code TEXT, name TEXT, stock INTEGER)")
            conn.executemany("INSERT INTO shop VALUES (?, ?, ?)", [("BJ001", "北京一店", 3), ("SH002", "上海二店", 7)])
            conn.commit()
            conn.close()

            sql_source = c.post(
                "/api/sources",
                json={
                    "name": "SQLite 测试源",
                    "plugin_id": "source.sql",
                    "config": {"driver": "sqlite", "dsn": str(sqlite_path), "query": "SELECT code, stock FROM shop", "max_rows": 50},
                },
            )
            assert sql_source.status_code == 200, sql_source.text
            sql_test = c.post(
                "/api/sources/test",
                json={"plugin_id": "source.sql", "config": sql_source.json()["config"]},
            ).json()
            assert sql_test["ok"] and sql_test["rows"][0]["code"] == "BJ001", sql_test
            print("[2/6] SQL 数据源取数正常")

            template = c.post(
                "/api/templates",
                json={"name": "测试模板", "title_tpl": "{{ count }} 条库存", "body_tpl": "{{ rows | md_table }}"},
            ).json()

            channel = c.post(
                "/api/channels",
                json={
                    "name": "联调 Webhook",
                    "plugin_id": "sink.webhook",
                    "config": {"url": f"{base}/api/dev/echo", "method": "POST", "headers": "{}", "body_template": '{"title": {{ title|tojson }}, "content": {{ content|tojson }}}'},
                },
            ).json()

            scenario = c.post(
                "/api/scenarios",
                json={
                    "name": "冒烟场景",
                    "description": "",
                    "enabled": True,
                    "source_id": sql_source.json()["id"],
                    "template_id": template["id"],
                    "channel_ids": [channel["id"]],
                    "schedule_mode": "manual",
                    "cron": "",
                    "options": {"send_when_empty": False, "retry": 1},
                },
            ).json()
            print("[3/6] 场景创建正常")

            preview = c.post(f"/api/scenarios/{scenario['id']}/preview", json={}).json()
            assert preview["row_count"] == 2 and "2 条库存" in preview["title"], preview
            print("[4/6] 模板渲染正常")

            run = c.post(f"/api/scenarios/{scenario['id']}/run").json()
            assert run["status"] == "success", run
            assert run["row_count"] == 2
            echo = c.get("/api/dev/echo").json()
            assert echo and echo[0]["body"]["title"] == "2 条库存", echo
            print("[5/6] 推送链路正常（Webhook 已收到）")

            detail = c.get(f"/api/runs/{run['run_id']}").json()
            assert len(detail["steps"]) >= 3, detail
            next_runs = c.get("/api/cron/next", params={"expr": "0 9 * * *"}).json()["next"]
            assert len(next_runs) == 3, next_runs
            print("[6/6] 运行记录与 cron 计算正常")

        print("\nSMOKE OK")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        tmp.cleanup()


if __name__ == "__main__":
    main()

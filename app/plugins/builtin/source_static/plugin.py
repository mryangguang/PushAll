"""静态数据源，用于联调与演示。"""

from __future__ import annotations

import json

from app.plugins.base import RunContext, SourcePlugin, TestResult


class StaticSource(SourcePlugin):
    id = "source.static"

    def test(self, config: dict) -> TestResult:
        try:
            rows = self.fetch(config, RunContext())
        except Exception as exc:  # noqa: BLE001
            return TestResult(ok=False, message=f"解析失败：{exc}")
        columns = list(rows[0].keys()) if rows else []
        return TestResult(ok=True, message=f"共 {len(rows)} 条示例数据", rows=rows[:5], columns=columns)

    def fetch(self, config: dict, ctx: RunContext) -> list[dict]:
        raw = config.get("rows")
        if isinstance(raw, list):
            rows = raw
        elif isinstance(raw, str):
            try:
                rows = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"示例数据不是合法 JSON：{exc}") from exc
        else:
            rows = []
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            raise ValueError("示例数据必须是 JSON 数组")
        return [row if isinstance(row, dict) else {"value": row} for row in rows]

"""示例插件：CSV 文件数据源。

把整个目录复制到 plugins/ 下即可被识别，无需修改主程序。
"""

from __future__ import annotations

import csv
from pathlib import Path

from app.plugins.base import RunContext, SourcePlugin, TestResult


class CsvSource(SourcePlugin):
    id = "source.csv"

    def test(self, config: dict) -> TestResult:
        try:
            rows = self.fetch(config, RunContext())
        except Exception as exc:  # noqa: BLE001
            return TestResult(ok=False, message=f"读取失败：{exc}")
        return TestResult(
            ok=True,
            message=f"读取成功，共 {len(rows)} 行",
            rows=rows[:5],
            columns=list(rows[0].keys()) if rows else [],
        )

    def fetch(self, config: dict, ctx: RunContext) -> list[dict]:
        path = Path(str(config.get("path") or "")).expanduser()
        if not path.exists():
            raise ValueError(f"文件不存在：{path}")
        encoding = str(config.get("encoding") or "utf-8-sig")
        delimiter = str(config.get("delimiter") or ",")
        max_rows = int(config.get("max_rows") or 200)
        with path.open("r", encoding=encoding, newline="") as handle:
            rows = [dict(row) for row in csv.DictReader(handle, delimiter=delimiter)]
        return rows[:max_rows]

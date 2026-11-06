"""通用 HTTP 接口数据源。"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.plugins.base import RunContext, SourcePlugin, TestResult


def _parse_json(raw: Any, default: Any) -> Any:
    if raw in (None, ""):
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 配置不合法：{exc}") from exc


def _resolve(payload: Any, path: str) -> Any:
    """支持 data.items[0].name 形式的取值路径。"""
    current = payload
    for part in [p for p in str(path).split(".") if p]:
        name = part
        index = None
        if "[" in part and part.endswith("]"):
            name, _, idx = part.partition("[")
            try:
                index = int(idx[:-1])
            except ValueError:
                index = None
        if name:
            if not isinstance(current, dict) or name not in current:
                raise ValueError(f"取值路径不存在：{path}（缺少 {name}）")
            current = current[name]
        if index is not None:
            if not isinstance(current, list) or len(current) <= index:
                raise ValueError(f"取值路径越界：{path}")
            current = current[index]
    return current


class HttpSource(SourcePlugin):
    id = "source.http"

    def test(self, config: dict) -> TestResult:
        try:
            rows = self.fetch(config, RunContext())
        except Exception as exc:  # noqa: BLE001
            return TestResult(ok=False, message=f"请求失败：{exc}")
        columns = list(rows[0].keys()) if rows else []
        return TestResult(
            ok=True,
            message=f"请求成功，解析出 {len(rows)} 条记录",
            rows=rows[:5],
            columns=columns,
            detail={"row_count": len(rows)},
        )

    def fetch(self, config: dict, ctx: RunContext) -> list[dict]:
        url = str(config.get("url") or "").strip()
        if not url:
            raise ValueError("接口地址不能为空")
        method = str(config.get("method") or "GET").upper()
        headers = _parse_json(config.get("headers"), {})
        params = _parse_json(config.get("params"), {})
        timeout = float(config.get("timeout") or 20)
        body = config.get("body")
        body_type = str(config.get("body_type") or "json")

        kwargs: dict[str, Any] = {}
        if body not in (None, ""):
            if body_type == "json":
                kwargs["json"] = _parse_json(body, {})
            elif body_type == "form":
                kwargs["data"] = _parse_json(body, {})
            else:
                kwargs["content"] = str(body).encode("utf-8")

        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.request(method, url, headers=headers, params=params, **kwargs)
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "json" in content_type:
            payload = resp.json()
        else:
            text = resp.text
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                payload = text

        data = payload
        path = str(config.get("data_path") or "").strip()
        if path:
            data = _resolve(payload, path)

        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise ValueError("接口返回不是数组或对象，无法作为表格数据")

        rows = [item if isinstance(item, dict) else {"value": item} for item in data]
        max_rows = int(config.get("max_rows") or 200)
        return rows[:max_rows]

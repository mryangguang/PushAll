"""通用 Webhook 下游，用于对接自建系统或联调。"""

from __future__ import annotations

import json
from typing import Any

import httpx
from jinja2.sandbox import SandboxedEnvironment

from app.plugins.base import RunContext, SendResult, SinkPlugin

ENV = SandboxedEnvironment(autoescape=False)
DEFAULT_BODY = '{"title": {{ title|tojson }}, "content": {{ content|tojson }}}'


def _parse_json(raw: Any, default: Any) -> Any:
    if raw in (None, ""):
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 配置不合法：{exc}") from exc


class WebhookSink(SinkPlugin):
    id = "sink.webhook"

    def test(self, config: dict) -> SendResult:
        return self.send(
            {"title": "PushAll 连接测试", "content": "这是一条来自 PushAll 的测试消息。", "data": []},
            config,
            RunContext(),
        )

    def send(self, message: dict, config: dict, ctx: RunContext) -> SendResult:
        url = str(config.get("url") or "").strip()
        if not url:
            return SendResult(ok=False, message="Webhook 地址为空")
        method = str(config.get("method") or "POST").upper()
        headers = _parse_json(config.get("headers"), {})
        body_template = str(config.get("body_template") or DEFAULT_BODY)

        try:
            rendered = ENV.from_string(body_template).render(
                title=message.get("title", ""),
                content=message.get("content", ""),
                message=message,
                data=message.get("data", []),
            )
        except Exception as exc:  # noqa: BLE001
            return SendResult(ok=False, message=f"请求体模板渲染失败：{exc}")

        kwargs: dict[str, Any] = {"headers": headers}
        try:
            payload = json.loads(rendered)
            kwargs["json"] = payload
        except json.JSONDecodeError:
            kwargs["content"] = rendered.encode("utf-8")
            headers.setdefault("Content-Type", "text/plain; charset=utf-8")

        try:
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                resp = client.request(method, url, **kwargs)
        except httpx.RequestError as exc:
            return SendResult(ok=False, message=f"网络请求失败：{exc}", retryable=True)

        ok = 200 <= resp.status_code < 300
        return SendResult(
            ok=ok,
            message="Webhook 调用成功" if ok else f"Webhook 返回 HTTP {resp.status_code}",
            detail={"status_code": resp.status_code, "response": resp.text[:500]},
            retryable=resp.status_code >= 500,
        )

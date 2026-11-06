"""钉钉群自定义机器人（支持加签）。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse

import httpx

from app.plugins.base import RunContext, SendResult, SinkPlugin

MAX_BYTES = 18000


def _truncate(text: str, limit: int = MAX_BYTES) -> str:
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    cut = raw[:limit].decode("utf-8", errors="ignore")
    return cut + "\n\n…（内容过长已截断）"


def _sign_url(webhook: str, secret: str) -> str:
    if not secret:
        return webhook
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(digest))
    sep = "&" if "?" in webhook else "?"
    return f"{webhook}{sep}timestamp={timestamp}&sign={sign}"


def _build_body(message: dict, config: dict) -> dict:
    title = str(message.get("title") or "PushAll 通知").strip()
    content = str(message.get("content") or "").strip()
    body_text = content if content.lstrip().startswith("#") else f"### {title}\n\n{content}"
    mobiles = [m.strip() for m in str(config.get("at_mobiles") or "").split(",") if m.strip()]
    return {
        "msgtype": "markdown",
        "markdown": {"title": title[:64], "text": _truncate(body_text)},
        "at": {"atMobiles": mobiles, "isAtAll": bool(config.get("at_all", False))},
    }


class DingTalkSink(SinkPlugin):
    id = "sink.dingtalk"

    def test(self, config: dict) -> SendResult:
        return self.send(
            {"title": "PushAll 连接测试", "content": "如果你收到这条消息，说明钉钉机器人配置成功。", "data": []},
            config,
            RunContext(),
        )

    def send(self, message: dict, config: dict, ctx: RunContext) -> SendResult:
        webhook = str(config.get("webhook") or "").strip()
        if not webhook:
            return SendResult(ok=False, message="Webhook 地址为空")
        url = _sign_url(webhook, str(config.get("secret") or "").strip())
        body = _build_body(message, config)

        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(url, json=body)
        except httpx.RequestError as exc:
            return SendResult(ok=False, message=f"网络请求失败：{exc}", retryable=True)

        detail = {"status_code": resp.status_code, "response": resp.text[:500]}
        try:
            data = resp.json()
            detail["response"] = data
        except ValueError:
            data = {}

        errcode = data.get("errcode")
        ok = resp.status_code == 200 and errcode == 0
        if ok:
            return SendResult(ok=True, message="钉钉推送成功", detail=detail)
        message_text = data.get("errmsg") or resp.text[:200] or f"HTTP {resp.status_code}"
        return SendResult(ok=False, message=f"钉钉返回错误：{message_text}", detail=detail, retryable=resp.status_code >= 500)


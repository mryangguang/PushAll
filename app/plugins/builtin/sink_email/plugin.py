"""SMTP 邮件推送。"""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

import markdown

from app.plugins.base import RunContext, SendResult, SinkPlugin

HTML_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; color: #1f2933; line-height: 1.65; }}
  h1, h2, h3 {{ color: #111827; }}
  table {{ border-collapse: collapse; margin: 12px 0; }}
  th, td {{ border: 1px solid #d9dee7; padding: 6px 10px; font-size: 14px; }}
  th {{ background: #f3f6fb; text-align: left; }}
  blockquote {{ margin: 10px 0; padding: 6px 12px; color: #5b6b7f; border-left: 3px solid #cdd7e5; background: #f8fafc; }}
  code {{ background: #f1f5f9; padding: 1px 4px; border-radius: 3px; }}
  pre {{ background: #f8fafc; padding: 10px; border: 1px solid #e5eaf1; overflow-x: auto; }}
</style></head><body>{body}</body></html>"""


class EmailSink(SinkPlugin):
    id = "sink.email"

    def test(self, config: dict) -> SendResult:
        return self.send(
            {
                "title": "PushAll 连接测试",
                "content": "### PushAll 连接测试\n\n如果你收到这封邮件，说明 SMTP 配置成功。",
                "data": [],
            },
            config,
            RunContext(),
        )

    def send(self, message: dict, config: dict, ctx: RunContext) -> SendResult:
        host = str(config.get("host") or "").strip()
        if not host:
            return SendResult(ok=False, message="SMTP 服务器地址为空")

        port = int(config.get("port") or 465)
        security = str(config.get("security") or "ssl")
        username = str(config.get("username") or "")
        password = str(config.get("password") or "")
        from_addr = str(config.get("from_addr") or username).strip()
        if not from_addr:
            return SendResult(ok=False, message="发件人地址为空")
        to_addrs = [a.strip() for a in str(config.get("to_addrs") or "").replace(";", ",").split(",") if a.strip()]
        if not to_addrs:
            return SendResult(ok=False, message="收件人为空")

        title = str(message.get("title") or "PushAll 通知")
        content = str(message.get("content") or "")
        subject_prefix = str(config.get("subject_prefix") or "")

        msg = EmailMessage()
        msg["Subject"] = f"{subject_prefix}{title}"
        msg["From"] = formataddr(("PushAll", from_addr))
        msg["To"] = ", ".join(to_addrs)
        msg.set_content(content)

        html_body = markdown.markdown(content, extensions=["tables", "fenced_code", "sane_lists"])
        msg.add_alternative(HTML_TEMPLATE.format(body=html_body), subtype="html")

        try:
            if security == "ssl":
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(host, port, timeout=20, context=context) as server:
                    if username:
                        server.login(username, password)
                    server.send_message(msg, from_addr=from_addr, to_addrs=to_addrs)
            else:
                with smtplib.SMTP(host, port, timeout=20) as server:
                    if security == "starttls":
                        server.starttls(context=ssl.create_default_context())
                    if username:
                        server.login(username, password)
                    server.send_message(msg, from_addr=from_addr, to_addrs=to_addrs)
        except (smtplib.SMTPException, OSError) as exc:
            return SendResult(ok=False, message=f"邮件发送失败：{exc}", retryable=True)

        return SendResult(
            ok=True,
            message=f"邮件已发送至 {len(to_addrs)} 个收件人",
            detail={"to": to_addrs, "subject": msg["Subject"]},
        )

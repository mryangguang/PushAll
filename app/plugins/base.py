"""插件基类与通用数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TestResult:
    ok: bool
    message: str = ""
    detail: dict | None = None
    rows: list[dict] | None = None
    columns: list[str] | None = None


@dataclass
class SendResult:
    ok: bool
    message: str = ""
    detail: dict | None = None
    retryable: bool = False


@dataclass
class RunContext:
    scenario: dict = field(default_factory=dict)
    trigger: str = "manual"
    logs: list[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        self.logs.append(message)


class SourcePlugin:
    """数据源插件基类。fetch() 返回 list[dict]。"""

    id = ""

    def test(self, config: dict) -> TestResult:  # pragma: no cover
        return TestResult(ok=True, message="插件未提供测试方法")

    def fetch(self, config: dict, ctx: RunContext) -> list[dict]:  # pragma: no cover
        raise NotImplementedError


class SinkPlugin:
    """推送渠道插件基类。"""

    id = ""

    def test(self, config: dict) -> SendResult:  # pragma: no cover
        return SendResult(ok=True, message="插件未提供测试方法")

    def send(self, message: dict, config: dict, ctx: RunContext) -> SendResult:  # pragma: no cover
        raise NotImplementedError


def validate_config(schema: dict, config: dict) -> list[str]:
    """按 JSON Schema 常用子集校验，错误信息为中文。"""
    errors: list[str] = []
    props: dict[str, Any] = schema.get("properties") or {}
    required = schema.get("required") or []

    for key in required:
        value = config.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            title = (props.get(key) or {}).get("title", key)
            errors.append(f"缺少必填项：{title}")

    for key, value in config.items():
        spec = props.get(key)
        if not spec or value is None or value == "":
            continue
        title = spec.get("title", key)
        expected = spec.get("type")
        if expected == "integer":
            try:
                int(value)
            except (TypeError, ValueError):
                errors.append(f"{title} 必须是整数")
        elif expected == "number":
            try:
                float(value)
            except (TypeError, ValueError):
                errors.append(f"{title} 必须是数字")
        elif expected == "boolean":
            if not isinstance(value, bool):
                errors.append(f"{title} 必须是布尔值")
        if "enum" in spec and value not in spec["enum"]:
            errors.append(f"{title} 取值不合法：{value}")
    return errors

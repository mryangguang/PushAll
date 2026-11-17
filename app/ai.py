"""AI 处理：调用（内网）OpenAI 兼容网关，对取数结果执行受控动作。

模型只能：过滤 / 新增 AI_ 字段 / 排序 / 取前 N / 写汇总；不能新增行、不能改原字段。
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from . import crypto, db

ERROR_LABELS = {
    "timeout": "请求超时",
    "http_401": "认证失败（401）",
    "http_403": "无权限（403）",
    "http_404": "接口不存在（404）",
    "http_429": "限流（429）",
    "empty_response": "模型返回为空",
    "invalid_json": "模型返回不是合法 JSON",
    "config": "模型配置不完整",
    "network": "网络错误",
}

DEFAULT_ERROR_TITLE = "【AI处理失败】{{ scenario.name }}"
DEFAULT_ERROR_BODY = """### AI 处理失败
> {{ ai.time }} ｜ 触发：{{ scenario.trigger }}
> 数据源：{{ source.name }}（{{ source.plugin_name }}）
> 主模型：{{ ai.model.name }}（{{ ai.model.model }}）
{% if ai.fallback_model %}备用模型：{{ ai.fallback_model.name }}（{{ ai.fallback_model.model }}）
{% endif %}> 原因：{{ ai.error }}
> 原始行数：{{ ai.row_count }}，用时：{{ ai.duration_ms }}ms

本次未推送业务数据，请检查网关或模型配置。"""

SYSTEM_PROMPT = """你是数据处理助手。你会收到一组表格数据和一段处理要求。
你只能输出一个 JSON 对象，不要输出解释、Markdown 代码块或任何多余文字。

允许的动作：
- {"type":"drop","index":行号,"reason":"原因"}：过滤掉该行
- {"type":"set","index":行号,"field":"AI_字段名","value":"值"}：给该行新增 AI_ 前缀字段
- {"type":"sort","field":"列名","order":"asc 或 desc"}：排序
- {"type":"top","count":N}：只保留前 N 条
- {"type":"summary","text":"汇总文字"}：生成汇总，不影响数据

规则：
1. index 从 0 开始，代表输入数组中的行号。
2. 只能新增以 AI_ 开头的字段，不能修改原有字段，不能新增行。
3. 输出格式：{"actions":[...],"summary":"可选汇总"}；不需要处理时输出 {"actions":[]}。
"""


def _provider(provider_id: Any) -> dict | None:
    try:
        pid = int(provider_id)
    except (TypeError, ValueError):
        return None
    if pid <= 0:
        return None
    row = db.fetch_one("ai_provider", pid)
    if not row:
        return None
    item = dict(row)
    raw = item.get("api_key") or ""
    if raw:
        try:
            data = crypto.loads(raw)
            if isinstance(data, dict):
                item["api_key"] = str(data.get("api_key") or "")
        except Exception:  # noqa: BLE001
            item["api_key"] = ""
    return item


def _mask(provider: dict) -> dict:
    item = dict(provider)
    key = str(item.get("api_key") or "")
    item["has_key"] = bool(key)
    item["api_key"] = ("*" * 8) if key else ""
    return item


def _truncate(value: Any, limit: int = 200) -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _prompt_rows(rows: list[dict], columns: list[str]) -> list[dict]:
    out = []
    for row in rows:
        item = {}
        for col in columns:
            if col in row:
                item[col] = _truncate(row[col])
        if not item:
            item = {k: _truncate(v) for k, v in list(row.items())[:20]}
        out.append(item)
    return out


def _build_messages(instruction: str, columns: list[str], rows: list[dict], scenario: dict) -> list[dict]:
    user = (
        f"场景：{scenario.get('name', '')}\n"
        f"处理要求：{instruction}\n"
        f"列名：{', '.join(columns)}\n"
        f"数据（JSON 数组，共 {len(rows)} 行）：\n"
        + json.dumps(rows, ensure_ascii=False)
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _headers(provider: dict) -> dict:
    headers = {"Content-Type": "application/json"}
    key = str(provider.get("api_key") or "")
    prefix = str(provider.get("auth_prefix") or "")
    if key:
        if str(provider.get("auth_type") or "bearer") == "header":
            headers[str(provider.get("auth_header") or "api-key")] = prefix + key
        else:
            headers["Authorization"] = (prefix or "Bearer ") + key
    extra = str(provider.get("extra_headers") or "").strip()
    if extra:
        try:
            data = json.loads(extra)
            if isinstance(data, dict):
                headers.update({str(k): str(v) for k, v in data.items()})
        except json.JSONDecodeError:
            pass
    return headers


def call_model(provider: dict, messages: list[dict]) -> dict:
    """调用一次模型。返回 {ok, content, error, error_code, duration_ms}。"""
    base = str(provider.get("base_url") or "").strip().rstrip("/")
    model = str(provider.get("model") or "").strip()
    if not base or not model:
        return {"ok": False, "error": "Base URL 或模型名未配置", "error_code": "config", "duration_ms": 0}

    url = base + "/chat/completions"
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": float(provider.get("temperature") or 0),
        "max_tokens": int(provider.get("max_tokens") or 2000),
        "stream": False,
    }
    if bool(provider.get("json_mode", True)):
        body["response_format"] = {"type": "json_object"}

    started = time.perf_counter()
    try:
        with httpx.Client(timeout=float(provider.get("timeout") or 30), verify=bool(provider.get("verify_tls", True))) as client:
            resp = client.post(url, headers=_headers(provider), json=body)
        duration = int((time.perf_counter() - started) * 1000)
        if resp.status_code >= 400:
            code = f"http_{resp.status_code}"
            return {
                "ok": False,
                "error": f"{ERROR_LABELS.get(code, 'HTTP ' + str(resp.status_code))}：{resp.text[:300]}",
                "error_code": code,
                "duration_ms": duration,
            }
        try:
            data = resp.json()
        except ValueError:
            return {"ok": False, "error": "网关返回内容不是 JSON", "error_code": "invalid_json", "duration_ms": duration}
        choices = data.get("choices") or []
        content = ""
        if choices:
            content = str(((choices[0] or {}).get("message") or {}).get("content") or "")
        if not content.strip():
            return {"ok": False, "error": "模型返回为空", "error_code": "empty_response", "duration_ms": duration}
        return {"ok": True, "content": _strip_fences(content), "duration_ms": duration, "usage": data.get("usage") or {}}
    except httpx.TimeoutException:
        return {
            "ok": False,
            "error": "请求超时",
            "error_code": "timeout",
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"网络错误：{exc}",
            "error_code": "network",
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }


def _parse_payload(content: str) -> tuple[dict | None, str]:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None, "模型返回不是合法 JSON"
    if isinstance(data, list):
        data = {"actions": data}
    if not isinstance(data, dict):
        return None, "模型返回结构不正确"
    if "actions" not in data and "summary" in data:
        data = {"actions": [], "summary": data.get("summary")}
    return data, ""


def _to_number(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def apply_actions(rows: list[dict], payload: dict) -> dict:
    actions = payload.get("actions") or []
    dropped: dict[int, str] = {}
    sets: list[tuple[int, str, Any]] = []
    sort_field = ""
    sort_order = "asc"
    top_count = 0
    summary = str(payload.get("summary") or "").strip()
    warnings: list[str] = []
    counts = {"drop": 0, "set": 0, "sort": 0, "top": 0, "summary": 0}

    for action in actions if isinstance(actions, list) else []:
        if not isinstance(action, dict):
            continue
        kind = str(action.get("type") or "").lower()
        if kind == "drop":
            try:
                idx = int(action.get("index"))
            except (TypeError, ValueError):
                warnings.append("drop 缺少合法 index")
                continue
            if 0 <= idx < len(rows) and idx not in dropped:
                dropped[idx] = str(action.get("reason") or "").strip() or "不符合条件"
                counts["drop"] += 1
        elif kind == "set":
            try:
                idx = int(action.get("index"))
            except (TypeError, ValueError):
                warnings.append("set 缺少合法 index")
                continue
            field = str(action.get("field") or "").strip()
            if not field.startswith("AI_"):
                warnings.append(f"忽略非 AI_ 字段：{field}")
                continue
            if 0 <= idx < len(rows):
                sets.append((idx, field, _truncate(action.get("value"), 500)))
                counts["set"] += 1
        elif kind == "sort":
            field = str(action.get("field") or "").strip()
            if field:
                sort_field = field
                sort_order = "desc" if str(action.get("order") or "asc").lower() == "desc" else "asc"
                counts["sort"] += 1
        elif kind == "top":
            try:
                top_count = max(0, int(action.get("count")))
                counts["top"] += 1
            except (TypeError, ValueError):
                warnings.append("top 缺少合法 count")
        elif kind == "summary":
            text = str(action.get("text") or "").strip()
            if text:
                summary = text
                counts["summary"] += 1
        else:
            warnings.append(f"未知动作：{kind}")

    work = [dict(row) for i, row in enumerate(rows) if i not in dropped]
    for idx, field, value in sets:
        if idx in dropped:
            continue
        target = None
        offset = 0
        for i, row in enumerate(rows):
            if i in dropped:
                continue
            if i == idx:
                target = offset
                break
            offset += 1
        if target is not None and 0 <= target < len(work):
            work[target][field] = value

    if sort_field:
        numeric = all(_to_number(r.get(sort_field)) is not None for r in work) if work else False
        if numeric:
            work.sort(key=lambda r: _to_number(r.get(sort_field)) or 0, reverse=(sort_order == "desc"))
        else:
            work.sort(key=lambda r: str(r.get(sort_field) or ""), reverse=(sort_order == "desc"))
    if top_count:
        work = work[:top_count]

    return {
        "rows": work,
        "dropped": [{"index": i, "reason": dropped[i]} for i in sorted(dropped)],
        "summary": summary,
        "counts": counts,
        "warnings": warnings,
    }


def process(ai_cfg: dict, rows: list[dict], scenario: dict, source: dict) -> dict:
    """主模型（重试）→ 全局备用模型（重试）→ 返回结果或错误。"""
    started = time.perf_counter()
    attempts: list[dict] = []

    default_id = db.get_setting("ai_default_model_id", "")
    fallback_id = db.get_setting("ai_fallback_model_id", "")
    primary_id = ai_cfg.get("model_id") or default_id
    primary = _provider(primary_id)
    fallback = _provider(fallback_id) if str(fallback_id) else None
    if fallback and primary and fallback.get("id") == primary.get("id"):
        fallback = None

    instruction = str(ai_cfg.get("instruction") or "").strip()
    columns = [c.strip() for c in str(ai_cfg.get("columns") or "").split(",") if c.strip()]
    if not columns:
        columns = list(rows[0].keys()) if rows else []
    prompt_rows = _prompt_rows(rows, columns)
    messages = _build_messages(instruction, columns, prompt_rows, scenario)
    retry = max(0, int(ai_cfg.get("retry", 1) or 0))

    def try_model(provider: dict | None, role: str) -> dict | None:
        if not provider:
            attempts.append({"role": role, "model": "", "ok": False, "error": "未配置模型", "error_code": "config"})
            return None
        if not int(provider.get("enabled", 1) or 0):
            attempts.append({"role": role, "model": provider.get("name"), "ok": False, "error": "模型已停用", "error_code": "config"})
            return None
        last: dict | None = None
        for _ in range(retry + 1):
            result = call_model(provider, messages)
            attempts.append(
                {
                    "role": role,
                    "model": provider.get("name"),
                    "model_id": provider.get("id"),
                    "model_name": provider.get("model"),
                    "ok": bool(result.get("ok")),
                    "duration_ms": result.get("duration_ms", 0),
                    "error": result.get("error", ""),
                    "error_code": result.get("error_code", ""),
                }
            )
            if result.get("ok"):
                return {"provider": provider, "content": result["content"]}
            last = result
        return last and {"provider": provider, "failed": True, "error": last.get("error"), "error_code": last.get("error_code")}

    chosen = try_model(primary, "primary")
    if chosen and chosen.get("content"):
        payload, err = _parse_payload(chosen["content"])
        if payload is None and retry > 0:
            attempts.append({"role": "primary", "model": primary.get("name"), "ok": False, "error": err, "error_code": "invalid_json"})
        if payload is None:
            chosen = {"provider": primary, "failed": True, "error": err, "error_code": "invalid_json"}

    if not chosen or chosen.get("failed"):
        if fallback:
            chosen = try_model(fallback, "fallback")
            if chosen and chosen.get("content"):
                payload, err = _parse_payload(chosen["content"])
                if payload is None:
                    chosen = {"provider": fallback, "failed": True, "error": err, "error_code": "invalid_json"}

    duration = int((time.perf_counter() - started) * 1000)
    if not chosen or chosen.get("failed"):
        last_err = (chosen or {}).get("error") or "模型调用失败"
        return {
            "ok": False,
            "error": last_err,
            "error_code": (chosen or {}).get("error_code") or "network",
            "attempts": attempts,
            "duration_ms": duration,
            "model": _mask(primary) if primary else None,
            "fallback_model": _mask(fallback) if fallback else None,
            "row_count": len(rows),
            "instruction": instruction,
        }

    provider = chosen["provider"]
    payload, _ = _parse_payload(chosen["content"])
    applied = apply_actions(rows, payload or {})
    return {
        "ok": True,
        "rows": applied["rows"],
        "dropped": applied["dropped"],
        "summary": applied["summary"],
        "actions": applied["counts"],
        "warnings": applied["warnings"],
        "attempts": attempts,
        "duration_ms": duration,
        "model": _mask(provider),
        "fallback_used": any(a.get("role") == "fallback" and a.get("ok") for a in attempts),
        "input_rows": len(rows),
        "kept": len(applied["rows"]),
        "raw": chosen["content"] if ai_cfg.get("save_raw") else "",
    }

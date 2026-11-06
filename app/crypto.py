"""敏感字段落库加密（可选）。

在 .env 里设置 PUSHALL_SECRET_KEY 后，webhook / password 等字段会以
`enc:v1:` 前缀加密写入 SQLite；读取时自动解密。未设置时按明文存储。
注意：密钥一旦更换，历史密文将无法解密。
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from . import settings

PREFIX = "enc:v1:"

SECRET_KEYS = {
    "secret",
    "password",
    "token",
    "webhook",
    "webhook_url",
    "access_token",
    "api_key",
    "smtp_password",
    "private_key",
}


class DecryptError(Exception):
    pass


def enabled() -> bool:
    return bool(settings.SECRET_KEY)


def _fernet():
    from cryptography.fernet import Fernet

    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest())
    return Fernet(key)


def _walk(value: Any, fn) -> Any:
    if isinstance(value, dict):
        return {key: fn(key, item) for key, item in value.items()}
    if isinstance(value, list):
        return [_walk(item, fn) for item in value]
    return value


def seal(value: Any) -> Any:
    if not enabled():
        return value
    fernet = _fernet()

    def fn(key: str, item: Any):
        if key.lower() in SECRET_KEYS and isinstance(item, str) and item and not item.startswith(PREFIX):
            return PREFIX + fernet.encrypt(item.encode("utf-8")).decode("ascii")
        return _walk(item, fn)

    return _walk(value, fn)


def unseal(value: Any) -> Any:
    if not enabled():
        return value
    fernet = _fernet()

    def fn(key: str, item: Any):
        if isinstance(item, str) and item.startswith(PREFIX):
            try:
                return fernet.decrypt(item[len(PREFIX):].encode("ascii")).decode("utf-8")
            except Exception as exc:  # noqa: BLE001 - 交给调用方决定如何提示
                raise DecryptError(f"字段 {key} 解密失败，请检查 PUSHALL_SECRET_KEY 是否被更换") from exc
        return _walk(item, fn)

    return _walk(value, fn)


def dumps(value: Any, seal_fields: bool = True) -> str:
    payload = seal(value) if seal_fields else value
    return json.dumps(payload, ensure_ascii=False)


def loads(raw: str | None) -> Any:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return unseal(value)

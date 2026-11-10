"""插件级公共设置。

在「插件」页面为某个插件统一填写参数（如账号、密码、地区编码），
该插件的所有数据源 / 渠道都会自动带上；单个数据源里填了同名字段时以数据源为准。
"""

from __future__ import annotations

from . import crypto, db


def get(plugin_id: str) -> dict:
    raw = db.plugin_settings(plugin_id)
    data = crypto.loads(raw) if raw else {}
    return data if isinstance(data, dict) else {}


def has(plugin_id: str) -> bool:
    return bool(get(plugin_id))


def save(plugin_id: str, config: dict) -> None:
    db.save_plugin_settings(plugin_id, crypto.dumps(config or {}))


def clear(plugin_id: str) -> None:
    db.clear_plugin_settings(plugin_id)


def merge(plugin_id: str, config: dict | None) -> dict:
    """插件设置作为默认值，数据源/渠道里非空的值优先。"""
    merged = get(plugin_id)
    for key, value in (config or {}).items():
        if value is None or value == "":
            continue
        merged[key] = value
    return merged

"""插件发现、加载、安装。"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .. import db, settings
from .base import validate_config

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,60}$")
PLUGIN_TYPES = {"source", "sink"}


class PluginError(Exception):
    pass


@dataclass
class Plugin:
    manifest: dict
    schema: dict
    path: Path
    builtin: bool
    instance: Any = None
    error: str = ""

    @property
    def id(self) -> str:
        return str(self.manifest.get("id", ""))

    @property
    def type(self) -> str:
        return str(self.manifest.get("type", ""))

    @property
    def name(self) -> str:
        return str(self.manifest.get("name", self.id))

    @property
    def version(self) -> str:
        return str(self.manifest.get("version", ""))

    @property
    def ok(self) -> bool:
        return self.instance is not None and not self.error


_cache: dict[str, Plugin] = {}
_signature: tuple = ()


def _dirs() -> list[tuple[Path, bool]]:
    return [(settings.BUILTIN_PLUGIN_DIR, True), (settings.PLUGIN_DIR, False)]


def _signature_of() -> tuple:
    stamps = []
    for base, builtin in _dirs():
        if not base.exists():
            continue
        for child in base.iterdir():
            manifest = child / "manifest.json"
            if child.is_dir() and manifest.exists():
                try:
                    stamps.append((str(child), manifest.stat().st_mtime, builtin))
                except OSError:
                    continue
    return tuple(sorted(stamps))


def _import_entry(path: Path, entry: str) -> Any:
    module_name, _, class_name = entry.partition(":")
    file_path = path / module_name
    if not file_path.exists():
        raise PluginError(f"入口文件不存在：{module_name}")

    mod_name = f"pushall_plugin_{abs(hash((str(path), file_path.stat().st_mtime)))}"
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    if not spec or not spec.loader:
        raise PluginError(f"无法加载入口文件：{module_name}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    added = str(path)
    sys.path.insert(0, added)
    try:
        spec.loader.exec_module(module)
    finally:
        try:
            sys.path.remove(added)
        except ValueError:
            pass

    cls = getattr(module, class_name, None)
    if cls is None:
        raise PluginError(f"入口类不存在：{class_name}")
    return cls()


def _load_one(path: Path, builtin: bool) -> Plugin:
    manifest: dict = {}
    schema: dict = {}
    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return Plugin(manifest={}, schema={}, path=path, builtin=builtin, error=f"manifest.json 解析失败：{exc}")

    plugin_id = str(manifest.get("id", "")).strip()
    if not ID_RE.match(plugin_id):
        return Plugin(manifest=manifest, schema={}, path=path, builtin=builtin, error=f"插件 id 不合法：{plugin_id}")
    if manifest.get("type") not in PLUGIN_TYPES:
        return Plugin(manifest=manifest, schema={}, path=path, builtin=builtin, error="type 必须是 source 或 sink")

    schema_file = str(manifest.get("config_schema") or "")
    if schema_file:
        try:
            schema = json.loads((path / schema_file).read_text(encoding="utf-8-sig"))
        except Exception as exc:  # noqa: BLE001
            return Plugin(manifest=manifest, schema={}, path=path, builtin=builtin, error=f"schema 解析失败：{exc}")

    try:
        instance = _import_entry(path, str(manifest.get("entry") or "plugin.py:Plugin"))
    except Exception as exc:  # noqa: BLE001
        return Plugin(manifest=manifest, schema=schema, path=path, builtin=builtin, error=f"插件加载失败：{exc}")

    return Plugin(manifest=manifest, schema=schema, path=path, builtin=builtin, instance=instance)


def all_plugins(force: bool = False) -> dict[str, Plugin]:
    global _signature
    signature = _signature_of()
    if not force and signature == _signature and _cache:
        return _cache

    loaded: dict[str, Plugin] = {}
    for base, builtin in _dirs():
        if not base.exists():
            continue
        for child in sorted(base.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if not (child / "manifest.json").exists():
                continue
            plugin = _load_one(child, builtin)
            key = plugin.id or f"invalid:{child.name}"
            if key in loaded:
                plugin.error = (plugin.error + "；" if plugin.error else "") + f"插件 id 与 {loaded[key].path.name} 重复"
                key = f"dup:{child.name}"
            loaded[key] = plugin

    _cache.clear()
    _cache.update(loaded)
    _signature = signature
    return _cache


def get_plugin(plugin_id: str) -> Plugin | None:
    return all_plugins().get(plugin_id)


def list_public() -> list[dict]:
    disabled = db.disabled_plugin_ids()
    items: list[dict] = []
    for plugin in all_plugins().values():
        items.append(
            {
                "id": plugin.id or plugin.path.name,
                "type": plugin.type,
                "name": plugin.name,
                "version": plugin.version,
                "description": plugin.manifest.get("description", ""),
                "author": plugin.manifest.get("author", ""),
                "permissions": plugin.manifest.get("permissions", []),
                "icon": plugin.manifest.get("icon", ""),
                "schema": plugin.schema,
                "builtin": plugin.builtin,
                "error": plugin.error,
                "enabled": bool(plugin.id) and plugin.id not in disabled and not plugin.error,
            }
        )
    return items


def check_config(plugin_id: str, config: dict) -> Plugin:
    plugin = get_plugin(plugin_id)
    if not plugin:
        raise PluginError(f"插件不存在：{plugin_id}")
    if plugin.error:
        raise PluginError(f"插件不可用：{plugin.error}")
    if plugin.id in db.disabled_plugin_ids():
        raise PluginError(f"插件已禁用：{plugin.name}")
    errors = validate_config(plugin.schema, config)
    if errors:
        raise PluginError("；".join(errors))
    return plugin


def reload() -> None:
    all_plugins(force=True)


def _safe_extract(zf: zipfile.ZipFile, target: Path) -> None:
    root = target.resolve()
    for member in zf.infolist():
        name = member.filename.replace("\\", "/")
        if name.startswith("/") or ".." in Path(name).parts:
            raise PluginError(f"压缩包包含非法路径：{member.filename}")
        dest = (target / name).resolve()
        if root not in dest.parents and dest != root:
            raise PluginError(f"压缩包包含非法路径：{member.filename}")
    zf.extractall(target)


def install_zip(data: bytes) -> dict:
    settings.ensure_dirs()
    tmp_root = settings.PLUGIN_DIR / ".tmp"
    if tmp_root.exists():
        shutil.rmtree(tmp_root, ignore_errors=True)
    tmp_root.mkdir(parents=True, exist_ok=True)
    try:
        archive = tmp_root / "upload.zip"
        archive.write_bytes(data)
        extract_dir = tmp_root / "extract"
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as zf:
            _safe_extract(zf, extract_dir)

        manifest_path = extract_dir / "manifest.json"
        source_dir = extract_dir
        if not manifest_path.exists():
            children = [p for p in extract_dir.iterdir() if p.is_dir()]
            if len(children) == 1 and (children[0] / "manifest.json").exists():
                source_dir = children[0]
                manifest_path = source_dir / "manifest.json"
        if not manifest_path.exists():
            raise PluginError("压缩包内未找到 manifest.json")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        plugin_id = str(manifest.get("id", "")).strip()
        if not ID_RE.match(plugin_id):
            raise PluginError(f"插件 id 不合法：{plugin_id}")
        if manifest.get("type") not in PLUGIN_TYPES:
            raise PluginError("type 必须是 source 或 sink")

        target = settings.PLUGIN_DIR / plugin_id
        if target.exists():
            raise PluginError(f"插件已存在：{plugin_id}，请先删除旧目录")
        shutil.copytree(source_dir, target)
        reload()
        plugin = get_plugin(plugin_id)
        if plugin and plugin.error:
            shutil.rmtree(target, ignore_errors=True)
            reload()
            raise PluginError(plugin.error)
        return manifest
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def delete_plugin(plugin_id: str) -> None:
    plugin = get_plugin(plugin_id)
    if not plugin:
        raise PluginError(f"插件不存在：{plugin_id}")
    if plugin.builtin:
        raise PluginError("内置插件不能删除，可禁用")
    shutil.rmtree(plugin.path)
    reload()

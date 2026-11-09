# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：Windows 便携版（onedir）。"""

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).resolve().parent


def tree(src: Path, dest: str):
    """按文件收集资源，跳过 __pycache__ 与 .pyc。"""
    items = []
    for base, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        rel = os.path.relpath(base, src)
        target = dest if rel == "." else f"{dest}/{rel.replace(os.sep, '/')}"
        for name in files:
            if name.endswith((".pyc", ".pyo")):
                continue
            items.append((os.path.join(base, name), target))
    return items


datas = tree(ROOT / "app" / "web", "app/web")
datas += tree(ROOT / "app" / "plugins" / "builtin", "app/plugins/builtin")
binaries = []
hiddenimports = []

for package in ("pythonnet", "clr_loader"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("apscheduler")
hiddenimports += [
    "app.main",
    "app.updater",
    "app.runner",
    "app.scheduler",
    "app.templating",
    "app.db",
    "app.crypto",
    "app.plugins.loader",
    "app.plugins.base",
    "webview.platforms.winforms",
    "pystray._win32",
    "anyio._backends._asyncio",
    "httpx._transports.default",
    "markdown.extensions.tables",
    "markdown.extensions.fenced_code",
    "markdown.extensions.sane_lists",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
]

for package in ("uvicorn", "fastapi", "starlette", "pydantic", "apscheduler", "httpx", "markdown", "jinja2", "webview", "pystray"):
    try:
        datas += copy_metadata(package)
    except Exception:
        pass

a = Analysis(
    [str(ROOT / "desktop.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc_data", "test"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PushAll",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "app" / "web" / "icon.ico"),
    version=str(ROOT / "packaging" / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="PushAll",
)



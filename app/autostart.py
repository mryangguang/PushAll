"""Windows 开机自启动（HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import settings

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "PushAll"


def supported() -> bool:
    return sys.platform == "win32"


def command() -> str:
    """返回写入注册表的启动命令（带 --tray，登录后只在托盘运行）。"""
    if settings.FROZEN:
        return f'"{sys.executable}" --tray'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    script = settings.APP_HOME / "desktop.py"
    return f'"{exe}" "{script}" --tray'


def _key_path(key_path: str | None = None) -> str:
    """允许用环境变量覆盖（测试用），默认写用户注册表 Run。"""
    return key_path or os.getenv("PUSHALL_AUTOSTART_KEY") or RUN_KEY


def is_enabled(key_path: str | None = None) -> bool:
    if not supported():
        return False
    import winreg

    key_path = _key_path(key_path)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(str(value).strip())
    except OSError:
        return False


def enable(key_path: str | None = None) -> str:
    if not supported():
        raise RuntimeError("仅支持 Windows")
    import winreg

    key_path = _key_path(key_path)
    cmd = command()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, cmd)
    return cmd


def disable(key_path: str | None = None) -> None:
    if not supported():
        return
    import winreg

    key_path = _key_path(key_path)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except OSError:
        pass

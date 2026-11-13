"""全局配置：读取环境变量与项目根目录下的 .env。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
# 只读资源：源码运行时是项目根；PyInstaller 打包后是 _internal
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
# 可写目录：数据、日志、用户插件都放 exe 同级，保证“解压即用、可整包搬走”
APP_HOME = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent.parent
BASE_DIR = APP_HOME
WEB_DIR = RESOURCE_DIR / "app" / "web"


def _load_env_file() -> None:
    path = BASE_DIR / ".env"
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


_load_env_file()


def _path(env_name: str, default: Path) -> Path:
    raw = (os.getenv(env_name) or "").strip()
    return Path(raw).expanduser().resolve() if raw else default.resolve()


def _int(env_name: str, default: int) -> int:
    raw = (os.getenv(env_name) or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


APP_NAME = "PushAll 消息中心"
VERSION = "0.1.20"

DATA_DIR = _path("PUSHALL_DATA_DIR", BASE_DIR / "data")
LOG_DIR = _path("PUSHALL_LOG_DIR", BASE_DIR / "logs")
PLUGIN_DIR = _path("PUSHALL_PLUGIN_DIR", BASE_DIR / "plugins")
UPDATES_DIR = DATA_DIR / "updates"
DB_PATH = DATA_DIR / "pushall.db"

TIMEZONE = (os.getenv("PUSHALL_TZ") or "Asia/Shanghai").strip()
API_TOKEN = (os.getenv("PUSHALL_TOKEN") or "").strip()
SECRET_KEY = (os.getenv("PUSHALL_SECRET_KEY") or "").strip()

MAX_ROWS = _int("PUSHALL_MAX_ROWS", 500)
LOG_KEEP_DAYS = _int("PUSHALL_LOG_KEEP_DAYS", 90)
HTTP_TIMEOUT = _int("PUSHALL_HTTP_TIMEOUT", 20)

BUILTIN_PLUGIN_DIR = RESOURCE_DIR / "app" / "plugins" / "builtin"


def ensure_dirs() -> None:
    for path in (DATA_DIR, LOG_DIR, PLUGIN_DIR, UPDATES_DIR):
        path.mkdir(parents=True, exist_ok=True)
















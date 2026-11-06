"""PushAll 桌面端。

- 双击启动（无控制台窗口）
- 关闭 / 最小化时收进系统托盘
- 托盘右键：打开主界面、重启服务、退出
- 重复启动只会唤回已运行窗口，不会再开一个实例
"""

from __future__ import annotations

import ctypes
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

import httpx
import uvicorn

BASE_DIR = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = int(os.getenv("PUSHALL_PORT", "8765") or 8765)
URL = f"http://{HOST}:{PORT}"
WEB_DIR = BASE_DIR / "app" / "web"
ICON_PNG = WEB_DIR / "icon.png"
ICON_ICO = WEB_DIR / "icon.ico"
LOG_FILE = BASE_DIR / "logs" / "desktop.log"


def ensure_streams() -> None:
    """pythonw 下 sys.stdout/stderr 为 None，uvicorn 日志会因此崩溃。"""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        (BASE_DIR / "logs").mkdir(parents=True, exist_ok=True)
        handle = open(BASE_DIR / "logs" / "desktop.out.log", "a", encoding="utf-8", buffering=1)
    except OSError:
        return
    if sys.stdout is None:
        sys.stdout = handle
    if sys.stderr is None:
        sys.stderr = handle


def log(message: str) -> None:
    """pythonw 无控制台，桌面端关键动作写文件便于排查。"""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > 2 * 1024 * 1024:
            LOG_FILE.write_text("", encoding="utf-8")
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass


def alert(message: str, title: str = "PushAll") -> None:
    """pythonw 没有控制台，用系统弹窗提示致命错误。"""
    try:
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)
    except Exception:  # noqa: BLE001
        print(f"{title}: {message}", file=sys.stderr)


# ---------------- 图标 ----------------

def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], k: float) -> tuple[int, int, int]:
    return tuple(int(round(a[i] + (b[i] - a[i]) * k)) for i in range(3))


def _gradient_color(t: float) -> tuple[int, int, int]:
    stops = [(0.0, (76, 141, 255)), (0.55, (47, 111, 237)), (1.0, (124, 92, 255))]
    for index in range(len(stops) - 1):
        t0, c0 = stops[index]
        t1, c1 = stops[index + 1]
        if t <= t1:
            k = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return _lerp(c0, c1, k)
    return stops[-1][1]


def ensure_icons() -> None:
    if ICON_PNG.exists() and ICON_ICO.exists():
        return
    from PIL import Image, ImageDraw, ImageFont

    WEB_DIR.mkdir(parents=True, exist_ok=True)
    size = 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gradient = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(gradient)
    for y in range(size):
        draw.line([(0, y), (size, y)], fill=_gradient_color(y / (size - 1)))

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=58, fill=255)
    image.paste(gradient, (0, 0), mask)

    font = None
    for name in ("arialbd.ttf", "seguisb.ttf", "segoeuib.ttf"):
        try:
            font = ImageFont.truetype(name, int(size * 0.40))
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default(size=int(size * 0.40))
    ImageDraw.Draw(image).text(
        (size / 2, size / 2 + 2), "PA", font=font, fill=(255, 255, 255, 255), anchor="mm"
    )

    image.save(ICON_PNG)
    image.save(
        ICON_ICO,
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


# ---------------- 服务 ----------------

def port_open(timeout: float = 0.3) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((HOST, PORT)) == 0


def http_ok(timeout: float = 1.0) -> bool:
    try:
        return httpx.get(f"{URL}/api/health", timeout=timeout).status_code == 200
    except Exception:  # noqa: BLE001
        return False


def wait_http(timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if http_ok(0.5):
            return True
        time.sleep(0.2)
    return False


class ServerManager:
    def __init__(self) -> None:
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        config = uvicorn.Config(
            "app.main:app", host=HOST, port=PORT, log_level="warning", access_log=False
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, name="pushall-server", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        if server:
            server.should_exit = True
        if thread:
            thread.join(timeout=10)

    def restart(self) -> bool:
        self.stop()
        for _ in range(60):
            if not port_open():
                break
            time.sleep(0.1)
        self.start()
        return wait_http(20)


# ---------------- 桌面应用 ----------------

class DesktopApp:
    def __init__(self, server: ServerManager) -> None:
        self.server = server
        self.window = None
        self.icon = None
        self.quitting = False
        self.tray_ready = False
        self._notified = False

    def attach(self, window) -> None:
        self.window = window

    # ----- GUI 线程启动后创建托盘 -----
    def on_gui_ready(self) -> None:
        try:
            import pystray
            from PIL import Image
        except ImportError:
            alert("缺少托盘依赖，请执行：pip install -r requirements-desktop.txt")
            return

        image = Image.open(ICON_PNG)
        menu = pystray.Menu(
            pystray.MenuItem("打开主界面", self.open_window, default=True),
            pystray.MenuItem("重启服务", self.restart_service),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self.quit_app),
        )
        self.icon = pystray.Icon("pushall", image, "PushAll 消息中心", menu)
        self.tray_ready = True
        threading.Thread(target=self._run_tray, name="pushall-tray", daemon=True).start()
        log("托盘图标已启动")

    def _run_tray(self) -> None:
        try:
            self.icon.run(setup=self._tray_setup)
        except Exception as exc:  # noqa: BLE001
            self.tray_ready = False
            log(f"托盘启动失败：{exc}")

    def _tray_setup(self, icon) -> None:
        icon.visible = True
        log("托盘图标已显示")

    # ----- 托盘动作 -----
    def open_window(self, icon=None, item=None) -> None:
        if not self.window:
            return
        try:
            self.window.show()
            self.window.restore()
        except Exception:  # noqa: BLE001
            pass

    def restart_service(self, icon=None, item=None) -> None:
        def work() -> None:
            log("开始重启服务")
            self._notify("正在重启服务…")
            ok = self.server.restart()
            log("服务重启完成" if ok else "服务重启失败")
            if self.window:
                try:
                    self.window.load_url(URL)
                except Exception:  # noqa: BLE001
                    pass
            self._notify("服务已重启" if ok else "服务重启失败，请查看日志")

        threading.Thread(target=work, name="pushall-restart", daemon=True).start()

    def quit_app(self, icon=None, item=None) -> None:
        log("用户从托盘退出")
        self.quitting = True
        try:
            if self.icon:
                self.icon.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            if self.window:
                self.window.destroy()
        except Exception:  # noqa: BLE001
            pass
        self.server.stop()

    # ----- 窗口事件 -----
    def on_closing(self) -> bool:
        """点关闭按钮时收进托盘；返回 False 表示阻止真正关闭。"""
        if self.quitting or not self.tray_ready:
            return True
        log("窗口关闭 → 收进托盘")
        try:
            self.window.hide()
        except Exception:  # noqa: BLE001
            pass
        self._notify_once("PushAll 已最小化到托盘，双击图标可重新打开")
        return False

    def on_minimized(self) -> None:
        if not self.tray_ready:
            return
        log("窗口最小化 → 收进托盘")
        try:
            self.window.hide()
        except Exception:  # noqa: BLE001
            pass
        self._notify_once("PushAll 已最小化到托盘，双击图标可重新打开")

    def _notify(self, text: str) -> None:
        try:
            if self.icon:
                self.icon.notify(text, "PushAll")
        except Exception:  # noqa: BLE001
            pass

    def _notify_once(self, text: str) -> None:
        if self._notified:
            return
        self._notified = True
        self._notify(text)


# ---------------- 入口 ----------------

def _run() -> int:
    ensure_icons()

    # 已有实例：唤回窗口后直接退出
    if http_ok(0.8):
        try:
            if httpx.post(f"{URL}/api/app/show", timeout=1.5).status_code == 200:
                return 0
        except Exception:  # noqa: BLE001
            pass
        webbrowser.open(URL)
        return 0

    if port_open():
        alert(f"端口 {PORT} 已被其他程序占用，PushAll 无法启动。")
        return 1

    log(f"启动桌面端，端口 {PORT}")
    server = ServerManager()
    server.start()
    if not wait_http():
        server.stop()
        alert("服务启动失败，请检查依赖是否安装完整，或在命令行运行 desktop.py 查看错误。")
        return 1

    try:
        import webview
    except ImportError:
        alert("未安装 pywebview，请执行：pip install -r requirements-desktop.txt")
        server.stop()
        return 1

    from app.main import app as fastapi_app

    window = webview.create_window(
        "PushAll 消息中心",
        URL,
        width=1280,
        height=840,
        min_size=(1000, 660),
        background_color="#f4f6fa",
        text_select=True,
    )
    desktop = DesktopApp(server)
    desktop.attach(window)
    fastapi_app.state.show_window = desktop.open_window
    log("主窗口已创建")

    window.events.closing += desktop.on_closing
    window.events.minimized += desktop.on_minimized

    try:
        webview.start(desktop.on_gui_ready, icon=str(ICON_ICO))
    finally:
        desktop.quitting = True
        try:
            if desktop.icon:
                desktop.icon.stop()
        except Exception:  # noqa: BLE001
            pass
        server.stop()
        log("桌面端已退出")
    return 0


def main() -> int:
    ensure_streams()
    try:
        return _run()
    except Exception:  # noqa: BLE001
        import traceback

        log("启动失败：\n" + traceback.format_exc())
        alert("启动失败，详细信息见 logs\\desktop.log")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())





"""更新进度窗口（tkinter）：升级时只显示这一个窗口，不弹命令行。"""

from __future__ import annotations

import os


class UpdateProgress:
    def __init__(self, version: str = "") -> None:
        import tkinter as tk
        from tkinter import ttk

        self._tk = tk
        self.root = tk.Tk()
        self.root.title("PushAll 更新")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)

        width, height = 420, 160
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        icon = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "web", "icon.ico")
        try:
            if os.path.exists(icon):
                self.root.iconbitmap(icon)
        except Exception:  # noqa: BLE001
            pass

        title = f"正在更新到 v{version}…" if version else "正在更新…"
        tk.Label(self.root, text=title, font=("Microsoft YaHei UI", 11, "bold")).pack(pady=(18, 6))
        self._status = tk.StringVar(value="准备更新…")
        tk.Label(self.root, textvariable=self._status, fg="#666666").pack()
        self._bar = ttk.Progressbar(self.root, mode="indeterminate", length=360)
        self._bar.pack(pady=14)
        self._bar.start(12)
        self._closed = False
        self._finished = False

    def set_status(self, text: str) -> None:
        def _apply():
            if not self._closed:
                self._status.set(text)

        try:
            self.root.after(0, _apply)
        except Exception:  # noqa: BLE001
            pass

    def finish(self, ok: bool, message: str) -> None:
        if self._finished:
            return
        self._finished = True

        def _apply():
            if self._closed:
                return
            try:
                self._bar.stop()
            except Exception:  # noqa: BLE001
                pass
            self._status.set(message)
            if ok:
                self.root.after(700, self._close)
            else:
                self.root.protocol("WM_DELETE_WINDOW", self._close)
                button = self._tk.Button(self.root, text="关闭", width=10, command=self._close)
                button.pack(pady=(4, 0))

        try:
            self.root.after(0, _apply)
        except Exception:  # noqa: BLE001
            pass

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.root.destroy()
        except Exception:  # noqa: BLE001
            pass

    def run(self) -> None:
        try:
            self.root.mainloop()
        except Exception:  # noqa: BLE001
            pass

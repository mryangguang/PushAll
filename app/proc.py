"""进程工具：隐藏控制台窗口、判断进程是否存活。"""

from __future__ import annotations

import os
import subprocess

CREATE_NO_WINDOW = 0x08000000


def hidden_kwargs() -> dict:
    """运行控制台程序（taskkill/tasklist/cmd）时不弹黑窗。"""
    if os.name != "nt":
        return {}
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
        "startupinfo": info,
    }


def detached_kwargs() -> dict:
    """启动独立进程（更新后的应用 / 清理脚本），不附着控制台。"""
    if os.name != "nt":
        return {"start_new_session": True}
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        "startupinfo": info,
    }


def pid_alive(pid: int) -> bool:
    """不调用 tasklist，直接用 Win32 API 判断进程是否还活着。"""
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)

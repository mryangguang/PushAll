"""GitHub Releases 自动更新。

流程：检查最新 Release → 下载 zip → 校验 SHA256 → 解压到临时目录
→ 启动独立更新脚本（等待本进程退出）→ 替换程序文件（保留 data/plugins/logs）→ 重启。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

from . import settings

DEFAULT_REPO = "mryangguang/PushAll"
API_URL = "https://api.github.com/repos/{repo}/releases/latest"
ALLOWED_HOSTS = ("github.com", "githubusercontent.com")


def repo() -> str:
    return (os.getenv("PUSHALL_UPDATE_REPO") or DEFAULT_REPO).strip()


def token() -> str:
    return (os.getenv("PUSHALL_UPDATE_TOKEN") or "").strip()


def enabled() -> bool:
    return (os.getenv("PUSHALL_UPDATE_DISABLED") or "").strip() not in ("1", "true", "yes")


def parse_version(text: str) -> tuple[int, ...]:
    numbers = [int(n) for n in re.findall(r"\d+", str(text or ""))][:4]
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()
    return tuple(numbers) if numbers else (0,)


def is_newer(latest: str, current: str | None = None) -> bool:
    return parse_version(latest) > parse_version(current or settings.VERSION)


def _headers() -> dict:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "PushAll-Updater"}
    if token():
        headers["Authorization"] = f"token {token()}"
    return headers


def check_latest(timeout: float = 12) -> dict:
    """查询 GitHub 最新 Release，网络失败时返回 ok=False，不抛异常。"""
    base = {"current": settings.VERSION, "repo": repo()}
    try:
        with httpx.Client(timeout=httpx.Timeout(timeout, connect=15.0), follow_redirects=True) as client:
            resp = client.get(API_URL.format(repo=repo()), headers=_headers())
    except httpx.HTTPError as exc:
        return {**base, "ok": False, "error": f"网络错误：{exc}"}

    if resp.status_code == 404:
        return {**base, "ok": False, "error": "未找到 Release（仓库可能未公开或尚未发布版本）"}
    if resp.status_code != 200:
        return {**base, "ok": False, "error": f"GitHub 返回 HTTP {resp.status_code}"}

    data = resp.json()
    tag = str(data.get("tag_name") or "")
    latest = tag.lstrip("vV")
    assets = data.get("assets") or []

    zip_asset = None
    for asset in assets:
        name = str(asset.get("name") or "")
        if name.endswith(".zip") and ("win64" in name or "windows" in name):
            zip_asset = asset
            break
    if zip_asset is None:
        for asset in assets:
            if str(asset.get("name") or "").endswith(".zip"):
                zip_asset = asset
                break

    sha_asset = next((a for a in assets if str(a.get("name") or "").endswith(".sha256")), None)

    return {
        **base,
        "ok": True,
        "tag": tag,
        "latest": latest,
        "update_available": is_newer(latest),
        "name": data.get("name") or tag,
        "notes": data.get("body") or "",
        "published_at": data.get("published_at") or "",
        "html_url": data.get("html_url") or "",
        "asset": {
            "name": zip_asset.get("name"),
            "url": zip_asset.get("browser_download_url"),
            "size": zip_asset.get("size") or 0,
        }
        if zip_asset
        else None,
        "sha256_url": (sha_asset or {}).get("browser_download_url"),
        "can_apply": settings.FROZEN,
    }


def _check_url(url: str) -> None:
    host = (urlparse(url).hostname or "").lower()
    if not any(host == allowed or host.endswith("." + allowed) for allowed in ALLOWED_HOSTS):
        raise ValueError(f"下载地址不在 GitHub 域名下：{host}")


def _mirror_url(url: str) -> str | None:
    """PUSHALL_UPDATE_MIRROR 支持前缀或 {url} 模板，例如 https://ghproxy.net/"""
    mirror = (os.getenv("PUSHALL_UPDATE_MIRROR") or "").strip()
    if not mirror:
        return None
    if "{url}" in mirror:
        return mirror.replace("{url}", url)
    return mirror.rstrip("/") + "/" + url


def _download(url: str, target: Path, timeout: float = 600) -> None:
    _check_url(url)
    headers = {"User-Agent": "PushAll-Updater"}
    if token():
        headers["Authorization"] = f"token {token()}"

    candidates = [u for u in (_mirror_url(url), url) if u]
    last_error: Exception | None = None
    for candidate in candidates:
        for attempt in range(2):
            try:
                with httpx.Client(timeout=httpx.Timeout(timeout, connect=15.0), follow_redirects=True) as client:
                    with client.stream("GET", candidate, headers=headers) as resp:
                        resp.raise_for_status()
                        with target.open("wb") as handle:
                            for chunk in resp.iter_bytes(65536):
                                handle.write(chunk)
                return
            except (httpx.HTTPError, OSError) as exc:
                last_error = exc
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(
        f"下载失败（直连与镜像均不可用）：{last_error}。"
        f"可手动下载后放到 data/updates/ 目录，再点一次更新。"
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_extract(archive: zipfile.ZipFile, target: Path) -> None:
    root = target.resolve()
    for member in archive.infolist():
        name = member.filename.replace("\\", "/")
        if name.startswith("/") or ".." in Path(name).parts:
            raise ValueError(f"压缩包包含非法路径：{member.filename}")
        dest = (target / name).resolve()
        if root not in dest.parents and dest != root:
            raise ValueError(f"压缩包包含非法路径：{member.filename}")
    archive.extractall(target)


def _extract(archive_path: Path, version: str) -> Path:
    work = Path(tempfile.gettempdir()) / f"pushall-update-{version}"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)

    extract_dir = work / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        _safe_extract(archive, extract_dir)

    candidates = [p.parent for p in extract_dir.rglob("PushAll.exe")]
    if not candidates:
        raise ValueError("安装包内未找到 PushAll.exe")
    candidates.sort(key=lambda p: 0 if (p / "_internal").exists() else 1)
    return candidates[0]


def stage_from_archive(archive_path: Path, version: str = "test") -> Path:
    """直接解压本地安装包（供测试与离线更新使用）。"""
    return _extract(Path(archive_path), version)


def stage(release: dict) -> Path:
    """准备安装包：优先使用 data/updates 下的同名文件，否则下载。"""
    asset = release.get("asset")
    if not asset or not asset.get("url"):
        raise ValueError("该 Release 没有可用的 zip 安装包")

    version = release.get("latest") or "latest"
    name = str(asset.get("name") or "update.zip")

    settings.ensure_dirs()
    local = settings.UPDATES_DIR / name
    if local.exists():
        archive_path = local
    else:
        work = Path(tempfile.gettempdir()) / f"pushall-download-{version}"
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True, exist_ok=True)
        archive_path = work / "update.zip"
        _download(asset["url"], archive_path)

    expected_size = int(asset.get("size") or 0)
    if expected_size and archive_path.stat().st_size != expected_size:
        raise ValueError("安装包大小与 Release 不一致，可能下载不完整")

    sha_text = ""
    local_sha = local.with_name(local.name + ".sha256")
    if local.exists() and local_sha.exists():
        sha_text = local_sha.read_text(encoding="utf-8", errors="ignore")
    elif release.get("sha256_url"):
        sha_file = archive_path.with_name(archive_path.name + ".sha256")
        try:
            _download(str(release["sha256_url"]), sha_file)
            sha_text = sha_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:  # noqa: BLE001 - 没拿到校验文件时退化为大小校验
            sha_text = ""

    match = re.search(r"[0-9a-fA-F]{64}", sha_text)
    if match and match.group(0).lower() != _sha256(archive_path):
        raise ValueError("SHA256 校验失败，已取消更新")

    return _extract(archive_path, version)


def launch_updater(source_dir: Path, app_dir: Path, pid: int | None = None, restart: bool = True) -> Path:
    """生成更新脚本并后台启动；脚本会等待 pid 退出后再替换文件。"""
    app_dir = app_dir.resolve()
    source_dir = source_dir.resolve()
    pid = pid or os.getpid()

    script = Path(tempfile.gettempdir()) / f"pushall-update-{int(time.time())}.cmd"
    log_file = app_dir / "logs" / "update.log"
    restart_line = f'start "" "{app_dir / "PushAll.exe"}"' if restart else "rem restart skipped"

    lines = [
        "@echo off",
        "chcp 65001 >nul",
        "setlocal",
        f'if not exist "{app_dir / "logs"}" mkdir "{app_dir / "logs"}"',
        f'echo [%date% %time%] update start >> "{log_file}"',
        ":wait_app",
        f'powershell -NoProfile -WindowStyle Hidden -Command "if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}"',
        "if not errorlevel 1 (timeout /t 1 /nobreak >nul & goto wait_app)",
        f'robocopy "{source_dir}" "{app_dir}" /E /IS /IT /XD data plugins logs /XF .env /R:5 /W:2 >> "{log_file}" 2>&1',
        "if errorlevel 8 (",
        f'  echo [%date% %time%] update failed, robocopy code %errorlevel% >> "{log_file}"',
        "  exit /b 1",
        ")",
        f'echo [%date% %time%] update done >> "{log_file}"',
        restart_line,
        "timeout /t 2 /nobreak >nul",
        f'rmdir /S /Q "{source_dir}"',
        '(goto) 2>nul & del "%~f0"',
    ]
    script.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")

    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    subprocess.Popen(
        ["cmd.exe", "/c", str(script)],
        cwd=str(app_dir),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )
    return script


# ---------------- 跳过记录 ----------------

def _state_file() -> Path:
    settings.ensure_dirs()
    return settings.DATA_DIR / "update_state.json"


def _read_state() -> dict:
    try:
        return json.loads(_state_file().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def is_skipped(version: str) -> bool:
    return str(_read_state().get("skipped") or "") == str(version)


def mark_skipped(version: str) -> None:
    state = _read_state()
    state["skipped"] = str(version)
    state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        _state_file().write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass





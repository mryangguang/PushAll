#!/usr/bin/env python3
"""推送前安全检查：拦截敏感文件、常见密钥与超大文件。

用法：
    python tools/security_check.py            # 检查当前跟踪的文件
    python tools/security_check.py --history  # 额外检查全部 git 历史
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN_DIRS = {
    ".venv", "venv", "env", "__pycache__", "data", "logs", "dist", "build",
    "node_modules", ".idea", ".vscode", ".pytest_cache", ".mypy_cache",
}
FORBIDDEN_SUFFIXES = {
    ".db", ".sqlite", ".sqlite3", ".log", ".zip", ".7z", ".rar", ".tar", ".gz",
    ".pem", ".key", ".pfx", ".p12", ".jks", ".keystore", ".lnk",
    ".xlsx", ".xls", ".csv", ".pdf", ".docx", ".doc", ".bak", ".tmp",
}
FORBIDDEN_NAMES = {
    ".env", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    "credentials.json", "secrets.json", "secrets.yml", "secrets.yaml",
}
ALLOWED = {".env.example", "plugins/.gitkeep"}
MAX_SIZE = 5 * 1024 * 1024

SECRET_PATTERNS = [
    ("DingTalk webhook token", re.compile(r"oapi\.dingtalk\.com/robot/send\?access_token=[A-Za-z0-9]{20,}")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("Hardcoded password", re.compile(r"(?i)\b(?:password|passwd|pwd)\s*[:=]\s*['\"][^'\"\s]{6,}['\"]")),
    ("Hardcoded secret", re.compile(r"(?i)\b(?:secret|token|api_key)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]")),
]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8", errors="ignore")


def tracked_files() -> list[str]:
    return [line for line in git("ls-files").splitlines() if line]


def history_files() -> set[str]:
    out = git("log", "--all", "--name-only", "--pretty=format:")
    return {line.strip() for line in out.splitlines() if line.strip()}


def check_path(name: str) -> list[str]:
    issues = []
    path = Path(name)
    if name in ALLOWED:
        return issues
    parts = set(path.parts)
    if parts & FORBIDDEN_DIRS:
        issues.append(f"{name}: 位于受禁目录（{', '.join(sorted(parts & FORBIDDEN_DIRS))}）")
    if path.suffix.lower() in FORBIDDEN_SUFFIXES:
        issues.append(f"{name}: 受禁文件类型（{path.suffix}）")
    if path.name in FORBIDDEN_NAMES:
        issues.append(f"{name}: 受禁文件名")
    return issues


def check_content(name: str) -> list[str]:
    issues = []
    path = ROOT / name
    if not path.is_file():
        return issues
    size = path.stat().st_size
    if size > MAX_SIZE:
        issues.append(f"{name}: 文件过大（{size / 1024 / 1024:.1f} MB > 5 MB）")
    if path.suffix.lower() in {".png", ".ico", ".jpg", ".jpeg", ".gif", ".woff", ".woff2", ".ttf", ".dll", ".pyd", ".exe"}:
        return issues
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return issues
    for label, pattern in SECRET_PATTERNS:
        match = pattern.search(text)
        if match:
            line = text.count("\n", 0, match.start()) + 1
            issues.append(f"{name}:{line}: 疑似 {label}")
    return issues


def check_history() -> list[str]:
    issues = []
    for name in sorted(history_files()):
        if name in ALLOWED:
            continue
        path = Path(name)
        if set(path.parts) & FORBIDDEN_DIRS or path.name in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            issues.append(f"历史提交中出现过受禁文件：{name}")
    diff = git("log", "--all", "-p", "--no-color")
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(diff):
            issues.append(f"历史提交中发现疑似 {label}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", action="store_true", help="扫描全部 git 历史")
    args = parser.parse_args()

    files = tracked_files()
    issues: list[str] = []
    for name in files:
        issues += check_path(name)
        issues += check_content(name)
    if args.history:
        issues += check_history()

    if issues:
        print(f"[FAIL] 发现 {len(issues)} 个问题，已阻止推送：")
        for item in dict.fromkeys(issues):
            print("  - " + item)
        print("\n处理方式：删除敏感文件并加入 .gitignore；若已提交，需要重写历史后再推送。")
        return 1

    print(f"[OK] 已检查 {len(files)} 个跟踪文件" + ("（含 git 历史）" if args.history else "") + "，未发现敏感内容。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

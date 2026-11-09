#!/usr/bin/env python3
"""提醒：每累计约 10 次提交，刷新 GitHub About 与 README。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
META = ROOT / ".github" / "project-meta.json"


def main() -> int:
    try:
        meta = json.loads(META.read_text(encoding="utf-8"))
    except Exception:
        print("[WARN] 缺少 .github/project-meta.json")
        return 0
    since = meta.get("last_readme_refresh", "1970-01-01")
    limit = int(meta.get("refresh_every", 10))
    try:
        count = int(
            subprocess.check_output(
                ["git", "rev-list", "--count", f"--since={since}", "HEAD"],
                cwd=ROOT,
                text=True,
            ).strip()
        )
    except Exception:
        print("[WARN] 无法统计提交数")
        return 0
    if count >= limit:
        print(f"[提醒] 距上次整理 README/About 已有 {count} 次提交（阈值 {limit}），建议更新。")
    else:
        print(f"[OK] 距上次整理 README/About：{count}/{limit} 次提交。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

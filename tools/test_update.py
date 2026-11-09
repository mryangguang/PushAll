"""更新流程测试（不会替换当前安装）。

用法：
    python tools/test_update.py           # 版本比较 + 查询最新 Release
    python tools/test_update.py --apply   # 额外验证下载、解压、替换逻辑（临时目录）
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import updater  # noqa: E402


def test_versions() -> None:
    cases = [
        ("v0.1.1", "0.1.0", True),
        ("0.1.0", "0.1.0", False),
        ("v0.1.1.0", "0.1.1", False),
        ("v1.0.0", "0.9.9", True),
        ("v0.10.0", "0.2.0", True),
    ]
    for latest, current, expected in cases:
        actual = updater.is_newer(latest, current)
        assert actual == expected, f"{latest} vs {current}: {actual} != {expected}"
    print("[1/3] 版本比较正常")


def test_check() -> dict:
    info = updater.check_latest()
    print("[2/3] Release 查询:", {k: info.get(k) for k in ("ok", "latest", "current", "update_available", "can_apply")})
    if not info.get("ok"):
        raise SystemExit(f"查询失败：{info.get('error')}")
    return info


def test_apply(info: dict) -> None:
    if not info.get("asset"):
        raise SystemExit("最新 Release 没有 zip 安装包")

    local = Path("dist") / f"PushAll-{info['latest']}-win64.zip"
    if local.exists():
        print(f"[3/3] 使用本地安装包验证：{local}")
        sha_file = local.with_name(local.name + ".sha256")
        if sha_file.exists():
            expected = sha_file.read_text(encoding="utf-8").split()[0].lower()
            assert updater._sha256(local) == expected, "本地包 SHA256 不匹配"
            print("      SHA256 校验通过")
        staged = updater.stage_from_archive(local, info["latest"])
    else:
        print("[3/3] 下载并解压最新安装包…")
        staged = updater.stage(info)
    assert (staged / "PushAll.exe").exists(), "缺少 PushAll.exe"
    assert (staged / "_internal").exists(), "缺少 _internal"

    fake = Path(tempfile.mkdtemp(prefix="pushall-fake-app-")) / "PushAll"
    (fake / "data").mkdir(parents=True)
    (fake / "plugins").mkdir(parents=True)
    (fake / "data" / "keep.txt").write_text("keep", encoding="utf-8")
    (fake / "plugins" / "keep.txt").write_text("keep", encoding="utf-8")
    (fake / "old.txt").write_text("old", encoding="utf-8")

    updater.launch_updater(staged, fake, pid=999999, restart=False)
    for _ in range(120):
        if (fake / "PushAll.exe").exists() and not staged.exists():
            break
        time.sleep(0.5)

    assert (fake / "PushAll.exe").exists(), "替换后缺少 exe"
    assert (fake / "_internal").exists(), "替换后缺少 _internal"
    assert (fake / "data" / "keep.txt").exists(), "data 未保留"
    assert (fake / "plugins" / "keep.txt").exists(), "plugins 未保留"
    assert not staged.exists(), "临时目录未清理"
    print("      替换验证通过，用户数据已保留")
    shutil.rmtree(fake.parent, ignore_errors=True)


def main() -> None:
    test_versions()
    info = test_check()
    if "--apply" in sys.argv:
        test_apply(info)
    print("OK")


if __name__ == "__main__":
    main()



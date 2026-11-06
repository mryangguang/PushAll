"""APScheduler 定时调度。"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import db, runner, settings

log = logging.getLogger("pushall.scheduler")
_scheduler: BackgroundScheduler | None = None


def start() -> None:
    global _scheduler
    if _scheduler:
        return
    _scheduler = BackgroundScheduler(
        timezone=settings.TIMEZONE,
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
    )
    _scheduler.start()
    sync()
    _scheduler.add_job(
        _purge,
        CronTrigger.from_crontab("30 3 * * *", timezone=settings.TIMEZONE),
        id="maintenance:purge",
        replace_existing=True,
    )
    log.info("调度器已启动，时区 %s", settings.TIMEZONE)


def shutdown() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def validate(expr: str) -> str | None:
    try:
        CronTrigger.from_crontab(expr.strip(), timezone=settings.TIMEZONE)
        return None
    except Exception as exc:  # noqa: BLE001
        return str(exc)


def next_runs(expr: str, count: int = 3) -> list[str]:
    try:
        trigger = CronTrigger.from_crontab(expr.strip(), timezone=settings.TIMEZONE)
    except Exception:  # noqa: BLE001
        return []
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo(settings.TIMEZONE))
    result = []
    previous = None
    for _ in range(count):
        nxt = trigger.get_next_fire_time(previous, now if previous is None else previous)
        if not nxt:
            break
        result.append(nxt.strftime("%Y-%m-%d %H:%M:%S"))
        previous = nxt
        now = nxt
    return result


def sync() -> None:
    if not _scheduler:
        return
    wanted: set[str] = set()
    for scenario in db.fetch_all("scenario"):
        job_id = f"scenario:{scenario['id']}"
        enabled = bool(scenario["enabled"]) and scenario["schedule_mode"] == "cron" and bool(scenario["cron"])
        if not enabled:
            continue
        if validate(scenario["cron"]):
            log.warning("场景 %s 的 cron 不合法：%s", scenario["name"], scenario["cron"])
            continue
        wanted.add(job_id)
        _scheduler.add_job(
            _run_scenario,
            CronTrigger.from_crontab(scenario["cron"].strip(), timezone=settings.TIMEZONE),
            id=job_id,
            args=[scenario["id"]],
            replace_existing=True,
        )

    for job in _scheduler.get_jobs():
        if job.id.startswith("scenario:") and job.id not in wanted:
            job.remove()


def _run_scenario(scenario_id: int) -> None:
    try:
        runner.run(scenario_id, trigger="cron")
    except Exception:  # noqa: BLE001
        log.exception("场景 %s 定时执行失败", scenario_id)


def _purge() -> None:
    removed = db.purge_old_runs(settings.LOG_KEEP_DAYS)
    if removed:
        log.info("清理历史运行记录 %s 条", removed)

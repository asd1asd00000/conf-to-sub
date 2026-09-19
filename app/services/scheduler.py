"""
زمان‌بندی ارسال خودکار بک‌آپ.
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..database import SessionLocal
from .backup_service import run_backup_job

_scheduler = BackgroundScheduler(timezone="UTC")
_started = False


def _job_callback():
    db = SessionLocal()
    try:
        ok, msg = run_backup_job(db)
        print(f"[BACKUP] {msg}", flush=True)
    finally:
        db.close()


def ensure_started():
    global _started
    if not _started:
        _scheduler.start()
        _started = True


def reschedule(hours: int):
    """
    تنظیم مجدد زمان‌بندی. hours=0 یعنی غیرفعال.
    """
    ensure_started()
    job_id = "gift_panel_backup"

    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)

    if hours and hours > 0:
        _scheduler.add_job(
            _job_callback,
            trigger=IntervalTrigger(hours=hours),
            id=job_id,
            replace_existing=True,
            next_run_time=None,  # اولین اجرا طبق interval
        )
        print(f"[SCHEDULER] بک‌آپ هر {hours} ساعت یک‌بار زمان‌بندی شد", flush=True)
    else:
        print("[SCHEDULER] زمان‌بندی بک‌آپ غیرفعال شد", flush=True)


def shutdown():
    if _started:
        _scheduler.shutdown(wait=False)

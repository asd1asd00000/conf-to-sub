"""
زمان‌بندی ارسال خودکار بک‌آپ (ایمیل و تلگرام جداگانه).
"""
import threading
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..database import SessionLocal
from .backup_service import run_email_backup, run_telegram_backup

_scheduler = BackgroundScheduler(timezone="UTC")
_started = False


def _email_job_callback():
    db = SessionLocal()
    try:
        ok, msg = run_email_backup(db)
        print(f"[BACKUP] {msg}", flush=True)
    except Exception as e:
        print(f"[BACKUP] خطای ایمیل: {e}", flush=True)
    finally:
        db.close()


def _telegram_job_callback():
    db = SessionLocal()
    try:
        ok, msg = run_telegram_backup(db)
        print(f"[BACKUP] {msg}", flush=True)
    except Exception as e:
        print(f"[BACKUP] خطای تلگرام: {e}", flush=True)
    finally:
        db.close()


def ensure_started():
    global _started
    if not _started:
        _scheduler.start()
        _started = True


def reschedule_email(hours: int):
    """تنظیم مجدد زمان‌بندی ایمیل. hours=0 یعنی غیرفعال."""
    ensure_started()
    job_id = "gift_panel_email_backup"

    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)

    if hours and hours > 0:
        job = _scheduler.add_job(
            _email_job_callback,
            trigger=IntervalTrigger(hours=hours),
            id=job_id,
            replace_existing=True,
        )
        print(f"[SCHEDULER] ایمیل هر {hours} ساعت | اجرای بعدی: {job.next_run_time}", flush=True)
    else:
        print("[SCHEDULER] زمان‌بندی ایمیل غیرفعال شد", flush=True)


def reschedule_telegram(hours: int):
    """تنظیم مجدد زمان‌بندی تلگرام. hours=0 یعنی غیرفعال."""
    ensure_started()
    job_id = "gift_panel_telegram_backup"

    if _scheduler.get_job(job_id):
        _scheduler.remove_job(job_id)

    if hours and hours > 0:
        job = _scheduler.add_job(
            _telegram_job_callback,
            trigger=IntervalTrigger(hours=hours),
            id=job_id,
            replace_existing=True,
        )
        print(f"[SCHEDULER] تلگرام هر {hours} ساعت | اجرای بعدی: {job.next_run_time}", flush=True)
    else:
        print("[SCHEDULER] زمان‌بندی تلگرام غیرفعال شد", flush=True)


def reschedule(hours: int, last_sent_iso: str = ""):
    """سازگاری با API قدیمی (هر دو مقصد را با یک بازه تنظیم می‌کند)."""
    reschedule_email(hours)
    reschedule_telegram(hours)


def catchup_if_overdue(hours: int, last_sent_iso: str):
    """اگر آخرین بک‌آپ قدیمی‌تر از بازه باشد، همین الان یکی اجرا کن."""
    if not hours or hours <= 0:
        return
    now = datetime.utcnow()
    last = None
    if last_sent_iso:
        try:
            last = datetime.fromisoformat(last_sent_iso)
        except ValueError:
            last = None
    if last is None or (now - last).total_seconds() > hours * 3600:
        threading.Thread(target=_email_job_callback, daemon=True).start()
        threading.Thread(target=_telegram_job_callback, daemon=True).start()
        print("[SCHEDULER] بک‌آپ عقب‌افتاده بود؛ الان اجرا می‌شود", flush=True)


def shutdown():
    global _started
    if _started:
        _scheduler.shutdown(wait=False)
        _started = False

"""
سرویس بک‌آپ‌گیری خودکار با زیپ رمزدار و ارسال به ایمیل و/یا تلگرام.
"""
import io
import json
import smtplib
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pyzipper
import requests

from ..models import User, Setting, BackupLog


def get_setting_val(db, key, default=""):
    s = db.query(Setting).filter(Setting.key == key).first()
    return s.value if s else default


def set_setting_val(db, key, value):
    s = db.query(Setting).filter(Setting.key == key).first()
    if s:
        s.value = str(value)
    else:
        db.add(Setting(key=key, value=str(value)))


def create_backup_zip(db, password: str) -> bytes:
    """ساخت فایل زیپ AES-256 رمزدار شامل کاربران و تنظیمات."""
    users_data = []
    for u in db.query(User).all():
        users_data.append({
            "id": u.id,
            "username": u.username,
            "sub_uuid": u.sub_uuid,
            "expire_date": u.expire_date.isoformat() if u.expire_date else None,
            "is_active": bool(u.is_active),
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "last_seen": u.last_seen.isoformat() if u.last_seen else None,
            "sub_update_count": u.sub_update_count or 0,
        })

    settings_data = {}
    for s in db.query(Setting).all():
        settings_data[s.key] = s.value

    backup_payload = {
        "version": 1,
        "type": "gift-panel-backup",
        "created_at": datetime.utcnow().isoformat(),
        "users_count": len(users_data),
        "users": users_data,
        "settings": settings_data,
    }

    buf = io.BytesIO()
    with pyzipper.AESZipFile(
        buf, "w",
        compression=pyzipper.ZIP_DEFLATED,
        encryption=pyzipper.WZ_AES,
    ) as zf:
        zf.setpassword((password or "gift123").encode("utf-8"))
        zf.writestr("backup.json", json.dumps(backup_payload, ensure_ascii=False, indent=2))
        zf.writestr("README.txt",
                    "Gift Panel Backup\n"
                    f"Created: {datetime.utcnow().isoformat()}\n"
                    "This archive is AES-256 encrypted. Use the password you set in panel settings.\n")

    return buf.getvalue()


def send_backup_email(
    smtp_server: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    to_addr: str,
    zip_bytes: bytes,
    filename: str,
    from_override: str = "",
) -> None:
    """ارسال فایل زیپ به ایمیل با SMTP قابل تنظیم."""
    # آدرس فرستنده هوشمند:
    # ۱) اگر From اختصاصی تنظیم شده → همان
    # ۲) اگر یوزر SMTP خودش ایمیل است (مثل Gmail) → همان
    # ۳) وگرنه (مثل Resend که یوزر="resend") → ایمیل مقصد
    if from_override and "@" in from_override:
        from_addr = from_override
    elif "@" in smtp_user:
        from_addr = smtp_user
    else:
        from_addr = to_addr

    msg = MIMEMultipart()
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = f"🎁 Gift Panel Backup - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    body = (
        "سلام،\n\n"
        "این یک بک‌آپ خودکار از پنل Gift Panel شماست.\n\n"
        f"📅 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"📦 نام فایل: {filename}\n"
        f"📏 حجم: {len(zip_bytes) / 1024:.1f} KB\n"
        "🔐 فایل زیپ با AES-256 محافظت شده است.\n\n"
        "برای ریستور:\n"
        "۱. فایل زیپ را با پسوردی که در تنظیمات وارد کردید باز کنید.\n"
        "۲. در پنل به بخش تنظیمات → بک‌آپ محلی و ریستور بروید.\n\n"
        "موفق باشید! 🎉\n"
        "- Gift Panel"
    )
    msg.attach(MIMEText(body, "plain", "utf-8"))

    part = MIMEBase("application", "zip")
    part.set_payload(zip_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    msg.attach(part)

    with smtplib.SMTP(smtp_server, smtp_port, timeout=30) as server:
        server.ehlo()
        if smtp_port != 465:
            server.starttls()
            server.ehlo()
        server.login(smtp_user, smtp_password.replace(" ", ""))
        server.send_message(msg, from_addr=from_addr, to_addrs=[to_addr])


def send_backup_telegram(
    bot_token: str,
    chat_id: str,
    zip_bytes: bytes,
    filename: str,
) -> None:
    """ارسال فایل زیپ به تلگرام."""
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    files = {"document": (filename, io.BytesIO(zip_bytes), "application/zip")}
    data = {
        "chat_id": chat_id,
        "caption": (
            f"🎁 Gift Panel Backup\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"📏 {len(zip_bytes) / 1024:.1f} KB\n"
            f"🔐 رمزگذاری AES-256"
        ),
    }
    resp = requests.post(url, files=files, data=data, timeout=60)
    resp.raise_for_status()


def log_backup(db, target: str, success: bool, details: str):
    """ثبت لاگ بکاپ (حفظ فقط ۱۰ تای آخر)."""
    db.add(BackupLog(target=target, success=success, details=details))
    db.commit()
    # حذف لاگ‌های قدیمی (حفظ ۱۰ تای آخر)
    logs = db.query(BackupLog).order_by(BackupLog.created_at.desc()).offset(10).all()
    for log in logs:
        db.delete(log)
    db.commit()


def run_email_backup(db) -> tuple[bool, str]:
    """اجرای بکاپ ایمیل. برمی‌گرداند (success, message)."""
    try:
        smtp_server = get_setting_val(db, "backup_email_smtp_server", "smtp.gmail.com").strip()
        smtp_port = int(get_setting_val(db, "backup_email_smtp_port", "587") or "587")
        smtp_user = get_setting_val(db, "backup_email_smtp_user", "").strip()
        smtp_password = get_setting_val(db, "backup_email_smtp_password", "").strip()
        to_addr = get_setting_val(db, "backup_email_to", "").strip()
        password = get_setting_val(db, "backup_password", "gift123").strip()

        if not to_addr or not smtp_user or not smtp_password:
            msg = "تنظیمات ایمیل ناقص است"
            log_backup(db, "email", False, msg)
            return False, f"❌ {msg}"

        zip_bytes = create_backup_zip(db, password)
        filename = f"gift-panel-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
        from_override = get_setting_val(db, "backup_email_from", "").strip()
        send_backup_email(smtp_server, smtp_port, smtp_user, smtp_password, to_addr, zip_bytes, filename, from_override=from_override)
        
        msg = f"ارسال به {to_addr}"
        log_backup(db, "email", True, msg)
        return True, f"✅ بکاپ ایمیل: {msg}"

    except smtplib.SMTPAuthenticationError:
        msg = "App Password اشتباه"
        log_backup(db, "email", False, msg)
        return False, f"❌ ایمیل: {msg}"
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        log_backup(db, "email", False, msg)
        return False, f"❌ ایمیل: {msg}"


def run_telegram_backup(db) -> tuple[bool, str]:
    """اجرای بکاپ تلگرام. برمی‌گرداند (success, message)."""
    try:
        bot_token = get_setting_val(db, "backup_telegram_bot_token", "").strip()
        chat_id = get_setting_val(db, "backup_telegram_chat_id", "").strip()
        password = get_setting_val(db, "backup_password", "gift123").strip()

        if not bot_token or not chat_id:
            msg = "تنظیمات تلگرام ناقص است"
            log_backup(db, "telegram", False, msg)
            return False, f"❌ {msg}"

        zip_bytes = create_backup_zip(db, password)
        filename = f"gift-panel-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
        send_backup_telegram(bot_token, chat_id, zip_bytes, filename)
        
        msg = f"ارسال به {chat_id}"
        log_backup(db, "telegram", True, msg)
        return True, f"✅ بکاپ تلگرام: {msg}"

    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        log_backup(db, "telegram", False, msg)
        return False, f"❌ تلگرام: {msg}"


def run_backup_job(db) -> tuple[bool, str]:
    """اجرای بکاپ به همه مقاصد فعال (برای سازگاری با scheduler قدیمی)."""
    results = []
    
    email_enabled = get_setting_val(db, "backup_email_enabled", "0") == "1"
    if email_enabled:
        ok, msg = run_email_backup(db)
        results.append(msg)

    telegram_enabled = get_setting_val(db, "backup_telegram_enabled", "0") == "1"
    if telegram_enabled:
        ok, msg = run_telegram_backup(db)
        results.append(msg)

    if results:
        return True, " | ".join(results)
    else:
        return False, "هیچ مقصدی فعال نیست"

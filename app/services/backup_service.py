"""
سرویس بک‌آپ‌گیری خودکار با زیپ رمزدار و ارسال به جیمیل و/یا تلگرام.
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

from ..models import User, Setting


def get_setting_val(db, key, default=""):
    s = db.query(Setting).filter(Setting.key == key).first()
    return s.value if s else default


def create_backup_zip(db, password: str) -> bytes:
    """
    ساخت فایل زیپ AES-256 رمزدار شامل کاربران و تنظیمات.
    """
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


def send_backup_email(from_addr: str, to_addr: str, smtp_password: str,
                      zip_bytes: bytes, filename: str) -> None:
    """ارسال فایل زیپ به جیمیل با SMTP."""
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

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(from_addr, smtp_password.replace(" ", ""))
        server.send_message(msg)


def send_backup_telegram(bot_token: str, chat_id: str,
                         zip_bytes: bytes, filename: str) -> None:
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


def run_backup_job(db) -> tuple[bool, str]:
    """
    اجرای یک job بک‌آپ کامل. برمی‌گرداند (success, message).
    """
    try:
        enabled = get_setting_val(db, "backup_enabled", "0") == "1"
        if not enabled:
            return False, "بک‌آپ غیرفعال است"

        password = get_setting_val(db, "backup_password", "gift123").strip()
        zip_bytes = create_backup_zip(db, password)
        filename = f"gift-panel-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"

        sent_to = []
        errors = []

        # --- ایمیل ---
        to_addr = get_setting_val(db, "backup_email_to", "").strip()
        from_addr = get_setting_val(db, "backup_email_from", "").strip() or to_addr
        smtp_pass = get_setting_val(db, "backup_smtp_password", "").strip()

        if to_addr and smtp_pass:
            try:
                send_backup_email(from_addr, to_addr, smtp_pass, zip_bytes, filename)
                sent_to.append(f"ایمیل ({to_addr})")
            except smtplib.SMTPAuthenticationError:
                errors.append("ایمیل: App Password اشتباه")
            except Exception as e:
                errors.append(f"ایمیل: {e}")

        # --- تلگرام ---
        telegram_bot_token = get_setting_val(db, "backup_telegram_bot_token", "").strip()
        telegram_chat_id = get_setting_val(db, "backup_telegram_chat_id", "").strip()

        if telegram_bot_token and telegram_chat_id:
            try:
                send_backup_telegram(telegram_bot_token, telegram_chat_id, zip_bytes, filename)
                sent_to.append("تلگرام")
            except Exception as e:
                errors.append(f"تلگرام: {e}")

        # ثبت زمان آخرین ارسال (اگر حداقل یکی موفق بود)
        if sent_to:
            s = db.query(Setting).filter(Setting.key == "backup_last_sent").first()
            now_iso = datetime.utcnow().isoformat()
            if s:
                s.value = now_iso
            else:
                db.add(Setting(key="backup_last_sent", value=now_iso))
            db.commit()

            msg = f"✅ بک‌آپ ارسال شد به: {', '.join(sent_to)}"
            if errors:
                msg += f" | خطاها: {'; '.join(errors)}"
            return True, msg
        else:
            if errors:
                return False, f"❌ هیچ مقصدی موفق نبود: {'; '.join(errors)}"
            else:
                return False, "⚠️ هیچ مقصدی تنظیم نشده (ایمیل یا تلگرام)"

    except Exception as e:
        return False, f"❌ خطا: {type(e).__name__}: {e}"

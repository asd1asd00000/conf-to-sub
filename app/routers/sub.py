"""
ساب‌اسکریپشن: تحویل کانفیگ‌ها به کلاینت‌ها + صفحه اطلاعات زیبا برای مرورگر.
"""
import base64
from datetime import datetime

from fastapi import APIRouter, Depends, Request, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Config, get_setting
from ..services.config_tools import apply_remark_to_raw

router = APIRouter(tags=["sub"])
templates = Jinja2Templates(directory="app/templates")

MSG_DELETED = "❌ این اشتراک وجود ندارد یا حذف شده است."
MSG_INACTIVE = "⛔ اشتراک شما غیرفعال است. برای فعال‌سازی با پشتیبانی تماس بگیرید."
MSG_EXPIRED = "⌛ اشتراک شما منقضی شده است. برای تمدید با پشتیبانی تماس بگیرید."
MSG_NO_CONFIG = "📭 فعلاً کانفیگی فعال نیست. لطفاً بعداً دوباره بررسی کنید."


def _make_fake_config(message: str, idx: int = 0) -> str:
    return (
        f"vless://{idx:08d}-0000-4000-8000-000000000000@127.0.0.1:443"
        f"?security=none&type=tcp#{message}"
    )


def _make_fake_configs(lines) -> str:
    if isinstance(lines, str):
        lines = [lines]
    return "\n".join(_make_fake_config(line, i) for i, line in enumerate(lines))


def _encode_and_respond(configs_text: str, user=None) -> Response:
    encoded = base64.b64encode(configs_text.encode("utf-8")).decode("utf-8")
    headers = {"profile-update-interval": "12"}
    if user is not None:
        headers["profile-title"] = base64.b64encode(
            f"Gift Panel | {user.username}".encode("utf-8")
        ).decode("utf-8")
    return Response(content=encoded, media_type="text/plain", headers=headers)


@router.get("/{sub_uuid}")
def get_sub(sub_uuid: str, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.sub_uuid == sub_uuid).first()
    if not user:
        return _encode_and_respond(_make_fake_configs(MSG_DELETED))

    now = datetime.utcnow()
    expired = bool(user.expire_date and user.expire_date <= now)

    # ===== تشخیص مرورگر (انسان) vs کلاینت (اپ) =====
    ua = request.headers.get("user-agent", "")
    accept = request.headers.get("accept", "")
    is_browser = ("Mozilla" in ua or "Safari" in ua) and "text/html" in accept

    if is_browser:
        if user.expire_date:
            remain = max(0, (user.expire_date - now).total_seconds())
            days_left = int(remain // 86400)
            hours_left = int((remain % 86400) // 3600)
            mins_left = int((remain % 3600) // 60)
        else:
            days_left = hours_left = mins_left = 0

        percent = 0
        if user.expire_date and user.created_at:
            total = (user.expire_date - user.created_at).total_seconds()
            elapsed = (now - user.created_at).total_seconds()
            if total > 0:
                percent = min(100, max(0, int(elapsed / total * 100)))

        if not user.is_active:
            status = "inactive"
        elif expired:
            status = "expired"
        else:
            status = "active"

        base_url = f"{request.url.scheme}://{request.url.netloc}"
        return templates.TemplateResponse("sub_info.html", {
            "request": request,
            "user": user,
            "status": status,
            "days_left": days_left,
            "hours_left": hours_left,
            "mins_left": mins_left,
            "percent": percent,
            "expired": expired,
            "sub_url": f"{base_url}/sub/{user.sub_uuid}",
        })

    # ===== ثبت دریافت ساب (فقط برای کلاینت‌ها) =====
    user.last_seen = now
    user.sub_update_count = (user.sub_update_count or 0) + 1
    db.commit()

    if not user.is_active:
        return _encode_and_respond(_make_fake_configs(MSG_INACTIVE), user)
    if expired:
        return _encode_and_respond(_make_fake_configs(MSG_EXPIRED), user)

    configs = db.query(Config).all()
    config_list = []

    # اطلاعیه‌های پنل (در صورت تنظیم در تنظیمات)
    notice = get_setting(db, "sub_notice", "")
    if notice:
        idx = 0
        for line in notice.split("\n"):
            if line.strip():
                config_list.append(_make_fake_config(f"📢 {line.strip()}", idx))
                idx += 1

    if not configs and not config_list:
        return _encode_and_respond(_make_fake_configs(MSG_NO_CONFIG), user)
    if not configs:
        return _encode_and_respond("\n".join(config_list), user)

    # همگام‌سازی نام کانفیگ با remark (رفع مشکل نام vmess)
    for config in configs:
        config_list.append(apply_remark_to_raw(config.raw_config, config.remark))

    raw_text = "\n".join(config_list)
    return _encode_and_respond(raw_text, user)

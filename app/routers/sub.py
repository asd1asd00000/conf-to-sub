from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Config
from datetime import datetime
import base64

router = APIRouter()

# پیام‌های سفارشی (هر زمان خواستید می‌توانید تغییر دهید)
MSG_EXPIRED = "⏰ زمان اشتراک شما به پایان رسیده است. برای تمدید با پشتیبانی تماس بگیرید."
MSG_INACTIVE = "⛔ حساب شما موقتاً غیرفعال شده است. با پشتیبانی تماس بگیرید."
MSG_DELETED = "❌ حساب شما غیرفعال شده است. برای اطلاعات بیشتر با پشتیبانی تماس بگیرید."


def _make_fake_config(message: str) -> str:
    """
    ساخت یک کانفیگ vless ساختگی که فقط پیام را در کلاینت نمایش می‌دهد.
    چون آدرس سرور نامعتبر است، اتصال برقرار نمی‌شود ولی نام کانفیگ (پیام) دیده می‌شود.
    """
    # کاراکترهای غیرمجاز در URL را escape می‌کنیم
    from urllib.parse import quote
    safe_msg = quote(message, safe="")
    return f"vless://00000000-0000-0000-0000-000000000000@expire.gift-panel.local:443?security=none&type=tcp#{safe_msg}"


def _encode_and_respond(configs_text: str, user=None) -> Response:
    """تبدیل متن کانفیگ‌ها به Base64 و ساخت پاسخ با هدرهای استاندارد."""
    encoded = base64.b64encode(configs_text.encode("utf-8")).decode("utf-8")
    headers = {"Profile-Update-Interval": "12"}
    if user:
        headers["Subscription-Userinfo"] = f"expire={int(user.expire_date.timestamp())}"
    return Response(
        content=encoded,
        media_type="text/plain; charset=utf-8",
        headers=headers
    )


@router.get("/{user_uuid}")
def get_subscription(user_uuid: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.sub_uuid == user_uuid).first()

    # حالت ۱: کاربر حذف شده است
    if not user:
        print(f"⚠️ درخواست ساب برای UUID نامعتبر: {user_uuid[:8]}...")
        fake_config = _make_fake_config(MSG_DELETED)
        return _encode_and_respond(fake_config)

    # به‌روزرسانی آخرین دیده‌شدن
    user.last_seen = datetime.utcnow()
    db.commit()

    # حالت ۲: کاربر غیرفعال شده است
    if not user.is_active:
        fake_config = _make_fake_config(MSG_INACTIVE)
        return _encode_and_respond(fake_config, user)

    # حالت ۳: کاربر منقضی شده است
    if user.expire_date < datetime.utcnow():
        fake_config = _make_fake_config(MSG_EXPIRED)
        return _encode_and_respond(fake_config, user)

    # حالت ۴: کاربر فعال - کانفیگ‌های واقعی را بده
    configs = db.query(Config).all()
    if not configs:
        # اگر هیچ کانفیگی در پنل نباشد، یک پیام موقت بده
        fake_config = _make_fake_config("⚠️ در حال حاضر هیچ کانفیگی در دسترس نیست. لطفاً بعداً تلاش کنید.")
        return _encode_and_respond(fake_config, user)

    config_list = []
    for config in configs:
        if "#" in config.raw_config:
            base_url = config.raw_config.split("#")[0]
            config_list.append(f"{base_url}#{config.remark}")
        else:
            config_list.append(config.raw_config)

    raw_text = "\n".join(config_list)
    return _encode_and_respond(raw_text, user)

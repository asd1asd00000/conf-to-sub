from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from urllib.parse import quote
from ..database import get_db
from ..models import User, Config
from datetime import datetime
import base64

router = APIRouter()

# ================= پیام‌های چندخطی =================
# خطوط مشترک پشتیبانی (می‌توانید تغییر دهید)
# ایکون‌ها (هر وقت خواستید عوض کنید)
TG_ICON = "📞"    # ایکون تلگرام (پاپرپلن = لوگوی خود تلگرام)
RUB_ICON = "📞"   # ایکون روبیکا (حباب گفتگو)
LRM = "\u200e"    # کاراکتر نامرئی: علامت @ را به اول آیدی قفل می‌کند

SUPPORT_LINES = [
    f"📞 با پشتیبانی تماس بگیرید: {LRM}@Oklavpn1",
    f"{TG_ICON} تلگرام: {LRM}@vpnposhtibanivpn",
    f"{RUB_ICON} روبیکا: {LRM}@okla_2027",
]

MSG_EXPIRED = ["⏰ زمان اشتراک شما به پایان رسیده"] + SUPPORT_LINES
MSG_INACTIVE = ["⛔ حساب شما غیرفعال شده است"] + SUPPORT_LINES
MSG_DELETED = ["❌ حساب شما حذف شده است"] + SUPPORT_LINES
MSG_NO_CONFIG = ["⚠️ فعلاً کانفیگی در دسترس نیست", "🔄 بعداً دوباره آپدیت کنید"]


def _make_fake_config(message: str, idx: int = 0) -> str:
    """
    ساخت یک کانفیگ vless ساختگی که فقط پیام را نمایش می‌دهد.
    برای هر خط یک UUID و پورت متفاوت می‌سازیم تا کلاینت‌ها آن‌ها را
    به عنوان ردیف‌های جداگانه نگه دارند (بدون حذف تکراری).
    """
    safe_msg = quote(message, safe="")
    uuid = f"00000000-0000-0000-0000-00000000000{idx % 10}"
    port = 443 + idx
    return f"vless://{uuid}@expire.gift-panel.local:{port}?security=none&type=tcp#{safe_msg}"


def _make_fake_configs(lines) -> str:
    """تبدیل لیست پیام‌ها به چند خط کانفیگ ساختگی."""
    return "\n".join(_make_fake_config(line, i) for i, line in enumerate(lines))


def _encode_and_respond(configs_text: str, user=None) -> Response:
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
        return _encode_and_respond(_make_fake_configs(MSG_DELETED))

    # به‌روزرسانی آخرین دیده‌شدن
    user.last_seen = datetime.utcnow()
    db.commit()

    # حالت ۲: کاربر غیرفعال شده است
    if not user.is_active:
        return _encode_and_respond(_make_fake_configs(MSG_INACTIVE), user)

    # حالت ۳: کاربر منقضی شده است
    if user.expire_date < datetime.utcnow():
        return _encode_and_respond(_make_fake_configs(MSG_EXPIRED), user)

    # حالت ۴: کاربر فعال - کانفیگ‌های واقعی
    configs = db.query(Config).all()
    if not configs:
        return _encode_and_respond(_make_fake_configs(MSG_NO_CONFIG), user)

    config_list = []
    for config in configs:
        if "#" in config.raw_config:
            base_url = config.raw_config.split("#")[0]
            config_list.append(f"{base_url}#{config.remark}")
        else:
            config_list.append(config.raw_config)

    raw_text = "\n".join(config_list)
    return _encode_and_respond(raw_text, user)

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Config
from datetime import datetime
import base64

router = APIRouter()

@router.get("/{user_uuid}")
def get_subscription(user_uuid: str, db: Session = Depends(get_db)):
    # ۱. یافتن کاربر
    user = db.query(User).filter(User.sub_uuid == user_uuid).first()
    
    if not user or not user.is_active:
        raise HTTPException(status_code=404, detail="کاربر یافت نشد یا غیرفعال است")
        
    # ۲. بررسی تاریخ انقضا
    if user.expire_date < datetime.utcnow():
        raise HTTPException(status_code=403, detail="اعتبار سابسکریپشن شما به پایان رسیده است")
        
    # ۳. دریافت تمام کانفیگ‌های موجود در پنل
    # (در آینده می‌توان این را به user_config_association محدود کرد)
    configs = db.query(Config).all()
    
    if not configs:
        raise HTTPException(status_code=404, detail="هیچ کانفیگی در حال حاضر موجود نیست")
        
    # ۴. آماده‌سازی لیست کانفیگ‌ها (هر کانفیگ در یک خط)
    config_list = [config.raw_config for config in configs]
    raw_text = "\n".join(config_list)
    
    # ۵. تبدیل به Base64 (استاندارد اکثر کلاینت‌ها مثل v2rayNG/v2rayN)
    encoded_data = base64.b64encode(raw_text.encode('utf-8')).decode('utf-8')
    
    # ۶. ارسال پاسخ با هدرهای استاندارد برای به‌روزرسانی خودکار
    return Response(
        content=encoded_data,
        media_type="text/plain; charset=utf-8",
        headers={
            "Profile-Update-Interval": "12", # درخواست به‌روزرسانی هر ۱۲ ساعت
            "Subscription-Userinfo": f"expire={int(user.expire_date.timestamp())}" # اطلاع‌رسانی تاریخ انقضا به کلاینت
        }
    )

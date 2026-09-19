from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Config
from datetime import datetime
import base64

router = APIRouter()

@router.get("/{user_uuid}")
def get_subscription(user_uuid: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.sub_uuid == user_uuid).first()
    if not user:
        raise HTTPException(status_code=404, detail="کاربر یافت نشد")

    # ثبت آخرین دیده‌شدن
    user.last_seen = datetime.utcnow()
    db.commit()

    if not user.is_active:
        raise HTTPException(status_code=403, detail="حساب غیرفعال است")
    if user.expire_date < datetime.utcnow():
        raise HTTPException(status_code=403, detail="اعتبار سابسکریپشن به پایان رسیده است")

    configs = db.query(Config).all()
    if not configs:
        raise HTTPException(status_code=404, detail="هیچ کانفیگی موجود نیست")

    config_list = []
    for config in configs:
        if "#" in config.raw_config:
            base_url = config.raw_config.split("#")[0]
            config_list.append(f"{base_url}#{config.remark}")
        else:
            config_list.append(config.raw_config)

    raw_text = "\n".join(config_list)
    encoded_data = base64.b64encode(raw_text.encode("utf-8")).decode("utf-8")

    return Response(
        content=encoded_data,
        media_type="text/plain; charset=utf-8",
        headers={
            "Profile-Update-Interval": "12",
            "Subscription-Userinfo": f"expire={int(user.expire_date.timestamp())}"
        }
    )

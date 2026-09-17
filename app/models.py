from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Table
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime
import re

# تابع پردازش و تمیز کردن نام کانفیگ
def process_config_remark(original_remark: str, added_time: datetime) -> str:
    base_name = f"gift-panel-{added_time.strftime('%H:%M')}"
    
    # ۱. استخراج پرچم‌ها (Emojis)
    flags = re.findall(r'[\U0001F1E6-\U0001F1FF]{2}', original_remark)
    
    # ۲. استخراج کدهای کشور (۲ حرفی)
    # لیست کدهای رایج در کانفیگ‌ها
    country_codes = re.findall(r'\b(US|UK|DE|FR|NL|SG|JP|KR|CA|AU|RU|TR|IN|BR|HK|TW|IT|ES|SE|CH|FI|NO|DK|PL|CZ|RO|BG|HU|AT|BE|IE|PT|GR)\b', original_remark, re.IGNORECASE)
    
    suffix_parts = []
    if flags:
        suffix_parts.extend(flags)
    if country_codes:
        # حذف تکراری‌ها و تبدیل به حروف بزرگ
        unique_codes = list(set([c.upper() for c in country_codes]))
        suffix_parts.extend(unique_codes)
        
    if suffix_parts:
        return f"{base_name} {' '.join(suffix_parts)}"
    return base_name

# جدول کاربران
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    sub_uuid = Column(String, unique=True, index=True)
    expire_date = Column(DateTime)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# جدول کانفیگ‌ها
class Config(Base):
    __tablename__ = "configs"
    id = Column(Integer, primary_key=True, index=True)
    raw_config = Column(String)
    remark = Column(String) # نام پردازش شده
    protocol = Column(String) # مثل vless, vmess
    added_time = Column(DateTime, default=datetime.utcnow)

# جدول ارتباط چندبه‌چند
user_config_association = Table(
    "user_configs", Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id")),
    Column("config_id", Integer, ForeignKey("configs.id"))
)

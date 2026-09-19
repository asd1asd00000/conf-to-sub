from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Table
from .database import Base
from datetime import datetime
import re

def process_config_remark(original_remark: str, added_time: datetime) -> str:
    # فرمت جدید: gift-panel-2026.09.19-11:33
    base_name = f"gift-panel-{added_time.strftime('%Y.%m.%d-%H:%M')}"
    flags = re.findall(r'[\U0001F1E6-\U0001F1FF]{2}', original_remark)
    country_codes = re.findall(r'\b(US|UK|DE|FR|NL|SG|JP|KR|CA|AU|RU|TR|IN|BR|HK|TW|IT|ES|SE|CH|FI|NO|DK|PL|CZ|RO|BG|HU|AT|BE|IE|PT|GR)\b', original_remark, re.IGNORECASE)
    suffix_parts = []
    if flags:
        suffix_parts.extend(flags)
    if country_codes:
        suffix_parts.extend(list(set([c.upper() for c in country_codes])))
    if suffix_parts:
        return f"{base_name} {' '.join(suffix_parts)}"
    return base_name

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    sub_uuid = Column(String, unique=True, index=True)
    expire_date = Column(DateTime)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, nullable=True)

class Config(Base):
    __tablename__ = "configs"
    id = Column(Integer, primary_key=True, index=True)
    raw_config = Column(String)
    remark = Column(String)
    protocol = Column(String)
    added_time = Column(DateTime, default=datetime.utcnow)

user_config_association = Table(
    "user_configs", Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id")),
    Column("config_id", Integer, ForeignKey("configs.id"))
)

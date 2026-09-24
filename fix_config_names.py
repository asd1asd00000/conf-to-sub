"""
ترمیم یک‌باره: نام داخل لینک همه کانفیگ‌ها را با remark فعلی همگام می‌کند.
اجرا:  ./venv/bin/python fix_config_names.py
"""
from app.database import SessionLocal
from app.models import Config
from app.services.config_tools import apply_remark_to_raw

PROTO = ("vmess://", "vless://", "trojan://", "ss://", "ssr://")


def find_raw_col(obj):
    for attr in ("raw", "config", "config_text", "text", "link", "body"):
        val = getattr(obj, attr, None)
        if isinstance(val, str) and val.strip().startswith(PROTO):
            return attr
    return None


def main():
    db = SessionLocal()
    fixed = 0
    for c in db.query(Config).all():
        col = find_raw_col(c)
        if not col:
            continue
        new = apply_remark_to_raw(getattr(c, col), c.remark)
        if new != getattr(c, col):
            setattr(c, col, new)
            fixed += 1
    db.commit()
    db.close()
    print(f"✅ {fixed} config link(s) repaired")


if __name__ == "__main__":
    main()

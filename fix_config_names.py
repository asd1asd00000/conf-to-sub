"""
ترمیم یک‌باره: نام داخل لینک همه کانفیگ‌ها را با remark فعلی همگام می‌کند.
اجرا:  ./venv/bin/python fix_config_names.py
"""
from app.database import SessionLocal
from app.models import Config
from app.services.config_tools import apply_remark_to_raw


def main():
    db = SessionLocal()
    fixed = 0
    for c in db.query(Config).all():
        raw = c.raw_config or ""
        new = apply_remark_to_raw(raw, c.remark)
        if new and new != raw:
            c.raw_config = new
            fixed += 1
    db.commit()
    db.close()
    print(f"✅ {fixed} config link(s) repaired")


if __name__ == "__main__":
    main()

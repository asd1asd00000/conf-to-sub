"""
تنظیم/تغییر نام کاربری و رمز عبور ادمین.
استفاده:  python set_admin.py <username> <password>
"""
import sys

from app.database import engine, Base, SessionLocal
from app.models import set_setting
from app.services.auth import hash_password


def main():
    if len(sys.argv) != 3:
        print("Usage: python set_admin.py <username> <password>")
        sys.exit(1)
    user, passwd = sys.argv[1], sys.argv[2]
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    set_setting(db, "admin_username", user)
    set_setting(db, "admin_password_hash", hash_password(passwd))
    db.close()
    print(f"✅ Admin credentials set for: {user}")


if __name__ == "__main__":
    main()

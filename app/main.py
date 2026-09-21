import atexit
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text, inspect
from .database import engine, Base, SessionLocal
from .models import Setting, get_setting, set_setting
from .services.auth import hash_password
from .routers import admin, sub, api
from .services import scheduler as backup_scheduler

Base.metadata.create_all(bind=engine)

_inspector = inspect(engine)
_user_cols = [c["name"] for c in _inspector.get_columns("users")]

if "last_seen" not in _user_cols:
    with engine.begin() as _conn:
        _conn.execute(text("ALTER TABLE users ADD COLUMN last_seen DATETIME"))

if "sub_update_count" not in _user_cols:
    with engine.begin() as _conn:
        _conn.execute(text("ALTER TABLE users ADD COLUMN sub_update_count INTEGER DEFAULT 0"))


class AuthMiddleware(BaseHTTPMiddleware):
    """محافظت از همه مسیرهای /admin به جز /admin/login"""
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/admin") and path != "/admin/login":
            if not request.session.get("admin_user"):
                return RedirectResponse("/admin/login", status_code=303)
        return await call_next(request)


app = FastAPI(title="Gift Panel")
app.add_middleware(AuthMiddleware)
app.add_middleware(SessionMiddleware, secret_key="gift-panel-secret-key-12345")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(admin.router, prefix="/admin")
app.include_router(sub.router, prefix="/sub")
app.include_router(api.router)


@app.on_event("startup")
def on_startup():
    # ۱) اطمینان از وجود اعتبارنامه ادمین (جلوگیری از قفل شدن)
    try:
        db = SessionLocal()
        try:
            if not get_setting(db, "admin_username", ""):
                import secrets as _s
                pwd = _s.token_urlsafe(12)
                set_setting(db, "admin_username", "admin")
                set_setting(db, "admin_password_hash", hash_password(pwd))
                print(f"[AUTH] اعتبارنامه ادمین ساخته شد: admin / {pwd}", flush=True)
                print("[AUTH] برای تغییر: python set_admin.py <user> <pass>", flush=True)
        finally:
            db.close()
    except Exception as e:
        print(f"[STARTUP] خطای ساخت اعتبارنامه: {e}", flush=True)

    # ۲) بارگذاری زمان‌بند بک‌آپ
    try:
        db = SessionLocal()
        try:
            s = db.query(Setting).filter(Setting.key == "backup_enabled").first()
            enabled = s and s.value == "1"
            h = db.query(Setting).filter(Setting.key == "backup_hours").first()
            hours = int(h.value) if h and h.value.isdigit() else 0
            l = db.query(Setting).filter(Setting.key == "backup_last_sent").first()
            last_sent = l.value if l else ""
            backup_scheduler.ensure_started()
            if enabled and hours > 0:
                backup_scheduler.reschedule(hours, last_sent)
                backup_scheduler.catchup_if_overdue(hours, last_sent)
            else:
                print("[STARTUP] زمان‌بند بک‌آپ شروع شد (غیرفعال)", flush=True)
        finally:
            db.close()
    except Exception as e:
        print(f"[STARTUP] خطا در بارگذاری تنظیمات بک‌آپ: {e}", flush=True)


@app.on_event("shutdown")
def on_shutdown():
    backup_scheduler.shutdown()


atexit.register(backup_scheduler.shutdown)

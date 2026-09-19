import atexit
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text, inspect
from .database import engine, Base, SessionLocal
from .models import Setting
from .routers import admin, sub
from .services import scheduler as backup_scheduler

Base.metadata.create_all(bind=engine)

# مهاجریت خودکار ستون‌های جدید
_inspector = inspect(engine)
_user_cols = [c["name"] for c in _inspector.get_columns("users")]

if "last_seen" not in _user_cols:
    with engine.begin() as _conn:
        _conn.execute(text("ALTER TABLE users ADD COLUMN last_seen DATETIME"))

if "sub_update_count" not in _user_cols:
    with engine.begin() as _conn:
        _conn.execute(text("ALTER TABLE users ADD COLUMN sub_update_count INTEGER DEFAULT 0"))

app = FastAPI(title="Gift Panel")
app.add_middleware(SessionMiddleware, secret_key="gift-panel-secret-key-12345")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(admin.router, prefix="/admin")
app.include_router(sub.router, prefix="/sub")


@app.on_event("startup")
def on_startup():
    """بارگذاری تنظیمات بک‌آپ و شروع زمان‌بند در هنگام استارت."""
    try:
        db = SessionLocal()
        try:
            s = db.query(Setting).filter(Setting.key == "backup_enabled").first()
            enabled = s and s.value == "1"
            h = db.query(Setting).filter(Setting.key == "backup_hours").first()
            hours = int(h.value) if h and h.value.isdigit() else 0
            if enabled and hours > 0:
                backup_scheduler.reschedule(hours)
                print(f"[STARTUP] زمان‌بند بک‌آپ با فاصله {hours} ساعت فعال شد", flush=True)
            else:
                backup_scheduler.ensure_started()
                print("[STARTUP] زمان‌بند بک‌آپ شروع شد (غیرفعال)", flush=True)
        finally:
            db.close()
    except Exception as e:
        print(f"[STARTUP] خطا در بارگذاری تنظیمات بک‌آپ: {e}", flush=True)


@app.on_event("shutdown")
def on_shutdown():
    backup_scheduler.shutdown()


atexit.register(backup_scheduler.shutdown)

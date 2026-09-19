from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text, inspect
from .database import engine, Base
from .routers import admin, sub

# ساخت جداول دیتابیس
Base.metadata.create_all(bind=engine)

# مهاجریت خودکار: افزودن ستون‌های جدید به دیتابیس‌های قدیمی
_inspector = inspect(engine)
_user_cols = [c["name"] for c in _inspector.get_columns("users")]

if "last_seen" not in _user_cols:
    with engine.begin() as _conn:
        _conn.execute(text("ALTER TABLE users ADD COLUMN last_seen DATETIME"))

if "sub_update_count" not in _user_cols:
    with engine.begin() as _conn:
        _conn.execute(text("ALTER TABLE users ADD COLUMN sub_update_count INTEGER DEFAULT 0"))

app = FastAPI(title="Gift Panel")

# فعال‌سازی Session با یک کلید امنیتی
app.add_middleware(SessionMiddleware, secret_key="gift-panel-secret-key-12345")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(admin.router, prefix="/admin")
app.include_router(sub.router, prefix="/sub")

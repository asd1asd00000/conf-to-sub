from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .database import engine, Base
from .routers import admin, sub  # <-- اضافه شدن sub

# ساخت جداول دیتابیس در اولین اجرا
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Gift Panel")

# تنظیمات فایل‌های استاتیک (CSS, JS)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ثبت مسیرهای (Routers) پنل ادمین و سابسکریپشن
app.include_router(admin.router, prefix="/admin")
app.include_router(sub.router, prefix="/sub")  # <-- اضافه شدن مسیر سابسکریپشن

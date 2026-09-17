from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from .database import engine, Base
from .routers import admin

# ساخت جداول دیتابیس در اولین اجرا
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Gift Panel")

# تنظیمات تمپلیت و استاتیک
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# اتصال روتر ادمین
app.include_router(admin.router, prefix="/admin")

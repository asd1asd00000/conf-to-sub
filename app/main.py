from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from .database import engine, Base
from .routers import admin, sub

# ساخت جداول دیتابیس
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Gift Panel")

# فعال‌سازی Session با یک کلید امنیتی
app.add_middleware(SessionMiddleware, secret_key="gift-panel-secret-key-12345")

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(admin.router, prefix="/admin")
app.include_router(sub.router, prefix="/sub")

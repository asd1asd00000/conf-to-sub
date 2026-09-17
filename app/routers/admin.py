from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Config, process_config_remark
from ..services import health_checker
from datetime import datetime, timedelta
import uuid
import asyncio

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    users = db.query(User).all()
    configs = db.query(Config).all()
    
    # دریافت پیام از Session و پاک کردن آن پس از نمایش
    message = request.session.pop("message", None)
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "users": users, 
        "configs": configs,
        "now": datetime.utcnow(),
        "message": message  # ارسال پیام به قالب HTML
    })

@router.post("/add-config")
async def add_config(request: Request, raw_text: str = Form(...), db: Session = Depends(get_db)):
    lines = raw_text.strip().split('\n')
    now = datetime.utcnow()
    
    configs_to_test = []
    config_data = []
    
    for line in lines:
        line = line.strip()
        if not line: continue
        
        protocol = line.split("://")[0] if "://" in line else "unknown"
        original_remark = line.split("#")[-1] if "#" in line else "Unknown"
        clean_remark = process_config_remark(original_remark, now)
        
        configs_to_test.append(line)
        config_data.append({
            "line": line,
            "remark": clean_remark,
            "protocol": protocol,
            "time": now
        })
    
    # تست سلامت
    tasks = [health_checker.test_config_health(config) for config in configs_to_test]
    results = await asyncio.gather(*tasks)
    
    saved_count = 0
    failed_count = 0
    
    for i, is_healthy in enumerate(results):
        if is_healthy:
            data = config_data[i]
            new_config = Config(
                raw_config=data["line"],
                remark=data["remark"],
                protocol=data["protocol"],
                added_time=data["time"]
            )
            db.add(new_config)
            saved_count += 1
        else:
            failed_count += 1
    
    db.commit()
    
    # ساخت پیام و ذخیره در Session
    if saved_count > 0 and failed_count > 0:
        msg = f"✅ {saved_count} کانفیگ سالم ذخیره شد |  {failed_count} کانفیگ خراب حذف شد"
    elif saved_count > 0:
        msg = f"🎉 همه {saved_count} کانفیگ سالم بودند و با موفقیت ذخیره شدند!"
    else:
        msg = f"⚠️ متأسفانه هیچ کانفیگ سالمی یافت نشد. ({failed_count} کانفیگ بررسی شد)"
        
    request.session["message"] = msg
    
    return RedirectResponse(url="/admin/", status_code=303)

@router.post("/add-user")
def add_user(request: Request, username: str = Form(...), days: int = Form(...), db: Session = Depends(get_db)):
    expire = datetime.utcnow() + timedelta(days=days)
    new_user = User(
        username=username,
        sub_uuid=str(uuid.uuid4()),
        expire_date=expire
    )
    db.add(new_user)
    db.commit()
    
    request.session["message"] = f"👤 کاربر {username} با موفقیت ساخته شد."
    return RedirectResponse(url="/admin/", status_code=303)

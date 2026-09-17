from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Config, process_config_remark
from datetime import datetime, timedelta
import uuid

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    users = db.query(User).all()
    configs = db.query(Config).all()
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "users": users, 
        "configs": configs,
        "now": datetime.utcnow()  # <-- این خط اضافه شد
    })

@router.post("/add-config")
def add_config(raw_text: str = Form(...), db: Session = Depends(get_db)):
    lines = raw_text.strip().split('\n')
    now = datetime.utcnow()
    
    for line in lines:
        line = line.strip()
        if not line: 
            continue
        
        protocol = line.split("://")[0] if "://" in line else "unknown"
        original_remark = line.split("#")[-1] if "#" in line else "Unknown"
        
        # پردازش نام کانفیگ برای حذف تبلیغات و اضافه کردن ساعت و پرچم
        clean_remark = process_config_remark(original_remark, now)
        
        new_config = Config(
            raw_config=line,
            remark=clean_remark,
            protocol=protocol,
            added_time=now
        )
        db.add(new_config)
    db.commit()
    return RedirectResponse(url="/admin/", status_code=303)

@router.post("/add-user")
def add_user(username: str = Form(...), days: int = Form(...), db: Session = Depends(get_db)):
    expire = datetime.utcnow() + timedelta(days=days)
    new_user = User(
        username=username,
        sub_uuid=str(uuid.uuid4()),
        expire_date=expire
    )
    db.add(new_user)
    db.commit()
    return RedirectResponse(url="/admin/", status_code=303)

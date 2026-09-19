from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Config, process_config_remark
from ..services import health_checker
from datetime import datetime, timedelta
import uuid

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    configs = db.query(Config).all()
    message = request.session.pop("message", None)
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "configs": configs, "now": datetime.utcnow(),
        "message": message, "active_page": "dashboard", "base_url": base_url
    })

@router.get("/users")
def users_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    query = db.query(User)
    if q:
        query = query.filter(User.username.contains(q))
    users = query.order_by(User.id.desc()).all()
    now = datetime.utcnow()
    total_count = db.query(User).count()
    active_count = db.query(User).filter(User.is_active == True, User.expire_date > now).count()
    expired_count = db.query(User).filter(User.expire_date < now).count()
    message = request.session.pop("message", None)
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    return templates.TemplateResponse("users.html", {
        "request": request, "users": users, "q": q, "now": now,
        "total_count": total_count, "active_count": active_count,
        "expired_count": expired_count, "message": message,
        "active_page": "users", "base_url": base_url
    })

@router.post("/users/create")
def create_user(request: Request, username: str = Form(...), days: int = Form(...), db: Session = Depends(get_db)):
    expire = datetime.utcnow() + timedelta(days=days)
    db.add(User(username=username, sub_uuid=str(uuid.uuid4()), expire_date=expire))
    db.commit()
    request.session["message"] = f"👤 کاربر {username} با موفقیت ساخته شد."
    return RedirectResponse(url="/admin/users", status_code=303)

@router.post("/users/{user_id}/edit")
def edit_user(request: Request, user_id: int, username: str = Form(...), days: int = Form(...), is_active: bool = Form(False), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.username = username
    user.expire_date = datetime.utcnow() + timedelta(days=days)
    user.is_active = is_active
    db.commit()
    request.session["message"] = f"✏️ کاربر {username} به‌روزرسانی شد."
    return RedirectResponse(url="/admin/users", status_code=303)

@router.post("/users/{user_id}/delete")
def delete_user(request: Request, user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        name = user.username
        db.delete(user)
        db.commit()
        request.session["message"] = f"🗑️ کاربر {name} حذف شد."
    return RedirectResponse(url="/admin/users", status_code=303)

@router.post("/add-config")
async def add_config(request: Request, raw_text: str = Form(...), db: Session = Depends(get_db)):
    lines = [l.strip() for l in raw_text.strip().split('\n') if l.strip()]
    now = datetime.utcnow()

    if not lines:
        request.session["message"] = "⚠️ هیچ کانفیگی وارد نشد."
        return RedirectResponse(url="/admin/", status_code=303)

    metas = []
    for line in lines:
        protocol = line.split("://")[0] if "://" in line else "unknown"
        original_remark = health_checker.get_remark(line) or "Unknown"
        base_remark = process_config_remark(original_remark, now)
        metas.append({"line": line, "base_remark": base_remark, "protocol": protocol})

    print(f"🔍 بررسی {len(metas)} کانفیگ...")
    results = await health_checker.check_configs([m["line"] for m in metas])

    saved = 0
    verified = 0
    discarded = 0

    for meta, res in zip(metas, results):
        if res == health_checker.RESULT_DISCARD:
            discarded += 1
            continue
        remark = meta["base_remark"]
        if res == health_checker.RESULT_VERIFIED:
            remark = f"{health_checker.MARK_OK} {remark}"
            verified += 1
        db.add(Config(raw_config=meta["line"], remark=remark, protocol=meta["protocol"], added_time=now))
        saved += 1

    db.commit()

    msg = f"💾 {saved} کانفیگ ذخیره شد"
    if verified:
        msg += f" | {verified} مورد تأیید شد ✅"
    if discarded:
        msg += f" | ⚠️ {discarded} ورودی نامعتبر دور ریخته شد"
    request.session["message"] = msg
    print(f"🏁 {msg}")
    return RedirectResponse(url="/admin/", status_code=303)

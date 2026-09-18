from fastapi import APIRouter, Request, Depends, Form
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
    users = db.query(User).all()
    configs = db.query(Config).all()
    message = request.session.pop("message", None)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "users": users,
        "configs": configs,
        "now": datetime.utcnow(),
        "message": message
    })

@router.post("/add-config")
async def add_config(request: Request, raw_text: str = Form(...), db: Session = Depends(get_db)):
    lines = [l.strip() for l in raw_text.strip().split('\n') if l.strip()]
    now = datetime.utcnow()

    if not lines:
        request.session["message"] = "⚠️ هیچ کانفیگی وارد نشد."
        return RedirectResponse(url="/admin/", status_code=303)

    # آماده‌سازی متادیتای هر کانفیگ
    metas = []
    for line in lines:
        protocol = line.split("://")[0] if "://" in line else "unknown"
        original_remark = health_checker.get_remark(line) or "Unknown"
        clean_remark = process_config_remark(original_remark, now)
        metas.append({"line": line, "remark": clean_remark, "protocol": protocol})

    print(f"🔍 شروع تست سلامت برای {len(metas)} کانفیگ (موازی: {health_checker.CONCURRENT})...")

    # تست دسته‌ای و موازی
    statuses = await health_checker.check_configs([m["line"] for m in metas])

    ok_count = 0
    untestable_count = 0
    fail_count = 0

    for meta, st in zip(metas, statuses):
        if st == health_checker.STATUS_FAIL:
            fail_count += 1
            print(f"❌ خراب: {meta['remark']}")
            continue
        if st == health_checker.STATUS_UNTESTABLE:
            untestable_count += 1
            print(f"⚠️ بدون تست (پروتکل غیرقابل تست با Xray): {meta['remark']}")
        else:
            ok_count += 1
            print(f"✅ سالم: {meta['remark']}")
        db.add(Config(
            raw_config=meta["line"],
            remark=meta["remark"],
            protocol=meta["protocol"],
            added_time=now
        ))

    db.commit()

    msg = f"✅ {ok_count} کانفیگ سالم ذخیره شد"
    if untestable_count:
        msg += f" | ⚠️ {untestable_count} کانفیگ بدون تست ذخیره شد"
    if fail_count:
        msg += f" | ❌ {fail_count} کانفیگ خراب حذف شد"
    request.session["message"] = msg

    print(f"🏁 پایان: {msg}")
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

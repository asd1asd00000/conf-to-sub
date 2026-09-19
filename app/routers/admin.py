from fastapi import APIRouter, Request, Depends, Form, HTTPException, Response, Query
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User, Config, process_config_remark, get_setting, set_setting, Setting
from ..services import health_checker
from ..services import backup_service, scheduler as backup_scheduler
from datetime import datetime, timedelta
import uuid
import io
import math
import qrcode
from qrcode.image.svg import SvgPathImage

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

def time_ago(dt, now):
    if not dt:
        return "هرگز"
    sec = (now - dt).total_seconds()
    if sec < 0:
        sec = 0
    if sec < 60:
        return "لحظاتی پیش"
    if sec < 3600:
        return f"{int(sec // 60)} دقیقه پیش"
    if sec < 86400:
        return f"{int(sec // 3600)} ساعت پیش"
    return f"{int(sec // 86400)} روز پیش"

@router.get("/")
def dashboard(request: Request, page: int = 1, per_page: int = 20, db: Session = Depends(get_db)):
    if per_page not in (10, 20, 50, 100):
        per_page = 20
    total_count = db.query(Config).count()
    total_pages = max(1, math.ceil(total_count / per_page))
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages
    configs = db.query(Config).order_by(Config.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    message = request.session.pop("message", None)
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    return templates.TemplateResponse("dashboard.html", {
        "request": request, "configs": configs, "now": datetime.utcnow(),
        "message": message, "active_page": "dashboard", "base_url": base_url,
        "page": page, "per_page": per_page, "total_pages": total_pages, "total_count": total_count
                "backup_enabled": backup_enabled,
        "backup_hours": backup_hours,
        "backup_email_to": backup_email_to,
        "backup_email_from": backup_email_from,
        "backup_last_sent": backup_last_sent,
    })

@router.get("/users")
def users_page(request: Request, q: str = "", page: int = Query(1), per_page: int = Query(20), db: Session = Depends(get_db)):
    if per_page not in (10, 20, 50, 100):
        per_page = 20
    query = db.query(User)
    if q:
        query = query.filter(User.username.contains(q))
    total_count = query.count()
    total_pages = max(1, math.ceil(total_count / per_page))
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages
    users = query.order_by(User.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    now = datetime.utcnow()

    for u in users:
        remain_sec = (u.expire_date - now).total_seconds()
        used_sec = max(0.0, (now - u.created_at).total_seconds())
        total_sec = max(1.0, (u.expire_date - u.created_at).total_seconds())

        if remain_sec < 0:
            u.expired = True
            u.days_left = u.hours_left = u.mins_left = 0
        else:
            u.expired = False
            u.days_left = int(remain_sec // 86400)
            u.hours_left = int((remain_sec % 86400) // 3600)
            u.mins_left = int((remain_sec % 3600) // 60)

        u.edit_days = max(0, math.ceil(remain_sec / 86400))

        u.used_txt = f"{int(used_sec // 86400)} روز و {int((used_sec % 86400) // 3600)} ساعت"
        u.total_txt = f"{int(total_sec // 86400)} روز و {int((total_sec % 86400) // 3600)} ساعت"
        u.percent = max(0, min(100, int(used_sec * 100 / total_sec)))

        u.seen_txt = time_ago(u.last_seen, now)
        u.seen_recent = bool(u.last_seen and (now - u.last_seen).total_seconds() < 86400)

    active_count = db.query(User).filter(User.is_active == True, User.expire_date > now).count()
    expired_count = db.query(User).filter(User.expire_date < now).count()
    message = request.session.pop("message", None)
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    return templates.TemplateResponse("users.html", {
        "request": request, "users": users, "q": q, "now": now,
        "total_count": total_count, "active_count": active_count,
        "expired_count": expired_count, "message": message,
        "active_page": "users", "base_url": base_url,
        "page": page, "per_page": per_page, "total_pages": total_pages
    })

@router.post("/users/create")
def create_user(request: Request, username: str = Form(...), days: int = Form(...), db: Session = Depends(get_db)):
    expire = datetime.utcnow() + timedelta(days=days)
    db.add(User(username=username, sub_uuid=str(uuid.uuid4()), expire_date=expire))
    db.commit()
    request.session["message"] = f"👤 کاربر {username} با موفقیت ساخته شد."
    return RedirectResponse(url="/admin/users", status_code=303)

@router.post("/users/bulk")
def bulk_users(request: Request, action: str = Form(...), ids: str = Form(...), db: Session = Depends(get_db)):
    id_list = [int(i) for i in ids.split(",") if i.strip().isdigit()]
    if not id_list:
        request.session["message"] = "⚠️ کاربری انتخاب نشده است."
        return RedirectResponse(url="/admin/users", status_code=303)
    users = db.query(User).filter(User.id.in_(id_list)).all()
    count = len(users)
    if action == "delete":
        for u in users:
            db.delete(u)
        msg = f"🗑️ {count} کاربر حذف شد"
    elif action == "activate":
        for u in users:
            u.is_active = True
        msg = f"✅ {count} کاربر فعال شد"
    elif action == "deactivate":
        for u in users:
            u.is_active = False
        msg = f"⛔ {count} کاربر غیرفعال شد"
    else:
        msg = "⚠️ عملیات نامعتبر"
    db.commit()
    request.session["message"] = msg
    return RedirectResponse(url="/admin/users", status_code=303)

@router.get("/users/{user_id}/qr")
def user_qr(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    url = f"{request.url.scheme}://{request.url.netloc}/sub/{user.sub_uuid}"
    img = qrcode.make(url, image_factory=SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    return Response(content=buf.getvalue(), media_type="image/svg+xml")

@router.post("/users/{user_id}/edit")
def edit_user(request: Request, user_id: int, username: str = Form(...), days: int = Form(...), is_active: bool = Form(False), reset_count: bool = Form(False), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.username = username
    user.expire_date = datetime.utcnow() + timedelta(days=days)
    user.is_active = is_active
    if reset_count:
        user.sub_update_count = 0
    db.commit()
    msg = f"✏️ کاربر {username} به‌روزرسانی شد."
    if reset_count:
        msg += " (شمارنده آپدیت صفر شد 🔄)"
    request.session["message"] = msg
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

# ========== کانفیگ‌ها ==========

@router.post("/configs/{config_id}/delete")
def delete_config(request: Request, config_id: int, db: Session = Depends(get_db)):
    config = db.query(Config).filter(Config.id == config_id).first()
    if config:
        remark = config.remark
        db.delete(config)
        db.commit()
        request.session["message"] = f"🗑️ کانفیگ {remark} حذف شد."
    return RedirectResponse(url="/admin/", status_code=303)

@router.post("/configs/bulk")
def bulk_configs(request: Request, action: str = Form(...), ids: str = Form(...), db: Session = Depends(get_db)):
    id_list = [int(i) for i in ids.split(",") if i.strip().isdigit()]
    if not id_list:
        request.session["message"] = "⚠️ کانفیگی انتخاب نشده است."
        return RedirectResponse(url="/admin/", status_code=303)
    configs = db.query(Config).filter(Config.id.in_(id_list)).all()
    count = len(configs)
    if action == "delete":
        for c in configs:
            db.delete(c)
        msg = f"🗑️ {count} کانفیگ حذف شد"
    else:
        msg = "⚠️ عملیات نامعتبر"
    db.commit()
    request.session["message"] = msg
    return RedirectResponse(url="/admin/", status_code=303)

@router.post("/add-config")
async def add_config(request: Request, raw_text: str = Form(...), db: Session = Depends(get_db)):
    try:
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

        print(f"🔍 بررسی {len(metas)} کانفیگ...", flush=True)
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
        print(f"🏁 {msg}", flush=True)

    except Exception as e:
        import traceback
        traceback.print_exc()
        request.session["message"] = f"❌ خطا هنگام ذخیره: {e}"

    return RedirectResponse(url="/admin/", status_code=303)

# ========== تنظیمات ==========
@router.get("/settings")
def settings_page(request: Request, db: Session = Depends(get_db)):
    message = request.session.pop("message", None)
    
    # تنظیمات اطلاع‌رسانی
    broadcast_enabled = get_setting(db, "broadcast_enabled", "0") == "1"
    broadcast_text = get_setting(db, "broadcast_text", "")
    
    # تنظیمات یادآوری
    try:
        reminder_hours = int(get_setting(db, "reminder_hours", "24") or "0")
    except ValueError:
        reminder_hours = 0
    reminder_text = get_setting(db, "reminder_text",
        "۲۴ ساعت از آخرین آپدیت شما گذشته\nلطفاً لینک اشتراک را آپدیت کنید تا سرورها لود شوند")
    
    # تنظیمات بک‌آپ
    backup_enabled = get_setting(db, "backup_enabled", "0") == "1"
    try:
        backup_hours = int(get_setting(db, "backup_hours", "0") or "0")
    except ValueError:
        backup_hours = 0
    backup_email_to = get_setting(db, "backup_email_to", "")
    backup_email_from = get_setting(db, "backup_email_from", "")
    backup_last_sent = get_setting(db, "backup_last_sent", "")
    
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "message": message,
        "active_page": "settings",
        "broadcast_enabled": broadcast_enabled,
        "broadcast_text": broadcast_text,
        "reminder_hours": reminder_hours,
        "reminder_text": reminder_text,
        "backup_enabled": backup_enabled,
        "backup_hours": backup_hours,
        "backup_email_to": backup_email_to,
        "backup_email_from": backup_email_from,
        "backup_last_sent": backup_last_sent
    })

@router.post("/settings/broadcast")
def save_broadcast(request: Request, broadcast_text: str = Form(""), broadcast_enabled: bool = Form(False), db: Session = Depends(get_db)):
    set_setting(db, "broadcast_enabled", "1" if broadcast_enabled else "0")
    set_setting(db, "broadcast_text", broadcast_text.strip())
    request.session["message"] = "⚙️ تنظیمات اطلاع‌رسانی ذخیره شد."
    return RedirectResponse(url="/admin/settings", status_code=303)

@router.post("/settings/reminder")
def save_reminder(request: Request, reminder_hours: int = Form(0), reminder_text: str = Form(""), db: Session = Depends(get_db)):
    # محدود کردن بین 0 (بی‌نهایت) تا 8760 (یک سال)
    hours = max(0, min(8760, reminder_hours))
    set_setting(db, "reminder_hours", str(hours))
    set_setting(db, "reminder_text", reminder_text.strip())
    request.session["message"] = f"⚙️ تنظیمات یادآوری ذخیره شد ({hours} ساعت)."
    return RedirectResponse(url="/admin/settings", status_code=303)

@router.post("/settings/broadcast")
def save_broadcast(request: Request, broadcast_text: str = Form(""), broadcast_enabled: bool = Form(False), db: Session = Depends(get_db)):
    set_setting(db, "broadcast_enabled", "1" if broadcast_enabled else "0")
    set_setting(db, "broadcast_text", broadcast_text.strip())
    request.session["message"] = "⚙️ تنظیمات اطلاع‌رسانی ذخیره شد."
    return RedirectResponse(url="/admin/settings", status_code=303)
    # ========== بک‌آپ ==========

@router.post("/settings/backup")
def save_backup_settings(
    request: Request,
    backup_enabled: bool = Form(False),
    backup_hours: int = Form(0),
    backup_email_to: str = Form(""),
    backup_email_from: str = Form(""),
    backup_password: str = Form(""),
    backup_smtp_password: str = Form(""),
    db: Session = Depends(get_db),
):
    set_setting(db, "backup_enabled", "1" if backup_enabled else "0")
    set_setting(db, "backup_hours", str(max(0, min(8760, backup_hours))))
    set_setting(db, "backup_email_to", backup_email_to.strip())
    set_setting(db, "backup_email_from", backup_email_from.strip())
    if backup_password:
        set_setting(db, "backup_password", backup_password)
    if backup_smtp_password:
        set_setting(db, "backup_smtp_password", backup_smtp_password.replace(" ", ""))

    # زمان‌بندی
    if backup_enabled and backup_hours > 0:
        backup_scheduler.reschedule(backup_hours)
    else:
        backup_scheduler.reschedule(0)

    # اولین بک‌آپ فوری هنگام فعال‌سازی
    last_sent = get_setting(db, "backup_last_sent", "")
    first_backup_msg = ""
    if backup_enabled and not last_sent and backup_email_to.strip():
        ok, msg = backup_service.run_backup_job(db)
        first_backup_msg = f" | اولین بک‌آپ: {msg}"

    request.session["message"] = f"💾 تنظیمات بک‌آپ ذخیره شد{first_backup_msg}"
    return RedirectResponse(url="/admin/settings", status_code=303)


@router.post("/settings/backup/test")
def test_backup_now(request: Request, db: Session = Depends(get_db)):
    ok, msg = backup_service.run_backup_job(db)
    request.session["message"] = f"🧪 تست بک‌آپ: {msg}"
    return RedirectResponse(url="/admin/settings", status_code=303)

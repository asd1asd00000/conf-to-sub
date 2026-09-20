"""
REST API برای اتصال اپ‌های خارجی به پنل.
"""
from datetime import datetime, timedelta
from typing import Optional, List
import secrets
import uuid
import math

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Setting, Config, get_setting, set_setting

router = APIRouter(prefix="/api", tags=["api"])
security = HTTPBearer(auto_error=False)

# ============ Pydantic Models ============

class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    days: int = Field(30, ge=1, le=3650)

    @field_validator("username")
    @classmethod
    def clean_username(cls, v):
        v = v.strip()
        if not v.replace("_", "").replace("-", "").replace(".", "").isalnum():
            raise ValueError("Username can only contain letters, numbers, _, -, .")
        return v


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=2, max_length=64)
    is_active: Optional[bool] = None
    change_expire: bool = False
    days: int = Field(0, ge=0, le=3650)
    hours: int = Field(0, ge=0, le=23)
    minutes: int = Field(0, ge=0, le=59)
    reset_update_count: bool = False

    @field_validator("username")
    @classmethod
    def clean_username(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v.replace("_", "").replace("-", "").replace(".", "").isalnum():
            raise ValueError("Username can only contain letters, numbers, _, -, .")
        return v


class RenewRequest(BaseModel):
    days: int = Field(0, ge=0, le=3650)
    hours: int = Field(0, ge=0, le=23)
    minutes: int = Field(0, ge=0, le=59)


class UserResponse(BaseModel):
    id: int
    username: str
    sub_uuid: str
    subscription_url: str
    expire_date: Optional[datetime]
    is_active: bool
    created_at: Optional[datetime]
    days_left: int
    hours_left: int
    mins_left: int


class UserListResponse(BaseModel):
    users: List[UserResponse]
    page: int
    per_page: int
    total: int
    total_pages: int


class HealthResponse(BaseModel):
    status: str
    version: str
    users_count: int
    configs_count: int
    time: str

# ============ Auth ============

def verify_api_key(
    credentials = Depends(security),
    db: Session = Depends(get_db),
):
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Missing Authorization header. Use: Bearer <API_KEY>"
        )
    stored_key = get_setting(db, "api_key", "").strip()
    if not stored_key:
        raise HTTPException(
            status_code=500,
            detail="API key is not configured on server"
        )
    # constant-time compare to prevent timing attacks
    if not secrets.compare_digest(credentials.credentials, stored_key):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True

# ============ Helpers ============

def user_to_dict(user: User, request: Request) -> dict:
    now = datetime.utcnow()
    if user.expire_date:
        remain = max(0, (user.expire_date - now).total_seconds())
        days_left = int(remain // 86400)
        hours_left = int((remain % 86400) // 3600)
        mins_left = int((remain % 3600) // 60)
    else:
        days_left = hours_left = mins_left = 0
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    return {
        "id": user.id,
        "username": user.username,
        "sub_uuid": user.sub_uuid,
        "subscription_url": f"{base_url}/sub/{user.sub_uuid}",
        "expire_date": user.expire_date,
        "is_active": bool(user.is_active),
        "created_at": user.created_at,
        "days_left": days_left,
        "hours_left": hours_left,
        "mins_left": mins_left,
    }


def get_user_or_404(user_id: int, db: Session) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail=f"User with id={user_id} not found"
        )
    return user

# ============ Endpoints ============

@router.get("/health", response_model=HealthResponse)
def health_check(request: Request, db: Session = Depends(get_db)):
    """بررسی سلامت پنل (بدون نیاز به API Key)."""
    return {
        "status": "ok",
        "version": "1.0.0",
        "users_count": db.query(User).count(),
        "configs_count": db.query(Config).count(),
        "time": datetime.utcnow().isoformat(),
    }


@router.get("/users", response_model=UserListResponse, dependencies=[Depends(verify_api_key)])
def api_list_users(
    request: Request,
    q: str = Query("", description="جستجو در نام کاربری"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """لیست کاربران با فیلتر و صفحه‌بندی."""
    query = db.query(User)
    if q:
        query = query.filter(User.username.contains(q))
    total = query.count()
    total_pages = max(1, math.ceil(total / per_page))
    page = min(page, total_pages)
    users = query.order_by(User.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return {
        "users": [user_to_dict(u, request) for u in users],
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    }


@router.post("/users", response_model=UserResponse, status_code=201, dependencies=[Depends(verify_api_key)])
def api_create_user(payload: UserCreate, request: Request, db: Session = Depends(get_db)):
    """ایجاد کاربر جدید."""
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Username '{payload.username}' already exists"
        )

    expire = datetime.utcnow() + timedelta(days=payload.days)
    user = User(
        username=payload.username,
        sub_uuid=str(uuid.uuid4()),
        expire_date=expire,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_to_dict(user, request)


@router.get("/users/{user_id}", response_model=UserResponse, dependencies=[Depends(verify_api_key)])
def api_get_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    """دریافت اطلاعات یک کاربر خاص."""
    user = get_user_or_404(user_id, db)
    return user_to_dict(user, request)


@router.patch("/users/{user_id}", response_model=UserResponse, dependencies=[Depends(verify_api_key)])
def api_update_user(user_id: int, payload: UserUpdate, request: Request, db: Session = Depends(get_db)):
    """
    ویرایش کاربر.
    - username: تغییر نام کاربری (اختیاری)
    - is_active: فعال/غیرفعال کردن (اختیاری)
    - change_expire + days/hours/minutes: تنظیم انقضای جدید از الان (اختیاری)
    - reset_update_count: صفر کردن شمارنده آپدیت (اختیاری)
    """
    user = get_user_or_404(user_id, db)

    # تغییر نام کاربری
    if payload.username is not None and payload.username != user.username:
        existing = db.query(User).filter(
            User.username == payload.username, User.id != user.id
        ).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Username '{payload.username}' already taken by another user"
            )
        user.username = payload.username

    # تغییر وضعیت فعال
    if payload.is_active is not None:
        user.is_active = payload.is_active

    # تغییر تاریخ انقضا (از همین لحظه)
    if payload.change_expire:
        user.expire_date = datetime.utcnow() + timedelta(
            days=payload.days,
            hours=payload.hours,
            minutes=payload.minutes
        )

    # ریست شمارنده
    if payload.reset_update_count:
        user.sub_update_count = 0

    db.commit()
    db.refresh(user)
    return user_to_dict(user, request)


@router.delete("/users/{user_id}", dependencies=[Depends(verify_api_key)])
def api_delete_user(user_id: int, db: Session = Depends(get_db)):
    """حذف کاربر."""
    user = get_user_or_404(user_id, db)
    username = user.username
    uid = user.id
    db.delete(user)
    db.commit()
    return {"success": True, "deleted": username, "id": uid}


@router.post("/users/{user_id}/renew", response_model=UserResponse, dependencies=[Depends(verify_api_key)])
def api_renew_user(user_id: int, payload: RenewRequest, request: Request, db: Session = Depends(get_db)):
    """
    تمدید اعتبار: افزودن N روز/ساعت/دقیقه به تاریخ انقضای فعلی.
    تفاوت مهم با PATCH: اگر انقضا در آینده باشد، از همان نقطه ادامه می‌دهد؛
    اگر گذشته باشد، از همین لحظه شروع می‌کند.
    """
    user = get_user_or_404(user_id, db)

    now = datetime.utcnow()
    base = user.expire_date if (user.expire_date and user.expire_date > now) else now

    user.expire_date = base + timedelta(
        days=payload.days,
        hours=payload.hours,
        minutes=payload.minutes
    )

    # اگر کاربر غیرفعال بود، با تمدید دوباره فعال شود
    if not user.is_active:
        user.is_active = True

    db.commit()
    db.refresh(user)
    return user_to_dict(user, request)


# ============ API Key Management (internal use by admin panel) ============

def generate_api_key(db: Session) -> str:
    key = secrets.token_urlsafe(32)
    set_setting(db, "api_key", key)
    return key


def get_api_key(db: Session) -> str:
    return get_setting(db, "api_key", "")

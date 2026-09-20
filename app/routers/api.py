"""
REST API برای اتصال اپ‌های خارجی به پنل.
"""
from datetime import datetime, timedelta
from typing import Optional, List
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User, Setting, get_setting, set_setting

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
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
):
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing Authorization header. Use: Bearer <API_KEY>")
    stored_key = get_setting(db, "api_key", "").strip()
    if not stored_key:
        raise HTTPException(status_code=500, detail="API key is not configured on server")
    # constant-time compare
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

# ============ Endpoints ============

@router.get("/health", response_model=HealthResponse)
def health_check(request: Request, db: Session = Depends(get_db)):
    """بررسی سلامت پنل (بدون نیاز به API Key)."""
    from ..models import Config
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
    import math
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
    # بررسی تکراری نبودن
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Username '{payload.username}' already exists")

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


# ============ API Key Management (internal use) ============

def generate_api_key(db: Session) -> str:
    key = secrets.token_urlsafe(32)
    set_setting(db, "api_key", key)
    return key

def get_api_key(db: Session) -> str:
    return get_setting(db, "api_key", "")

from fastapi import FastAPI, Depends, HTTPException, Request, Header, Body
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, HttpUrl
from database import get_db, URL, Base, engine  # Pastikan import Base dan engine
import os
import random
import string
import secrets
from urllib.parse import urlparse
from datetime import datetime, date
from sqlalchemy import Column, Integer, String, DateTime, Boolean

# Buat tabel api_keys kalau belum ada
class ApiKey(Base):
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(64), unique=True, index=True, nullable=False)
    tier = Column(Integer, nullable=False)  # 1-4
    name = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    daily_limit = Column(Integer, nullable=True)  # null = unlimited
    usage_count_today = Column(Integer, default=0)
    last_reset = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# Ambil BASE_URL dari env
BASE_URL = os.getenv("BASE_URL")

# Super admin key (khusus pemilik, set via env)
SUPER_ADMIN_KEY = os.getenv("SUPER_ADMIN_KEY")
if not SUPER_ADMIN_KEY:
    raise ValueError("SUPER_ADMIN_KEY environment variable harus di-set!")

app = FastAPI(title="Simple - URL Shortener")

class URLCreate(BaseModel):
    url: HttpUrl

def generate_short_code(length: int = 6) -> str:
    chars = string.ascii_letters + string.digits
    db = next(get_db())
    while True:
        code = ''.join(random.choice(chars) for _ in range(length))
        if not db.query(URL).filter(URL.short_code == code).first():
            return code

@app.post("/shorten")
def shorten_url(
    item: URLCreate,
    x_api_key: str = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API Key diperlukan di header X-API-Key")

    api_key_entry = db.query(ApiKey).filter(
        ApiKey.key == x_api_key,
        ApiKey.is_active == True
    ).first()

    if not api_key_entry:
        raise HTTPException(status_code=401, detail="API Key tidak valid atau dinonaktifkan")

    # Reset usage harian jika perlu
    today = datetime.utcnow().date()
    last_reset_date = api_key_entry.last_reset.date() if api_key_entry.last_reset else today

    if last_reset_date < today:
        api_key_entry.usage_count_today = 0
        api_key_entry.last_reset = datetime.utcnow()
        db.commit()

    # Cek limit
    if api_key_entry.daily_limit is not None and api_key_entry.usage_count_today >= api_key_entry.daily_limit:
        raise HTTPException(
            status_code=429,
            detail=f"Limit harian tercapai ({api_key_entry.daily_limit}/hari untuk tier {api_key_entry.tier})"
        )

    # Tambah usage
    api_key_entry.usage_count_today += 1
    db.commit()

    # Logic shorten seperti biasa
    original_url = str(item.url).rstrip('/')
    parsed = urlparse(original_url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="URL harus http:// atau https://")

    existing = db.query(URL).filter(URL.original_url == original_url).first()
    if existing:
        return {"short_url": f"{BASE_URL}/{existing.short_code}"}

    new_url = URL(original_url=original_url)
    short_code = generate_short_code(length=6)
    new_url.short_code = short_code

    db.add(new_url)
    db.commit()
    db.refresh(new_url)

    return {"short_url": f"{BASE_URL}/{short_code}"}

@app.get("/{short_code}")
def redirect(short_code: str, request: Request, db: Session = Depends(get_db)):
    url_entry = db.query(URL).filter(URL.short_code == short_code).first()
    if not url_entry:
        raise HTTPException(status_code=404, detail="Short URL tidak ditemukan")

    url_entry.clicks += 1
    db.commit()

    return RedirectResponse(url=url_entry.original_url, status_code=301)

@app.get("/stats/{short_code}")
def get_stats(short_code: str, db: Session = Depends(get_db)):
    url = db.query(URL).filter(URL.short_code == short_code).first()
    if not url:
        raise HTTPException(status_code=404, detail="Short URL tidak ditemukan")

    return {
        "short_code": short_code,
        "original_url": url.original_url,
        "clicks": url.clicks,
        "created_at": url.created_at.isoformat() if url.created_at else None
    }

# Endpoint khusus super admin untuk generate key baru
@app.post("/admin/generate-key")
def generate_api_key(
    payload: dict = Body(...),
    x_api_key: str = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    if not x_api_key or x_api_key != SUPER_ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Akses ditolak. Hanya super admin.")

    tier = payload.get("tier")
    name = payload.get("name", "Unnamed Key")

    if tier not in [1, 2, 3, 4]:
        raise HTTPException(status_code=400, detail="Tier harus antara 1 sampai 4")

    # Limit per tier (bisa disesuaikan)
    limits = {1: 100, 2: 1000, 3: 10000, 4: None}  # 4 = unlimited
    daily_limit = limits.get(tier)

    new_key = secrets.token_urlsafe(32)  # Secure random key (\~43 char)

    db_key = ApiKey(
        key=new_key,
        tier=tier,
        name=name,
        daily_limit=daily_limit,
        created_at=datetime.utcnow(),
        last_reset=datetime.utcnow(),
        is_active=True
    )

    db.add(db_key)
    db.commit()
    db.refresh(db_key)

    return {
        "status": "success",
        "generated_key": new_key,
        "tier": tier,
        "daily_limit": daily_limit,
        "name": name,
        "created_at": db_key.created_at.isoformat()
    }

# Opsional: Endpoint untuk lihat semua key (hanya super admin)
@app.get("/admin/keys")
def list_api_keys(
    x_api_key: str = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    if not x_api_key or x_api_key != SUPER_ADMIN_KEY:
        raise HTTPException(status_code=403, detail="Akses ditolak. Hanya super admin.")

    keys = db.query(ApiKey).all()
    return [
        {
            "id": k.id,
            "key": k.key[:10] + "..." + k.key[-10:],  # sembunyikan sebagian untuk keamanan
            "tier": k.tier,
            "name": k.name,
            "daily_limit": k.daily_limit,
            "usage_today": k.usage_count_today,
            "is_active": k.is_active,
            "created_at": k.created_at.isoformat()
        } for k in keys
    ]

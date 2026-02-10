from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, HttpUrl
from database import get_db, URL
import os
import random
import string
from urllib.parse import urlparse

# Ambil BASE_URL dari environment variable
BASE_URL = os.getenv("BASE_URL", "http://yourdomain.com")

app = FastAPI(title="FASTAPI-URL-SHORTENER")

class URLCreate(BaseModel):
    url: HttpUrl

def generate_short_code(length: int = 6) -> str:
    """
    Generate random short code (huruf besar/kecil + angka) dan pastikan unik di DB
    """
    chars = string.ascii_letters + string.digits  # 62 karakter
    db = next(get_db())  # Ambil session DB manual (karena dipakai di luar route)
    while True:
        code = ''.join(random.choice(chars) for _ in range(length))
        if not db.query(URL).filter(URL.short_code == code).first():
            return code

@app.post("/shorten")
def shorten_url(item: URLCreate, db: Session = Depends(get_db)):
    """
    Buat short URL baru atau kembalikan yang sudah ada
    """
    original_url = str(item.url).rstrip('/')  # Hilangkan trailing slash biar konsisten

    # Validasi scheme (hanya http/https)
    parsed = urlparse(original_url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="URL harus dimulai dengan http:// atau https://")

    # Cek apakah URL sudah pernah dishorten
    existing = db.query(URL).filter(URL.original_url == original_url).first()
    if existing:
        return {"short_url": f"{BASE_URL}/{existing.short_code}"}

    # Buat entry baru
    new_url = URL(original_url=original_url)

    # Generate short code unik
    short_code = generate_short_code(length=6)
    new_url.short_code = short_code

    db.add(new_url)
    db.commit()
    db.refresh(new_url)

    return {"short_url": f"{BASE_URL}/{short_code}"}

@app.get("/{short_code}")
def redirect(short_code: str, request: Request, db: Session = Depends(get_db)):
    """
    Redirect ke URL asli + tambah hitungan klik
    """
    url_entry = db.query(URL).filter(URL.short_code == short_code).first()
    if not url_entry:
        raise HTTPException(status_code=404, detail="Short URL tidak ditemukan")

    # Tambah counter klik
    url_entry.clicks += 1
    db.commit()

    return RedirectResponse(url=url_entry.original_url, status_code=301)

@app.get("/stats/{short_code}")
def get_stats(short_code: str, db: Session = Depends(get_db)):
    """
    Tampilkan statistik short URL (klik, tanggal dibuat, URL asli)
    """
    url = db.query(URL).filter(URL.short_code == short_code).first()
    if not url:
        raise HTTPException(status_code=404, detail="Short URL tidak ditemukan")

    return {
        "short_code": short_code,
        "original_url": url.original_url,
        "clicks": url.clicks,
        "created_at": url.created_at.isoformat() if url.created_at else None
    }

# Untuk development: jalankan dengan
# uvicorn main:app --reload --host 0.0.0.0 --port 8000

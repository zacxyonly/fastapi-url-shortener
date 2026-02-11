from fastapi import FastAPI, Depends, HTTPException, Request, Header, Body, Query, status
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from pydantic import BaseModel, HttpUrl, Field, validator
from typing import Optional, List
from datetime import datetime, timedelta
from urllib.parse import urlparse
import os
import secrets
import qrcode
from io import BytesIO
import logging

from database import get_db, URL, URLClick, ApiKey, Base, engine
from utils import (
    generate_short_code, is_valid_short_code, hash_password, 
    verify_password, generate_api_key, parse_user_agent,
    validate_url, get_domain_from_url, sanitize_tags
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
SUPER_ADMIN_KEY = os.getenv("SUPER_ADMIN_KEY")
if not SUPER_ADMIN_KEY:
    raise ValueError("SUPER_ADMIN_KEY environment variable must be set!")

# Create tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(
    title="Advanced URL Shortener API",
    description="Production-ready URL shortener with analytics, QR codes (on-demand), and more",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class URLCreate(BaseModel):
    url: HttpUrl
    custom_code: Optional[str] = Field(None, min_length=3, max_length=20)
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)
    password: Optional[str] = Field(None, min_length=4, max_length=100)
    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    tags: Optional[str] = Field(None, max_length=500)
    
    @validator('custom_code')
    def validate_custom_code(cls, v):
        if v and not is_valid_short_code(v):
            raise ValueError('Custom code can only contain letters, numbers, hyphens, and underscores')
        return v


class BulkURLCreate(BaseModel):
    urls: List[HttpUrl] = Field(..., max_items=100)


class URLUpdate(BaseModel):
    url: Optional[HttpUrl] = None
    title: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    tags: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None


class PasswordVerify(BaseModel):
    password: str


class ApiKeyCreate(BaseModel):
    tier: int = Field(..., ge=1, le=4)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    daily_limit: Optional[int] = Field(None, ge=0)
    monthly_limit: Optional[int] = Field(None, ge=0)


# Dependency for API key validation
def verify_api_key(
    x_api_key: str = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="API Key required in X-API-Key header"
        )
    
    api_key_entry = db.query(ApiKey).filter(
        ApiKey.key == x_api_key,
        ApiKey.is_active == True
    ).first()
    
    if not api_key_entry:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API Key"
        )
    
    # Reset daily usage if needed
    today = datetime.utcnow().date()
    last_reset_date = api_key_entry.last_reset_daily.date() if api_key_entry.last_reset_daily else today
    
    if last_reset_date < today:
        api_key_entry.usage_count_today = 0
        api_key_entry.last_reset_daily = datetime.utcnow()
        db.commit()
    
    # Reset monthly usage if needed
    current_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if api_key_entry.last_reset_monthly < current_month:
        api_key_entry.usage_count_month = 0
        api_key_entry.last_reset_monthly = datetime.utcnow()
        db.commit()
    
    # Check daily limit
    if api_key_entry.daily_limit and api_key_entry.usage_count_today >= api_key_entry.daily_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily limit reached ({api_key_entry.daily_limit} requests/day for tier {api_key_entry.tier})"
        )
    
    # Check monthly limit
    if api_key_entry.monthly_limit and api_key_entry.usage_count_month >= api_key_entry.monthly_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Monthly limit reached ({api_key_entry.monthly_limit} requests/month)"
        )
    
    return api_key_entry


def verify_super_admin(x_api_key: str = Header(None, alias="X-API-Key")):
    if not x_api_key or x_api_key != SUPER_ADMIN_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Super admin only."
        )
    return True


# Health check endpoint
@app.get("/health", tags=["System"])
def health_check(db: Session = Depends(get_db)):
    try:
        # Test database connection
        db.execute("SELECT 1")
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "database": "connected"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unhealthy"
        )


# Create short URL
@app.post("/shorten", tags=["URLs"])
def shorten_url(
    item: URLCreate,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(verify_api_key)
):
    try:
        original_url = str(item.url).rstrip('/')
        
        # Validate URL
        if not validate_url(original_url):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or unsafe URL"
            )
        
        # Check custom code permissions
        if item.custom_code and not api_key.can_create_custom_code:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your tier doesn't support custom short codes"
            )
        
        # Check expiration permissions
        if item.expires_in_days and not api_key.can_set_expiration:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your tier doesn't support expiration dates"
            )
        
        # Check password protection permissions
        if item.password and not api_key.can_password_protect:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your tier doesn't support password protection"
            )
        
        # Generate or use custom short code
        if item.custom_code:
            short_code = item.custom_code
            # Check if custom code already exists
            if db.query(URL).filter(URL.short_code == short_code, URL.is_deleted == False).first():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Custom short code already in use"
                )
        else:
            # Check if URL already exists
            existing = db.query(URL).filter(
                URL.original_url == original_url,
                URL.is_deleted == False,
                URL.is_active == True
            ).first()
            if existing:
                return {
                    "short_url": f"{BASE_URL}/{existing.short_code}",
                    "short_code": existing.short_code,
                    "created_at": existing.created_at.isoformat()
                }
            
            # Generate unique short code
            while True:
                short_code = generate_short_code(length=6)
                if not db.query(URL).filter(URL.short_code == short_code).first():
                    break
        
        # Calculate expiration
        expires_at = None
        if item.expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=item.expires_in_days)
        
        # Hash password if provided
        password_hash = None
        if item.password:
            password_hash = hash_password(item.password)
        
        # Create URL entry
        new_url = URL(
            short_code=short_code,
            original_url=original_url,
            expires_at=expires_at,
            password_hash=password_hash,
            creator_api_key=api_key.key,
            title=item.title,
            description=item.description,
            tags=sanitize_tags(item.tags) if item.tags else None
        )
        
        db.add(new_url)
        
        # Update API key usage
        api_key.usage_count_today += 1
        api_key.usage_count_month += 1
        
        db.commit()
        db.refresh(new_url)
        
        response = {
            "short_url": f"{BASE_URL}/{short_code}",
            "short_code": short_code,
            "original_url": original_url,
            "created_at": new_url.created_at.isoformat()
        }
        
        if expires_at:
            response["expires_at"] = expires_at.isoformat()
        if item.password:
            response["password_protected"] = True
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating short URL: {e}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create short URL"
        )


# Bulk create URLs
@app.post("/shorten/bulk", tags=["URLs"])
def bulk_shorten_urls(
    item: BulkURLCreate,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(verify_api_key)
):
    if not api_key.can_bulk_create:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your tier doesn't support bulk operations"
        )
    
    results = []
    errors = []
    
    for idx, url in enumerate(item.urls):
        try:
            original_url = str(url).rstrip('/')
            
            if not validate_url(original_url):
                errors.append({"index": idx, "url": original_url, "error": "Invalid URL"})
                continue
            
            # Check if exists
            existing = db.query(URL).filter(
                URL.original_url == original_url,
                URL.is_deleted == False,
                URL.is_active == True
            ).first()
            
            if existing:
                results.append({
                    "short_url": f"{BASE_URL}/{existing.short_code}",
                    "short_code": existing.short_code,
                    "original_url": original_url,
                    "existing": True
                })
                continue
            
            # Generate short code
            while True:
                short_code = generate_short_code(length=6)
                if not db.query(URL).filter(URL.short_code == short_code).first():
                    break
            
            new_url = URL(
                short_code=short_code,
                original_url=original_url,
                creator_api_key=api_key.key
            )
            
            db.add(new_url)
            
            results.append({
                "short_url": f"{BASE_URL}/{short_code}",
                "short_code": short_code,
                "original_url": original_url,
                "existing": False
            })
            
        except Exception as e:
            errors.append({"index": idx, "url": str(url), "error": str(e)})
    
    # Update usage
    api_key.usage_count_today += len(results)
    api_key.usage_count_month += len(results)
    
    db.commit()
    
    return {
        "success_count": len(results),
        "error_count": len(errors),
        "results": results,
        "errors": errors
    }


# Redirect endpoint
@app.get("/{short_code}", tags=["URLs"])
async def redirect_to_url(
    short_code: str,
    request: Request,
    password: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    url_entry = db.query(URL).filter(
        URL.short_code == short_code,
        URL.is_deleted == False
    ).first()
    
    if not url_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short URL not found"
        )
    
    # Check if active
    if not url_entry.is_active:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This short URL has been deactivated"
        )
    
    # Check expiration
    if url_entry.expires_at and datetime.utcnow() > url_entry.expires_at:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This short URL has expired"
        )
    
    # Check password protection
    if url_entry.password_hash:
        if not password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Password required. Add ?password=YOUR_PASSWORD to URL"
            )
        if not verify_password(password, url_entry.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect password"
            )
    
    # Parse user agent
    user_agent_string = request.headers.get("user-agent", "")
    ua_info = parse_user_agent(user_agent_string)
    
    # Get IP (considering proxy headers)
    ip_address = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not ip_address:
        ip_address = request.headers.get("x-real-ip", "")
    if not ip_address:
        ip_address = request.client.host if request.client else None
    
    # Record click
    click = URLClick(
        url_id=url_entry.id,
        ip_address=ip_address,
        user_agent=user_agent_string[:500] if user_agent_string else None,
        referer=request.headers.get("referer", "")[:500] if request.headers.get("referer") else None,
        device_type=ua_info.get("device_type"),
        browser=ua_info.get("browser")[:50] if ua_info.get("browser") else None,
        os=ua_info.get("os")[:50] if ua_info.get("os") else None,
    )
    
    db.add(click)
    
    # Update click count
    url_entry.clicks += 1
    
    db.commit()
    
    return RedirectResponse(url=url_entry.original_url, status_code=status.HTTP_301_MOVED_PERMANENTLY)


# Get QR code
@app.get("/qr/{short_code}", tags=["URLs"])
def get_qr_code(
    short_code: str,
    size: int = Query(300, ge=100, le=1000),
    db: Session = Depends(get_db)
):
    url_entry = db.query(URL).filter(
        URL.short_code == short_code,
        URL.is_deleted == False
    ).first()
    
    if not url_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short URL not found"
        )
    
    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(f"{BASE_URL}/{short_code}")
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img = img.resize((size, size))
    
    # Convert to bytes
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    
    return StreamingResponse(buf, media_type="image/png")


# NEW v3.0: Batch statistics
@app.post("/stats/batch", tags=["Analytics"])
def get_batch_stats(
    short_codes: List[str] = Body(..., max_items=100),
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(verify_api_key)
):
    """Get statistics for multiple URLs at once (max 100)"""
    results = []
    
    for code in short_codes:
        url_entry = db.query(URL).filter(
            URL.short_code == code,
            URL.is_deleted == False
        ).first()
        
        if url_entry:
            results.append({
                "short_code": code,
                "original_url": url_entry.original_url,
                "clicks": url_entry.clicks,
                "is_active": url_entry.is_active,
                "created_at": url_entry.created_at.isoformat()
            })
        else:
            results.append({
                "short_code": code,
                "error": "Not found"
            })
    
    return {
        "total": len(results),
        "results": results
    }


# NEW v3.0: Search URLs
@app.get("/urls/search", tags=["URLs"])
def search_urls(
    q: str = Query(..., min_length=1),
    search_in: str = Query("all", regex="^(url|title|description|tags|all)$"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(verify_api_key)
):
    """Search in user's URLs by keyword"""
    query = db.query(URL).filter(
        URL.creator_api_key == api_key.key,
        URL.is_deleted == False
    )
    
    search_term = f"%{q}%"
    
    if search_in == "url":
        query = query.filter(URL.original_url.ilike(search_term))
    elif search_in == "title":
        query = query.filter(URL.title.ilike(search_term))
    elif search_in == "description":
        query = query.filter(URL.description.ilike(search_term))
    elif search_in == "tags":
        query = query.filter(URL.tags.ilike(search_term))
    else:  # all
        query = query.filter(
            or_(
                URL.original_url.ilike(search_term),
                URL.title.ilike(search_term),
                URL.description.ilike(search_term),
                URL.tags.ilike(search_term)
            )
        )
    
    results = query.limit(limit).all()
    
    return {
        "query": q,
        "search_in": search_in,
        "total": len(results),
        "results": [
            {
                "short_code": u.short_code,
                "short_url": f"{BASE_URL}/{u.short_code}",
                "original_url": u.original_url,
                "title": u.title,
                "description": u.description,
                "tags": u.tags.split(',') if u.tags else [],
                "clicks": u.clicks,
                "created_at": u.created_at.isoformat()
            }
            for u in results
        ]
    }


# NEW v3.0: Export analytics to CSV
@app.get("/analytics/export/{short_code}", tags=["Analytics"])
def export_analytics(
    short_code: str,
    format: str = Query("csv", regex="^(csv|json)$"),
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(verify_api_key)
):
    """Export click analytics to CSV or JSON"""
    url_entry = db.query(URL).filter(
        URL.short_code == short_code,
        URL.is_deleted == False
    ).first()
    
    if not url_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short URL not found"
        )
    
    # Check ownership
    if url_entry.creator_api_key != api_key.key and api_key.key != SUPER_ADMIN_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only export analytics for URLs you created"
        )
    
    clicks = db.query(URLClick).filter(URLClick.url_id == url_entry.id).all()
    
    if format == "csv":
        import csv
        output = BytesIO()
        output.write(b'\xef\xbb\xbf')  # UTF-8 BOM
        writer = csv.writer(output.wrapped if hasattr(output, 'wrapped') else output, 
                           delimiter=',', quoting=csv.QUOTE_MINIMAL)
        
        # Header
        writer.writerow(['Timestamp', 'Device', 'Browser', 'OS', 'Country', 'City', 'Referer'])
        
        # Data
        for click in clicks:
            output.write((
                f"{click.clicked_at.isoformat()},{click.device_type or 'unknown'},"
                f"{click.browser or 'unknown'},{click.os or 'unknown'},"
                f"{click.country or 'unknown'},{click.city or 'unknown'},"
                f"\"{click.referer or 'direct'}\"\n"
            ).encode('utf-8'))
        
        output.seek(0)
        return StreamingResponse(
            output,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=analytics_{short_code}.csv"
            }
        )
    else:  # json
        data = [
            {
                "timestamp": c.clicked_at.isoformat(),
                "device": c.device_type,
                "browser": c.browser,
                "os": c.os,
                "country": c.country,
                "city": c.city,
                "referer": c.referer,
                "ip": c.ip_address[:10] + "..." if c.ip_address else None  # Partial IP for privacy
            }
            for c in clicks
        ]
        
        return {
            "short_code": short_code,
            "total_clicks": len(data),
            "exported_at": datetime.utcnow().isoformat(),
            "data": data
        }


# NEW v3.0: Get link preview/metadata
@app.get("/preview/{short_code}", tags=["URLs"])
def get_link_preview(
    short_code: str,
    db: Session = Depends(get_db)
):
    """Get link preview metadata (useful for sharing on social media)"""
    url_entry = db.query(URL).filter(
        URL.short_code == short_code,
        URL.is_deleted == False,
        URL.is_active == True
    ).first()
    
    if not url_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short URL not found"
        )
    
    # Check if expired
    if url_entry.expires_at and datetime.utcnow() > url_entry.expires_at:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="This link has expired"
        )
    
    return {
        "short_url": f"{BASE_URL}/{short_code}",
        "original_url": url_entry.original_url,
        "title": url_entry.title or "Short Link",
        "description": url_entry.description or f"Redirects to {get_domain_from_url(url_entry.original_url)}",
        "domain": get_domain_from_url(url_entry.original_url),
        "clicks": url_entry.clicks,
        "created_at": url_entry.created_at.isoformat(),
        "has_password": bool(url_entry.password_hash),
        "qr_code_url": f"{BASE_URL}/qr/{short_code}"
    }


# NEW v3.0: Deactivate/Reactivate URL
@app.post("/urls/{short_code}/toggle", tags=["URLs"])
def toggle_url_status(
    short_code: str,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(verify_api_key)
):
    """Toggle URL active status (activate/deactivate)"""
    url_entry = db.query(URL).filter(
        URL.short_code == short_code,
        URL.is_deleted == False
    ).first()
    
    if not url_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short URL not found"
        )
    
    # Check ownership
    if url_entry.creator_api_key != api_key.key and api_key.key != SUPER_ADMIN_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only toggle URLs you created"
        )
    
    # Toggle status
    url_entry.is_active = not url_entry.is_active
    url_entry.updated_at = datetime.utcnow()
    
    db.commit()
    
    return {
        "short_code": short_code,
        "is_active": url_entry.is_active,
        "message": "URL activated" if url_entry.is_active else "URL deactivated"
    }


# NEW v3.0: Clone/Duplicate URL
@app.post("/urls/{short_code}/clone", tags=["URLs"])
def clone_url(
    short_code: str,
    new_code: Optional[str] = Body(None),
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(verify_api_key)
):
    """Clone an existing URL with a new short code"""
    original = db.query(URL).filter(
        URL.short_code == short_code,
        URL.is_deleted == False
    ).first()
    
    if not original:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short URL not found"
        )
    
    # Generate new short code
    if new_code:
        if not api_key.can_create_custom_code:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your tier doesn't support custom codes"
            )
        if not is_valid_short_code(new_code):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid short code format"
            )
        if db.query(URL).filter(URL.short_code == new_code).first():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Short code already exists"
            )
        cloned_code = new_code
    else:
        while True:
            cloned_code = generate_short_code(length=6)
            if not db.query(URL).filter(URL.short_code == cloned_code).first():
                break
    
    # Create clone
    cloned = URL(
        short_code=cloned_code,
        original_url=original.original_url,
        title=original.title,
        description=original.description,
        tags=original.tags,
        expires_at=original.expires_at,
        password_hash=original.password_hash,
        creator_api_key=api_key.key
    )
    
    db.add(cloned)
    api_key.usage_count_today += 1
    api_key.usage_count_month += 1
    db.commit()
    db.refresh(cloned)
    
    return {
        "original_code": short_code,
        "cloned_code": cloned_code,
        "short_url": f"{BASE_URL}/{cloned_code}",
        "message": "URL cloned successfully"
    }


# NEW v3.0: Get popular/trending URLs
@app.get("/analytics/trending", tags=["Analytics"])
def get_trending_urls(
    period: str = Query("day", regex="^(day|week|month|all)$"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(verify_api_key)
):
    """Get trending/most clicked URLs for the user"""
    query = db.query(URL).filter(
        URL.creator_api_key == api_key.key,
        URL.is_deleted == False
    )
    
    # Filter by period
    if period == "day":
        since = datetime.utcnow() - timedelta(days=1)
    elif period == "week":
        since = datetime.utcnow() - timedelta(days=7)
    elif period == "month":
        since = datetime.utcnow() - timedelta(days=30)
    else:  # all time
        since = None
    
    urls = query.order_by(URL.clicks.desc()).limit(limit).all()
    
    results = []
    for url in urls:
        # Get clicks in period
        clicks_query = db.query(URLClick).filter(URLClick.url_id == url.id)
        if since:
            clicks_query = clicks_query.filter(URLClick.clicked_at >= since)
        period_clicks = clicks_query.count()
        
        results.append({
            "short_code": url.short_code,
            "short_url": f"{BASE_URL}/{url.short_code}",
            "original_url": url.original_url,
            "title": url.title,
            "total_clicks": url.clicks,
            "period_clicks": period_clicks,
            "created_at": url.created_at.isoformat()
        })
    
    return {
        "period": period,
        "limit": limit,
        "results": results
    }


# Get URL stats
@app.get("/stats/{short_code}", tags=["Analytics"])
def get_url_stats(
    short_code: str,
    include_clicks: bool = Query(False),
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(verify_api_key)
):
    url_entry = db.query(URL).filter(
        URL.short_code == short_code,
        URL.is_deleted == False
    ).first()
    
    if not url_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short URL not found"
        )
    
    # Basic stats
    stats = {
        "short_code": short_code,
        "short_url": f"{BASE_URL}/{short_code}",
        "original_url": url_entry.original_url,
        "title": url_entry.title,
        "description": url_entry.description,
        "tags": url_entry.tags.split(',') if url_entry.tags else [],
        "clicks": url_entry.clicks,
        "created_at": url_entry.created_at.isoformat(),
        "is_active": url_entry.is_active,
        "expires_at": url_entry.expires_at.isoformat() if url_entry.expires_at else None,
        "has_password": bool(url_entry.password_hash),
        "qr_code_url": f"{BASE_URL}/qr/{short_code}"  # Available on-demand
    }
    
    # Click analytics
    clicks = db.query(URLClick).filter(URLClick.url_id == url_entry.id).all()
    
    # Device breakdown
    device_counts = {}
    browser_counts = {}
    os_counts = {}
    
    for click in clicks:
        device_counts[click.device_type or "unknown"] = device_counts.get(click.device_type or "unknown", 0) + 1
        browser_counts[click.browser or "unknown"] = browser_counts.get(click.browser or "unknown", 0) + 1
        os_counts[click.os or "unknown"] = os_counts.get(click.os or "unknown", 0) + 1
    
    stats["analytics"] = {
        "devices": device_counts,
        "browsers": dict(sorted(browser_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
        "operating_systems": dict(sorted(os_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
        "total_clicks": len(clicks)
    }
    
    # Include individual clicks if requested
    if include_clicks:
        stats["recent_clicks"] = [
            {
                "clicked_at": c.clicked_at.isoformat(),
                "device_type": c.device_type,
                "browser": c.browser,
                "os": c.os,
                "referer": c.referer,
            }
            for c in sorted(clicks, key=lambda x: x.clicked_at, reverse=True)[:100]
        ]
    
    return stats


# Update URL
@app.patch("/urls/{short_code}", tags=["URLs"])
def update_url(
    short_code: str,
    updates: URLUpdate,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(verify_api_key)
):
    url_entry = db.query(URL).filter(
        URL.short_code == short_code,
        URL.is_deleted == False
    ).first()
    
    if not url_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short URL not found"
        )
    
    # Check ownership (only creator or super admin can update)
    if url_entry.creator_api_key != api_key.key and api_key.key != SUPER_ADMIN_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update URLs you created"
        )
    
    # Apply updates
    if updates.url:
        url_entry.original_url = str(updates.url).rstrip('/')
    if updates.title is not None:
        url_entry.title = updates.title
    if updates.description is not None:
        url_entry.description = updates.description
    if updates.tags is not None:
        url_entry.tags = sanitize_tags(updates.tags)
    if updates.is_active is not None:
        url_entry.is_active = updates.is_active
    
    url_entry.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(url_entry)
    
    return {
        "message": "URL updated successfully",
        "short_code": short_code,
        "updated_at": url_entry.updated_at.isoformat()
    }


# Delete URL (soft delete)
@app.delete("/urls/{short_code}", tags=["URLs"])
def delete_url(
    short_code: str,
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(verify_api_key)
):
    url_entry = db.query(URL).filter(
        URL.short_code == short_code,
        URL.is_deleted == False
    ).first()
    
    if not url_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short URL not found"
        )
    
    # Check ownership
    if url_entry.creator_api_key != api_key.key and api_key.key != SUPER_ADMIN_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete URLs you created"
        )
    
    # Soft delete
    url_entry.is_deleted = True
    url_entry.is_active = False
    url_entry.updated_at = datetime.utcnow()
    
    db.commit()
    
    return {"message": "URL deleted successfully", "short_code": short_code}


# List user's URLs
@app.get("/urls", tags=["URLs"])
def list_urls(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(verify_api_key)
):
    query = db.query(URL).filter(
        URL.creator_api_key == api_key.key,
        URL.is_deleted == False
    )
    
    if active_only:
        query = query.filter(URL.is_active == True)
    
    total = query.count()
    urls = query.order_by(URL.created_at.desc()).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "urls": [
            {
                "short_code": u.short_code,
                "short_url": f"{BASE_URL}/{u.short_code}",
                "original_url": u.original_url,
                "title": u.title,
                "clicks": u.clicks,
                "created_at": u.created_at.isoformat(),
                "is_active": u.is_active,
            }
            for u in urls
        ]
    }


# Admin: Generate API key
@app.post("/admin/api-keys", tags=["Admin"])
def create_api_key(
    key_data: ApiKeyCreate,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_super_admin)
):
    # Set permissions based on tier
    tier_permissions = {
        1: {"can_create_custom_code": False, "can_set_expiration": False, "can_password_protect": False, "can_bulk_create": False},
        2: {"can_create_custom_code": True, "can_set_expiration": False, "can_password_protect": False, "can_bulk_create": False},
        3: {"can_create_custom_code": True, "can_set_expiration": True, "can_password_protect": True, "can_bulk_create": True},
        4: {"can_create_custom_code": True, "can_set_expiration": True, "can_password_protect": True, "can_bulk_create": True},
    }
    
    # Default limits
    default_limits = {
        1: {"daily": 100, "monthly": 2000},
        2: {"daily": 1000, "monthly": 20000},
        3: {"daily": 10000, "monthly": 200000},
        4: {"daily": None, "monthly": None},
    }
    
    new_key = generate_api_key()
    permissions = tier_permissions[key_data.tier]
    limits = default_limits[key_data.tier]
    
    db_key = ApiKey(
        key=new_key,
        tier=key_data.tier,
        name=key_data.name,
        description=key_data.description,
        daily_limit=key_data.daily_limit if key_data.daily_limit is not None else limits["daily"],
        monthly_limit=key_data.monthly_limit if key_data.monthly_limit is not None else limits["monthly"],
        **permissions
    )
    
    db.add(db_key)
    db.commit()
    db.refresh(db_key)
    
    return {
        "api_key": new_key,
        "tier": key_data.tier,
        "name": key_data.name,
        "daily_limit": db_key.daily_limit,
        "monthly_limit": db_key.monthly_limit,
        "permissions": permissions,
        "created_at": db_key.created_at.isoformat()
    }


# Admin: List all API keys
@app.get("/admin/api-keys", tags=["Admin"])
def list_api_keys(
    db: Session = Depends(get_db),
    _: bool = Depends(verify_super_admin)
):
    keys = db.query(ApiKey).all()
    
    return {
        "total": len(keys),
        "keys": [
            {
                "id": k.id,
                "key_preview": f"{k.key[:10]}...{k.key[-10:]}",
                "tier": k.tier,
                "name": k.name,
                "daily_limit": k.daily_limit,
                "monthly_limit": k.monthly_limit,
                "usage_today": k.usage_count_today,
                "usage_month": k.usage_count_month,
                "is_active": k.is_active,
                "created_at": k.created_at.isoformat()
            }
            for k in keys
        ]
    }


# NEW v3.0: Get single API key details
@app.get("/admin/api-keys/{key_id}", tags=["Admin"])
def get_api_key_details(
    key_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_super_admin)
):
    """Get detailed information about a specific API key"""
    api_key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Get URL count for this key
    url_count = db.query(URL).filter(
        URL.creator_api_key == api_key.key,
        URL.is_deleted == False
    ).count()
    
    # Get total clicks for URLs created by this key
    total_clicks = db.query(func.sum(URL.clicks)).filter(
        URL.creator_api_key == api_key.key,
        URL.is_deleted == False
    ).scalar() or 0
    
    return {
        "id": api_key.id,
        "key_preview": f"{api_key.key[:10]}...{api_key.key[-10:]}",
        "tier": api_key.tier,
        "name": api_key.name,
        "description": api_key.description,
        "daily_limit": api_key.daily_limit,
        "monthly_limit": api_key.monthly_limit,
        "usage_count_today": api_key.usage_count_today,
        "usage_count_month": api_key.usage_count_month,
        "is_active": api_key.is_active,
        "permissions": {
            "can_create_custom_code": api_key.can_create_custom_code,
            "can_set_expiration": api_key.can_set_expiration,
            "can_password_protect": api_key.can_password_protect,
            "can_bulk_create": api_key.can_bulk_create,
        },
        "statistics": {
            "total_urls_created": url_count,
            "total_clicks": total_clicks
        },
        "created_at": api_key.created_at.isoformat(),
        "updated_at": api_key.updated_at.isoformat() if api_key.updated_at else None
    }


# NEW v3.0: Update API key
@app.patch("/admin/api-keys/{key_id}", tags=["Admin"])
def update_api_key(
    key_id: int,
    name: Optional[str] = Body(None),
    description: Optional[str] = Body(None),
    daily_limit: Optional[int] = Body(None),
    monthly_limit: Optional[int] = Body(None),
    is_active: Optional[bool] = Body(None),
    db: Session = Depends(get_db),
    _: bool = Depends(verify_super_admin)
):
    """Update API key settings"""
    api_key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    if name is not None:
        api_key.name = name
    if description is not None:
        api_key.description = description
    if daily_limit is not None:
        api_key.daily_limit = daily_limit
    if monthly_limit is not None:
        api_key.monthly_limit = monthly_limit
    if is_active is not None:
        api_key.is_active = is_active
    
    api_key.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(api_key)
    
    return {
        "message": "API key updated successfully",
        "id": api_key.id,
        "name": api_key.name,
        "is_active": api_key.is_active,
        "updated_at": api_key.updated_at.isoformat()
    }


# NEW v3.0: Delete API key
@app.delete("/admin/api-keys/{key_id}", tags=["Admin"])
def delete_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_super_admin)
):
    """Permanently delete an API key"""
    api_key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    # Check if key has created URLs
    url_count = db.query(URL).filter(URL.creator_api_key == api_key.key).count()
    
    db.delete(api_key)
    db.commit()
    
    return {
        "message": "API key deleted successfully",
        "id": key_id,
        "urls_created": url_count,
        "note": "Associated URLs will remain but won't show owner"
    }


# NEW v3.0: Reset API key usage counters
@app.post("/admin/api-keys/{key_id}/reset-usage", tags=["Admin"])
def reset_api_key_usage(
    key_id: int,
    reset_type: str = Body(..., regex="^(daily|monthly|both)$"),
    db: Session = Depends(get_db),
    _: bool = Depends(verify_super_admin)
):
    """Reset usage counters for an API key"""
    api_key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    
    if reset_type in ["daily", "both"]:
        api_key.usage_count_today = 0
        api_key.last_reset_daily = datetime.utcnow()
    
    if reset_type in ["monthly", "both"]:
        api_key.usage_count_month = 0
        api_key.last_reset_monthly = datetime.utcnow()
    
    db.commit()
    
    return {
        "message": f"Usage counters reset ({reset_type})",
        "id": key_id,
        "usage_count_today": api_key.usage_count_today,
        "usage_count_month": api_key.usage_count_month
    }


# NEW v3.0: Bulk delete URLs
@app.post("/urls/bulk-delete", tags=["URLs"])
def bulk_delete_urls(
    short_codes: List[str] = Body(..., max_items=100),
    permanent: bool = Body(False),
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(verify_api_key)
):
    """Delete multiple URLs at once (soft delete by default)"""
    deleted = []
    errors = []
    
    for code in short_codes:
        try:
            url_entry = db.query(URL).filter(
                URL.short_code == code,
                URL.is_deleted == False
            ).first()
            
            if not url_entry:
                errors.append({"short_code": code, "error": "Not found"})
                continue
            
            # Check ownership
            if url_entry.creator_api_key != api_key.key and api_key.key != SUPER_ADMIN_KEY:
                errors.append({"short_code": code, "error": "Not authorized"})
                continue
            
            if permanent and api_key.key == SUPER_ADMIN_KEY:
                # Permanent delete (only super admin)
                db.delete(url_entry)
            else:
                # Soft delete
                url_entry.is_deleted = True
                url_entry.is_active = False
                url_entry.updated_at = datetime.utcnow()
            
            deleted.append(code)
            
        except Exception as e:
            errors.append({"short_code": code, "error": str(e)})
    
    db.commit()
    
    return {
        "deleted_count": len(deleted),
        "error_count": len(errors),
        "deleted": deleted,
        "errors": errors,
        "type": "permanent" if permanent else "soft"
    }


# NEW v3.0: Get user's own API key info
@app.get("/me", tags=["User"])
def get_my_info(
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(verify_api_key)
):
    """Get information about your own API key"""
    # Count URLs
    url_count = db.query(URL).filter(
        URL.creator_api_key == api_key.key,
        URL.is_deleted == False
    ).count()
    
    active_urls = db.query(URL).filter(
        URL.creator_api_key == api_key.key,
        URL.is_deleted == False,
        URL.is_active == True
    ).count()
    
    # Total clicks
    total_clicks = db.query(func.sum(URL.clicks)).filter(
        URL.creator_api_key == api_key.key,
        URL.is_deleted == False
    ).scalar() or 0
    
    # Calculate remaining quota
    daily_remaining = None
    monthly_remaining = None
    
    if api_key.daily_limit:
        daily_remaining = max(0, api_key.daily_limit - api_key.usage_count_today)
    
    if api_key.monthly_limit:
        monthly_remaining = max(0, api_key.monthly_limit - api_key.usage_count_month)
    
    return {
        "tier": api_key.tier,
        "name": api_key.name,
        "description": api_key.description,
        "limits": {
            "daily_limit": api_key.daily_limit,
            "monthly_limit": api_key.monthly_limit,
            "daily_used": api_key.usage_count_today,
            "monthly_used": api_key.usage_count_month,
            "daily_remaining": daily_remaining,
            "monthly_remaining": monthly_remaining,
        },
        "permissions": {
            "can_create_custom_code": api_key.can_create_custom_code,
            "can_set_expiration": api_key.can_set_expiration,
            "can_password_protect": api_key.can_password_protect,
            "can_bulk_create": api_key.can_bulk_create,
        },
        "statistics": {
            "total_urls": url_count,
            "active_urls": active_urls,
            "total_clicks": total_clicks,
        },
        "account_created": api_key.created_at.isoformat()
    }


# NEW v3.0: Validate short code availability
@app.get("/validate/code/{short_code}", tags=["Utilities"])
def validate_code_availability(
    short_code: str,
    db: Session = Depends(get_db)
):
    """Check if a short code is available (no auth required)"""
    if not is_valid_short_code(short_code):
        return {
            "available": False,
            "short_code": short_code,
            "reason": "Invalid format (use only letters, numbers, hyphens, underscores)"
        }
    
    if len(short_code) < 3 or len(short_code) > 20:
        return {
            "available": False,
            "short_code": short_code,
            "reason": "Length must be between 3 and 20 characters"
        }
    
    existing = db.query(URL).filter(URL.short_code == short_code).first()
    
    if existing:
        return {
            "available": False,
            "short_code": short_code,
            "reason": "Already in use"
        }
    
    return {
        "available": True,
        "short_code": short_code,
        "message": "Available for use"
    }


# NEW v3.0: Get URL history/audit log
@app.get("/urls/{short_code}/history", tags=["URLs"])
def get_url_history(
    short_code: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    api_key: ApiKey = Depends(verify_api_key)
):
    """Get click history for a URL"""
    url_entry = db.query(URL).filter(
        URL.short_code == short_code,
        URL.is_deleted == False
    ).first()
    
    if not url_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Short URL not found"
        )
    
    # Check ownership
    if url_entry.creator_api_key != api_key.key and api_key.key != SUPER_ADMIN_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view history for URLs you created"
        )
    
    clicks = db.query(URLClick).filter(
        URLClick.url_id == url_entry.id
    ).order_by(URLClick.clicked_at.desc()).limit(limit).all()
    
    return {
        "short_code": short_code,
        "total_clicks": url_entry.clicks,
        "history_count": len(clicks),
        "history": [
            {
                "timestamp": c.clicked_at.isoformat(),
                "device": c.device_type,
                "browser": c.browser,
                "os": c.os,
                "referer": c.referer,
                "country": c.country,
                "city": c.city
            }
            for c in clicks
        ]
    }


# NEW v3.0: System statistics (public)
@app.get("/stats/system", tags=["System"])
def get_system_stats(db: Session = Depends(get_db)):
    """Get public system statistics"""
    total_urls = db.query(URL).filter(URL.is_deleted == False).count()
    total_clicks = db.query(func.sum(URL.clicks)).scalar() or 0
    active_urls = db.query(URL).filter(
        URL.is_deleted == False,
        URL.is_active == True
    ).count()
    
    # URLs created in last 24 hours
    yesterday = datetime.utcnow() - timedelta(days=1)
    urls_today = db.query(URL).filter(
        URL.created_at >= yesterday,
        URL.is_deleted == False
    ).count()
    
    return {
        "total_urls": total_urls,
        "active_urls": active_urls,
        "total_clicks": total_clicks,
        "urls_created_today": urls_today,
        "uptime": "Healthy",
        "version": "3.0.0"
    }


# Admin: Dashboard stats
@app.get("/admin/dashboard", tags=["Admin"])
def admin_dashboard(
    db: Session = Depends(get_db),
    _: bool = Depends(verify_super_admin)
):
    total_urls = db.query(URL).filter(URL.is_deleted == False).count()
    active_urls = db.query(URL).filter(URL.is_deleted == False, URL.is_active == True).count()
    total_clicks = db.query(func.sum(URL.clicks)).scalar() or 0
    total_api_keys = db.query(ApiKey).count()
    active_api_keys = db.query(ApiKey).filter(ApiKey.is_active == True).count()
    
    # Recent URLs
    recent_urls = db.query(URL).filter(URL.is_deleted == False).order_by(URL.created_at.desc()).limit(10).all()
    
    # Top URLs by clicks
    top_urls = db.query(URL).filter(URL.is_deleted == False).order_by(URL.clicks.desc()).limit(10).all()
    
    return {
        "summary": {
            "total_urls": total_urls,
            "active_urls": active_urls,
            "total_clicks": total_clicks,
            "total_api_keys": total_api_keys,
            "active_api_keys": active_api_keys,
        },
        "recent_urls": [
            {
                "short_code": u.short_code,
                "original_url": u.original_url,
                "clicks": u.clicks,
                "created_at": u.created_at.isoformat()
            }
            for u in recent_urls
        ],
        "top_urls": [
            {
                "short_code": u.short_code,
                "original_url": u.original_url,
                "clicks": u.clicks,
            }
            for u in top_urls
        ]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

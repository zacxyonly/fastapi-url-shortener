from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./urls.db")

engine = create_engine(
    DATABASE_URL, 
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
    pool_recycle=3600
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class URL(Base):
    __tablename__ = "urls"
    
    id = Column(Integer, primary_key=True, index=True)
    short_code = Column(String(20), unique=True, index=True, nullable=False)
    original_url = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    clicks = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_deleted = Column(Boolean, default=False, nullable=False)
    password_hash = Column(String(255), nullable=True)
    creator_api_key = Column(String(64), nullable=True)
    
    # Metadata
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    tags = Column(String(500), nullable=True)  # Comma-separated tags
    
    __table_args__ = (
        Index('idx_short_code_active', 'short_code', 'is_active'),
        Index('idx_created_at', 'created_at'),
    )


class URLClick(Base):
    __tablename__ = "url_clicks"
    
    id = Column(Integer, primary_key=True, index=True)
    url_id = Column(Integer, nullable=False, index=True)
    clicked_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Analytics data
    ip_address = Column(String(45), nullable=True)  # IPv6 can be up to 45 chars
    user_agent = Column(Text, nullable=True)
    referer = Column(Text, nullable=True)
    country = Column(String(2), nullable=True)
    city = Column(String(100), nullable=True)
    device_type = Column(String(20), nullable=True)  # mobile, tablet, desktop
    browser = Column(String(50), nullable=True)
    os = Column(String(50), nullable=True)
    
    __table_args__ = (
        Index('idx_url_clicked', 'url_id', 'clicked_at'),
    )


class ApiKey(Base):
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(64), unique=True, index=True, nullable=False)
    tier = Column(Integer, nullable=False)  # 1-4
    name = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Rate limiting
    daily_limit = Column(Integer, nullable=True)  # null = unlimited
    monthly_limit = Column(Integer, nullable=True)
    usage_count_today = Column(Integer, default=0)
    usage_count_month = Column(Integer, default=0)
    last_reset_daily = Column(DateTime, default=datetime.utcnow)
    last_reset_monthly = Column(DateTime, default=datetime.utcnow)
    
    # Permissions
    can_create_custom_code = Column(Boolean, default=False)
    can_set_expiration = Column(Boolean, default=False)
    can_password_protect = Column(Boolean, default=False)
    can_bulk_create = Column(Boolean, default=False)


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

import string
import random
import hashlib
import secrets
from typing import Optional
from user_agents import parse
import re

BASE62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def encode_base62(num: int) -> str:
    """Encode number to base62"""
    if num == 0:
        return BASE62[0]
    arr = []
    while num:
        num, rem = divmod(num, 62)
        arr.append(BASE62[rem])
    return ''.join(reversed(arr))


def decode_base62(s: str) -> int:
    """Decode base62 string to number"""
    num = 0
    for char in s:
        num = num * 62 + BASE62.index(char)
    return num


def generate_short_code(length: int = 6) -> str:
    """Generate random short code"""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


def is_valid_short_code(code: str) -> bool:
    """Validate short code format"""
    if not code or len(code) < 3 or len(code) > 20:
        return False
    # Only alphanumeric and hyphens/underscores allowed
    return bool(re.match(r'^[a-zA-Z0-9_-]+$', code))


def hash_password(password: str) -> str:
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    return hash_password(password) == hashed


def generate_api_key() -> str:
    """Generate secure API key"""
    return secrets.token_urlsafe(32)


def parse_user_agent(user_agent_string: str) -> dict:
    """Parse user agent string to extract device info"""
    try:
        user_agent = parse(user_agent_string)
        
        # Determine device type
        if user_agent.is_mobile:
            device_type = "mobile"
        elif user_agent.is_tablet:
            device_type = "tablet"
        elif user_agent.is_pc:
            device_type = "desktop"
        else:
            device_type = "other"
        
        return {
            "device_type": device_type,
            "browser": f"{user_agent.browser.family} {user_agent.browser.version_string}",
            "os": f"{user_agent.os.family} {user_agent.os.version_string}",
        }
    except Exception:
        return {
            "device_type": "unknown",
            "browser": "unknown",
            "os": "unknown",
        }


def validate_url(url: str) -> bool:
    """Validate URL format and safety"""
    # Basic validation
    if not url or len(url) > 2048:
        return False
    
    # Check for valid protocol
    if not url.startswith(('http://', 'https://')):
        return False
    
    # Block localhost and private IPs for security
    blocked_patterns = [
        'localhost',
        '127.0.0.1',
        '0.0.0.0',
        '10.',
        '192.168.',
        '172.16.',
    ]
    
    for pattern in blocked_patterns:
        if pattern in url.lower():
            return False
    
    return True


def get_domain_from_url(url: str) -> str:
    """Extract domain from URL"""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc
    except Exception:
        return "unknown"


def sanitize_tags(tags: str) -> str:
    """Sanitize and normalize tags"""
    if not tags:
        return ""
    # Split, clean, and rejoin
    tag_list = [t.strip().lower() for t in tags.split(',') if t.strip()]
    return ','.join(tag_list[:10])  # Max 10 tags

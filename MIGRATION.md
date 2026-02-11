# Migration Guide: v1 → v2

Panduan untuk upgrade dari versi lama ke versi enhanced baru.

## Overview Perubahan

### Database Changes
- ✅ Added `url_clicks` table untuk detailed analytics
- ✅ Enhanced `urls` table dengan fields baru:
  - `expires_at`, `password_hash`, `creator_api_key`
  - `title`, `description`, `tags`
  - `is_active`, `is_deleted`, `updated_at`
- ✅ Enhanced `api_keys` table dengan permissions dan monthly limits

### API Changes
- ✅ New endpoints untuk bulk operations, QR codes, update, delete
- ✅ Enhanced statistics dengan device/browser/OS tracking
- ✅ Admin dashboard endpoint

## Migration Steps

### Option 1: Fresh Install (Recommended untuk Development)

1. **Backup data lama** (jika ada):
```bash
cp urls.db urls.db.backup
```

2. **Install dependencies baru**:
```bash
pip install -r requirements.txt
```

3. **Setup environment**:
```bash
cp .env.example .env
# Edit .env dan set SUPER_ADMIN_KEY
```

4. **Run aplikasi baru**:
```bash
uvicorn main:app --reload
```

Database baru akan dibuat otomatis dengan schema lengkap.

### Option 2: Migrate Existing Data

Jika Anda punya data existing yang ingin dipertahankan:

#### Step 1: Backup Database
```bash
cp urls.db urls.db.backup
```

#### Step 2: Create Migration Script

Simpan sebagai `migrate_v1_to_v2.py`:

```python
import sqlite3
from datetime import datetime

# Connect to old database
old_conn = sqlite3.connect('urls.db.backup')
old_cursor = old_conn.cursor()

# Connect to new database (will be created by new app)
# First run the new app once to create tables
new_conn = sqlite3.connect('urls.db')
new_cursor = new_conn.cursor()

# Migrate URLs
print("Migrating URLs...")
old_cursor.execute("SELECT id, short_code, original_url, created_at, clicks FROM urls")
urls = old_cursor.fetchall()

for url in urls:
    old_id, short_code, original_url, created_at, clicks = url
    
    # Insert with new schema
    new_cursor.execute("""
        INSERT INTO urls 
        (short_code, original_url, created_at, clicks, is_active, is_deleted)
        VALUES (?, ?, ?, ?, 1, 0)
    """, (short_code, original_url, created_at or datetime.utcnow(), clicks or 0))

new_conn.commit()
print(f"Migrated {len(urls)} URLs")

# Migrate API Keys
print("Migrating API Keys...")
old_cursor.execute("""
    SELECT id, key, tier, name, created_at, is_active, 
           daily_limit, usage_count_today, last_reset 
    FROM api_keys
""")
keys = old_cursor.fetchall()

for key in keys:
    old_id, api_key, tier, name, created_at, is_active, \
    daily_limit, usage_today, last_reset = key
    
    # Set permissions based on tier
    can_custom = tier >= 2
    can_expire = tier >= 3
    can_password = tier >= 3
    can_bulk = tier >= 3
    
    new_cursor.execute("""
        INSERT INTO api_keys 
        (key, tier, name, created_at, is_active, daily_limit,
         usage_count_today, last_reset_daily, last_reset_monthly,
         can_create_custom_code, can_set_expiration, 
         can_password_protect, can_bulk_create)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        api_key, tier, name, created_at, is_active, daily_limit,
        usage_today or 0, last_reset or datetime.utcnow(), 
        datetime.utcnow(), can_custom, can_expire, can_password, can_bulk
    ))

new_conn.commit()
print(f"Migrated {len(keys)} API Keys")

# Close connections
old_conn.close()
new_conn.close()

print("Migration complete!")
print("Please verify the data and update SUPER_ADMIN_KEY in .env")
```

#### Step 3: Run Migration
```bash
# First, run new app once to create tables
uvicorn main:app --reload
# Stop it after tables are created

# Run migration script
python migrate_v1_to_v2.py

# Start new app
uvicorn main:app --reload
```

### Option 3: Side-by-Side (Zero Downtime)

1. **Deploy v2 ke port berbeda**:
```bash
uvicorn main:app --port 8001
```

2. **Test thoroughly** di port 8001

3. **Migrate data** menggunakan script di atas

4. **Update nginx/load balancer** untuk point ke port 8001

5. **Stop v1** setelah yakin v2 berjalan baik

## Verification Checklist

Setelah migration, verify:

- [ ] Health check endpoint works: `GET /health`
- [ ] Existing short URLs still redirect correctly
- [ ] API keys masih berfungsi
- [ ] Statistics accessible
- [ ] Admin endpoints work
- [ ] New features accessible (QR, bulk, etc.)

## Breaking Changes

⚠️ **Important**: Beberapa perubahan yang perlu diperhatikan:

1. **Database schema berbeda** - tidak backward compatible
2. **New required env var**: `SUPER_ADMIN_KEY`
3. **API response format** sedikit berbeda (ada field tambahan)
4. **Import paths** berubah:
   - Old: `from database import ...`
   - New: `from database_enhanced import ...`

## Rollback Plan

Jika ada masalah, rollback dengan:

1. **Stop v2 application**
2. **Restore backup**:
```bash
cp urls.db.backup urls.db
```
3. **Start v1 application** kembali

## New Environment Variables

Update `.env` file Anda:

```env
# Required (NEW)
SUPER_ADMIN_KEY=your-secure-admin-key

# Optional (existing)
BASE_URL=http://localhost:8000
DATABASE_URL=sqlite:///./urls.db

# Optional (new)
CORS_ORIGINS=*
```

## Testing After Migration

Run test script:
```bash
chmod +x test_api.sh
./test_api.sh
```

Atau manual testing:

```bash
# 1. Test health
curl http://localhost:8000/health

# 2. Test existing URL redirect
curl -I http://localhost:8000/existing-code

# 3. Test create with existing API key
curl -X POST http://localhost:8000/shorten \
  -H "X-API-Key: your-existing-key" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'

# 4. Test new features
curl http://localhost:8000/qr/abc123
```

## Support & Troubleshooting

### Issue: API keys tidak bekerja setelah migration

**Solution**: Re-generate API keys atau manually update permissions di database:

```sql
UPDATE api_keys 
SET can_create_custom_code = 1,
    can_set_expiration = 1,
    can_password_protect = 1,
    can_bulk_create = 1
WHERE tier >= 3;
```

### Issue: Click counts hilang

**Solution**: Pastikan migration script running dengan benar. Check:

```sql
SELECT short_code, clicks FROM urls WHERE clicks > 0;
```

### Issue: Old URLs tidak redirect

**Solution**: Verify migration:

```sql
SELECT COUNT(*) FROM urls WHERE is_deleted = 0 AND is_active = 1;
```

## Production Deployment

Untuk production:

1. **Use PostgreSQL** instead of SQLite
2. **Set proper CORS_ORIGINS**
3. **Use HTTPS** (BASE_URL dengan https://)
4. **Setup monitoring** dan logging
5. **Configure backup** schedule

## Questions?

Jika ada pertanyaan atau masalah saat migration, buka issue atau contact support.

---

**Happy Migrating! 🚀**

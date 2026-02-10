🔗 **Self-hosted URL shortener** sederhana & aman berbasis **FastAPI** + **SQLite**.  
Mendukung short code random 6 karakter, redirect 301, tracking klik, statistik, serta **API Key authentication** dengan tier limit harian.

## Fitur Utama

- Short link unik dengan kode random 6 karakter (huruf + angka)
- Redirect permanen (HTTP 301) + hitung klik
- Endpoint statistik (`/stats/{short_code}`)
- **API Key wajib** untuk endpoint `/shorten` (keamanan tinggi)
- **Tier system** (1–4) dengan limit request harian:
  - Tier 1: 100/hari (Basic)
  - Tier 2: 1.000/hari (Standard)
  - Tier 3: 10.000/hari (Pro)
  - Tier 4: Unlimited (Super/Admin)
- Super admin key khusus pemilik → bisa generate API key baru via `/admin/generate-key`
- Endpoint admin: list semua key (`/admin/keys`)
- Configurable `BASE_URL` via environment variable
- Ringan: hanya SQLite, tanpa Redis atau DB eksternal

## Teknologi

- **Backend**: FastAPI (Python)
- **Database**: SQLite (`urls.db` + `api_keys` table)
- **Dependencies**: fastapi, uvicorn, sqlalchemy, pydantic

## Instalasi & Cara Menjalankan

### Prasyarat
- Python 3.10+
- Git

### Langkah-langkah

1. Clone repository
   ```bash
   git clone https://github.com/zacxyonly/fastapi-url-shortener
   cd fastapi-url-shortener
   ```

2. Buat virtual environment & install dependencies
   ```bash
   python -m venv venv
   source venv/bin/activate    # Linux/Mac
   # atau venv\Scripts\activate  (Windows)
   pip install -r requirements.txt
   ```

3. Set environment variables (wajib!)
   ```bash
   export BASE_URL="http://localhost:8000"               # atau https://youdomain.com
   export SUPER_ADMIN_KEY="super-secret-owner-only-xyz123"  # GANTI DENGAN KEY RAHASIA ANDA
   ```

4. Jalankan server (development)
   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

   Akses dokumentasi interaktif:
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

## Semua Endpoint

| Method | Endpoint                        | Deskripsi                                      | Auth dibutuhkan?       | Contoh Request / Response                                                                 |
|--------|---------------------------------|------------------------------------------------|-------------------------|-------------------------------------------------------------------------------------------|
| POST   | `/shorten`                      | Buat short URL baru                            | Ya (X-API-Key)          | `{"url": "https://example.com"}` → `{"short_url": "http://.../abc123"}`                   |
| GET    | `/{short_code}`                 | Redirect ke URL asli + tambah klik             | Tidak (public)          | GET `/abc123` → 301 Redirect ke original URL                                              |
| GET    | `/stats/{short_code}`           | Tampilkan statistik (klik, created_at, dll)    | Tidak (public)          | `{"short_code":"abc123", "original_url":"...", "clicks":5, "created_at":"..."}`          |
| POST   | `/admin/generate-key`           | Generate API key baru (tier 1–4)               | Ya (SUPER_ADMIN_KEY)    | `{"tier":3, "name":"pro-user"}` → `{"generated_key":"..."}`                               |
| GET    | `/admin/keys`                   | List semua API key (dengan info tier & usage)  | Ya (SUPER_ADMIN_KEY)    | Array of keys (key disembunyikan sebagian)                                                |

### Contoh Penggunaan via cURL

**Generate API key baru (hanya super admin)**
```bash
curl -X POST "http://localhost:8000/admin/generate-key" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: super-secret-owner-only-xyz123" \
  -d '{"tier": 3, "name": "member-pro-2026"}'
```

**Shorten URL dengan key yang sudah digenerate**
```bash
curl -X POST "http://localhost:8000/shorten" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: d5ggj2oRSoTTeseLJ9AMMUIBeOtObrkPIdlmqs2upBQ" \
  -d '{"url": "https://www.tokopedia.com"}'
```

**Cek statistik**
```bash
curl http://localhost:8000/stats/abc123
```

## Konfigurasi Tambahan

- **SUPER_ADMIN_KEY**: Key khusus pemilik (set via env). Jangan share!
- **BASE_URL**: Agar short link pakai domain yang benar (bukan localhost)
- **HTTPS**: Sangat direkomendasikan (pakai Caddy/Nginx + Let's Encrypt)

## Deploy (Rekomendasi)

- **Railway / Render / Fly.io**: Push repo → set env vars (`BASE_URL`, `SUPER_ADMIN_KEY`) → deploy Python app
- **Docker**: Tambah Dockerfile sederhana nanti
- **Production**: Gunakan supervisor/systemd, HTTPS, dan backup `urls.db` + `api_keys` table

## Kontribusi

Pull request welcome!  
Ide pengembangan:
- Endpoint deactivate/reactivate key
- Rate limiting lebih canggih (slowapi)
- Hash API key di database (bcrypt)
- Dashboard sederhana (list link + usage per key)
- Migrasi ke PostgreSQL untuk skalabilitas

## Lisensi

[MIT License](LICENSE)  
Bebas digunakan, dimodifikasi, dan didistribusikan (dengan menyertakan kredit asli).

---

Dibuat dengan ❤️ oleh zacxyonly – 2026

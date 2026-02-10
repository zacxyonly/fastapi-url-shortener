## FASTAPI-URL-SHORTENER

🔗 **Simple self-hosted URL shortener** built with **FastAPI** + **SQLite**.  
Random 6-character short codes, 301 redirects, click tracking, and basic stats endpoint.  
Lightweight, easy to run locally or deploy anywhere.

Personal project by **ZAKI** (Jakarta, Indonesia) – started as a learning project in 2026.

## Fitur Utama

- Membuat short link dengan kode random unik (6 karakter: huruf + angka)
- Redirect permanen (HTTP 301)
- Tracking jumlah klik per link
- Endpoint statistik sederhana (/stats/{short_code})
- Validasi URL dasar (hanya http/https)
- BASE_URL configurable via environment variable
- Sangat ringan: hanya SQLite, tanpa Redis atau DB eksternal

## Teknologi

- **Backend**: FastAPI (Python)
- **Database**: SQLite (file `urls.db`)
- **Dependencies**: fastapi, uvicorn, sqlalchemy, pydantic

## Instalasi & Cara Menjalankan

### Prasyarat
- Python 3.10+
- Git

### Langkah-langkah

1. Clone repository
   ```bash
   git clone https://github.com/[username-anda]/zaki-url-shortener.git
   cd zaki-url-shortener
   ```

2. Buat virtual environment & install dependencies
   ```bash
   python -m venv venv
   source venv/bin/activate    # Linux/Mac
   # atau venv\Scripts\activate  (Windows)
   pip install -r requirements.txt
   ```

3. Jalankan server (development mode)
   ```bash
   export BASE_URL="http://localhost:8000"   # atau IP/domain kamu
   # Contoh: export BASE_URL="https://short.zaki.my.id"
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

4. Buka dokumentasi interaktif:
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

Server siap di http://localhost:8000 (atau IP kamu).

## Semua Endpoint

| Method | Endpoint                  | Deskripsi                              | Contoh Request                                      | Contoh Response                                      |
|--------|---------------------------|----------------------------------------|-----------------------------------------------------|------------------------------------------------------|
| POST   | `/shorten`                | Buat short URL baru                    | `{"url": "https://www.tokopedia.com"}`             | `{"short_url": "http://localhost:8000/ltrdYB"}`     |
| GET    | `/{short_code}`           | Redirect ke URL asli + tambah klik     | GET http://localhost:8000/ltrdYB                   | 301 Redirect → https://www.tokopedia.com            |
| GET    | `/stats/{short_code}`     | Lihat statistik link                   | GET http://localhost:8000/stats/ltrdYB             | `{"short_code":"ltrdYB", "original_url": "...", "clicks": 5, "created_at": "..."}` |

### Contoh Penggunaan via cURL

**Buat short link**
```bash
curl -X POST "http://localhost:8000/shorten" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}'
```

**Cek statistik**
```bash
curl http://localhost:8000/stats/ltrdYB
```

**Tes redirect (header saja)**
```bash
curl -I http://localhost:8000/ltrdYB
```

## Konfigurasi Tambahan

- **BASE_URL**: Atur lewat environment variable supaya short link pakai domain yang benar  
  Contoh di production:
  ```bash
  export BASE_URL="https://short.zaki.my.id"
  ```

- **Port / Host**: Ubah di command uvicorn, misal `--port 80` (butuh sudo di Linux)

## Deploy (Rekomendasi Cepat)

- **Railway.app / Render / Fly.io**: Push repo → set env `BASE_URL` → deploy Python app
- **Docker** (opsional): Tambah Dockerfile sederhana nanti
- **HTTPS**: Gunakan Caddy / Nginx reverse proxy + Let's Encrypt

## Kontribusi

Pull request welcome!  
Ide yang mungkin:
- Custom alias (/example)
- Rate limiting
- Dashboard admin sederhana
- Migrasi ke PostgreSQL / Redis untuk skalabilitas

## Lisensi

[MIT License](LICENSE)  
Bebas digunakan, dimodifikasi, dan didistribusikan (dengan menyertakan kredit asli).

---

Dibuat dengan ❤️ oleh zacxyonly – 2026
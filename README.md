# Log Aggregator

Pub-Sub Log Aggregator dengan Idempotent Consumer dan Deduplication

- Nama: Hairul Irawan
- NIM: 11221043
- Kelas: A

Demo: <tautan-demo-diisi>

Laporan/Report: <tautan-laporan-diisi>

---

## Daftar Isi
- Prasyarat
- Quick Start (Docker)
- Docker Compose (Aggregator + Publisher)
- Konfigurasi (Environment Variables)
- API Referensi
- Keandalan & Ordering
- Pengujian (Unit & Performa) via Docker
- Struktur Proyek
- Troubleshooting

## Prasyarat
Catatan: Seluruh instruksi di bawah menggunakan Docker.

## Quick Start (Docker)
Bangun image dan jalankan aggregator.

```bash
# build image
docker build -t uts-aggregator:latest .

# siapkan volume untuk database dedup
mkdir -p ./data

# jalankan container
docker run -d \
  --name aggregator \
  -p 8080:8080 \
  -v "$(pwd)/data:/app/data" \
  -e DEDUP_DB_PATH=/app/data/dedup.db \
  uts-aggregator:latest

# verifikasi health & stats
curl -s http://localhost:8080/health
curl -s http://localhost:8080/stats | jq
```

Kirim event contoh:
```bash
curl -s -X POST http://localhost:8080/publish \
  -H 'content-type: application/json' \
  -d '{"events":[{"topic":"orders","event_id":"e-1","timestamp":"2025-01-01T00:00:00Z","source":"demo","payload":{}}]}'
```

Hentikan & hapus container:
```bash
docker stop aggregator && docker rm aggregator
```

Reset state dedup:
```bash
rm -rf ./data && mkdir -p ./data
```

## Docker Compose (Aggregator + Publisher)
Menjalankan dua layanan pada jaringan internal default Compose.

```bash
# memulai
docker compose up --build
# atau latar belakang:
# docker compose up -d --build
```

- aggregator: http://localhost:8080 (volume: ./data)
- publisher: mengirim batch event ke aggregator, lalu berhenti

Menghentikan layanan:
```bash
docker compose down
```

## Konfigurasi (Environment Variables)
- Aggregator:
  - DEDUP_DB_PATH: lokasi file SQLite (default: data/dedup.db). Pada container gunakan path volume, contoh: /app/data/dedup.db
- Publisher (di docker-compose.yaml):
  - COUNT: total event yang dikirim (contoh: 5000)
  - UNIQUE: jumlah event unik (sisanya duplikat)
  - BATCH: ukuran batch per request (contoh: 500)
  - CONC: concurrency pengiriman (contoh: 4)

Contoh pada docker-compose.yaml:
```yaml
environment:
  - COUNT=5000
  - UNIQUE=4000
  - BATCH=500
  - CONC=4
```

## API Referensi

- POST /publish
  - Body: {"events": [{ "topic","event_id","timestamp","source","payload" }]}
  - Respon: 202 Accepted, contoh: {"enqueued": 1}

- GET /stats
  - {"received","unique_processed","duplicate_dropped","processed_total","topics","uptime_seconds","queue_size"}

- GET /events?topic={topic}
  - Jika topic diisi: kembalikan daftar event unik untuk topic tersebut.
  - Jika topic kosong: kembalikan ringkasan jumlah event unik per topic.

- GET /health
  - {"status":"ok"}

Contoh:
```bash
curl -s http://localhost:8080/events?topic=orders | jq
```


## Pengujian
Menjalankan pengujian tanpa setup Python lokal, menggunakan container.

Unit tests (pytest):
```bash
docker run --rm -t \
  -v "$(pwd):/app" -w /app \
  python:3.11-slim bash -lc "
    pip install --no-cache-dir -r requirements.txt pytest &&
    pytest -v
  "
```

Uji performa minimum (≥ 5.000 event, ≥ 20% duplikasi):
```bash
# pastikan aggregator sudah berjalan (docker run atau docker compose)
docker run --rm -t \
  -v "$(pwd):/app" -w /app \
  python:3.11-slim bash -lc "
    pip install --no-cache-dir -r requirements.txt httpx &&
    python scripts/perf_load_test.py -n 5000 -d 0.25 -b 100 -c 10
  "
```


## Struktur Proyek
```
sister-uts/
├── src/                 # kode aplikasi (FastAPI, consumer, dedup)
├── tests/               # unit tests + plugin summary PASS/FAIL
├── scripts/             # publisher & perf load test
├── data/                # volume untuk SQLite (persisten)
├── Dockerfile           # image aggregator
├── publisher.Dockerfile # image publisher
├── docker-compose.yaml  # orkestrasi publisher + aggregator
├── requirements.txt     # dependencies
└── README.md            # dokumen ini
```

---

## Troubleshooting
- Port 8080 sudah dipakai:
  - Jalankan dengan -p 8081:8080 dan akses di http://localhost:8081
- Duplikasi tidak terdeteksi:
  - Pastikan topic dan event_id identik; periksa log container.
- Performa menurun saat uji:
  - Gunakan batch 100–500, naikkan CONC di publisher bertahap, pastikan direktori ./data berada di disk yang cepat.
- Reset state dedup:
  - Hentikan container dan hapus folder ./data, lalu jalankan kembali.

---
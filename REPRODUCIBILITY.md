# Reproducibility Guide

## Tujuan

Panduan ini menjelaskan cara membaca dan mereplikasi sebagian artefak penelitian RAMA berdasarkan paket publik yang telah disanitasi.

## Lingkungan Eksperimen Asli

Eksperimen asli dijalankan pada lingkungan terbatas dengan karakteristik umum:

- Single-node VPS target: 2 vCPU, 4 GB RAM, CPU-only inference.
- VPS load generator terpisah.
- Docker dan Docker Compose.
- k6 sebagai load generator (5 VU).
- Prometheus dan Grafana sebagai observability stack.

Nilai IP, domain, credential, dan konfigurasi operasional sensitif tidak dipublikasikan.

## Artefak Utama

1. Manifest eksperimen: `automation/manifests/vps-main-180.yaml`
2. Konfigurasi deployment tersanitasi: `deployments/docker-compose.yml`
3. Kontrak gRPC: `proto/*.proto`
4. Skrip k6: `experiments/k6/`
5. Skrip fault injection: `experiments/fault-injection/`
6. Skrip recovery: `experiments/recovery/start_all.sh`
7. Pipeline postprocessing: `experiments/postprocess/`
8. Hasil pascaproses: `experiments/processed/`
9. Bukti observabilitas: `experiments/evidence/screenshots/` (Grafana) dan `experiments/evidence/logs/` (log backend)

## Langkah Replikasi Terbatas

1. Baca manifest eksperimen untuk memahami rancangan skenario dan parameter.
2. Siapkan lingkungan Docker Compose dengan konfigurasi setara `deployments/docker-compose.yml`.
3. Sesuaikan nilai environment yang disamarkan (DB password, JWT secret, dsb.).
4. Gunakan `deployments/docker-compose.treatment.yml` untuk kondisi RAMA (treatment).
5. Gunakan `deployments/docker-compose.static-resilience.yml` untuk kondisi SRB (kontrol).
6. Jalankan skenario berdasarkan manifest dengan k6 menggunakan skrip di `experiments/k6/`.
7. Injeksi fault secara manual menggunakan skrip di `experiments/fault-injection/`.
8. Jalankan recovery menggunakan `experiments/recovery/start_all.sh`.
9. Ekspor hasil dari DB dan hitung metrik menggunakan `experiments/postprocess/build_summary.py`.
10. Bandingkan hasil lokal dengan `experiments/processed/final_summary.csv`.
11. Gunakan `experiments/processed/data_dictionary.md` untuk memahami definisi kolom hasil.

## Batasan Replikasi

Repository ini tidak menjamin replikasi byte-to-byte karena:

- Lingkungan VPS menggunakan sumber daya bersama (hasil dapat bervariasi).
- Model weight AI worker tidak dipublikasikan.
- Credential, endpoint, dan domain asli disamarkan.
- Data mentah lengkap tidak dimasukkan ke main branch.
- Beberapa artefak hanya diberikan sebagai bukti representatif.

## Catatan Struktur Kode

`backend/` dan `workers/` adalah *source code excerpts* dari repo privat terpisah, bukan full buildable codebase:

- `backend/services/*.go` memuat 5 komponen inti RAMA. File-file ini mengimport dari `temandifa-backend/internal/` (cache, clients, logger, metrics, generated gRPC stubs) yang tidak dipublikasikan karena di luar scope metodologi.
- `backend/config/config.go` ditempatkan di `backend/config/` untuk display artifact. Dalam codebase asli, file ini berada di `internal/config/config.go` (import path: `temandifa-backend/internal/config`).
- `workers/{vision,ocr,speech}/` memuat handler gRPC dan model inference. Package `app/` (core config, auth, metrics, generated proto stubs) tidak dipublikasikan.

Proto files di `proto/` adalah sumber tunggal kebenaran kontrak gRPC — konsisten dengan import di `backend/services/` dan implementasi di `workers/`.

## Interpretasi

Repository ini terutama mendukung audit akademik dan verifikasi metodologi, bukan deployment produksi.

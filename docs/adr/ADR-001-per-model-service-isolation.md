# ADR-001: Per-Model Service Isolation

**Status:** Diterima  
**Tanggal:** 2026-04  
**Konteks:** TemanDifa membutuhkan inferensi multimodal (vision, OCR, speech) dalam satu request.

---

## Konteks

Sistem menerima satu request multimodal yang memerlukan tiga model AI sekaligus: deteksi objek (YOLOv8), ekstraksi teks (PaddleOCR), dan transkripsi audio (Whisper/ASR). Ketiga model memiliki karakteristik komputasi yang sangat berbeda dan profil kegagalan yang independen.

Opsi yang dipertimbangkan:

1. **Monolitik**: satu proses Python menjalankan ketiga model sekaligus.
2. **Per-model service** (dipilih): setiap model berjalan sebagai container terpisah, dikomunikasikan lewat gRPC.

## Keputusan

Setiap AI worker berjalan sebagai layanan gRPC mandiri dalam container Docker tersendiri:

- `vision-worker` (container `temandifa_vision`) — YOLOv8 via ONNX Runtime
- `ocr-worker` (container `temandifa_ocr`) — PaddleOCR 2.7 + PaddlePaddle 2.6
- `speech-worker` (container `temandifa_speech`) — model ASR berbasis Whisper

Go backend menginstansiasi tiga gRPC client independen (`clients.AIClients`) dan memanggil setiap worker secara konkuren (`sync.WaitGroup` di orchestrator) per health-check dan secara paralel per request melalui `ai_service.go`.

Setiap worker mengekspos endpoint gRPC tersendiri (port berbeda) dan endpoint health HTTP (`/health`) untuk liveness probe.

## Konsekuensi

**Positif:**
- Kegagalan satu worker (OOM, crash, `docker stop`) tidak memengaruhi container worker lain — isolasi proses dan memori penuh di level OS.
- Setiap worker dapat di-restart, di-update, atau di-scale secara independen.
- Profil resource (CPU/memory limit) dapat dikalibrasi per model tanpa trade-off antar model.
- Memungkinkan circuit breaker per-worker di layer orchestrator (lihat ADR-003).

**Negatif:**
- Overhead gRPC per panggilan vs. in-process function call.
- Butuh tiga set konfigurasi TLS + three healthcheck endpoint.
- Startup time lebih panjang karena tiga model ONNX/PaddlePaddle/ASR harus dimuat secara paralel.

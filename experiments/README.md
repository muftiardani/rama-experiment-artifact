# Experiments

Direktori ini berisi artefak eksperimen RAMA yang telah disanitasi.

## Struktur

```
experiments/
  calibration/       — hasil kalibrasi beban (keputusan 5 VU)
  k6/                — skrip beban k6 per kelas skenario (SS, A, B, C)
  fault-injection/   — skrip injeksi fault manual per skenario (a1–c2)
  recovery/          — skrip pemulihan worker (start_all.sh)
  postprocess/       — pipeline komputasi metrik dari request_logs DB ke CSV
  processed/         — hasil pascaproses final (CSV + statistik)
  evidence/
    screenshots/     — screenshot observabilitas representatif
    logs/            — log backend representatif saat fault aktif
  data/
    raw/             — indeks data mentah (data penuh tidak dipublikasikan)
```

## Status Artefak

| Direktori | Status |
|---|---|
| `calibration/` | Tersedia sebagian |
| `k6/` | **Tersedia** — 5 skrip (payloads.js stub) |
| `fault-injection/` | **Tersedia** — 8 skrip (a1–a3, b1–b3, c1, c2) |
| `recovery/` | **Tersedia** — start_all.sh |
| `postprocess/` | **Tersedia** — 10 skrip Python |
| `processed/` | **Tersedia** — 180 run valid (full run ke-2, 2026-06-27 s.d. 2026-06-29) |
| `evidence/screenshots/` | **Tersedia** — 18 screenshot Grafana (1 per skenario × kondisi, fase fault_active; SS: after_run) |
| `evidence/logs/` | **Tersedia** — 18 log backend representatif (1 per skenario × kondisi, fase fault_active; SS: after_run) |
| `data/raw/` | Tidak dipublikasikan penuh (lihat `data/raw/raw-data-not-published.md`) |

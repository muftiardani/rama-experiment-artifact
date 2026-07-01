# Artifact Manifest

## Ringkasan

Dokumen ini mencatat daftar artefak yang tersedia pada repository publik RAMA TemanDifa.

| Kode | Artefak | Lokasi | Status | Fungsi |
|---|---|---|---|---|
| A | ADR RAMA | `docs/adr/` | Tersedia (4 ADR) | Audit keputusan arsitektural |
| B | Konfigurasi deployment | `deployments/` | Tersedia | Audit konfigurasi implementasi |
| C | Kontrak gRPC/Protobuf | `proto/` | Tersedia (3 proto) | Audit klasifikasi respons dan kontrak AI worker |
| D | Manifest eksperimen | `automation/manifests/` | Tersedia (disanitasi) | Audit skenario eksperimen 180 run |
| E | Kalibrasi beban | `experiments/calibration/` | Tersedia sebagian | Audit keputusan 5 VU |
| F | Data mentah | `experiments/data/raw/` | Tidak dipublikasikan | Disediakan indeks karena alasan keamanan operasional |
| G | Hasil pascaproses | `experiments/processed/` | **Tersedia** | 180 run, 68.776 baris data; final_summary.csv, paired_summary.csv, statistical_tests.csv, data_dictionary.md |
| H | Bukti observabilitas | `experiments/evidence/` | **Tersedia** | screenshots/: 18 Grafana PNG (9 skenario × 2 kondisi); logs/: 18 backend log (fault_active, IP disanitasi) |
| I | Skrip eksperimen — automation | `automation/experimentctl/` | **Tersedia** (8 skrip) | runner.py, state_machine.py, k6_runner.py, fault_scheduler.py, invalidator.py, validator.py, statistical_analyzer.py, screenshot_collector.py |
| I2 | Skrip eksperimen — k6 load | `experiments/k6/` | **Tersedia** (5 skrip; payloads.js stub) | steady-state.js, class-a.js, class-b.js, class-c.js, common.js; payloads.js tidak dipublikasikan (media base64) |
| I3 | Skrip postprocessing | `experiments/postprocess/` | **Tersedia** (10 skrip) | Pipeline komputasi metrik: export_requests, compute_latency, compute_response_category, compute_pa, compute_tfs, compute_ttr, compute_slo_violation, compute_k6_throughput, build_summary, postprocess_utils |
| I4 | Skrip fault injection | `experiments/fault-injection/` | **Tersedia** (8 skrip) | a1–a3 (CPU/mem stress), b1–b3 (docker stop per worker), c1 (gradual mem), c2 (kaskade) |
| I5 | Skrip recovery | `experiments/recovery/` | **Tersedia** | start_all.sh: restart semua worker + polling health + catat event ke DB |
| J | Log bukti representatif | `experiments/evidence/logs/` | **Tersedia** (18 log, disanitasi) | Bukti perilaku sistem semua skenario (SS, A1–A3, B1–B3, C1–C2) × 2 kondisi, fase fault_active |
| K | Versi artefak | `README.md` dan `ARTIFACT_MANIFEST.md` | Tersedia | Keterlacakan repository dan commit |
| L | JSON Schema validasi | `automation/schemas/` | **Tersedia** (4 schema) | final_metadata, invalid_run, network_probe, snapshot — dipakai validator.py |
| M | Kode backend RAMA | `backend/` | **Tersedia** | config.go + 5 services: circuit_breaker, orchestrator, ai_service, fallback_service, response_classifier |
| N | Kode AI workers | `workers/` | **Tersedia** | OCR (PaddleOCR), Speech (faster-whisper), Vision (YOLOv8 ONNX) — masing-masing grpc_server, main, model |

## Catatan Sanitasi

Semua artefak yang dipublikasikan telah disanitasi dari credential, token, private key, IP publik, private IP, domain privat, URL repository privat, dan informasi operasional sensitif.

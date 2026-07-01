# Screenshot Observabilitas

Direktori ini berisi screenshot Grafana representatif dari eksperimen full run (180 run, 2026-06-27 s.d. 2026-06-29).

Cakupan: **18 screenshot** — 1 per kombinasi skenario × kondisi (9 skenario × 2 kondisi). Fase yang diambil adalah `fault_active` (menunjukkan sistem saat injeksi fault aktif), kecuali skenario SS yang hanya memiliki fase `after_run`.

## Daftar Screenshot

| Nama File | Skenario | Kondisi | Fase |
|---|---|---|---|
| `grafana_SS_static_resilience_run_01_after_run.png` | SS (Steady State) | static_resilience | after_run |
| `grafana_SS_treatment_run_01_after_run.png` | SS (Steady State) | treatment | after_run |
| `grafana_A1_static_resilience_run_01_fault_active.png` | A1 (CPU stress — vision) | static_resilience | fault_active |
| `grafana_A1_treatment_run_01_fault_active.png` | A1 (CPU stress — vision) | treatment | fault_active |
| `grafana_A2_static_resilience_run_01_fault_active.png` | A2 (memory stress — speech) | static_resilience | fault_active |
| `grafana_A2_treatment_run_01_fault_active.png` | A2 (memory stress — speech) | treatment | fault_active |
| `grafana_A3_static_resilience_run_01_fault_active.png` | A3 (CPU+memory — vision+speech) | static_resilience | fault_active |
| `grafana_A3_treatment_run_01_fault_active.png` | A3 (CPU+memory — vision+speech) | treatment | fault_active |
| `grafana_B1_static_resilience_run_01_fault_active.png` | B1 (stop vision worker) | static_resilience | fault_active |
| `grafana_B1_treatment_run_01_fault_active.png` | B1 (stop vision worker) | treatment | fault_active |
| `grafana_B2_static_resilience_run_01_fault_active.png` | B2 (stop speech worker) | static_resilience | fault_active |
| `grafana_B2_treatment_run_01_fault_active.png` | B2 (stop speech worker) | treatment | fault_active |
| `grafana_B3_static_resilience_run_01_fault_active.png` | B3 (stop OCR worker) | static_resilience | fault_active |
| `grafana_B3_treatment_run_01_fault_active.png` | B3 (stop OCR worker) | treatment | fault_active |
| `grafana_C1_static_resilience_run_01_fault_active.png` | C1 (gradual memory — speech) | static_resilience | fault_active |
| `grafana_C1_treatment_run_01_fault_active.png` | C1 (gradual memory — speech) | treatment | fault_active |
| `grafana_C2_static_resilience_run_01_fault_active.png` | C2 (cascade stop — vision+speech) | static_resilience | fault_active |
| `grafana_C2_treatment_run_01_fault_active.png` | C2 (cascade stop — vision+speech) | treatment | fault_active |

## Sanitasi

Semua screenshot telah diperiksa:
- [x] Tidak ada token atau credential
- [x] Tidak ada IP publik atau domain privat
- [x] Tidak ada username server
- [x] Panel Grafana terbaca (judul, metrik, grafik)

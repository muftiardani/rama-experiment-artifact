# Log Bukti Representatif

Direktori ini berisi cuplikan log backend representatif dari eksperimen full run (180 run, 2026-06-27 s.d. 2026-06-29).

Cakupan: **18 log** — 1 per kombinasi skenario × kondisi (9 skenario × 2 kondisi). Fase yang diambil adalah `fault_active` (menunjukkan respons sistem saat injeksi fault aktif), kecuali skenario SS yang hanya memiliki fase `after_run`.

## Daftar Log

| Nama File | Skenario | Kondisi | Fase |
|---|---|---|---|
| `backend_tail_SS_static_resilience_run_01_after_run.log` | SS (Steady State) | static_resilience | after_run |
| `backend_tail_SS_treatment_run_01_after_run.log` | SS (Steady State) | treatment | after_run |
| `backend_tail_A1_static_resilience_run_01_fault_active.log` | A1 (CPU stress — vision) | static_resilience | fault_active |
| `backend_tail_A1_treatment_run_01_fault_active.log` | A1 (CPU stress — vision) | treatment | fault_active |
| `backend_tail_A2_static_resilience_run_01_fault_active.log` | A2 (memory stress — speech) | static_resilience | fault_active |
| `backend_tail_A2_treatment_run_01_fault_active.log` | A2 (memory stress — speech) | treatment | fault_active |
| `backend_tail_A3_static_resilience_run_01_fault_active.log` | A3 (CPU+memory — vision+speech) | static_resilience | fault_active |
| `backend_tail_A3_treatment_run_01_fault_active.log` | A3 (CPU+memory — vision+speech) | treatment | fault_active |
| `backend_tail_B1_static_resilience_run_01_fault_active.log` | B1 (stop vision worker) | static_resilience | fault_active |
| `backend_tail_B1_treatment_run_01_fault_active.log` | B1 (stop vision worker) | treatment | fault_active |
| `backend_tail_B2_static_resilience_run_01_fault_active.log` | B2 (stop speech worker) | static_resilience | fault_active |
| `backend_tail_B2_treatment_run_01_fault_active.log` | B2 (stop speech worker) | treatment | fault_active |
| `backend_tail_B3_static_resilience_run_01_fault_active.log` | B3 (stop OCR worker) | static_resilience | fault_active |
| `backend_tail_B3_treatment_run_01_fault_active.log` | B3 (stop OCR worker) | treatment | fault_active |
| `backend_tail_C1_static_resilience_run_01_fault_active.log` | C1 (gradual memory — speech) | static_resilience | fault_active |
| `backend_tail_C1_treatment_run_01_fault_active.log` | C1 (gradual memory — speech) | treatment | fault_active |
| `backend_tail_C2_static_resilience_run_01_fault_active.log` | C2 (cascade stop — vision+speech) | static_resilience | fault_active |
| `backend_tail_C2_treatment_run_01_fault_active.log` | C2 (cascade stop — vision+speech) | treatment | fault_active |

## Sanitasi

Semua log telah disanitasi sebelum dipublikasikan:
- [x] Private IP (`172.18.0.x`) diganti `[IP-DISAMARKAN]`
- [x] Tidak ada token atau credential
- [x] Tidak ada domain atau hostname privat

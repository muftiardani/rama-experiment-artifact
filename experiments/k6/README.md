# Skrip Beban k6

Skrip pengujian beban untuk setiap kelas skenario eksperimen RAMA.

| File | Skenario | Deskripsi |
|---|---|---|
| `steady-state.js` | SS | Beban normal tanpa fault |
| `class-a.js` | A1–A3 | Beban untuk resource exhaustion (CPU/memory pressure) |
| `class-b.js` | B1–B3 | Beban untuk component failure (worker dihentikan) |
| `class-c.js` | C1–C2 | Beban untuk cascading failure (tekanan memori bertahap + kaskade) |
| `common.js` | — | Helper bersama: build payload request, konfigurasi dasar k6 |
| `payloads.js` | — | Stub — media base64 asli tidak dipublikasikan (lihat komentar di dalam file) |

Dijalankan oleh `automation/experimentctl/k6_runner.py` sebagai proses eksternal dari load generator terpisah (bukan di target VPS).

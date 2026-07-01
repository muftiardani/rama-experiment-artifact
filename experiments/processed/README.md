# Hasil Pascaproses

Folder ini berisi data agregat hasil eksperimen RAMA (full run ke-2, 2026-06-27 s.d. 2026-06-29).

## File

| File | Baris | Deskripsi |
|---|---|---|
| `final_summary.csv` | 180 | Satu baris per run valid — semua metrik per run |
| `paired_summary.csv` | 90 | Delta per pasangan run (skenario × repetisi) — static vs treatment |
| `statistical_tests.csv` | 63 | Hasil uji Wilcoxon signed-rank per metrik |

Lihat `data_dictionary.md` di folder ini untuk definisi kolom lengkap.

## Ringkasan Eksperimen

- **Rancangan:** 9 skenario × 2 kondisi × 10 repetisi = 180 run
- **Hasil validasi:** 180/180 run valid (100%)
- **Baris data mentah pascaproses:** 68.776 baris
- **Alat pengujian beban:** k6 (5 VU, durasi ~10 menit per run)
- **Referensi commit:** `0538f79`

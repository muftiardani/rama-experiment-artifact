# Kalibrasi Beban — 10 VU

Direktori ini berisi ringkasan kalibrasi beban dengan konfigurasi 10 Virtual User (VU).

## Hasil Kalibrasi

Tanggal: 2026-06-06 | Commit: `04f55bc`

| VU | p95 (ms) | Error Rate | RPS | OK |
|---:|---:|---:|---:|---|
| 5  | 39.088 | 0,0% | 0,19 | ✓ (0% error) |
| 10 | 60.315 | 38,9% | 0,17 | ✗ (timeout massal) |

## Alasan Tidak Dipilih

VU=10 ditolak karena menyebabkan saturasi resource pada target single-node: p95 mencapai 60 detik (tepat di batas timeout backend) dengan error rate 38,9% — jauh melampaui ambang toleransi 10%. Pola latensi tidak stabil dan tidak representatif untuk perbandingan kondisi eksperimen.

VU yang dipilih adalah **5 VU** (lihat `../vu5/README.md`).

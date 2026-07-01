# Kalibrasi Beban — 5 VU

Direktori ini berisi ringkasan kalibrasi beban dengan konfigurasi 5 Virtual User (VU).

## Hasil Kalibrasi

Tanggal: 2026-06-06 | Commit: `04f55bc`

| VU | p95 (ms) | Error Rate | RPS | OK |
|---:|---:|---:|---:|---|
| 5  | 39.088 | 0,0% | 0,19 | ✓ (0% error) |
| 10 | 60.315 | 38,9% | 0,17 | ✗ (timeout massal) |

## Keputusan

**VU final dipilih: 5**

VU=5 adalah satu-satunya konfigurasi dengan 0% error rate. Bottleneck utama adalah ASR worker (Faster-Whisper) yang bersifat serial — antrian 5 request × ~6 detik per request menghasilkan p95 ≈ 39 detik, masih dalam batas timeout backend. VU=10 menyebabkan timeout massal (38,9% error rate) karena saturasi antrian ASR.

Threshold k6 ditetapkan `p95 < 60 s` (realistis untuk VU=5 multimodal pada VPS resource-constrained).

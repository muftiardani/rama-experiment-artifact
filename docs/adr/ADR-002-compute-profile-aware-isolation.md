# ADR-002: Compute Profile-Aware Resource Isolation

**Status:** Diterima  
**Tanggal:** 2026-04  
**Konteks:** Ketiga AI worker berjalan pada satu node fisik dengan resource terbatas (single-node resource-constrained).

---

## Konteks

Pada lingkungan single-node, tiga worker bersaing untuk CPU dan memori yang sama. Tanpa pembatasan resource eksplisit, satu worker yang mengalami memory pressure (skenario eksperimen) dapat menyebabkan OOM-kill pada worker lain melalui page reclaim kernel — menyebabkan kegagalan kaskade yang bukan merupakan perilaku yang ingin diuji.

Profil komputasi setiap model berbeda secara signifikan:

| Worker | Model | Karakteristik dominan |
|---|---|---|
| Vision | YOLOv8 (ONNX) | CPU burst saat inferensi, memori moderat |
| OCR | PaddleOCR + MKL-DNN | CPU intensif; MKL-DNN membutuhkan ~800MB–1GB |
| Speech | Whisper/ASR | Memori besar untuk load model; CPU relatif rendah |

## Keputusan

Setiap worker dikonfigurasi dengan `deploy.resources.limits` dan `reservations` Docker Compose yang mencerminkan profil aktualnya:

```
Vision : cpus=0.80 limit / 0.30 reserved | memory=768MB limit  / 256MB reserved
OCR    : cpus=0.50 limit / 0.20 reserved | memory=1024MB limit / 512MB reserved
Speech : cpus=0.40 limit / 0.10 reserved | memory=1280MB limit / 768MB reserved
```

Nilai limit diturunkan secara iteratif dari kalibrasi beban (`experiments/calibration/`) — bukan dari spesifikasi teoritis model. Backend Go dikonfigurasi terpisah: `cpus=0.50`, `memory=512MB`.

`stop_grace_period: 45s` ditetapkan pada setiap worker untuk memberi waktu cukup bagi lifespan gRPC (`grpc_process.join(timeout=35)`) selesai sebelum Docker mengirim SIGKILL.

## Konsekuensi

**Positif:**
- Isolasi resource mencegah OOM satu worker memicu page reclaim yang memengaruhi worker lain — fault injection (skenario A, B) hanya memengaruhi target yang dimaksud.
- Reservasi memori menjamin minimum alokasi saat startup model (ONNX load, PaddlePaddle init, model ASR).
- Limit eksplisit membuat perilaku sistem di bawah tekanan lebih deterministik dan reproducible antar run eksperimen.

**Negatif:**
- Nilai limit harus dikalibrasi ulang jika model diganti atau versi framework diupgrade.
- Pada skenario stress (A1–A3), limit yang ketat mempercepat OOM/throttling — ini adalah perilaku yang diinginkan untuk eksperimen tetapi bukan kondisi produksi umum.

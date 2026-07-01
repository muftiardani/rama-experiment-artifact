# Skrip Injeksi Fault

Skrip shell yang menyuntikkan fault sesuai skenario, dijalankan pada target VPS oleh `automation/experimentctl/fault_scheduler.py`.

| File | Skenario | Fault |
|---|---|---|
| `a1_cpu_vision.sh` | A1 | CPU pressure pada vision worker |
| `a2_mem_speech.sh` | A2 | Memory pressure pada speech worker |
| `a3_combined.sh` | A3 | CPU + memory pressure kombinasi (vision + speech paralel) |
| `b1_stop_vision.sh` | B1 | Hentikan container vision |
| `b2_stop_speech.sh` | B2 | Hentikan container speech |
| `b3_stop_ocr.sh` | B3 | Hentikan container OCR |
| `c1_gradual_mem.sh` | C1 | Tekanan memori bertahap pada speech (3 tahap) |
| `c2_cascade.sh` | C2 | Kaskade — stop vision, tunggu, lalu stop speech |

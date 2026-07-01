# AI Workers (Python) — Source Excerpt

Tiga AI worker RAMA (rasional isolasi per-model: lihat `docs/adr/ADR-001-per-model-service-isolation.md`):

| Worker | Model | File |
|---|---|---|
| `vision/` | YOLOv8 via ONNX Runtime | `grpc_server.py`, `main.py`, `models/yolo.py` |
| `ocr/` | PaddleOCR 2.7 + PaddlePaddle 2.6 | `grpc_server.py`, `main.py`, `models/ocr_model.py` |
| `speech/` | Faster-Whisper (ASR) | `grpc_server.py`, `main.py`, `models/speech_model.py` |

Bukan full buildable codebase — lihat [`REPRODUCIBILITY.md`](../REPRODUCIBILITY.md#catatan-struktur-kode) untuk daftar dependency internal yang tidak dipublikasikan.

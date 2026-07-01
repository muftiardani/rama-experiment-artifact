import logging
import threading
import time
from typing import Optional

import cv2
import numpy as np
import onnxruntime as ort

from app.core.config import (
    MAX_IMAGE_DIMENSION,
    MODEL_PATH,
    VISION_INFERENCE_SEM_TIMEOUT_S,
    VISION_MAX_CONCURRENT_INFERENCES,
    YOLO_INPUT_SIZE,
)
from app.core.image_validation import check_image_dimensions_precheck, validate_image_bytes
from app.core.yolo_postprocess import parse_yolo_output

logger = logging.getLogger(__name__)

_session: Optional[ort.InferenceSession] = None
_model_lock = threading.Lock()
_inference_sem = threading.Semaphore(max(1, VISION_MAX_CONCURRENT_INFERENCES))


def _ensure_model(model_path: str) -> None:
    import os
    if os.path.exists(model_path):
        return
    logger.info(f"Model tidak ditemukan di {model_path}, mengunduh YOLOv8n...")
    try:
        from ultralytics import YOLO
        os.makedirs(os.path.dirname(model_path) or "models", exist_ok=True)
        model = YOLO("yolov8n.pt")
        model.export(format="onnx", imgsz=640)
        import shutil
        src = "yolov8n.onnx"
        if os.path.exists(src):
            shutil.move(src, model_path)
            logger.info(f"Model berhasil diunduh dan disimpan ke {model_path}")
        else:
            raise FileNotFoundError("yolov8n.onnx tidak terbentuk setelah export")
    except Exception as e:
        logger.error(f"Gagal mengunduh model: {e}")
        raise


def load_model(model_path: str = MODEL_PATH) -> None:
    global _session
    try:
        _ensure_model(model_path)
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        session = ort.InferenceSession(
            model_path, opts, providers=['CPUExecutionProvider']
        )
        input_type = session.get_inputs()[0].type
        if input_type != 'tensor(float)':
            raise ValueError(
                f"Model ONNX membutuhkan input tipe '{input_type}', bukan float32. "
                "Gunakan model YOLOv8 yang diekspor dengan format standar."
            )
        with _model_lock:
            _session = session
        logger.info(f"YOLOv8 model loaded: {model_path}")
        _warmup()
    except Exception as e:
        logger.error(f"Failed to load model: {e}")
        raise


def _warmup() -> None:
    """Jalankan inference dummy untuk kompilasi JIT agar request pertama tidak lambat."""
    with _model_lock:
        session = _session
    if session is None:
        return
    try:
        dummy = np.zeros((1, 3, YOLO_INPUT_SIZE, YOLO_INPUT_SIZE), dtype=np.float32)
        input_name = session.get_inputs()[0].name
        session.run(None, {input_name: dummy})
        logger.info("YOLOv8 model warm-up selesai")
    except Exception as e:
        logger.warning(f"Model warm-up gagal (non-fatal): {e}")


def is_model_loaded() -> bool:
    with _model_lock:
        return _session is not None


def detect(image_bytes: bytes, confidence_threshold: float = 0.5) -> dict:
    with _model_lock:
        session = _session
    if session is None:
        raise RuntimeError("Model tidak dimuat")
    if not image_bytes:
        raise ValueError("Data gambar kosong")

    validate_image_bytes(image_bytes)
    # Cek dimensi dari header sebelum decode penuh untuk mencegah alokasi memori besar
    check_image_dimensions_precheck(image_bytes)

    acquired = _inference_sem.acquire(timeout=VISION_INFERENCE_SEM_TIMEOUT_S)
    if not acquired:
        raise RuntimeError(
            f"Vision engine timeout: tidak dapat mulai inferensi dalam "
            f"{VISION_INFERENCE_SEM_TIMEOUT_S:.0f}s"
        )
    try:
        start = time.perf_counter()

        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        del nparr

        if img is None:
            raise ValueError("Tidak dapat mendekode gambar: format tidak valid atau rusak")

        orig_h, orig_w = img.shape[:2]
        # PIL precheck bisa gagal diam-diam (except Exception: pass); cek decode hasil
        # sebagai fallback agar gambar beresolusi tinggi tidak lolos ke inferensi.
        if orig_h > MAX_IMAGE_DIMENSION or orig_w > MAX_IMAGE_DIMENSION:
            del img
            raise ValueError(
                f"Dimensi gambar terlalu besar: {orig_w}x{orig_h} "
                f"(maks {MAX_IMAGE_DIMENSION}px)"
            )

        img_resized = cv2.resize(img, (YOLO_INPUT_SIZE, YOLO_INPUT_SIZE))
        del img

        img_normalized = img_resized.astype(np.float32) / 255.0
        del img_resized

        img_transposed = np.transpose(img_normalized, (2, 0, 1))
        del img_normalized

        img_batched = np.expand_dims(img_transposed, axis=0)
        del img_transposed

        input_name = session.get_inputs()[0].name
        outputs = session.run(None, {input_name: img_batched})
        del img_batched
    finally:
        _inference_sem.release()

    elapsed_ms = (time.perf_counter() - start) * 1000
    objects = parse_yolo_output(outputs[0], confidence_threshold, (orig_h, orig_w))

    return {
        "objects": objects,
        "inference_time_ms": round(elapsed_ms, 2),
    }

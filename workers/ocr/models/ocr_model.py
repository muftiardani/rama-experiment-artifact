import logging
import threading
import time
from typing import Optional

import cv2
import numpy as np
from paddleocr import PaddleOCR

from app.core.config import (
    ALLOWED_OCR_LANGUAGES,
    MAX_IMAGE_DIMENSION,
    OCR_LANGUAGE,
)
from app.core.image_validation import check_image_dimensions_precheck, validate_image_bytes

logger = logging.getLogger(__name__)

_ocr: Optional[PaddleOCR] = None
_ocr_lock = threading.Lock()
# PaddleOCR tidak thread-safe; semaphore membatasi inferensi ke satu thread sekaligus.
_ocr_sem = threading.Semaphore(1)
_OCR_SEM_TIMEOUT_S = 60


def load_model() -> None:
    global _ocr
    try:
        model = PaddleOCR(
            use_angle_cls=True,
            lang=OCR_LANGUAGE,
            use_gpu=False,
            show_log=False,
            enable_mkldnn=True,
        )
        with _ocr_lock:
            _ocr = model
        logger.info(f"PaddleOCR model loaded: lang={OCR_LANGUAGE}")
        _warmup()
    except Exception as e:
        logger.error(f"Failed to load PaddleOCR model: {e}")
        raise


def _warmup() -> None:
    """Jalankan inference dummy agar JIT/cache terisi sebelum request pertama."""
    if _ocr is None:
        return
    try:
        dummy = np.full((32, 32, 3), 255, dtype=np.uint8)
        with _ocr_sem:
            _ocr.ocr(dummy, cls=True)
        logger.info("PaddleOCR model warm-up selesai")
    except Exception as e:
        logger.warning(f"Model warm-up gagal (non-fatal): {e}")


def is_model_loaded() -> bool:
    with _ocr_lock:
        return _ocr is not None


def recognize(
    image_bytes: bytes,
    language: str = "id",
    include_coordinates: bool = True,
) -> dict:
    with _ocr_lock:
        ocr_instance = _ocr
    if ocr_instance is None:
        raise RuntimeError("OCR model tidak dimuat")
    if not image_bytes:
        raise ValueError("Data gambar kosong")

    validate_image_bytes(image_bytes)
    # Cek dimensi dari header sebelum decode penuh untuk mencegah alokasi memori besar
    check_image_dimensions_precheck(image_bytes)

    if language not in ALLOWED_OCR_LANGUAGES:
        raise ValueError(
            f"Bahasa OCR '{language}' tidak didukung. "
            f"Gunakan salah satu: {', '.join(sorted(ALLOWED_OCR_LANGUAGES))}"
        )
    elif language != OCR_LANGUAGE:
        raise ValueError(
            f"Bahasa OCR '{language}' berbeda dari model yang dimuat ('{OCR_LANGUAGE}'). "
            "Restart worker dengan OCR_LANGUAGE yang sesuai untuk mengganti bahasa."
        )
    else:
        effective_lang = language

    start = time.perf_counter()

    # Acquire semaphore SEBELUM decode agar numpy array besar tidak dialokasikan
    # oleh beberapa thread sekaligus saat menunggu giliran inferensi.
    # Worst-case dengan MAX_IMAGE_DIMENSION=8000: satu array BGR = 192 MB;
    # menggeser acquire ke sini membatasi alokasi menjadi satu array sekaligus.
    acquired = _ocr_sem.acquire(timeout=_OCR_SEM_TIMEOUT_S)
    if not acquired:
        raise RuntimeError(
            f"OCR engine timeout: tidak dapat mulai inferensi dalam {_OCR_SEM_TIMEOUT_S}s "
            "(kemungkinan ada proses yang macet)"
        )
    try:
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

        result = ocr_instance.ocr(img, cls=True)
        del img
    finally:
        _ocr_sem.release()

    elapsed_ms = (time.perf_counter() - start) * 1000

    blocks = []
    full_text_parts = []

    if result and result[0]:
        for line in result[0]:
            try:
                box, (text, confidence) = line
            except (TypeError, ValueError):
                logger.warning(f"Format hasil PaddleOCR tidak terduga, baris dilewati: {line!r}")
                continue
            full_text_parts.append(text)
            block = {"text": text, "confidence": round(float(confidence), 4)}
            if include_coordinates:
                xs = [p[0] for p in box]
                ys = [p[1] for p in box]
                block.update({
                    "x1": float(min(xs)), "y1": float(min(ys)),
                    "x2": float(max(xs)), "y2": float(max(ys)),
                })
            blocks.append(block)

    return {
        "blocks": blocks,
        "full_text": " ".join(full_text_parts),
        "inference_time_ms": round(elapsed_ms, 2),
        "language": effective_lang,
        "text_detected": len(blocks) > 0,
    }

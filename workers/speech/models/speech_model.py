import io
import logging
import threading
import time
from typing import Optional

from faster_whisper import WhisperModel

from app.core.audio_validation import validate_audio_bytes
from app.core.config import (
    SPEECH_INFERENCE_SEM_TIMEOUT_S,
    SPEECH_MAX_CONCURRENT_INFERENCES,
    WHISPER_BEAM_SIZE,
    WHISPER_MODEL_SIZE,
    WHISPER_VAD_FILTER,
    WHISPER_VAD_MIN_SILENCE_MS,
)

logger = logging.getLogger(__name__)

_model: Optional[WhisperModel] = None
_model_lock = threading.Lock()
_transcribe_sem = threading.Semaphore(max(1, SPEECH_MAX_CONCURRENT_INFERENCES))

KEYWORDS = [
    "deteksi", "scan", "baca", "buka", "tutup", "kiri", "kanan",
    "atas", "bawah", "bantu", "stop", "mulai", "ulangi", "keluar",
]


def load_model(model_size: str = WHISPER_MODEL_SIZE) -> None:
    global _model
    try:
        m = WhisperModel(
            model_size,
            device="cpu",
            compute_type="int8",
            cpu_threads=2,
            num_workers=1,
        )
        with _model_lock:
            _model = m
        logger.info(f"Faster-Whisper model loaded: {model_size} (int8, cpu)")
        _warmup()
    except Exception as e:
        logger.error(f"Failed to load Faster-Whisper model: {e}")
        raise


def _warmup() -> None:
    with _model_lock:
        session = _model
    if session is None:
        return
    try:
        silent_wav = (
            b'RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00'
            b'\x01\x00\x01\x00\x80\xbb\x00\x00\x00w\x01\x00'
            b'\x02\x00\x10\x00data\x00\x00\x00\x00'
        )
        list(session.transcribe(io.BytesIO(silent_wav), beam_size=1)[0])
        logger.info("Faster-Whisper model warm-up selesai")
    except Exception as e:
        logger.warning(f"Model warm-up gagal (non-fatal): {e}")


def is_model_loaded() -> bool:
    with _model_lock:
        return _model is not None


def transcribe(
    audio_bytes: bytes,
    language: str = None,
    keyword_only: bool = False,
) -> dict:
    with _model_lock:
        session = _model
    if session is None:
        raise RuntimeError("Speech model tidak dimuat")
    if not audio_bytes:
        raise ValueError("Data audio kosong")

    audio_buffer = io.BytesIO(audio_bytes)
    validate_audio_bytes(audio_bytes, audio_buffer)

    acquired = _transcribe_sem.acquire(timeout=SPEECH_INFERENCE_SEM_TIMEOUT_S)
    if not acquired:
        raise RuntimeError(
            f"Speech engine timeout: tidak dapat mulai inferensi dalam "
            f"{SPEECH_INFERENCE_SEM_TIMEOUT_S:.0f}s"
        )
    try:
        start = time.perf_counter()
        segments, info = session.transcribe(
            audio_buffer,
            language=language or None,
            beam_size=WHISPER_BEAM_SIZE,
            vad_filter=WHISPER_VAD_FILTER,
            vad_parameters={"min_silence_duration_ms": WHISPER_VAD_MIN_SILENCE_MS},
        )

        text_parts = [segment.text.strip() for segment in segments]
        detected_language = info.language
        language_probability = float(info.language_probability)
    finally:
        _transcribe_sem.release()
    del session

    full_text = " ".join(text_parts)
    elapsed_ms = (time.perf_counter() - start) * 1000

    detected_keywords = []
    if keyword_only:
        detected_keywords = [kw for kw in KEYWORDS if kw.lower() in full_text.lower()]

    return {
        "text": full_text,
        "detected_language": detected_language,
        "confidence": language_probability,
        "inference_time_ms": round(elapsed_ms, 2),
        "keywords": detected_keywords,
    }

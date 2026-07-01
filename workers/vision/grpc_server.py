import logging
import multiprocessing
import signal
import time
from concurrent import futures

import grpc

from app.core.config import (
    ENVIRONMENT,
    GRPC_AUTH_TOKEN,
    GRPC_MAX_MESSAGE_MB,
    GRPC_MAX_WORKERS,
    GRPC_PORT,
    GRPC_TLS_CERT_FILE,
    GRPC_TLS_ENABLED,
    GRPC_TLS_KEY_FILE,
    METRICS_TOKEN,
    MODEL_PATH,
    REQUIRE_GRPC_AUTH,
    YOLO_CONFIDENCE_DEFAULT,
)
from app.core.grpc_auth import TokenInterceptor
from app.core.health import get_health_status
from app.core.logging_config import configure_logging
from app.core.metrics import INFERENCE_COUNTER, INFERENCE_LATENCY
from app.models.yolo import detect, is_model_loaded, load_model
from app.proto import vision_pb2, vision_pb2_grpc

logger = logging.getLogger(__name__)


def _bind_grpc_port(server: grpc.Server) -> int:
    addr = f'[::]:{GRPC_PORT}'
    if GRPC_TLS_ENABLED:
        if not GRPC_TLS_CERT_FILE or not GRPC_TLS_KEY_FILE:
            raise RuntimeError(
                "GRPC_TLS_ENABLED=true tetapi GRPC_TLS_CERT_FILE/GRPC_TLS_KEY_FILE belum dikonfigurasi"
            )
        try:
            with open(GRPC_TLS_KEY_FILE, "rb") as key_file:
                private_key = key_file.read()
            with open(GRPC_TLS_CERT_FILE, "rb") as cert_file:
                certificate_chain = cert_file.read()
        except OSError as e:
            logger.critical(
                "Gagal membaca file TLS gRPC (key=%s cert=%s): %s",
                GRPC_TLS_KEY_FILE, GRPC_TLS_CERT_FILE, e,
            )
            raise
        credentials = grpc.ssl_server_credentials(((private_key, certificate_chain),))
        return server.add_secure_port(addr, credentials)
    return server.add_insecure_port(addr)


class VisionServicer(vision_pb2_grpc.VisionServiceServicer):

    def DetectObjects(self, request, context):
        _remaining = context.time_remaining()
        if _remaining is not None and _remaining <= 0:
            context.set_code(grpc.StatusCode.DEADLINE_EXCEEDED)
            context.set_details("Deadline exceeded before inference")
            return vision_pb2.DetectResponse(service_level="FALLBACK")

        start = time.perf_counter()
        try:
            threshold = (
                request.confidence_threshold
                if 0 < request.confidence_threshold <= 1.0
                else YOLO_CONFIDENCE_DEFAULT
            )
            result = detect(
                image_bytes=request.image_data,
                confidence_threshold=threshold,
            )
            elapsed = time.perf_counter() - start
            _remaining = context.time_remaining()
            if _remaining is not None and _remaining <= 0:
                INFERENCE_COUNTER.labels(status="timeout").inc()
                INFERENCE_LATENCY.labels(status="timeout").observe(elapsed)
                context.set_code(grpc.StatusCode.DEADLINE_EXCEEDED)
                context.set_details("Deadline exceeded during inference")
                return vision_pb2.DetectResponse(service_level="FALLBACK")
            INFERENCE_COUNTER.labels(status="success").inc()
            INFERENCE_LATENCY.labels(status="success").observe(elapsed)
            objects = [
                vision_pb2.DetectionObject(
                    label=obj["label"],
                    confidence=obj["confidence"],
                    x1=obj["x1"], y1=obj["y1"],
                    x2=obj["x2"], y2=obj["y2"],
                )
                for obj in result["objects"]
            ]
            return vision_pb2.DetectResponse(
                objects=objects,
                total_detected=len(objects),
                inference_time_ms=result["inference_time_ms"],
                service_level="FULL",
            )
        except ValueError as e:
            logger.warning(f"DetectObjects invalid input: {e}")
            INFERENCE_COUNTER.labels(status="error").inc()
            INFERENCE_LATENCY.labels(status="error").observe(time.perf_counter() - start)
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(e))
            return vision_pb2.DetectResponse(service_level="FALLBACK")
        except RuntimeError as e:
            logger.warning(f"DetectObjects overloaded: {e}")
            INFERENCE_COUNTER.labels(status="error").inc()
            INFERENCE_LATENCY.labels(status="error").observe(time.perf_counter() - start)
            context.set_code(grpc.StatusCode.RESOURCE_EXHAUSTED)
            context.set_details(str(e))
            return vision_pb2.DetectResponse(service_level="FALLBACK")
        except Exception as e:
            logger.error(f"DetectObjects error: {e}")
            INFERENCE_COUNTER.labels(status="error").inc()
            INFERENCE_LATENCY.labels(status="error").observe(time.perf_counter() - start)
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Internal error during inference")
            return vision_pb2.DetectResponse(service_level="FALLBACK")

    def HealthCheck(self, request, context):
        import os
        s = get_health_status(os.path.basename(MODEL_PATH), is_loaded=is_model_loaded())
        return vision_pb2.HealthResponse(
            status=s["status"],
            model_loaded=s["model_loaded"],
            memory_usage_mb=s["memory_usage_mb"],
            cpu_usage_percent=s["cpu_usage_percent"],
            version=s["version"],
        )


def start_grpc_server(model_ready_event: multiprocessing.Event):
    configure_logging()

    if ENVIRONMENT == "production" and not METRICS_TOKEN:
        logger.critical("METRICS_TOKEN wajib dikonfigurasi saat ENVIRONMENT=production")
        raise ValueError("METRICS_TOKEN wajib dikonfigurasi saat ENVIRONMENT=production")

    if REQUIRE_GRPC_AUTH and not GRPC_AUTH_TOKEN:
        raise RuntimeError("GRPC_AUTH_TOKEN wajib dikonfigurasi saat REQUIRE_GRPC_AUTH=true")
    if not GRPC_AUTH_TOKEN:
        logger.warning(
            "GRPC_AUTH_TOKEN tidak dikonfigurasi — Vision Worker berjalan TANPA autentikasi. "
            "Set GRPC_AUTH_TOKEN di environment untuk production."
        )

    try:
        load_model(MODEL_PATH)
    except Exception:
        logger.critical("Model gagal dimuat, subprocess keluar")
        return  # monitor di main.py akan deteksi kematian proses dan restart container

    interceptors = [TokenInterceptor(GRPC_AUTH_TOKEN)] if GRPC_AUTH_TOKEN else []

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=GRPC_MAX_WORKERS),
        interceptors=interceptors,
        options=[
            ('grpc.max_send_message_length', GRPC_MAX_MESSAGE_MB * 1024 * 1024),
            ('grpc.max_receive_message_length', GRPC_MAX_MESSAGE_MB * 1024 * 1024),
            # Backend client menggunakan PermitWithoutStream=true: izinkan ping
            # saat tidak ada stream aktif agar koneksi idle tidak di-GOAWAY.
            ('grpc.keepalive_permit_without_calls', 1),
            ('grpc.http2.min_ping_interval_without_data_ms', 5000),
        ],
    )
    vision_pb2_grpc.add_VisionServiceServicer_to_server(VisionServicer(), server)
    port = _bind_grpc_port(server)
    if port == 0:
        raise RuntimeError(
            f"Gagal bind gRPC port {GRPC_PORT}: port sudah dipakai atau tidak diizinkan"
        )
    signal.signal(signal.SIGTERM, lambda _s, _f: server.stop(grace=30))
    server.start()
    scheme = "TLS" if GRPC_TLS_ENABLED else "insecure"
    logger.info(f"Vision gRPC server started on port {GRPC_PORT} ({scheme})")

    model_ready_event.set()

    server.wait_for_termination()

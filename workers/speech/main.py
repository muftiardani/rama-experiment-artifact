import asyncio
import logging
import multiprocessing
import os
import shutil
from contextlib import asynccontextmanager, suppress
from pathlib import Path


def _configure_prometheus_multiprocess() -> None:
    metrics_dir = os.getenv("PROMETHEUS_MULTIPROC_DIR", "/tmp/prometheus_multiproc")
    os.environ["PROMETHEUS_MULTIPROC_DIR"] = metrics_dir
    if multiprocessing.current_process().name == "MainProcess":
        path = Path(metrics_dir)
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)


_configure_prometheus_multiprocess()

import psutil
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from prometheus_client import CollectorRegistry, make_asgi_app, multiprocess

from app.core.config import WHISPER_MODEL_SIZE
from app.core.health import get_health_status
from app.core.metrics_auth import metrics_auth_middleware
from app.core.metrics import CPU_USAGE, MEMORY_USAGE
from app.grpc_server import start_grpc_server

logger = logging.getLogger(__name__)

_model_ready = multiprocessing.Event()


async def _monitor_grpc_process(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(2)
        grpc_process = app.state.grpc_process
        if not grpc_process.is_alive():
            logger.critical(
                "gRPC subprocess died (exit code: %s); exiting for container restart",
                grpc_process.exitcode,
            )
            if grpc_process.pid is not None:
                multiprocess.mark_process_dead(grpc_process.pid)
            os._exit(1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    grpc_process = multiprocessing.Process(
        target=start_grpc_server, args=(_model_ready,)
    )
    grpc_process.start()
    app.state.grpc_process = grpc_process
    # Prime subprocess CPU counter — panggilan pertama selalu 0.0, harus dibuang
    try:
        psutil.Process(grpc_process.pid).cpu_percent(interval=None)
    except psutil.NoSuchProcess:
        pass
    monitor_task = asyncio.create_task(_monitor_grpc_process(app))
    monitor_task.add_done_callback(
        lambda t: t.cancelled() or t.exception() and os._exit(1)
    )
    yield
    monitor_task.cancel()
    with suppress(asyncio.CancelledError):
        await monitor_task
    grpc_process.terminate()
    grpc_process.join(timeout=35)
    if grpc_process.is_alive():
        grpc_process.kill()
        grpc_process.join(timeout=5)
    if grpc_process.pid is not None:
        multiprocess.mark_process_dead(grpc_process.pid)


app = FastAPI(title="Speech Worker", version="1.0.0", lifespan=lifespan)
app.middleware("http")(metrics_auth_middleware)

metrics_registry = CollectorRegistry()
multiprocess.MultiProcessCollector(metrics_registry)
metrics_app = make_asgi_app(registry=metrics_registry)
app.mount("/metrics", metrics_app)


@app.get("/health")
async def health_check():
    model_name = f"faster-whisper-{WHISPER_MODEL_SIZE}"
    status = get_health_status(model_name, is_loaded=_model_ready.is_set())
    grpc_process = app.state.grpc_process
    try:
        _gp = psutil.Process(grpc_process.pid)
        MEMORY_USAGE.set(_gp.memory_info().rss)
        CPU_USAGE.set(_gp.cpu_percent(interval=None))
    except psutil.NoSuchProcess:
        MEMORY_USAGE.set(0)
        CPU_USAGE.set(0.0)
    if not grpc_process.is_alive():
        status["status"] = "UNHEALTHY"
        status["grpc_process"] = "dead"
    if status["status"] == "UNHEALTHY":
        return JSONResponse(status_code=503, content=status)
    return status


@app.get("/ready")
async def readiness_check():
    grpc_process = app.state.grpc_process
    if _model_ready.is_set() and grpc_process.is_alive():
        return {"ready": True}
    return JSONResponse(status_code=503, content={"ready": False})

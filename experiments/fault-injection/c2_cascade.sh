#!/usr/bin/env bash
# Menguji TTR (Time-to-Recovery) dan stabilitas fallback multi-worker.
set -euo pipefail

SCENARIO=${SCENARIO:-C2}
: "${CONDITION:?Set CONDITION=static_resilience atau treatment}"
RUN=${RUN:-1}
BASE_URL=${BASE_URL:-http://localhost:8080}
ACCESS_TOKEN=${ACCESS_TOKEN:-}
HOLD_SECONDS=${HOLD_SECONDS:-90}   # waktu tahan setelah kedua worker dihentikan

if [[ -z "${ACCESS_TOKEN}" ]]; then
  echo "[C2] ERROR: Set ACCESS_TOKEN sebelum menjalankan eksperimen." >&2
  exit 1
fi

log_event() {
  # best-effort: kegagalan log tidak boleh menghentikan eksekusi fault.
  curl -sf -m 10 -X POST "${BASE_URL}/api/v1/experiments/fault-events" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -d "$1" \
    || echo "[C2] WARN: Gagal mencatat event ke backend — catat manual ke DB jika diperlukan." >&2
}

if ! docker inspect -f '{{.State.Running}}' temandifa_vision 2>/dev/null | grep -qx true; then
  echo "[C2] ERROR: Container temandifa_vision tidak ditemukan atau tidak berjalan." >&2
  exit 1
fi
if ! docker inspect -f '{{.State.Running}}' temandifa_speech 2>/dev/null | grep -qx true; then
  echo "[C2] ERROR: Container temandifa_speech tidak ditemukan atau tidak berjalan." >&2
  exit 1
fi

# Catat event SEBELUM menghentikan container agar event_time di DB = fault-onset.
echo "[C2] Langkah 1: catat fault_injected lalu hentikan vision worker..."
log_event "{\"scenario\":\"${SCENARIO}\",\"condition\":\"${CONDITION}\",\"run_number\":${RUN},\"event_type\":\"fault_injected\",\"target_service\":\"vision\",\"notes\":\"C2 step1: docker stop vision\"}"
docker stop temandifa_vision

echo "[C2] Menunggu 30 detik sebelum langkah kedua..."
sleep 30

echo "[C2] Langkah 2: catat fault_injected lalu hentikan speech worker..."
log_event "{\"scenario\":\"${SCENARIO}\",\"condition\":\"${CONDITION}\",\"run_number\":${RUN},\"event_type\":\"fault_injected\",\"target_service\":\"speech\",\"notes\":\"C2 step2: docker stop speech\"}"
docker stop temandifa_speech

echo "[C2] Menahan kondisi kaskade selama ${HOLD_SECONDS}s..."
sleep "${HOLD_SECONDS}"

echo "[C2] Fault selesai. Jalankan recovery/start_all.sh untuk memulihkan."

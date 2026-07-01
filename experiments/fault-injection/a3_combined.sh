#!/usr/bin/env bash
set -euo pipefail

SCENARIO=${SCENARIO:-A3}
: "${CONDITION:?Set CONDITION=static_resilience atau treatment}"
RUN=${RUN:-1}
BASE_URL=${BASE_URL:-http://localhost:8080}
ACCESS_TOKEN=${ACCESS_TOKEN:-}
DURATION=${DURATION:-180}

if [[ -z "${ACCESS_TOKEN}" ]]; then
  echo "[A3] ERROR: Set ACCESS_TOKEN sebelum menjalankan eksperimen." >&2
  exit 1
fi

if ! docker inspect -f '{{.State.Running}}' temandifa_vision 2>/dev/null | grep -qx true; then
  echo "[A3] ERROR: Container temandifa_vision tidak ditemukan atau tidak berjalan." >&2
  exit 1
fi
if ! docker inspect -f '{{.State.Running}}' temandifa_speech 2>/dev/null | grep -qx true; then
  echo "[A3] ERROR: Container temandifa_speech tidak ditemukan atau tidak berjalan." >&2
  exit 1
fi
if ! docker exec temandifa_vision command -v stress-ng >/dev/null 2>&1; then
  echo "[A3] ERROR: stress-ng tidak ditemukan di dalam temandifa_vision." >&2
  exit 1
fi
if ! docker exec temandifa_speech command -v stress-ng >/dev/null 2>&1; then
  echo "[A3] ERROR: stress-ng tidak ditemukan di dalam temandifa_speech." >&2
  exit 1
fi

echo "[A3] Mencatat fault event ke backend..."
curl -sf -m 10 -X POST "${BASE_URL}/api/v1/experiments/fault-events" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -d "{\"scenario\":\"${SCENARIO}\",\"condition\":\"${CONDITION}\",\"run_number\":${RUN},\"event_type\":\"fault_injected\",\"target_service\":\"vision+speech\",\"notes\":\"CPU 90% vision + Memory 1024M speech selama ${DURATION}s\"}" \
  || echo "[A3] WARN: Gagal mencatat fault_injected ke backend — eksekusi dilanjutkan." >&2

echo ""
echo "[A3] Memulai CPU pressure pada vision dan memory pressure pada speech..."
docker exec temandifa_vision stress-ng --cpu 1 --cpu-load 90 --timeout "${DURATION}" &
VISION_PID=$!
docker exec temandifa_speech stress-ng --vm 1 --vm-bytes 1024M --timeout "${DURATION}" &
SPEECH_PID=$!

wait "${VISION_PID}" "${SPEECH_PID}"
echo "[A3] Fault selesai."

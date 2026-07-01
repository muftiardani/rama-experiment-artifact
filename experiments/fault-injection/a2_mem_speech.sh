#!/usr/bin/env bash
set -euo pipefail

SCENARIO=${SCENARIO:-A2}
: "${CONDITION:?Set CONDITION=static_resilience atau treatment}"
RUN=${RUN:-1}
BASE_URL=${BASE_URL:-http://localhost:8080}
ACCESS_TOKEN=${ACCESS_TOKEN:-}
DURATION=${DURATION:-180}

if [[ -z "${ACCESS_TOKEN}" ]]; then
  echo "[A2] ERROR: Set ACCESS_TOKEN sebelum menjalankan eksperimen." >&2
  exit 1
fi

if ! docker inspect -f '{{.State.Running}}' temandifa_speech 2>/dev/null | grep -qx true; then
  echo "[A2] ERROR: Container temandifa_speech tidak ditemukan atau tidak berjalan." >&2
  exit 1
fi
if ! docker exec temandifa_speech command -v stress-ng >/dev/null 2>&1; then
  echo "[A2] ERROR: stress-ng tidak ditemukan di dalam temandifa_speech. Gunakan image yang sudah terinstal stress-ng." >&2
  exit 1
fi

echo "[A2] Mencatat fault event ke backend..."
curl -sf -m 10 -X POST "${BASE_URL}/api/v1/experiments/fault-events" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -d "{\"scenario\":\"${SCENARIO}\",\"condition\":\"${CONDITION}\",\"run_number\":${RUN},\"event_type\":\"fault_injected\",\"target_service\":\"speech\",\"notes\":\"Memory pressure 1024M selama ${DURATION}s\"}" \
  || echo "[A2] WARN: Gagal mencatat fault_injected ke backend — eksekusi dilanjutkan." >&2

echo ""
echo "[A2] Menekan memori speech worker selama ${DURATION}s..."
docker exec temandifa_speech stress-ng --vm 1 --vm-bytes 1024M --timeout "${DURATION}"

echo "[A2] Fault selesai."

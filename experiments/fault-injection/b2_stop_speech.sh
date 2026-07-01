#!/usr/bin/env bash
set -euo pipefail

SCENARIO=${SCENARIO:-B2}
: "${CONDITION:?Set CONDITION=static_resilience atau treatment}"
RUN=${RUN:-1}
BASE_URL=${BASE_URL:-http://localhost:8080}
ACCESS_TOKEN=${ACCESS_TOKEN:-}

if [[ -z "${ACCESS_TOKEN}" ]]; then
  echo "[B2] ERROR: Set ACCESS_TOKEN sebelum menjalankan eksperimen." >&2
  exit 1
fi

if ! docker inspect -f '{{.State.Running}}' temandifa_speech 2>/dev/null | grep -qx true; then
  echo "[B2] ERROR: Container temandifa_speech tidak ditemukan atau tidak berjalan. Pastikan stack sudah naik (docker-compose up -d)." >&2
  exit 1
fi

echo "[B2] Mencatat fault event ke backend..."
curl -sf -m 10 -X POST "${BASE_URL}/api/v1/experiments/fault-events" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -d "{\"scenario\":\"${SCENARIO}\",\"condition\":\"${CONDITION}\",\"run_number\":${RUN},\"event_type\":\"fault_injected\",\"target_service\":\"speech\",\"notes\":\"docker stop temandifa_speech\"}" \
  || {
    echo "[B2] WARN: Gagal mencatat fault_injected ke backend — catat manual ke DB jika diperlukan." >&2
    echo "[B2] Payload: scenario=${SCENARIO} condition=${CONDITION} run=${RUN} event_type=fault_injected target_service=speech" >&2
  }

echo "[B2] Menghentikan speech worker..."
docker stop temandifa_speech

echo "[B2] Speech worker dihentikan."

#!/usr/bin/env bash
set -euo pipefail

SCENARIO=${SCENARIO:-B1}
: "${CONDITION:?Set CONDITION=static_resilience atau treatment}"
RUN=${RUN:-1}
BASE_URL=${BASE_URL:-http://localhost:8080}
ACCESS_TOKEN=${ACCESS_TOKEN:-}

if [[ -z "${ACCESS_TOKEN}" ]]; then
  echo "[B1] ERROR: Set ACCESS_TOKEN sebelum menjalankan eksperimen." >&2
  exit 1
fi

if ! docker inspect -f '{{.State.Running}}' temandifa_vision 2>/dev/null | grep -qx true; then
  echo "[B1] ERROR: Container temandifa_vision tidak ditemukan atau tidak berjalan. Pastikan stack sudah naik (docker-compose up -d)." >&2
  exit 1
fi

# Catat event SEBELUM menghentikan container agar event_time di DB = fault-onset,
# bukan post-stop. fault_scheduler.py juga mengikuti urutan ini.
echo "[B1] Mencatat fault event ke backend..."
curl -sf -m 10 -X POST "${BASE_URL}/api/v1/experiments/fault-events" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -d "{\"scenario\":\"${SCENARIO}\",\"condition\":\"${CONDITION}\",\"run_number\":${RUN},\"event_type\":\"fault_injected\",\"target_service\":\"vision\",\"notes\":\"docker stop temandifa_vision\"}" \
  || {
    echo "[B1] WARN: Gagal mencatat fault_injected ke backend — catat manual ke DB jika diperlukan." >&2
    echo "[B1] Payload: scenario=${SCENARIO} condition=${CONDITION} run=${RUN} event_type=fault_injected target_service=vision" >&2
  }

echo "[B1] Menghentikan vision worker..."
docker stop temandifa_vision

echo "[B1] Vision worker dihentikan. Jalankan recovery/start_all.sh untuk memulihkan."

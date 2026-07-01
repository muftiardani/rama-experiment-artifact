#!/usr/bin/env bash
set -euo pipefail

SCENARIO=${SCENARIO:-A1}
: "${CONDITION:?Set CONDITION=static_resilience atau treatment}"
RUN=${RUN:-1}
BASE_URL=${BASE_URL:-http://localhost:8080}
ACCESS_TOKEN=${ACCESS_TOKEN:-}
DURATION=${DURATION:-180}   # detik

if [[ -z "${ACCESS_TOKEN}" ]]; then
  echo "[A1] ERROR: Set ACCESS_TOKEN sebelum menjalankan eksperimen." >&2
  exit 1
fi

if ! docker inspect -f '{{.State.Running}}' temandifa_vision 2>/dev/null | grep -qx true; then
  echo "[A1] ERROR: Container temandifa_vision tidak ditemukan atau tidak berjalan." >&2
  exit 1
fi
if ! docker exec temandifa_vision command -v stress-ng >/dev/null 2>&1; then
  echo "[A1] ERROR: stress-ng tidak ditemukan di dalam temandifa_vision. Gunakan image yang sudah terinstal stress-ng." >&2
  exit 1
fi

echo "[A1] Mencatat fault event ke backend..."
curl -sf -m 10 -X POST "${BASE_URL}/api/v1/experiments/fault-events" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -d "{\"scenario\":\"${SCENARIO}\",\"condition\":\"${CONDITION}\",\"run_number\":${RUN},\"event_type\":\"fault_injected\",\"target_service\":\"vision\",\"notes\":\"CPU 90% selama ${DURATION}s\"}" \
  || echo "[A1] WARN: Gagal mencatat fault_injected ke backend — eksekusi dilanjutkan." >&2

echo ""
echo "[A1] Menekan CPU vision worker selama ${DURATION}s..."
docker exec temandifa_vision stress-ng --cpu 1 --cpu-load 90 --timeout "${DURATION}"

echo "[A1] Fault selesai. Jalankan recovery/start_all.sh jika diperlukan."

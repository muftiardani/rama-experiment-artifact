#!/usr/bin/env bash
# Menguji TFS (Time-to-Fallback Stabilization).
set -euo pipefail

SCENARIO=${SCENARIO:-C1}
: "${CONDITION:?Set CONDITION=static_resilience atau treatment}"
RUN=${RUN:-1}
BASE_URL=${BASE_URL:-http://localhost:8080}
ACCESS_TOKEN=${ACCESS_TOKEN:-}
STEP_DURATION=${STEP_DURATION:-60}   # detik per step

if [[ -z "${ACCESS_TOKEN}" ]]; then
  echo "[C1] ERROR: Set ACCESS_TOKEN sebelum menjalankan eksperimen." >&2
  exit 1
fi

if ! docker inspect -f '{{.State.Running}}' temandifa_speech 2>/dev/null | grep -qx true; then
  echo "[C1] ERROR: Container temandifa_speech tidak ditemukan atau tidak berjalan." >&2
  exit 1
fi
if ! docker exec temandifa_speech command -v stress-ng >/dev/null 2>&1; then
  echo "[C1] ERROR: stress-ng tidak ditemukan di dalam temandifa_speech. Gunakan image yang sudah terinstal stress-ng." >&2
  exit 1
fi

echo "[C1] Mencatat fault event — mulai tekanan bertahap..."
curl -sf -m 10 -X POST "${BASE_URL}/api/v1/experiments/fault-events" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -d "{\"scenario\":\"${SCENARIO}\",\"condition\":\"${CONDITION}\",\"run_number\":${RUN},\"event_type\":\"fault_injected\",\"target_service\":\"speech\",\"notes\":\"Gradual memory: 256M → 512M → 1024M @ ${STEP_DURATION}s per step\"}" \
  || echo "[C1] WARN: Gagal mencatat fault_injected ke backend — eksekusi dilanjutkan." >&2

echo ""
echo "[C1] Langkah 1: memory 256M selama ${STEP_DURATION}s..."
docker exec temandifa_speech stress-ng --vm 1 --vm-bytes 256M --timeout "${STEP_DURATION}" \
  || echo "[C1] WARN: Langkah 1 selesai non-zero (kemungkinan OOM) — lanjut ke langkah 2." >&2

echo "[C1] Langkah 2: memory 512M selama ${STEP_DURATION}s..."
docker exec temandifa_speech stress-ng --vm 1 --vm-bytes 512M --timeout "${STEP_DURATION}" \
  || echo "[C1] WARN: Langkah 2 selesai non-zero (kemungkinan OOM) — lanjut ke langkah 3." >&2

echo "[C1] Langkah 3: memory 1024M selama ${STEP_DURATION}s..."
docker exec temandifa_speech stress-ng --vm 1 --vm-bytes 1024M --timeout "${STEP_DURATION}" \
  || echo "[C1] WARN: Langkah 3 selesai non-zero (kemungkinan OOM) — injeksi selesai." >&2

echo "[C1] Fault selesai. Sistem diharapkan sudah stabilisasi fallback selama tekanan."

#!/usr/bin/env bash
set -euo pipefail

: "${SCENARIO:?Set SCENARIO=A1/A2/A3/B1/B2/B3/C1/C2 sesuai eksperimen yang dipulihkan}"
: "${CONDITION:?Set CONDITION=static_resilience atau treatment}"
RUN=${RUN:-1}
BASE_URL=${BASE_URL:-http://localhost:8080}
ACCESS_TOKEN=${ACCESS_TOKEN:-}

if [[ -z "${ACCESS_TOKEN}" ]]; then
  echo "[RECOVERY] ERROR: Set ACCESS_TOKEN sebelum menjalankan recovery." >&2
  exit 1
fi

log_event() {
  # best-effort: kegagalan log tidak boleh menghentikan proses recovery fisik.
  curl -sf -m 10 -X POST "${BASE_URL}/api/v1/experiments/fault-events" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${ACCESS_TOKEN}" \
    -d "$1" \
    || echo "[RECOVERY] WARN: Gagal mencatat event ke backend — lanjut recovery." >&2
}

start_or_running() {
  local container="$1"
  if docker inspect -f '{{.State.Running}}' "${container}" 2>/dev/null | grep -qx true; then
    echo "[RECOVERY] ${container} sudah berjalan."
    return 0
  fi
  # Kegagalan docker start tidak membatalkan script; health check akan mendeteksi kondisi ini.
  if docker start "${container}" >/dev/null; then
    echo "[RECOVERY] ${container} start command dikirim."
  else
    echo "[RECOVERY] WARN: Gagal memulai ${container} — health check akan gagal." >&2
  fi
}

# Catat recovery_started SEBELUM memanggil docker start agar event selalu tercatat
# meski docker start gagal. Semantik: "inisiasi recovery dimulai pada timestamp ini."
echo "[RECOVERY] Mencatat event recovery_started..."
log_event "{\"scenario\":\"${SCENARIO}\",\"condition\":\"${CONDITION}\",\"run_number\":${RUN},\"event_type\":\"recovery_started\",\"target_service\":\"all\",\"notes\":\"start_all.sh invoked\"}"

echo "[RECOVERY] Memulai kembali semua worker..."
start_or_running temandifa_vision || true
start_or_running temandifa_speech || true
start_or_running temandifa_ocr || true

# Tunggu sebentar sebelum polling — model loading (Whisper/YOLO) butuh waktu setelah
# container start; curl pertama yang langsung dieksekusi pasti gagal dan membuang budget.
sleep 10
echo "[RECOVERY] Menunggu worker siap (maks 90 detik)..."
deadline=$((SECONDS + 90))
all_healthy=false
while [[ $SECONDS -lt $deadline ]]; do
  health=$(curl -sf -m 5 "${BASE_URL}/api/v1/health" 2>/dev/null || true)
  if echo "${health}" | grep -qE '"status"[[:space:]]*:[[:space:]]*"HEALTHY"'; then
    all_healthy=true
    break
  fi
  sleep 5
done

if [[ "${all_healthy}" == "true" ]]; then
  echo "[RECOVERY] Backend melaporkan HEALTHY."
  echo "[RECOVERY] Mencatat event recovered..."
  log_event "{\"scenario\":\"${SCENARIO}\",\"condition\":\"${CONDITION}\",\"run_number\":${RUN},\"event_type\":\"recovered\",\"target_service\":\"all\",\"notes\":\"Semua worker di-restart\"}"
else
  echo "[RECOVERY] WARNING: Backend belum melaporkan HEALTHY setelah 90 detik." >&2
  echo "[RECOVERY] WARNING: Event 'recovered' TIDAK dicatat karena sistem belum HEALTHY." >&2
fi

echo "[RECOVERY] Selesai."

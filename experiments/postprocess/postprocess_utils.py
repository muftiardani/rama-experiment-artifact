"""
postprocess_utils.py — Konstanta dan helper bersama untuk pipeline postprocessing.

Definisi di satu tempat memastikan TFS dan TTR dihitung dengan metodologi identik.
Ubah nilai di sini; perubahan langsung berlaku untuk compute_tfs.py dan compute_ttr.py.
"""
import os
from datetime import datetime
from typing import Callable, List, Optional

STABILITY_WINDOW = 5

# Jeda maksimum (detik) antar dua respons sukses berurutan sebelum streak di-reset.
# Harus > (p95_latency + sleep_per_vu) / active_vu agar tidak memicu false-reset
# saat traffic rendah. Kalibrasi VPS: 5 VU, p95 ≈ 39s, sleep 1s → gap maks ≈ 40s.
# Nilai 90s memberi buffer 2× dan sejajar dengan batas tunggu health-check recovery.
STABILITY_MAX_GAP_SECONDS = 90


def parse_dt(s):
    if not s:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S%z",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            pass
    return None


def ensure_parent(path: str) -> None:
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)


def fill_na_rows(
    results: list,
    req_by_key: dict,
    computed_keys: set,
    blank_ts_fields: List[str],
    metric_na_field: str,
    count_field: str,
) -> None:
    """Tambah baris N/A ke results untuk key yang ada di req_by_key tapi tidak di computed_keys.

    Dipakai oleh compute_tfs.py dan compute_ttr.py agar format baris N/A tetap sinkron.
    """
    for key in sorted(set(req_by_key.keys()) - computed_keys):
        scenario, condition, run = key
        row: dict = {"scenario": scenario, "condition": condition, "run_number": run}
        for f in blank_ts_fields:
            row[f] = ""
        row[metric_na_field] = "N/A"
        row[count_field] = len(req_by_key[key])
        results.append(row)


def find_stabilization_point(
    rows: List[dict],
    success_fn: Callable[[dict], bool],
) -> Optional[datetime]:
    """Cari titik pertama saat STABILITY_WINDOW request berturut-turut memenuhi success_fn.

    rows harus sudah diurutkan berdasarkan '_ts' (datetime) ascending; setiap dict
    harus memiliki kunci '_ts' (datetime hasil parse_dt, bukan string mentah).

    Return: datetime stabilisasi atau None jika tidak tercapai dalam rows.
    """
    streak = 0
    last_success_ts = None
    for r in rows:
        curr_ts = r["_ts"]
        if success_fn(r):
            if (last_success_ts is not None
                    and (curr_ts - last_success_ts).total_seconds() > STABILITY_MAX_GAP_SECONDS):
                streak = 0
            streak += 1
            last_success_ts = curr_ts
            if streak >= STABILITY_WINDOW:
                return curr_ts
        else:
            streak = 0
            last_success_ts = None
    return None

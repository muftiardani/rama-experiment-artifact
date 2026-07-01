"""
compute_tfs.py — Hitung Time-to-Fallback Stabilization (TFS).

TFS = waktu dari fault_injected pertama hingga sistem secara konsisten
      menghasilkan partial/full response (bukan failure) selama window tertentu.

Algoritma:
1. Ambil timestamp fault_injected dari fault_events.
2. Ambil request_logs setelah fault.
3. Cari titik pertama di mana STABILITY_WINDOW request berturut-turut
   adalah partial atau full.
4. TFS = (timestamp stabilisasi - timestamp fault) dalam detik.

Penggunaan:
    python experiments/postprocess/compute_tfs.py \
        --requests experiments/data/processed/all_request_logs.csv \
        --faults experiments/data/processed/all_fault_events.csv \
        --out experiments/data/processed/tfs_summary.csv
"""

import argparse
import collections
import csv

from postprocess_utils import (
    STABILITY_WINDOW,
    ensure_parent,
    fill_na_rows,
    find_stabilization_point,
    parse_dt,
)

FIELDNAMES = [
    "scenario",
    "condition",
    "run_number",
    "fault_injected_at",
    "stabilized_at",
    "tfs_seconds",
    "requests_after_fault",
]


def compute(requests_path, faults_path, out_path):
    with open(requests_path, newline="", encoding="utf-8-sig") as f:
        req_rows = list(csv.DictReader(f))
    with open(faults_path, newline="", encoding="utf-8-sig") as f:
        fault_rows = list(csv.DictReader(f))

    # Pre-compute timestamps sekali untuk setiap request row — hindari parse_dt berulang
    # saat filter, sort, dan streak loop.
    for r in req_rows:
        r["_ts"] = parse_dt(r.get("created_at"))

    # Kelompokkan request rows by (scenario, condition, run_number) untuk lookup O(1)
    req_by_key: dict = collections.defaultdict(list)
    for r in req_rows:
        if r.get("scenario") and r.get("condition") and r.get("run_number"):
            req_by_key[(r["scenario"], r["condition"], r["run_number"])].append(r)

    faults = {}
    for row in fault_rows:
        if row.get("event_type") == "fault_injected":
            key = (row["scenario"], row["condition"], row["run_number"])
            dt = parse_dt(row.get("event_time"))
            if dt and (key not in faults or dt < faults[key]):
                faults[key] = dt

    all_run_keys = set(req_by_key.keys())

    results = []
    for (scenario, condition, run), fault_time in sorted(faults.items()):
        key = (scenario, condition, run)
        after = sorted(
            (r for r in req_by_key.get(key, []) if r["_ts"] is not None and r["_ts"] >= fault_time),
            key=lambda r: r["_ts"],
        )

        stabilized_at = find_stabilization_point(
            after,
            lambda r: r.get("response_category") in ("full", "partial"),
        )

        tfs_seconds = round((stabilized_at - fault_time).total_seconds(), 2) if stabilized_at else None
        if stabilized_at:
            streak_window = [r for r in after if r["_ts"] <= stabilized_at][-STABILITY_WINDOW:]
            if not any(r.get("response_category") == "full" for r in streak_window):
                print(f"[WARN] {scenario}/{condition}/run-{run}: TFS tercapai hanya dari respons 'partial' "
                      f"— tidak ada 'full' dalam window stabilisasi. "
                      f"Periksa TTR; jika TTR=N/A, sistem mungkin permanently degraded.")
        results.append({
            "scenario": scenario,
            "condition": condition,
            "run_number": run,
            "fault_injected_at": fault_time.isoformat(),
            "stabilized_at": stabilized_at.isoformat() if stabilized_at else "",
            "tfs_seconds": tfs_seconds if tfs_seconds is not None else "N/A",
            "requests_after_fault": len(after),
        })

    # Tulis baris N/A untuk run yang muncul di req_rows tapi tidak punya fault_injected event
    # (mencakup skenario SS dan run fault yang event-nya gagal direkam).
    computed_keys = {(r["scenario"], r["condition"], r["run_number"]) for r in results}
    fill_na_rows(results, req_by_key, computed_keys,
                 blank_ts_fields=["fault_injected_at", "stabilized_at"],
                 metric_na_field="tfs_seconds", count_field="requests_after_fault")

    ensure_parent(out_path)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)

    print(f"TFS summary ({len(results)} grup) -> {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", default="experiments/data/processed/all_request_logs.csv")
    parser.add_argument("--faults", default="experiments/data/processed/all_fault_events.csv")
    parser.add_argument("--out", default="experiments/data/processed/tfs_summary.csv")
    args = parser.parse_args()
    compute(args.requests, args.faults, args.out)


if __name__ == "__main__":
    main()

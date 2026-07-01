"""
compute_ttr.py — Hitung Time-to-Recovery (TTR).

TTR = waktu dari recovery_started hingga sistem menghasilkan full response
      secara konsisten (tanpa fallback aktif) selama window tertentu.

Penggunaan:
    python experiments/postprocess/compute_ttr.py \
        --requests experiments/data/processed/all_request_logs.csv \
        --faults experiments/data/processed/all_fault_events.csv \
        --out experiments/data/processed/ttr_summary.csv
"""

import argparse
import collections
import csv

from postprocess_utils import ensure_parent, fill_na_rows, find_stabilization_point, parse_dt

FIELDNAMES = [
    "scenario",
    "condition",
    "run_number",
    "recovery_started_at",
    "recovered_at",
    "ttr_seconds",
    "requests_after_recovery",
]


def compute(requests_path, faults_path, out_path):
    with open(requests_path, newline="", encoding="utf-8-sig") as f:
        req_rows = list(csv.DictReader(f))
    with open(faults_path, newline="", encoding="utf-8-sig") as f:
        fault_rows = list(csv.DictReader(f))

    for r in req_rows:
        r["_ts"] = parse_dt(r.get("created_at"))

    # Kelompokkan request rows by (scenario, condition, run_number) untuk lookup O(1).
    req_by_key: dict = collections.defaultdict(list)
    for r in req_rows:
        if r.get("scenario") and r.get("condition") and r.get("run_number"):
            req_by_key[(r["scenario"], r["condition"], r["run_number"])].append(r)

    # Pilih recovery_started target="all" (dicatat oleh recovery.py).
    # Dalam kondisi normal tiap run memiliki tepat 1 event; jika lebih dari 1
    # (mis. operator manual re-run start_all.sh), ambil yang PERTAMA (min) karena
    # TTR diukur dari inisiasi recovery pertama — lebih konservatif dan akurat.
    grouped = {}
    for row in fault_rows:
        if row.get("event_type") == "recovery_started":
            key = (row["scenario"], row["condition"], row["run_number"])
            dt = parse_dt(row.get("event_time"))
            if dt:
                grouped.setdefault(key, []).append((dt, row.get("target_service", "")))

    recoveries = {}
    for key, events in grouped.items():
        all_events = [dt for dt, target in events if target == "all"]
        if all_events:
            if len(all_events) > 1:
                print(f"[WARN] {key}: {len(all_events)} event recovery_started/target=all ditemukan — "
                      f"TTR dihitung dari yang pertama (paling awal).")
            recoveries[key] = min(all_events)
        else:
            # Tidak ada event target='all' — kemungkinan data lama sebelum recovery.py
            # diubah ke target='all'. TTR mungkin sedikit berbeda karena baseline per-service
            # bisa berbeda dari event 'all'. Verifikasi manual disarankan.
            print(f"[WARN] {key}: tidak ada event recovery_started/target='all'. "
                  f"TTR dihitung dari event per-service (kemungkinan data lama).")
            recoveries[key] = min(dt for dt, _ in events)

    results = []
    for (scenario, condition, run), recovery_time in sorted(recoveries.items()):
        key = (scenario, condition, run)
        after = sorted(
            (r for r in req_by_key.get(key, []) if r["_ts"] is not None and r["_ts"] >= recovery_time),
            key=lambda r: r["_ts"],
        )

        recovered_at = find_stabilization_point(
            after,
            lambda r: (
                r.get("response_category") == "full"
                and r.get("fallback_active", "false").lower() != "true"
            ),
        )

        ttr_seconds = round((recovered_at - recovery_time).total_seconds(), 2) if recovered_at else None
        results.append({
            "scenario": scenario,
            "condition": condition,
            "run_number": run,
            "recovery_started_at": recovery_time.isoformat(),
            "recovered_at": recovered_at.isoformat() if recovered_at else "",
            "ttr_seconds": ttr_seconds if ttr_seconds is not None else "N/A",
            "requests_after_recovery": len(after),
        })

    # Tulis baris N/A untuk run yang ada di req_rows tapi tidak punya recovery_started event
    # (mencakup kondisi SS dan run di mana start_all.sh tidak pernah dijalankan).
    # Konsisten dengan compute_tfs.py agar JOIN antara kedua CSV tidak kehilangan baris.
    computed_keys = set(recoveries.keys())
    fill_na_rows(results, req_by_key, computed_keys,
                 blank_ts_fields=["recovery_started_at", "recovered_at"],
                 metric_na_field="ttr_seconds", count_field="requests_after_recovery")

    ensure_parent(out_path)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)

    print(f"TTR summary ({len(results)} grup) -> {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", default="experiments/data/processed/all_request_logs.csv")
    parser.add_argument("--faults", default="experiments/data/processed/all_fault_events.csv")
    parser.add_argument("--out", default="experiments/data/processed/ttr_summary.csv")
    args = parser.parse_args()
    compute(args.requests, args.faults, args.out)


if __name__ == "__main__":
    main()

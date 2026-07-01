"""
compute_response_category.py — Rekap jumlah dan proporsi full/partial/failure.

Penggunaan:
    python experiments/postprocess/compute_response_category.py \
        --input experiments/data/processed/all_request_logs.csv \
        --out experiments/data/processed/response_category_summary.csv
"""

import argparse
import csv
import os

FIELDNAMES = [
    "scenario",
    "condition",
    "run_number",
    "total",
    "full",
    "partial",
    "failure",
    "other",
    "full_pct",
    "partial_pct",
    "failure_pct",
]


def compute(input_path, out_path):
    rows = []
    with open(input_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    groups = {}
    for row in rows:
        key = (row.get("scenario", ""), row.get("condition", ""), row.get("run_number", ""))
        cat = row.get("response_category", "unknown")
        g = groups.setdefault(key, {"full": 0, "partial": 0, "failure": 0, "other": 0})
        if cat in g:
            g[cat] += 1
        else:
            g["other"] += 1

    results = []
    for (scenario, condition, run), counts in sorted(groups.items()):
        total = sum(counts.values())
        results.append({
            "scenario": scenario,
            "condition": condition,
            "run_number": run,
            "total": total,
            "full": counts["full"],
            "partial": counts["partial"],
            "failure": counts["failure"],
            "other": counts["other"],
            "full_pct": round(counts["full"] / total * 100, 2) if total else 0,
            "partial_pct": round(counts["partial"] / total * 100, 2) if total else 0,
            "failure_pct": round(counts["failure"] / total * 100, 2) if total else 0,
        })

    os.makedirs(os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)

    print(f"Response category summary ({len(results)} grup) -> {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="experiments/data/processed/all_request_logs.csv")
    parser.add_argument("--out", default="experiments/data/processed/response_category_summary.csv")
    args = parser.parse_args()
    compute(args.input, args.out)


if __name__ == "__main__":
    main()

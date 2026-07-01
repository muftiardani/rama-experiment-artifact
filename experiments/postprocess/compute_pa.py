"""
compute_pa.py — Hitung Partial Availability (PA).

PA = (full + partial) / total

Nilai PA = 1.0 berarti semua request menghasilkan setidaknya hasil parsial.
PA = 0.0 berarti seluruh request gagal total.

Penggunaan:
    python experiments/postprocess/compute_pa.py \
        --input experiments/data/processed/response_category_summary.csv \
        --out experiments/data/processed/partial_availability_summary.csv
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
    "partial_availability",
    "partial_availability_pct",
    "error_rate_percent",
]


def compute(input_path, out_path):
    rows = []
    with open(input_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    results = []
    for row in rows:
        total = int(row.get("total", 0))
        full = int(row.get("full", 0))
        partial = int(row.get("partial", 0))
        pa = round((full + partial) / total, 4) if total > 0 else 0.0
        failure = int(row.get("failure", 0))
        results.append({
            "scenario": row["scenario"],
            "condition": row["condition"],
            "run_number": row["run_number"],
            "total": total,
            "full": full,
            "partial": partial,
            "failure": failure,
            "partial_availability": pa,
            "partial_availability_pct": round(pa * 100, 2),
            "error_rate_percent": round((failure / total) * 100, 2) if total > 0 else 0.0,
        })

    os.makedirs(os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)

    print(f"Partial Availability summary ({len(results)} grup) -> {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="experiments/data/processed/response_category_summary.csv")
    parser.add_argument("--out", default="experiments/data/processed/partial_availability_summary.csv")
    args = parser.parse_args()
    compute(args.input, args.out)


if __name__ == "__main__":
    main()

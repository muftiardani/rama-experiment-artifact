"""
compute_latency.py — Hitung mean, median, p95, p99, dan IQR latency dari request_logs.

Penggunaan:
    python experiments/postprocess/compute_latency.py \
        --input experiments/data/processed/all_request_logs.csv \
        --out experiments/data/processed/latency_summary.csv
"""

import argparse
import csv
import statistics
import os

FIELDNAMES = [
    "scenario",
    "condition",
    "run_number",
    "n",
    "mean_ms",
    "median_ms",
    "p95_ms",
    "p99_ms",
    "iqr_ms",
    "min_ms",
    "max_ms",
]


def percentile(data, p):
    if not data:
        return None
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p / 100
    f, c = int(k), int(k) + 1
    if c >= len(sorted_data):
        return sorted_data[-1]
    return sorted_data[f] + (sorted_data[c] - sorted_data[f]) * (k - f)


def compute(input_path, out_path):
    rows = []
    with open(input_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Kelompokkan berdasarkan run. SLO memakai latency run-level, bukan subset kategori respons.
    groups = {}
    for row in rows:
        key = (row.get("scenario", ""), row.get("condition", ""), row.get("run_number", ""))
        try:
            latency = float(row["latency_ms"])
        except (ValueError, KeyError):
            continue
        groups.setdefault(key, []).append(latency)

    results = []
    for (scenario, condition, run), latencies in sorted(groups.items()):
        n = len(latencies)
        results.append({
            "scenario": scenario,
            "condition": condition,
            "run_number": run,
            "n": n,
            "mean_ms": round(statistics.mean(latencies), 2),
            "median_ms": round(statistics.median(latencies), 2),
            "p95_ms": round(percentile(latencies, 95), 2),
            "p99_ms": round(percentile(latencies, 99), 2),
            "iqr_ms": round(percentile(latencies, 75) - percentile(latencies, 25), 2),
            "min_ms": round(min(latencies), 2),
            "max_ms": round(max(latencies), 2),
        })

    os.makedirs(os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)

    print(f"Latency summary ({len(results)} grup) -> {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="experiments/data/processed/all_request_logs.csv")
    parser.add_argument("--out", default="experiments/data/processed/latency_summary.csv")
    args = parser.parse_args()
    compute(args.input, args.out)


if __name__ == "__main__":
    main()

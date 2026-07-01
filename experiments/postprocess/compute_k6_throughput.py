"""
compute_k6_throughput.py — Hitung throughput (req/s) dari output k6.

Membaca dua format:
1. k6 summary-export JSON (--summary-export=k6_summary.json) — diutamakan
2. k6 stream JSON (--out json=k6_result.json) — fallback

Penggunaan:
    python experiments/postprocess/compute_k6_throughput.py \
        --raw-dir experiments/data/raw \
        --out experiments/data/processed/throughput_summary.csv

Struktur raw-dir yang diharapkan:
    raw/<scenario>/<condition>/run<n>/k6_summary.json   (utama, automated)
    raw/<scenario>/<condition>/run<n>/k6_result.json    (fallback, automated)
    raw/<scenario>/<condition>/run-<n>/k6_summary.json  (legacy manual, didukung)
"""

import argparse
import csv
import json
import os

FIELDNAMES = [
    "scenario",
    "condition",
    "run_number",
    "throughput_rps",
    "total_requests",
    "source",
]


def read_summary_export(path):
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)
    http_reqs = data.get("metrics", {}).get("http_reqs", {})
    if not http_reqs:
        http_reqs = data.get("http_reqs", {})
    rate = http_reqs.get("values", {}).get("rate") or http_reqs.get("rate")
    count = http_reqs.get("values", {}).get("count") or http_reqs.get("count")
    return rate, count


def read_stream_json(path):
    times = []
    count = 0
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "Point" and obj.get("metric") == "http_reqs":
                count += obj.get("data", {}).get("value", 0)
                t = obj.get("data", {}).get("time", "")
                if t:
                    times.append(t)
    if len(times) < 2:
        return None, count
    from datetime import datetime, timezone

    def parse_t(s):
        s = s.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return None

    first = parse_t(min(times))
    last = parse_t(max(times))
    if first and last and last > first:
        duration = (last - first).total_seconds()
        rate = count / duration if duration > 0 else 0
        return round(rate, 4), int(count)
    return None, int(count)


def scan_raw_dir(raw_dir):
    results = []
    for scenario in os.listdir(raw_dir):
        scenario_dir = os.path.join(raw_dir, scenario)
        if not os.path.isdir(scenario_dir):
            continue
        for condition in os.listdir(scenario_dir):
            cond_dir = os.path.join(scenario_dir, condition)
            if not os.path.isdir(cond_dir):
                continue
            for run_dir in os.listdir(cond_dir):
                run_path = os.path.join(cond_dir, run_dir)
                if not os.path.isdir(run_path):
                    continue
                # Support both "run1" (automated) and "run-1" (legacy manual)
                run_num = run_dir.removeprefix("run-").removeprefix("run")
                if not run_num.isdigit():
                    continue

                # Support both underscore (automated) and dash (legacy) filenames
                summary_path = os.path.join(run_path, "k6_summary.json")
                if not os.path.exists(summary_path):
                    summary_path = os.path.join(run_path, "k6-summary.json")
                stream_path = os.path.join(run_path, "k6_result.json")
                if not os.path.exists(stream_path):
                    stream_path = os.path.join(run_path, "k6-result.json")

                rate, count = None, None
                source = None

                if os.path.exists(summary_path):
                    try:
                        rate, count = read_summary_export(summary_path)
                        source = "summary-export"
                    except Exception as e:
                        print(f"[WARN] Gagal baca {summary_path}: {e}")

                if rate is None and os.path.exists(stream_path):
                    try:
                        rate, count = read_stream_json(stream_path)
                        source = "stream-json"
                    except Exception as e:
                        print(f"[WARN] Gagal baca {stream_path}: {e}")

                results.append({
                    "scenario": scenario,
                    "condition": condition,
                    "run_number": run_num,
                    "throughput_rps": round(rate, 4) if rate is not None else "N/A",
                    "total_requests": int(count) if count is not None else "N/A",
                    "source": source or "not_found",
                })

    return sorted(results, key=lambda r: (r["scenario"], r["condition"], r["run_number"]))


def compute(raw_dir, out_path):
    os.makedirs(os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True)

    if not os.path.exists(raw_dir):
        print(f"[WARN] {raw_dir} tidak ada - throughput tidak dihitung.")
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()
        return []

    results = scan_raw_dir(raw_dir)
    if not results:
        print("[WARN] Tidak ada data k6 ditemukan di raw_dir.")
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()
        return []

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)

    print(f"Throughput summary ({len(results)} run) -> {out_path}")
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="experiments/data/raw")
    parser.add_argument("--out", default="experiments/data/processed/throughput_summary.csv")
    args = parser.parse_args()
    compute(args.raw_dir, args.out)


if __name__ == "__main__":
    main()

"""
compute_slo_violation.py — Hitung SLO Violation Score.

SLO yang didefinisikan:
    - P95 latency <= 10.000 ms (steady state) / 30.000 ms (fault scenarios)
    - Error rate (failure_pct) <= 20% (SS) / 50% (fault)
    - Partial Availability >= 0.80 (treatment only)

SLO Violation Score = sum(V_i) / n_checks  (aproksimasi per-run)

    V_i (lower-is-better) = max(0, (M_actual - M_SLO) / M_SLO)
    V_i (higher-is-better) = max(0, (M_SLO - M_actual) / M_SLO)

Hasilnya adalah normalized score dalam [0, +∞):
    0.0  = tidak ada pelanggaran SLO
    >0   = semakin tinggi semakin besar pelanggaran

Penggunaan:
    python experiments/postprocess/compute_slo_violation.py \
        --latency experiments/data/processed/latency_summary.csv \
        --category experiments/data/processed/response_category_summary.csv \
        --pa experiments/data/processed/partial_availability_summary.csv \
        --out experiments/data/processed/slo_violation_summary.csv
"""

import argparse
import csv
import os

SLO_P95_SS = 10_000   # ms
SLO_P95_FAULT = 30_000
SLO_ERROR_RATE_SS = 20.0   # persen
SLO_ERROR_RATE_FAULT = 50.0
SLO_PA_TREATMENT = 0.80

STEADY_STATE_SCENARIOS = {"SS"}
FIELDNAMES = [
    "scenario",
    "condition",
    "run_number",
    "slo_violation_score",
    "violation_details",
    "p95_ms",
    "failure_pct",
]


def is_fault_scenario(scenario):
    return scenario not in STEADY_STATE_SCENARIOS


def load_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def compute(latency_path, category_path, pa_path, out_path):
    latency_rows = {(r["scenario"], r["condition"], r["run_number"]): r for r in load_csv(latency_path)}
    cat_rows = {(r["scenario"], r["condition"], r["run_number"]): r for r in load_csv(category_path)}
    pa_rows = {(r["scenario"], r["condition"], r["run_number"]): r for r in load_csv(pa_path)}

    all_keys = set(latency_rows) | set(cat_rows) | set(pa_rows)
    results = []

    for key in sorted(all_keys):
        scenario, condition, run = key
        fault = is_fault_scenario(scenario)
        violations = []

        vi_list = []
        violation_labels = []

        # SLO 1: P95 latency (lower is better)
        lat = latency_rows.get(key)
        p95 = float(lat["p95_ms"]) if lat and lat.get("p95_ms") else None
        slo_p95 = SLO_P95_FAULT if fault else SLO_P95_SS
        if p95 is not None:
            v_p95 = max(0.0, (p95 - slo_p95) / slo_p95)
            vi_list.append(v_p95)
            if v_p95 > 0:
                violation_labels.append(f"p95_latency>{slo_p95}ms(actual={p95}ms)")
        else:
            vi_list.append(0.0)

        # SLO 2: Error rate (lower is better)
        cat = cat_rows.get(key)
        err_pct = float(cat["failure_pct"]) if cat and cat.get("failure_pct") else None
        slo_err = SLO_ERROR_RATE_FAULT if fault else SLO_ERROR_RATE_SS
        if err_pct is not None:
            v_err = max(0.0, (err_pct - slo_err) / slo_err)
            vi_list.append(v_err)
            if v_err > 0:
                violation_labels.append(f"error_rate>{slo_err}%(actual={err_pct}%)")
        else:
            vi_list.append(0.0)

        # SLO 3: PA hanya untuk treatment (higher is better)
        if condition == "treatment":
            pa = pa_rows.get(key)
            pa_val = float(pa["partial_availability"]) if pa and pa.get("partial_availability") else None
            if pa_val is not None:
                v_pa = max(0.0, (SLO_PA_TREATMENT - pa_val) / SLO_PA_TREATMENT)
                vi_list.append(v_pa)
                if v_pa > 0:
                    violation_labels.append(f"PA<{SLO_PA_TREATMENT}(actual={pa_val})")
            else:
                vi_list.append(0.0)

        slo_score = round(sum(vi_list) / len(vi_list), 4) if vi_list else 0.0

        results.append({
            "scenario": scenario,
            "condition": condition,
            "run_number": run,
            "slo_violation_score": slo_score,
            "violation_details": "; ".join(violation_labels) if violation_labels else "none",
            "p95_ms": p95 if p95 is not None else "N/A",
            "failure_pct": err_pct if err_pct is not None else "N/A",
        })

    os.makedirs(os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(results)

    print(f"SLO Violation summary ({len(results)} grup) -> {out_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--latency", default="experiments/data/processed/latency_summary.csv")
    parser.add_argument("--category", default="experiments/data/processed/response_category_summary.csv")
    parser.add_argument("--pa", default="experiments/data/processed/partial_availability_summary.csv")
    parser.add_argument("--out", default="experiments/data/processed/slo_violation_summary.csv")
    args = parser.parse_args()
    compute(args.latency, args.category, args.pa, args.out)


if __name__ == "__main__":
    main()

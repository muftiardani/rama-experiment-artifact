"""statistical_analyzer.py -- Analisis statistik static_resilience vs treatment per skenario.

Wilcoxon signed-rank test (paired), matched-pairs rank-biserial correlation,
Holm-Bonferroni multiple testing correction.
"""

import csv
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rich.console import Console
from rich.table import Table

console = Console()

FINAL_SUMMARY = Path("experiments/results/final_summary.csv")
QUARANTINE_JSON = Path("experiments/reports/advanced/quarantine_report.json")
REPORT_MD = Path("experiments/reports/advanced/statistical_analysis_report.md")
STATS_CSV = Path("experiments/reports/advanced/statistical_summary.csv")
COMPARISON_CSV = Path("experiments/reports/advanced/baseline_treatment_comparison.csv")
STATISTICAL_TESTS_CSV = Path("experiments/results/statistical_tests.csv")
PAIRED_SUMMARY_CSV = Path("experiments/results/paired_summary.csv")

METRICS = [
    ("p95_ms",                   "p95 latency (ms)",         "lower"),
    ("p99_ms",                   "p99 latency (ms)",         "lower"),
    ("throughput_rps",           "Throughput (rps)",          "higher"),
    ("partial_availability_pct", "Partial Availability (%)", "higher"),
    ("tfs_seconds",              "TFS (s)",                   "lower"),
    ("ttr_seconds",              "TTR (s)",                   "lower"),
    ("slo_violation_score",      "SLO Violation Score",       "lower"),
]

ALL_SCENARIOS = ["SS", "A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2"]


def _read_summary() -> List[dict]:
    if not FINAL_SUMMARY.exists():
        return []
    with FINAL_SUMMARY.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _excluded_keys() -> set:
    if not QUARANTINE_JSON.exists():
        return set()
    try:
        data = json.loads(QUARANTINE_JSON.read_text(encoding="utf-8"))
        return {
            (r["scenario"], r["condition"], str(r["run"]))
            for r in data if r.get("review_status") == "EXCLUDED"
        }
    except Exception:
        return set()


def _vals(rows: List[dict], field: str) -> List[float]:
    out = []
    for r in rows:
        v = r.get(field, "")
        try:
            out.append(float(v))
        except (ValueError, TypeError):
            pass
    return out


def _stats(values: List[float]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "median": None, "std": None, "min": None, "max": None, "iqr": None}
    import statistics
    s = sorted(values)
    n = len(s)
    mean = sum(s) / n
    median = statistics.median(s)
    std = statistics.stdev(s) if n >= 2 else 0.0
    if n >= 4:
        q = statistics.quantiles(s, n=4)
        q1, q3 = q[0], q[2]
    else:
        q1, q3 = s[0], s[-1]
    return {
        "n": n, "mean": round(mean, 3), "median": round(median, 3),
        "std": round(std, 3), "min": round(s[0], 3), "max": round(s[-1], 3),
        "iqr": round(q3 - q1, 3),
    }


def _relative_change(sr: Optional[float], tr: Optional[float], direction: str) -> dict:
    if sr is None or tr is None or sr == 0:
        return {"pct": None, "improved": None, "label": "N/A"}
    pct = round((tr - sr) / abs(sr) * 100, 1)
    improved = (pct < 0 if direction == "lower" else pct > 0)
    return {"pct": pct, "improved": improved, "label": f"{'+' if pct >= 0 else ''}{pct}%"}


def _paired_rb_correlation(diffs: List[float]) -> Optional[float]:
    """Matched-pairs rank-biserial correlation (signed) dari list selisih (treatment - sr)."""
    nonzero = [d for d in diffs if d != 0]
    n = len(nonzero)
    if n == 0:
        return 0.0

    sorted_idx = sorted(range(n), key=lambda i: abs(nonzero[i]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and abs(nonzero[sorted_idx[j]]) == abs(nonzero[sorted_idx[i]]):
            j += 1
        rank_avg = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[sorted_idx[k]] = rank_avg
        i = j

    w_plus = sum(ranks[i] for i in range(n) if nonzero[i] > 0)
    w_minus = sum(ranks[i] for i in range(n) if nonzero[i] < 0)
    total = w_plus + w_minus
    if total == 0:
        return 0.0
    return round((w_plus - w_minus) / total, 4)


def _wilcoxon_test(sr_vals: List[float], tr_vals: List[float], direction: str = "lower") -> dict:
    """Paired Wilcoxon signed-rank test + matched-pairs rank-biserial correlation.

    direction: "lower" → hipotesis treatment < baseline (latensi, TFS, TTR, SLO lebih kecil lebih baik)
               "higher" → hipotesis treatment > baseline (throughput, PA lebih besar lebih baik)

    Menggunakan uji satu-sisi sesuai arah hipotesis penelitian untuk memaksimalkan power.
    diffs = treatment - static_resilience; "lower" berarti diffs negatif → alternative="less".
    """
    n_pairs = len(sr_vals)
    base = {"n_pairs": n_pairs, "w_stat": None, "p_value": None, "effect_size_r": None}

    if n_pairs < 5 or n_pairs != len(tr_vals):
        return base

    diffs = [t - s for t, s in zip(tr_vals, sr_vals)]
    nonzero_diffs = [d for d in diffs if d != 0]
    if len(nonzero_diffs) < 2:
        return base

    alternative = "less" if direction == "lower" else "greater"

    try:
        from scipy.stats import wilcoxon as _wilcoxon
        stat, pval = _wilcoxon(diffs, zero_method="wilcox", alternative=alternative)
    except ImportError:
        console.print("[yellow]scipy tidak tersedia — Wilcoxon test dilewati[/yellow]")
        return base
    except Exception as e:
        console.print(f"[yellow]Wilcoxon error: {e}[/yellow]")
        return base

    r_rb = _paired_rb_correlation(diffs)

    return {
        "n_pairs": n_pairs,
        "w_stat": round(float(stat), 3),
        "p_value": round(float(pval), 6),
        "effect_size_r": r_rb,
    }


def _mann_whitney_test(sr_vals: List[float], tr_vals: List[float]) -> dict:
    """Mann-Whitney U test — fallback jika pairing tidak valid (n_pairs < 5).

    Rank-biserial correlation: r = 1 - 2U / (n1 * n2).
    """
    base = {"n_sr": len(sr_vals), "n_tr": len(tr_vals), "u_stat": None, "p_value": None, "effect_size_r": None}
    if len(sr_vals) < 2 or len(tr_vals) < 2:
        return base
    try:
        from scipy.stats import mannwhitneyu
        stat, pval = mannwhitneyu(sr_vals, tr_vals, alternative="two-sided")
        n1, n2 = len(sr_vals), len(tr_vals)
        u = float(stat)
        r_rb = round(1 - 2 * u / (n1 * n2), 4) if n1 * n2 > 0 else None
        base["u_stat"] = round(u, 3)
        base["p_value"] = round(float(pval), 6)
        base["effect_size_r"] = r_rb
    except ImportError:
        console.print("[yellow]scipy tidak tersedia — Mann-Whitney U test dilewati[/yellow]")
    except Exception as e:
        console.print(f"[yellow]Mann-Whitney U error: {e}[/yellow]")
    return base


def _holm_bonferroni(
    pvalues: List[Optional[float]], alpha: float = 0.05
) -> Tuple[List[bool], List[Optional[float]]]:
    """Holm-Bonferroni step-down correction untuk multiple testing.

    Returns (rejected: list[bool], adjusted_pvalues: list[Optional[float]]).
    """
    m = len(pvalues)
    if m == 0:
        return [], []

    valid = [(i, p) for i, p in enumerate(pvalues) if p is not None]
    sorted_valid = sorted(valid, key=lambda x: x[1])

    adjusted: List[Optional[float]] = [None] * m
    rejected = [False] * m

    prev_adj = 0.0
    for rank, (orig_idx, p) in enumerate(sorted_valid):
        adj = min(1.0, (m - rank) * p)
        adj = max(adj, prev_adj)
        adjusted[orig_idx] = round(adj, 6)
        prev_adj = adj

    for i in range(m):
        if adjusted[i] is not None and adjusted[i] <= alpha:
            rejected[i] = True

    return rejected, adjusted


def analyze() -> dict:
    rows = _read_summary()
    if not rows:
        console.print("[red]final_summary.csv not found -- run postprocess first[/red]")
        return {}

    excluded = _excluded_keys()
    rows = [r for r in rows
            if (r.get("scenario"), r.get("condition"), str(r.get("run_number", r.get("run", "")))) not in excluded]

    results = {}
    test_records: List[dict] = []
    comparisons: List[dict] = []

    for scenario in ALL_SCENARIOS:
        sr_by_run = {r.get("run_number"): r for r in rows
                     if r.get("scenario") == scenario and r.get("condition") == "static_resilience"}
        tr_by_run = {r.get("run_number"): r for r in rows
                     if r.get("scenario") == scenario and r.get("condition") == "treatment"}

        if not sr_by_run and not tr_by_run:
            continue

        common_runs = sorted(
            set(sr_by_run.keys()) & set(tr_by_run.keys()),
            key=lambda x: int(x) if str(x).isdigit() else 0,
        )

        results[scenario] = {}
        for field_key, label, direction in METRICS:
            sr_all = _vals(list(sr_by_run.values()), field_key)
            tr_all = _vals(list(tr_by_run.values()), field_key)

            sr_paired, tr_paired = [], []
            for rn in common_runs:
                try:
                    sr_paired.append(float(sr_by_run[rn].get(field_key, "")))
                    tr_paired.append(float(tr_by_run[rn].get(field_key, "")))
                except (ValueError, TypeError):
                    pass

            sr_stats = _stats(sr_all)
            tr_stats = _stats(tr_all)
            change = _relative_change(sr_stats["median"], tr_stats["median"], direction)
            test_result = _wilcoxon_test(sr_paired, tr_paired, direction=direction)

            test_method = "wilcoxon"
            u_stat = None
            if test_result["n_pairs"] < 5:
                mw = _mann_whitney_test(sr_all, tr_all)
                test_method = "mann_whitney"
                test_result["p_value"] = mw.get("p_value")
                test_result["effect_size_r"] = mw.get("effect_size_r")
                # w_stat tidak berlaku untuk Mann-Whitney; kosongkan agar laporan tidak
                # menampilkan nilai Wilcoxon di sebelah p-value Mann-Whitney
                test_result["w_stat"] = None
                u_stat = mw.get("u_stat")

            results[scenario][field_key] = {
                "label": label,
                "direction": direction,
                "static_resilience": sr_stats,
                "treatment": tr_stats,
                "relative_change": change,
                "wilcoxon": test_result,
            }

            test_records.append({
                "scenario": scenario,
                "metric": field_key,
                "metric_label": label,
                "direction": direction,
                "test_method": test_method,
                "n_pairs": test_result["n_pairs"],
                "w_stat": test_result.get("w_stat"),
                "u_stat": u_stat,
                "p_value": test_result.get("p_value"),
                "effect_size_r": test_result.get("effect_size_r"),
                "sr_median": sr_stats["median"],
                "tr_median": tr_stats["median"],
                "relative_change_pct": change["pct"],
                "improved": change["improved"],
            })

            comparisons.append({
                "scenario": scenario,
                "metric": label,
                "static_resilience_median": sr_stats["median"],
                "treatment_median": tr_stats["median"],
                "static_resilience_std": sr_stats["std"],
                "treatment_std": tr_stats["std"],
                "relative_change_pct": change["pct"],
                "improved": change["improved"],
                "direction": direction,
            })

    pvalues = [r.get("p_value") for r in test_records]
    rejected, adj_pvalues = _holm_bonferroni(pvalues)
    for i, rec in enumerate(test_records):
        rec["p_adj_holm"] = adj_pvalues[i]
        rec["significant"] = rejected[i]
        sc, metric = rec["scenario"], rec["metric"]
        if sc in results and metric in results[sc]:
            results[sc][metric]["wilcoxon"]["significant"] = rejected[i]

    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    PAIRED_SUMMARY_CSV.parent.mkdir(parents=True, exist_ok=True)

    _write_report(results, test_records)
    _write_comparison_csv(comparisons)
    _write_stats_csv(results)
    _write_statistical_tests_csv(test_records)
    _write_paired_summary(rows)

    return results


def _write_report(results: dict, test_records: List[dict]) -> None:
    lines = [
        "# Statistical Analysis Report\n\n",
        "> Analisis inferensial menggunakan Wilcoxon signed-rank test (paired) dengan\n"
        "> Holm-Bonferroni multiple testing correction. α = 0.05.\n\n",
        "## Perbandingan Static Resilience Baseline vs RAMA Treatment\n\n",
        "| Scenario | Metric | SRB Median | TR Median | Change | W | p-value | p_adj | Sig | r_rb |\n",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|\n",
    ]

    test_idx = 0
    for sc, metrics in results.items():
        for field_key, data in metrics.items():
            sr_med = data["static_resilience"]["median"]
            tr_med = data["treatment"]["median"]
            change = data["relative_change"]
            w_data = data.get("wilcoxon", {})
            imp = "YES" if change.get("improved") else ("NO" if change.get("improved") is False else "-")

            if test_idx < len(test_records):
                rec = test_records[test_idx]
                w_str = str(rec.get("w_stat") or "-")
                p_str = str(rec.get("p_value") or "-")
                p_adj_str = str(rec.get("p_adj_holm") or "-")
                sig_str = "✓" if rec.get("significant") else "-"
                r_str = str(rec.get("effect_size_r") or "-")
                test_idx += 1
            else:
                w_str = p_str = p_adj_str = sig_str = r_str = "-"

            lines.append(
                f"| {sc} | {data['label']} "
                f"| {sr_med if sr_med is not None else '-'} "
                f"| {tr_med if tr_med is not None else '-'} "
                f"| {change['label']} | {w_str} | {p_str} | {p_adj_str} | {sig_str} | {r_str} |\n"
            )

    lines.append("\n## Detail per Skenario\n\n")
    for sc, metrics in results.items():
        lines.append(f"### {sc}\n\n")
        lines.append("| Metric | SRB mean | SRB median | SRB std | TR mean | TR median | TR std | W | p-value | r_rb |\n")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for field_key, data in metrics.items():
            sr = data["static_resilience"]
            tr = data["treatment"]
            w_data = data.get("wilcoxon", {})
            lines.append(
                f"| {data['label']} "
                f"| {sr['mean'] or '-'} | {sr['median'] or '-'} | {sr['std'] or '-'} "
                f"| {tr['mean'] or '-'} | {tr['median'] or '-'} | {tr['std'] or '-'} "
                f"| {w_data.get('w_stat') or '-'} "
                f"| {w_data.get('p_value') or '-'} "
                f"| {w_data.get('effect_size_r') or '-'} |\n"
            )
        lines.append("\n")

    REPORT_MD.write_text("".join(lines), encoding="utf-8")
    console.print(f"[green]Statistical report -> {REPORT_MD}[/green]")


def _write_comparison_csv(comparisons: List[dict]) -> None:
    if not comparisons:
        return
    with COMPARISON_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(comparisons[0].keys()))
        writer.writeheader()
        writer.writerows(comparisons)
    console.print(f"[dim]Comparison CSV -> {COMPARISON_CSV}[/dim]")


def _write_stats_csv(results: dict) -> None:
    rows = []
    for sc, metrics in results.items():
        for field_key, data in metrics.items():
            for cond, stats in [("static_resilience", data["static_resilience"]), ("treatment", data["treatment"])]:
                rows.append({
                    "scenario": sc, "condition": cond, "metric": field_key,
                    **{k: v for k, v in stats.items()},
                })
    if not rows:
        return
    with STATS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    console.print(f"[dim]Stats CSV -> {STATS_CSV}[/dim]")


def _write_statistical_tests_csv(test_records: List[dict]) -> None:
    if not test_records:
        return
    STATISTICAL_TESTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with STATISTICAL_TESTS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(test_records[0].keys()))
        writer.writeheader()
        writer.writerows(test_records)
    console.print(f"[green]Statistical tests CSV -> {STATISTICAL_TESTS_CSV}[/green]")


def _write_paired_summary(rows: List[dict]) -> None:
    """Tulis paired_summary.csv dengan kolom nama eksak sesuai spesifikasi."""
    sr_index = {(r.get("scenario"), r.get("run_number")): r
                for r in rows if r.get("condition") == "static_resilience"}
    tr_index = {(r.get("scenario"), r.get("run_number")): r
                for r in rows if r.get("condition") == "treatment"}

    def _flt(row: dict, field: str) -> Optional[float]:
        try:
            return float(row.get(field, ""))
        except (ValueError, TypeError):
            return None

    def _error_rate(row: dict) -> Optional[float]:
        try:
            total = int(row.get("total", 0) or row.get("total_requests", 0) or 0)
            failure = int(row.get("failure", 0) or row.get("failure_count", 0) or 0)
            return round(failure / total * 100, 4) if total > 0 else 0.0
        except (ValueError, TypeError):
            return None

    def _delta(a: Optional[float], b: Optional[float]) -> str:
        return "" if (a is None or b is None) else str(round(b - a, 4))

    def _delta_pct(a: Optional[float], b: Optional[float]) -> str:
        if a is None or b is None or a == 0:
            return ""
        return str(round((b - a) / abs(a) * 100, 2))

    paired_rows = []
    for key in sorted(set(sr_index.keys()) | set(tr_index.keys())):
        scenario, run_num = key
        sr = sr_index.get(key, {})
        tr = tr_index.get(key, {})

        sr_p95 = _flt(sr, "p95_ms")
        tr_p95 = _flt(tr, "p95_ms")
        sr_err = _error_rate(sr)
        tr_err = _error_rate(tr)
        sr_pa = _flt(sr, "partial_availability_pct") or _flt(sr, "partial_availability_percent")
        tr_pa = _flt(tr, "partial_availability_pct") or _flt(tr, "partial_availability_percent")
        sr_tfs = _flt(sr, "tfs_seconds")
        tr_tfs = _flt(tr, "tfs_seconds")
        sr_ttr = _flt(sr, "ttr_seconds")
        tr_ttr = _flt(tr, "ttr_seconds")
        sr_slo = _flt(sr, "slo_violation_score") or _flt(sr, "slo_violations")
        tr_slo = _flt(tr, "slo_violation_score") or _flt(tr, "slo_violations")

        paired_rows.append({
            "scenario": scenario,
            "run_number": run_num,
            "pair_id": f"{scenario}-{run_num}",
            "static_p95_ms": "" if sr_p95 is None else sr_p95,
            "treatment_p95_ms": "" if tr_p95 is None else tr_p95,
            "delta_p95_ms": _delta(sr_p95, tr_p95),
            "delta_p95_percent": _delta_pct(sr_p95, tr_p95),
            "static_error_rate_percent": "" if sr_err is None else sr_err,
            "treatment_error_rate_percent": "" if tr_err is None else tr_err,
            "delta_error_rate_pp": _delta(sr_err, tr_err),
            "static_pa_percent": "" if sr_pa is None else sr_pa,
            "treatment_pa_percent": "" if tr_pa is None else tr_pa,
            "delta_pa_pp": _delta(sr_pa, tr_pa),
            "static_tfs_seconds": "" if sr_tfs is None else sr_tfs,
            "treatment_tfs_seconds": "" if tr_tfs is None else tr_tfs,
            "delta_tfs_seconds": _delta(sr_tfs, tr_tfs),
            "static_ttr_seconds": "" if sr_ttr is None else sr_ttr,
            "treatment_ttr_seconds": "" if tr_ttr is None else tr_ttr,
            "delta_ttr_seconds": _delta(sr_ttr, tr_ttr),
            "static_slo_score": "" if sr_slo is None else sr_slo,
            "treatment_slo_score": "" if tr_slo is None else tr_slo,
            "delta_slo_score": _delta(sr_slo, tr_slo),
        })

    if not paired_rows:
        return

    PAIRED_SUMMARY_CSV.parent.mkdir(parents=True, exist_ok=True)
    with PAIRED_SUMMARY_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(paired_rows[0].keys()))
        writer.writeheader()
        writer.writerows(paired_rows)
    console.print(f"[green]Paired summary -> {PAIRED_SUMMARY_CSV}[/green]")


def print_summary(results: dict) -> None:
    table = Table(title="Statistical Summary (Static Resilience Baseline vs RAMA Treatment)", show_lines=False)
    table.add_column("Scenario")
    table.add_column("Metric")
    table.add_column("SRB Median", justify="right")
    table.add_column("TR Median", justify="right")
    table.add_column("Change")
    table.add_column("Better")
    table.add_column("p-value", justify="right")
    table.add_column("Sig")
    for sc, metrics in results.items():
        for field_key, data in metrics.items():
            change = data["relative_change"]
            imp = change.get("improved")
            color = "green" if imp else ("red" if imp is False else "dim")
            w_data = data.get("wilcoxon", {})
            pval = w_data.get("p_value")
            sig = "*" if w_data.get("significant") else "-"
            table.add_row(
                sc, data["label"],
                str(data["static_resilience"]["median"] or "-"),
                str(data["treatment"]["median"] or "-"),
                f"[{color}]{change['label']}[/{color}]",
                "[green]YES[/green]" if imp else ("[red]NO[/red]" if imp is False else "-"),
                str(round(pval, 4)) if pval is not None else "-",
                sig,
            )
    console.print(table)

import csv
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.table import Table

from .config import Context
from .utils.paths import run_dir as _run_dir

console = Console()

INVALID_RUNS_JSON = Path("experiments/reports/invalid_runs.json")
INVALID_RUNS_MD = Path("experiments/reports/invalid_runs.md")
FINAL_SUMMARY_VALIDITY = Path("experiments/data/summary/final_summary_with_validity.csv")
FINAL_SUMMARY = Path("experiments/results/final_summary.csv")

ALL_SCENARIOS = ["SS", "A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2"]
ALL_CONDITIONS = ["static_resilience", "treatment"]
NO_FAULT = {"SS"}
RECOVERY_SCEN = {"B1", "B2", "B3", "C1", "C2"}
CASCADE_SCEN = {"C1", "C2"}


@dataclass
class InvalidationResult:
    scenario: str
    condition: str
    run: int
    valid: bool = True
    invalid_codes: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    retryable: bool = False


def _read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


_ALL_FAULT_EVENTS_CACHE: Optional[List[dict]] = None


def _read_fault_events_for_run(d: Path, scenario: str, condition: str, run: int) -> List[dict]:
    per_run = d / "db_fault_events.csv"
    if per_run.exists():
        return _read_csv(per_run)
    # Fallback: filter dari all_fault_events.csv (tersedia setelah postprocess)
    global _ALL_FAULT_EVENTS_CACHE
    all_path = Path("experiments/data/processed/all_fault_events.csv")
    if not all_path.exists():
        return []
    if _ALL_FAULT_EVENTS_CACHE is None:
        _ALL_FAULT_EVENTS_CACHE = _read_csv(all_path)
    return [
        e for e in _ALL_FAULT_EVENTS_CACHE
        if e.get("scenario") == scenario
        and e.get("condition") == condition
        and str(e.get("run_number")) == str(run)
    ]


def _validate_run(scenario: str, condition: str, run: int) -> InvalidationResult:
    d = _run_dir(scenario, condition, run)
    result = InvalidationResult(scenario, condition, run)

    def flag(code: str, reason: str, retryable: bool = False):
        result.valid = False
        result.invalid_codes.append(code)
        result.reasons.append(reason)
        if retryable:
            result.retryable = True

    k6_env = _read_json(d / "k6_environment.json")
    if k6_env:
        if k6_env.get("run_on_vps") is True:
            flag("INVALID_K6_LOCATION", "k6 run_on_vps=true -- load generator berjalan di VPS")
    # Absence of k6_environment.json is not itself invalid (may not have run yet)

    k6_summary = _read_json(d / "k6_summary.json")
    k6_stdout = _read_text(d / "k6_stdout.log")
    k6_stderr = _read_text(d / "k6_stderr.log")

    if k6_summary is None and (d / "k6_stdout.log").exists():
        flag("INVALID_K6_FAILED", "k6_summary.json tidak ada meskipun k6 dijalankan", retryable=True)

    if k6_summary:
        http_reqs = k6_summary.get("metrics", {}).get("http_reqs", {})
        count = http_reqs.get("count", http_reqs.get("values", {}).get("count", 0))
        if isinstance(count, dict):
            count = count.get("count", 0)
        if int(count or 0) < 10:
            flag("INVALID_LOW_REQUEST_COUNT", f"Hanya {count} request -- terlalu sedikit")

    request_logs = _read_csv(d / "db_request_logs.csv")
    if any(str(r.get("status_code", "")) == "429" for r in request_logs):
        flag("INVALID_RATE_LIMITED", "Ada request dengan status 429 -- rate limiter aktif", retryable=True)

    if any(str(r.get("status_code", "")) in ("401", "403") for r in request_logs):
        flag("INVALID_AUTH_ERROR", "Ada 401/403 -- token expired atau tidak valid", retryable=True)

    latency_vals = [r.get("latency_ms", "") for r in request_logs]
    non_empty = [v for v in latency_vals if v not in ("", None, "0")]
    if request_logs and not non_empty:
        flag("INVALID_EMPTY_LATENCY", "latency_ms kosong di semua request_logs")

    fault_events = _read_fault_events_for_run(d, scenario, condition, run)
    event_types = {e.get("event_type", "") for e in fault_events}

    if scenario not in NO_FAULT:
        if "fault_injected" not in event_types:
            flag("INVALID_MISSING_FAULT_EVENT", f"Skenario {scenario} tidak punya event fault_injected", retryable=True)

        if scenario in RECOVERY_SCEN:
            if "recovery_started" not in event_types:
                flag("INVALID_MISSING_RECOVERY_EVENT", "Tidak ada event recovery_started", retryable=True)
            if "recovered" not in event_types:
                flag("INVALID_RECOVERY_FAILED", "Tidak ada event recovered -- recovery gagal", retryable=True)

        if scenario in CASCADE_SCEN:
            stage_evts = [e for e in fault_events if "stage" in e.get("event_type", "")]
            if not stage_evts:
                flag("INVALID_MISSING_FAULT_EVENT", f"Skenario cascade {scenario} tidak punya stage events", retryable=True)

    for log_file in ["speech.log", "vision.log", "ocr.log", "backend.log"]:
        text = _read_text(d / log_file)
        if "OOMKilled" in text or "out of memory" in text.lower():
            flag("INVALID_OOM", f"OOM terdeteksi di {log_file}", retryable=True)
            break

    oom_text = _read_text(d / "snapshot_after" / "oom_check.txt")
    if oom_text and "killed process" in oom_text.lower():
        flag("INVALID_OOM", "OOM terdeteksi di dmesg/oom_check.txt", retryable=True)

    # DB precheck snapshot — cari per-run dulu, fallback ke path global (bisa stale antar-sesi)
    _db_precheck_per_run = d / "db_precheck.json"
    _db_precheck_global = Path("experiments/evidence/db") / "db-precheck.json"
    if _db_precheck_per_run.exists():
        db_precheck = _read_json(_db_precheck_per_run)
    else:
        db_precheck = _read_json(_db_precheck_global)
    if db_precheck:
        if db_precheck.get("oom_killed"):
            flag("INVALID_DB_OOM", "PostgreSQL OOMKilled=true pada precheck sebelum run", retryable=True)
        if (db_precheck.get("restart_count") or 0) > 0:
            flag("INVALID_DB_RESTART",
                 f"PostgreSQL RestartCount={db_precheck['restart_count']} sebelum run", retryable=True)

    snapshots_file = Path("experiments/evidence/db") / "db-runtime-snapshots.jsonl"
    if snapshots_file.exists():
        run_snapshots = []
        for line in snapshots_file.read_text(encoding="utf-8").splitlines():
            try:
                s = json.loads(line)
                if (str(s.get("scenario")) == scenario
                        and str(s.get("condition")) == condition
                        and str(s.get("run_number")) == str(run)):
                    run_snapshots.append(s)
            except Exception:
                pass

        if run_snapshots:
            if any(s.get("oom_killed") for s in run_snapshots):
                flag("INVALID_DB_OOM", "PostgreSQL OOMKilled=true selama run (runtime monitor)", retryable=True)

            restart_values = [s.get("restart_count", 0) for s in run_snapshots
                              if s.get("restart_count") is not None]
            if len(restart_values) >= 2 and restart_values[-1] > restart_values[0]:
                flag("INVALID_DB_RESTART",
                     f"PostgreSQL RestartCount naik {restart_values[0]}->{restart_values[-1]} selama run",
                     retryable=True)

            mem_pcts = [s.get("postgres_memory_percent", -1) for s in run_snapshots]
            saturated = [p for p in mem_pcts if isinstance(p, (int, float)) and p >= 99.0]
            if len(saturated) >= max(2, len(run_snapshots) // 2):
                flag("INVALID_DB_MEMORY_PRESSURE",
                     f"PostgreSQL ≥99% memory pada {len(saturated)}/{len(run_snapshots)} snapshot",
                     retryable=True)

            conn_values = [s.get("connection_count", 0) for s in run_snapshots]
            valid_conn = [c for c in conn_values if isinstance(c, int) and c > 0]
            if len(valid_conn) >= 2 and valid_conn[-1] > valid_conn[0] * 2:
                flag("INVALID_DB_CONNECTION_LEAK",
                     f"Connection count naik {valid_conn[0]}->{valid_conn[-1]} selama run",
                     retryable=True)

            if any(isinstance(s.get("idle_in_transaction_count"), int)
                   and s["idle_in_transaction_count"] > 0 for s in run_snapshots):
                flag("INVALID_DB_CONNECTION_LEAK", "Idle in transaction terdeteksi selama run", retryable=True)

    probe = _read_json(d / "network_probe_before.json")
    if probe:
        loss = probe.get("packet_loss_percent", 0)
        if loss > 5:
            flag("INVALID_NETWORK_UNSTABLE", f"Packet loss {loss}% > 5% sebelum run", retryable=True)

    if request_logs:
        for r in request_logs[:5]:
            if r.get("scenario") and r["scenario"] != scenario:
                flag("INVALID_SCENARIO_MISMATCH",
                     f"DB scenario={r['scenario']} != manifest scenario={scenario}")
                break

    backend_log = _read_text(d / "backend.log")
    if 'X-Cache: HIT' in backend_log:
        flag("INVALID_CACHE_CONTAMINATED", "Cache hit ditemukan di log backend -- ENABLE_AI_CACHE_EXPERIMENT mungkin true")

    prom_file = d / "prometheus_response_total.json"
    if prom_file.exists():
        prom_data = _read_json(prom_file)
        if prom_data and prom_data.get("status") != "success":
            flag("INVALID_PROMETHEUS_MISSING", "Prometheus query gagal", retryable=True)

    return result


validate_run = _validate_run


def validate_all(
    scenarios: List[str] = None,
    conditions: List[str] = None,
    runs: List[int] = None,
) -> List[InvalidationResult]:
    global _ALL_FAULT_EVENTS_CACHE
    _ALL_FAULT_EVENTS_CACHE = None
    scenarios = scenarios or ALL_SCENARIOS
    conditions = conditions or ALL_CONDITIONS
    runs = runs or list(range(1, 11))
    return [_validate_run(sc, cond, r) for sc in scenarios for cond in conditions for r in runs]


def write_reports(results: List[InvalidationResult]) -> None:
    INVALID_RUNS_JSON.parent.mkdir(parents=True, exist_ok=True)

    data = []
    for r in results:
        data.append({
            "scenario": r.scenario,
            "condition": r.condition,
            "run": r.run,
            "valid": r.valid,
            "invalid_codes": r.invalid_codes,
            "reasons": r.reasons,
            "retryable": r.retryable,
        })
    INVALID_RUNS_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")

    lines = ["# Invalid Runs Report\n\n",
             "| Scenario | Condition | Run | Valid | Codes | Retryable |\n",
             "|---|---|---:|---|---|---|\n"]
    for r in results:
        codes = ", ".join(r.invalid_codes) if r.invalid_codes else "-"
        lines.append(f"| {r.scenario} | {r.condition} | {r.run} "
                     f"| {'YES' if r.valid else 'NO'} | {codes} "
                     f"| {'yes' if r.retryable else '-'} |\n")
    INVALID_RUNS_MD.write_text("".join(lines), encoding="utf-8")

    if FINAL_SUMMARY.exists():
        validity_map = {(r.scenario, r.condition, str(r.run)): r for r in results}
        rows = _read_csv(FINAL_SUMMARY)
        FINAL_SUMMARY_VALIDITY.parent.mkdir(parents=True, exist_ok=True)
        with FINAL_SUMMARY_VALIDITY.open("w", newline="", encoding="utf-8") as f:
            if rows:
                fieldnames = list(rows[0].keys()) + ["valid", "invalid_codes"]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    run_val = str(row.get("run_number", row.get("run", "")))
                    key = (row.get("scenario", ""), row.get("condition", ""), run_val)
                    vr = validity_map.get(key)
                    row["valid"] = vr.valid if vr else True
                    row["invalid_codes"] = "|".join(vr.invalid_codes) if vr else ""
                    writer.writerow(row)

    console.print(f"[dim]Invalid runs report -> {INVALID_RUNS_JSON}[/dim]")


def print_results(results: List[InvalidationResult]) -> None:
    table = Table(title="Invalidation Results", show_lines=True)
    table.add_column("Scenario")
    table.add_column("Condition")
    table.add_column("Run", justify="right")
    table.add_column("Valid")
    table.add_column("Codes")
    table.add_column("Retry")
    for r in results:
        color = "green" if r.valid else "red"
        codes = "\n".join(r.invalid_codes) if r.invalid_codes else "-"
        table.add_row(r.scenario, r.condition, str(r.run),
                      f"[{color}]{'YES' if r.valid else 'NO'}[/{color}]",
                      codes, "yes" if r.retryable else "-")
    console.print(table)
    valid_n = sum(1 for r in results if r.valid)
    console.print(f"\nTotal: {len(results)} | Valid: {valid_n} | Invalid: {len(results)-valid_n}")

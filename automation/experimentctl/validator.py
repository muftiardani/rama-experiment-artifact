import csv
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.table import Table

console = Console()

FINAL_SUMMARY = Path("experiments/results/final_summary.csv")
REPORT_PATH = Path("experiments/reports/validation_report.md")
REPORT_JSON = Path("experiments/reports/validation_report.json")

ALL_SCENARIOS = ["SS", "A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2"]
ALL_CONDITIONS = ["static_resilience", "treatment"]
RUNS_PER = 10

EXPECTED_K6_MAX_VU = 5
EXPECTED_REQUEST_TIMEOUT_SECONDS = 90
VALID_LOADGEN_LOCATIONS = {"vps-loadgen", "external_vps", "external"}

NO_FAULT_SCENARIOS = {"SS"}
RECOVERY_SCENARIOS = {"B1", "B2", "B3", "C1", "C2"}
CASCADE_SCENARIOS = {"C1", "C2"}


@dataclass
class RunValidation:
    scenario: str
    condition: str
    run: int
    status: str = "VALID"
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "VALID"


def _read_final_summary() -> List[dict]:
    if not FINAL_SUMMARY.exists():
        return []
    with FINAL_SUMMARY.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


_ALL_FAULT_EVENTS_CACHE: Optional[List[dict]] = None


_RAW_DIR = Path("experiments/data/raw")

def _read_fault_events(scenario: str, condition: str, run: int) -> List[dict]:
    # Only probe per-run file if raw/ directory exists — skips 160 ENOENT syscalls
    # when raw/ has been deleted after postprocess.
    if _RAW_DIR.exists():
        per_run = _RAW_DIR / scenario / condition / f"run{run}" / "db_fault_events.csv"
        if per_run.exists():
            with per_run.open(newline="", encoding="utf-8") as f:
                return list(csv.DictReader(f))
    # Fallback: filter dari all_fault_events.csv (tersedia setelah postprocess)
    global _ALL_FAULT_EVENTS_CACHE
    all_path = Path("experiments/data/processed/all_fault_events.csv")
    if not all_path.exists():
        return []
    if _ALL_FAULT_EVENTS_CACHE is None:
        with all_path.open(newline="", encoding="utf-8") as f:
            _ALL_FAULT_EVENTS_CACHE = list(csv.DictReader(f))
    return [
        e for e in _ALL_FAULT_EVENTS_CACHE
        if e.get("scenario") == scenario
        and e.get("condition") == condition
        and str(e.get("run_number")) == str(run)
    ]


def _read_k6_env(scenario: str, condition: str, run: int) -> Optional[dict]:
    p = Path(f"experiments/data/raw/{scenario}/{condition}/run{run}/k6_environment.json")
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def validate_all(scenarios=None, conditions=None, runs=None) -> List[RunValidation]:
    scenarios = scenarios or ALL_SCENARIOS
    conditions = conditions or ALL_CONDITIONS
    runs = runs or list(range(1, RUNS_PER + 1))

    summary_rows = {
        (r["scenario"], r["condition"], str(r["run_number"])): r
        for r in _read_final_summary()
        if r.get("scenario") and r.get("condition") and r.get("run_number")
    }

    results: List[RunValidation] = []

    for sc in scenarios:
        for cond in conditions:
            for run in runs:
                v = _validate_run(sc, cond, run, summary_rows)
                results.append(v)

    return results


def _validate_run(
    scenario: str, condition: str, run: int, summary_rows: dict
) -> RunValidation:
    key = (scenario, condition, str(run))
    v = RunValidation(scenario, condition, run)

    row = summary_rows.get(key)
    if row is None:
        v.status = "MISSING"
        v.reason = "no data in final_summary.csv"
        return v

    if row.get("request_timeout_seconds"):
        try:
            if int(row["request_timeout_seconds"]) != EXPECTED_REQUEST_TIMEOUT_SECONDS:
                v.status = "INVALID"
                v.reason = "INVALID_TIMEOUT_CONFIG"
                return v
        except (ValueError, TypeError):
            pass

    if row.get("k6_max_vu"):
        try:
            if int(row["k6_max_vu"]) != EXPECTED_K6_MAX_VU:
                v.status = "INVALID"
                v.reason = "INVALID_K6_VU"
                return v
        except (ValueError, TypeError):
            pass

    if row.get("load_generator_location"):
        loc = row["load_generator_location"].strip().lower()
        if loc in {"target_vps", "same_host_as_target", "localhost", "local"}:
            v.status = "INVALID"
            v.reason = "INVALID_LOADGEN_LOCATION"
            return v

    if not row.get("p95_ms"):
        v.status = "INVALID"
        v.reason = "p95_ms missing"
        return v

    # SRB tidak menghasilkan partial response — kondisi ini mustahil kecuali ada bug
    if condition == "static_resilience":
        try:
            partial_count = int(row.get("partial_count", 0))
            if partial_count > 0:
                v.status = "INVALID"
                v.reason = "INVALID_STATIC_BASELINE_PARTIAL"
                return v
        except (ValueError, TypeError):
            pass

    # Legacy check: k6_environment.json masih ada di raw/ jika raw/ belum dihapus
    k6_env = _read_k6_env(scenario, condition, run)
    if k6_env:
        if k6_env.get("run_on_vps") is True:
            v.status = "INVALID"
            v.reason = "INVALID_LOADGEN_LOCATION"
            return v
        if k6_env.get("k6_max_vu") and int(k6_env["k6_max_vu"]) != EXPECTED_K6_MAX_VU:
            v.status = "INVALID"
            v.reason = "INVALID_K6_VU"
            return v

    if scenario not in NO_FAULT_SCENARIOS:
        fault_events = _read_fault_events(scenario, condition, run)
        event_types = {e.get("event_type") for e in fault_events}

        if "fault_injected" not in event_types:
            v.status = "INVALID"
            v.reason = "missing fault_injected event"
            return v

        if scenario in RECOVERY_SCENARIOS:
            if "recovery_started" not in event_types:
                v.status = "INVALID"
                v.reason = "missing recovery_started event"
                return v
            if "recovered" not in event_types:
                v.status = "INVALID"
                v.reason = "missing recovered event"
                return v

        if scenario in CASCADE_SCENARIOS:
            stage_events = [e for e in fault_events if "stage" in e.get("event_type", "")]
            if not stage_events:
                v.status = "INVALID"
                v.reason = "missing stage events for cascade scenario"
                return v

    log_path = Path(f"experiments/data/raw/{scenario}/{condition}/run{run}/speech.log")
    if log_path.exists():
        log_text = log_path.read_text(encoding="utf-8", errors="ignore")
        if "OOMKilled" in log_text or "out of memory" in log_text.lower():
            v.status = "INVALID"
            v.reason = "OOM detected in speech worker"
            return v

    v.status = "VALID"
    return v


def check_pairing(results: List[RunValidation]) -> List[dict]:
    """Cek pasangan run. pair_status = 'unpaired' jika salah satu kondisi missing/invalid."""
    valid_by_key: dict = {}
    conditions_seen: set = set()
    for r in results:
        key = (r.scenario, r.run)
        if key not in valid_by_key:
            valid_by_key[key] = {}
        valid_by_key[key][r.condition] = r.ok
        conditions_seen.add(r.condition)

    pairs = []
    for (scenario, run), cond_status in sorted(valid_by_key.items()):
        sr_valid = cond_status.get("static_resilience", False) if "static_resilience" in conditions_seen else None
        tr_valid = cond_status.get("treatment", False) if "treatment" in conditions_seen else None
        both_evaluated = sr_valid is not None and tr_valid is not None
        if both_evaluated and sr_valid and tr_valid:
            pair_status = "paired"
        elif both_evaluated and (sr_valid or tr_valid):
            pair_status = "unpaired"
        elif both_evaluated:
            pair_status = "both_invalid"
        else:
            pair_status = "partial_evaluation"
        pairs.append({
            "pair_id": f"{scenario}-{run}",
            "scenario": scenario,
            "run": run,
            "static_resilience_valid": sr_valid,
            "treatment_valid": tr_valid,
            "pair_status": pair_status,
        })
    return pairs


def write_report(results: List[RunValidation]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    pairs = check_pairing(results)
    n_paired = sum(1 for p in pairs if p["pair_status"] == "paired")
    n_unpaired = sum(1 for p in pairs if p["pair_status"] == "unpaired")

    lines = ["# Validation Report\n\n",
             f"Pasangan valid (paired): {n_paired} | Tidak berpasangan (unpaired): {n_unpaired}\n\n",
             "| Scenario | Condition | Run | Status | Reason |\n",
             "|---|---|---:|---|---|\n"]
    for r in results:
        lines.append(f"| {r.scenario} | {r.condition} | {r.run} | {r.status} | {r.reason or '-'} |\n")

    lines.append("\n## Pairing Status\n\n")
    lines.append("| pair_id | SR Valid | TR Valid | pair_status |\n")
    lines.append("|---|---|---|---|\n")
    for p in pairs:
        lines.append(
            f"| {p['pair_id']} | {'✓' if p['static_resilience_valid'] else '✗'} "
            f"| {'✓' if p['treatment_valid'] else '✗'} | {p['pair_status']} |\n"
        )

    REPORT_PATH.write_text("".join(lines), encoding="utf-8")

    data = [{"scenario": r.scenario, "condition": r.condition, "run": r.run,
             "status": r.status, "reason": r.reason} for r in results]
    REPORT_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")

    console.print(f"[dim]Validation report -> {REPORT_PATH}[/dim]")


def print_results(results: List[RunValidation]) -> None:
    table = Table(title="Validation Results", show_lines=True)
    table.add_column("Scenario")
    table.add_column("Condition")
    table.add_column("Run", justify="right")
    table.add_column("Status")
    table.add_column("Reason")

    for r in results:
        color = {"VALID": "green", "INVALID": "red", "MISSING": "yellow"}.get(r.status, "white")
        table.add_row(r.scenario, r.condition, str(r.run),
                      f"[{color}]{r.status}[/{color}]", r.reason or "-")
    console.print(table)

    valid = sum(1 for r in results if r.ok)
    console.print(f"\nTotal: {len(results)} | Valid: {valid} | Invalid: {len(results)-valid}")

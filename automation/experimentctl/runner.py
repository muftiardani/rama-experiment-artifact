import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from rich.console import Console

from .config import Context
from .cooldown import run_cooldown
from .deploy import deploy_local, deploy_remote, wait_ready
from .exporter import export_run
from .fault_scheduler import run_fault
from .invalidator import _validate_run as validate_run_inline
from .k6_runner import start_k6
from .manifest import ScenarioConfig
from .network_probe import probe as network_probe
from .postprocess import run_postprocess
from .recovery import forced_cleanup, run_recovery
from .snapshotter import take_snapshot
from .state_machine import RunStatus, State
from .utils.logging import log_state_event
from .utils.time import wait_with_progress


def _api_run_start(ctx: "Context", scenario: str, condition: str, run: int) -> Optional[int]:
    rt = ctx.manifest.runtime
    token = ctx.access_token()
    if not rt.backend_url or not token:
        console.print("[red]Tidak dapat mendaftarkan run: backend_url atau ACCESS_TOKEN kosong[/red]")
        return None
    try:
        import requests as _req
        body = {
            "scenario": scenario,
            "condition": condition,
            "run_number": run,
            "notes": "via experimentctl",
            "experiment_id": ctx.manifest.experiment.name,
            "repetition_index": run,
            "manifest_name": ctx.manifest._path or ctx.manifest.experiment.name,
            "k6_max_vu": ctx.manifest.global_config.k6_max_vu,
            "request_timeout_seconds": ctx.manifest.global_config.request_timeout_seconds,
            "load_generator_location": ctx.manifest.load_generator.location,
            "target_host": rt.backend_url,
        }
        resp = _req.post(
            f"{rt.backend_url.rstrip('/')}/v1/experiments/runs/start",
            json=body,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 201:
            return resp.json().get("run_id")
        console.print(f"[red]Gagal mendaftarkan run: HTTP {resp.status_code} {resp.text[:300]}[/red]")
    except Exception as e:
        console.print(f"[red]Gagal mendaftarkan run: {e}[/red]")
    return None


def _api_run_end(ctx: "Context", run_id: int) -> None:
    rt = ctx.manifest.runtime
    token = ctx.access_token()
    if not rt.backend_url or not token or not run_id:
        return
    try:
        import requests as _req
        _req.post(
            f"{rt.backend_url.rstrip('/')}/v1/experiments/runs/{run_id}/end",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except Exception:
        pass

console = Console()

STATE_FILE = Path("experiments/state/experiment_state.json")


@dataclass
class RunRecord:
    scenario: str
    condition: str
    run: int
    status: RunStatus = RunStatus.PENDING
    reason: str = ""
    pair_id: str = ""  # format: "{scenario}-{run_number}" e.g. "B1-7"

    def __post_init__(self):
        if not self.pair_id:
            self.pair_id = f"{self.scenario}-{self.run}"


def _load_state(experiment: str) -> dict:
    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if data.get("experiment") == experiment:
            return data
    return {"experiment": experiment, "completed": [], "failed": [], "next": None}


def _save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(state, indent=2)
    # Tulis ke file sementara lalu rename secara atomik agar dua proses paralel
    # tidak mengkorupsi state.json dengan partial write.
    fd, tmp = tempfile.mkstemp(dir=STATE_FILE.parent, suffix=".tmp", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp, STATE_FILE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _is_completed(state: dict, scenario: str, condition: str, run: int) -> bool:
    for c in state.get("completed", []):
        if c["scenario"] == scenario and c["condition"] == condition and c["run"] == run:
            return True
    return False


def run_one(
    ctx: Context,
    scenario_id: str,
    condition: str,
    run: int,
    skip_export: bool = False,
) -> RunRecord:
    m = ctx.manifest
    exp = m.experiment
    scenario = m.scenario(scenario_id)
    if scenario is None:
        return RunRecord(scenario_id, condition, run, RunStatus.FAILED_PRECHECK, "scenario not found")

    record = RunRecord(scenario_id, condition, run)

    def log(state: str, status: str, msg: str = "") -> None:
        log_state_event(exp.name, scenario_id, condition, run, state, status, msg)

    console.rule(f"[bold]{scenario_id}/{condition}/run{run}[/bold]")

    m.refresh_token_if_needed()

    log(State.NETWORK_PROBE_BEFORE, "start")
    try:
        network_probe(ctx, scenario_id, condition, run, phase="before")
        log(State.NETWORK_PROBE_BEFORE, "success")
    except Exception as e:
        log(State.NETWORK_PROBE_BEFORE, "warn", str(e))

    log(State.SNAPSHOT_BEFORE, "start")
    try:
        take_snapshot(ctx, scenario_id, condition, run, phase="before")
        log(State.SNAPSHOT_BEFORE, "success")
    except Exception as e:
        log(State.SNAPSHOT_BEFORE, "warn", str(e))

    log(State.DEPLOY_CONDITION, "start")
    if ctx.ssh:
        ok = deploy_remote(ctx, condition)
    else:
        ok = deploy_local(ctx, condition)
    if not ok:
        record.status = RunStatus.FAILED_PRECHECK
        record.reason = "deploy failed"
        log(State.DEPLOY_CONDITION, "failed", "deploy failed")
        return record
    log(State.DEPLOY_CONDITION, "success")

    log(State.WAIT_READY, "start")
    ready = wait_ready(ctx, timeout_seconds=m.global_config.wait_ready_timeout_seconds)
    if not ready:
        record.status = RunStatus.FAILED_PRECHECK
        record.reason = "system not ready"
        log(State.WAIT_READY, "failed", "system not ready")
        forced_cleanup(ctx)
        return record
    log(State.WAIT_READY, "success")

    log(State.START_RUN, "start")
    record.status = RunStatus.RUNNING
    run_id: Optional[int] = None
    if ctx.dry_run:
        console.print("[dim]DRY RUN: skip run registration[/dim]")
    else:
        run_id = _api_run_start(ctx, scenario_id, condition, run)
    if not ctx.dry_run and not run_id:
        record.status = RunStatus.FAILED_PRECHECK
        record.reason = "start run registration failed"
        log(State.START_RUN, "failed", record.reason)
        forced_cleanup(ctx)
        return record
    if run_id:
        console.print(f"[dim]Run registered: id={run_id}[/dim]")
    log(State.START_RUN, "success")

    log(State.START_K6, "start")
    k6_handle = start_k6(ctx, scenario_id, condition, run, ctx.load_generator)
    if k6_handle is None:
        record.status = RunStatus.FAILED_K6
        record.reason = "k6 failed to start"
        log(State.START_K6, "failed", record.reason)
        _api_run_end(ctx, run_id)
        forced_cleanup(ctx)
        return record
    log(State.START_K6, "success")

    if scenario.fault.type != "none":
        log(State.WAIT_STEADY_LOAD, "start")
        log(State.INJECT_FAULT, "start")
        try:
            fault_ok = run_fault(ctx, scenario, condition, run, run_id=run_id, load_process=k6_handle.process)
        except Exception as _fault_exc:
            console.print(f"[red]Fault injection exception: {_fault_exc}[/red]")
            fault_ok = False
        if not fault_ok:
            record.status = RunStatus.FAILED_FAULT
            record.reason = "fault injection failed"
            log(State.INJECT_FAULT, "failed")
            k6_handle.terminate()
            _api_run_end(ctx, run_id)
            forced_cleanup(ctx)
            run_cooldown(ctx, scenario)
            return record
        log(State.INJECT_FAULT, "success")

        try:
            from .evidence_collector import collect as _ev_collect
            _ev_collect(ctx, phase="during_run", scenario=scenario_id,
                        condition=condition, run=run, checkpoint="fault_active")
        except Exception:
            pass

        log(State.RECOVER, "start")
        rec_ok = run_recovery(ctx, scenario, condition, run)
        if not rec_ok:
            record.status = RunStatus.FAILED_RECOVERY
            record.reason = "recovery failed"
            log(State.RECOVER, "failed")
        else:
            log(State.RECOVER, "success")

        try:
            from .evidence_collector import collect as _ev_collect
            _ev_collect(ctx, phase="during_run", scenario=scenario_id,
                        condition=condition, run=run, checkpoint="recovery_phase")
        except Exception:
            pass

    # Wait k6 to finish; timeout jauh melebihi durasi terpanjang (class-c ~17 menit).
    # try/finally memastikan proses k6 selalu dihentikan apapun yang terjadi (timeout
    # maupun KeyboardInterrupt dari operator), agar proses tidak jadi orphan.
    try:
        k6_ok = k6_handle.wait(timeout=1800)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted — menghentikan k6...[/yellow]")
        k6_handle.terminate()
        _api_run_end(ctx, run_id)
        raise
    finally:
        if k6_handle.process is not None and k6_handle.process.poll() is None:
            console.print("[yellow]k6 masih hidup setelah 1800s; proses dihentikan[/yellow]")
            k6_handle.terminate()
    if not k6_ok:
        if record.status == RunStatus.RUNNING:
            record.status = RunStatus.FAILED_K6
            record.reason = "k6 failed"
        log(State.END_RUN, "failed", "k6 failed")
        _api_run_end(ctx, run_id)
        forced_cleanup(ctx)
        run_cooldown(ctx, scenario)
        return record

    log(State.END_RUN, "success")
    _api_run_end(ctx, run_id)

    try:
        from .evidence_collector import collect as _ev_collect
        _ev_collect(ctx, phase="during_run", scenario=scenario_id,
                    condition=condition, run=run, checkpoint="after_run")
    except Exception:
        pass

    log(State.SNAPSHOT_AFTER, "start")
    try:
        take_snapshot(ctx, scenario_id, condition, run, phase="after")
        log(State.SNAPSHOT_AFTER, "success")
    except Exception as e:
        log(State.SNAPSHOT_AFTER, "warn", str(e))

    log(State.NETWORK_PROBE_AFTER, "start")
    try:
        network_probe(ctx, scenario_id, condition, run, phase="after")
        log(State.NETWORK_PROBE_AFTER, "success")
    except Exception as e:
        log(State.NETWORK_PROBE_AFTER, "warn", str(e))

    exp_ok = True
    if not skip_export:
        log(State.EXPORT_DATA, "start")
        exp_ok = export_run(ctx, scenario_id, condition, run)
        log(State.EXPORT_DATA, "success" if exp_ok else "warn")
        if not exp_ok:
            console.print(f"[yellow]Export gagal untuk {scenario_id}/{condition}/run{run} "
                          f"— data ada di DB, inline validation dilewati[/yellow]")

    log(State.COOLDOWN, "start")
    run_cooldown(ctx, scenario)
    log(State.COOLDOWN, "success")

    # Inline invalidation — hanya jika export berhasil (data lokal tersedia)
    if not skip_export and exp_ok:
        # Snapshot db_precheck ke run dir agar invalidator bisa baca per-run (bukan hanya global)
        import shutil as _shutil
        _dbc_src = Path("experiments/evidence/db") / "db-precheck.json"
        _dbc_dst = k6_handle.out / "db_precheck.json"
        if _dbc_src.exists() and not _dbc_dst.exists():
            _shutil.copy2(_dbc_src, _dbc_dst)

        log(State.INVALIDATE_OR_VALIDATE, "start")
        try:
            validation = validate_run_inline(scenario_id, condition, run)
            if not validation.valid:
                console.print(f"[yellow]Run {scenario_id}/{condition}/{run} marked INVALID: "
                              f"{', '.join(validation.invalid_codes)}[/yellow]")
                log(State.INVALIDATE_OR_VALIDATE, "invalid", str(validation.invalid_codes))
                record.status = RunStatus.INVALID_DATA
                record.reason = "; ".join(validation.reasons)
            else:
                log(State.INVALIDATE_OR_VALIDATE, "valid")
        except Exception as e:
            log(State.INVALIDATE_OR_VALIDATE, "warn", str(e))
    elif skip_export:
        log(State.INVALIDATE_OR_VALIDATE, "warn", "skipped — export dilewati")

    if record.status in (RunStatus.RUNNING, RunStatus.INVALID_DATA):
        if record.status == RunStatus.RUNNING:
            record.status = RunStatus.SUCCESS
    return record


def run_pilot(ctx: Context) -> List[RunRecord]:
    """Run pilot: semua skenario dalam manifest × semua kondisi × 1 repetisi.

    Menggunakan kondisi dari manifest (bukan hardcoded 'baseline') sehingga
    pilot selalu selaras dengan kondisi eksperimen yang dikonfigurasi.
    """
    m = ctx.manifest
    conditions = m.experiment.conditions
    results = []
    for sc_cfg in m.scenarios:
        for cond in conditions:
            r = run_one(ctx, sc_cfg.id, cond, 1)
            results.append(r)
            console.print(
                f"[{'green' if r.status == RunStatus.SUCCESS else 'red'}]"
                f"{sc_cfg.id}/{cond}/run1: {r.status}[/]"
            )
    return results


def run_full(ctx: Context, resume: bool = False) -> List[RunRecord]:
    m = ctx.manifest
    state = _load_state(m.experiment.name)
    results: List[RunRecord] = []

    scenarios = [s.id for s in m.scenarios]
    conditions = m.experiment.conditions
    n_reps = m.experiment.repetitions

    for sc in scenarios:
        for cond in conditions:
            for run in range(1, n_reps + 1):
                if resume and _is_completed(state, sc, cond, run):
                    console.print(f"[dim]Skipping completed: {sc}/{cond}/run{run}[/dim]")
                    results.append(RunRecord(sc, cond, run, RunStatus.SKIPPED))
                    continue

                r = run_one(ctx, sc, cond, run)
                results.append(r)

                if r.status == RunStatus.SUCCESS:
                    state["completed"].append({"scenario": sc, "condition": cond, "run": run})
                else:
                    state["failed"].append({"scenario": sc, "condition": cond, "run": run, "reason": r.reason})

                try:
                    _save_state(state)
                except OSError as _e:
                    msg = f"[WARN] Gagal menyimpan state setelah {sc}/{cond}/run{run}: {_e} — run ini tidak akan ada di --resume\n"
                    console.print(f"[yellow]{msg.strip()}[/yellow]")
                    sys.stderr.write(msg)
                _print_run_result(r)

    state["next"] = None
    try:
        _save_state(state)
    except OSError as _e:
        msg = f"[WARN] Gagal menyimpan state final: {_e}\n"
        console.print(f"[yellow]{msg.strip()}[/yellow]")
        sys.stderr.write(msg)
    return results


def _print_run_result(r: RunRecord) -> None:
    ok = r.status == RunStatus.SUCCESS
    color = "green" if ok else "red"
    console.print(f"[{color}]{r.scenario}/{r.condition}/run{r.run} -> {r.status}[/{color}]" +
                  (f" ({r.reason})" if r.reason else ""))

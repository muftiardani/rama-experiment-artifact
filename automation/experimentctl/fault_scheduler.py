import logging
import shlex
import subprocess
import time
from typing import Optional

from rich.console import Console

from .config import Context
from .manifest import ScenarioConfig
from .utils import http
from .utils.ssh import run as ssh_run, run_parallel as ssh_run_parallel
from .utils.shell import run as shell_run
from .utils.time import wait_with_progress

logger = logging.getLogger(__name__)


def _run_cmd(ctx: "Context", cmd: str, timeout: int = 300):
    if ctx.ssh:
        return ssh_run(ctx.ssh, cmd, timeout=timeout)
    return shell_run(cmd, timeout=timeout)


def _is_process_running(process: Optional[subprocess.Popen]) -> bool:
    return process is None or process.poll() is None


def _preflight_command(ctx: "Context", cmd: str) -> bool:
    try:
        parts = shlex.split(cmd)
    except ValueError as exc:
        console.print(f"[red]Invalid fault command: {cmd} ({exc})[/red]")
        return False

    if len(parts) >= 3 and parts[0] == "docker" and parts[1] in {"exec", "stop", "restart", "start"}:
        container = parts[2]
        inspect = _run_cmd(ctx, f"docker inspect -f '{{{{.State.Running}}}}' {shlex.quote(container)}", timeout=30)
        if not inspect.ok:
            console.print(f"[red]Container not found for fault command: {container}[/red]")
            return False
        if parts[1] in {"exec", "stop"} and inspect.stdout.strip() != "true":
            console.print(f"[red]Container is not running for fault command: {container}[/red]")
            return False
        if parts[1] == "exec" and len(parts) >= 4 and parts[3] == "stress-ng":
            check = _run_cmd(ctx, f"docker exec {shlex.quote(container)} which stress-ng", timeout=30)
            if not check.ok:
                console.print(f"[red]stress-ng is not available in container: {container}[/red]")
                return False

    return True


def _preflight_commands(ctx: "Context", commands: list[str]) -> bool:
    return all(_preflight_command(ctx, cmd) for cmd in commands)

console = Console()


def _record_event(ctx: Context, event_type: str, target: str, run_id: Optional[int] = None,
                  scenario: str = "", condition: str = "", run: int = 0, extra: str = "") -> bool:
    rt = ctx.manifest.runtime
    token = ctx.access_token()
    if ctx.dry_run:
        return True
    base = rt.backend_url.rstrip("/").replace("/api", "") if rt.backend_url else ""
    if not base:
        logger.error("_record_event failed: backend_url is empty")
        return False
    if not token:
        logger.error("_record_event failed: ACCESS_TOKEN is empty")
        return False
    import requests
    payload = {
        "event_type": event_type,
        "target_service": target,
        "scenario": scenario,
        "condition": condition,
        "run_number": run,
        "notes": extra,
    }
    if run_id:
        payload["experiment_run_id"] = run_id
    headers = {"Authorization": f"Bearer {token}"}
    for attempt in range(3):
        try:
            resp = requests.post(
                f"{base}/api/v1/experiments/fault-events",
                json=payload,
                headers=headers,
                timeout=15,
            )
            if 200 <= resp.status_code < 300:
                return True
            logger.warning("_record_event attempt %d/3 got HTTP %s: %s",
                           attempt + 1, resp.status_code, resp.text[:300])
        except Exception as e:
            logger.warning("_record_event attempt %d/3 failed (%s/%s run%s %s): %s",
                           attempt + 1, scenario, condition, run, event_type, e)
        if attempt < 2:
            time.sleep(3)
    return False


def run_fault(
    ctx: Context,
    scenario: ScenarioConfig,
    condition: str,
    run: int,
    run_id: Optional[int] = None,
    load_process: Optional[subprocess.Popen] = None,
) -> bool:
    m = ctx.manifest
    fault = scenario.fault

    if fault.type == "none":
        console.print("[dim]No fault for this scenario[/dim]")
        return True

    # Preflight sebelum menunggu steady load agar latensi SSH tidak masuk ke
    # window pengukuran — fault_injected_at dicatat tepat sebelum eksekusi fault.
    if not ctx.dry_run:
        if fault.type in ("cpu_pressure", "memory_pressure", "stop_container"):
            preflight_cmds = fault.commands
        elif fault.type == "combined_pressure":
            preflight_cmds = fault.parallel
        elif fault.type == "gradual_memory_pressure":
            preflight_cmds = [stage["command"] for stage in fault.stages]
        elif fault.type == "cascade_failure":
            preflight_cmds = [step["command"] for step in fault.sequence]
        else:
            preflight_cmds = []
        if preflight_cmds and not _preflight_commands(ctx, preflight_cmds):
            return False

    wait_secs = m.global_config.steady_load_wait_seconds
    console.print(f"[cyan]Waiting {wait_secs}s for steady load before fault injection...[/cyan]")
    if not ctx.dry_run:
        wait_with_progress(wait_secs, "Waiting steady load")

    if not _is_process_running(load_process):
        console.print("[red]k6 process sudah berhenti sebelum fault injection[/red]")
        return False

    success = True
    fault_event_recorded = False
    failure_event_recorded = False

    if ctx.dry_run:
        console.print(f"[dim]DRY RUN: fault type={fault.type} target={fault.event_target}[/dim]")
        _record_event(ctx, "fault_finished", fault.event_target, run_id,
                      scenario=scenario.id, condition=condition, run=run)
        return True

    def _record_fault_injected() -> bool:
        """Catat fault_injected. Return True jika berhasil; caller wajib update fault_event_recorded."""
        if _record_event(ctx, "fault_injected", fault.event_target, run_id,
                         scenario=scenario.id, condition=condition, run=run):
            return True
        console.print("[yellow]Gagal mencatat fault_injected ke backend - "
                      "fault tetap dieksekusi, run mungkin diinvalidasi[/yellow]")
        return False

    try:
        if fault.type in ("cpu_pressure", "memory_pressure", "stop_container"):
            fault_event_recorded = _record_fault_injected()
            for cmd in fault.commands:
                r = _run_cmd(ctx, cmd, timeout=300)
                if not r.ok:
                    console.print(f"[red]Fault command failed: {cmd}[/red]")
                    console.print(f"[red]{r.stderr}[/red]")
                    success = False
                    _record_event(ctx, "fault_failed", fault.event_target, run_id,
                                  scenario=scenario.id, condition=condition, run=run,
                                  extra=f"command failed: {cmd}")
                    failure_event_recorded = True
                    break

        elif fault.type == "combined_pressure":
            fault_event_recorded = _record_fault_injected()
            if ctx.ssh:
                results = ssh_run_parallel(ctx.ssh, fault.parallel, timeout=300)
            else:
                results = [shell_run(c, timeout=300) for c in fault.parallel]
            for i, r in enumerate(results):
                if not r.ok:
                    console.print(f"[red]Parallel fault[{i}] failed: {fault.parallel[i]}[/red]")
                    success = False
            if not success:
                _record_event(ctx, "fault_failed", fault.event_target, run_id,
                              scenario=scenario.id, condition=condition, run=run,
                              extra="parallel command failed")
                failure_event_recorded = True

        elif fault.type == "gradual_memory_pressure":
            fault_event_recorded = _record_fault_injected()
            for idx, stage in enumerate(fault.stages):
                _record_event(ctx, "fault_stage_started", scenario.target, run_id,
                              scenario=scenario.id, condition=condition, run=run,
                              extra=f"stage={idx+1}")
                r = _run_cmd(ctx, stage["command"], timeout=int(stage.get("duration_seconds", 120)) + 30)
                if not r.ok:
                    console.print(f"[red]Stage {idx+1} failed: {r.stderr}[/red]")
                    success = False
                    _record_event(ctx, "fault_stage_failed", scenario.target, run_id,
                                  scenario=scenario.id, condition=condition, run=run,
                                  extra=f"stage={idx+1}")
                    _record_event(ctx, "fault_stage_finished", scenario.target, run_id,
                                  scenario=scenario.id, condition=condition, run=run,
                                  extra=f"stage={idx+1}")
                    failure_event_recorded = True
                    break
                _record_event(ctx, "fault_stage_finished", scenario.target, run_id,
                              scenario=scenario.id, condition=condition, run=run,
                              extra=f"stage={idx+1}")

        elif fault.type == "cascade_failure":
            fault_event_recorded = _record_fault_injected()
            for i, step in enumerate(fault.sequence):
                _record_event(ctx, "fault_stage_started", step.get("target", ""), run_id,
                              scenario=scenario.id, condition=condition, run=run,
                              extra=f"step={i+1}")
                r = _run_cmd(ctx, step["command"], timeout=300)
                if not r.ok:
                    console.print(f"[red]Cascade step {i+1} failed[/red]")
                    success = False
                    _record_event(ctx, "fault_stage_failed", step.get("target", ""), run_id,
                                  scenario=scenario.id, condition=condition, run=run,
                                  extra=f"step={i+1}")
                    _record_event(ctx, "fault_stage_finished", step.get("target", ""), run_id,
                                  scenario=scenario.id, condition=condition, run=run,
                                  extra=f"step={i+1}")
                    failure_event_recorded = True
                    break
                wait_secs = int(step.get("wait_after_seconds", 0))
                if wait_secs > 0:
                    wait_with_progress(wait_secs, f"Waiting after cascade step {i+1}")
                _record_event(ctx, "fault_stage_finished", step.get("target", ""), run_id,
                              scenario=scenario.id, condition=condition, run=run,
                              extra=f"step={i+1}")
    except Exception:
        success = False
        raise
    finally:
        if fault_event_recorded:
            if success:
                _record_event(ctx, "fault_finished", fault.event_target, run_id,
                              scenario=scenario.id, condition=condition, run=run)
            elif not failure_event_recorded:
                _record_event(ctx, "fault_failed", fault.event_target, run_id,
                              scenario=scenario.id, condition=condition, run=run)

    if not success:
        return False

    observe_secs = m.global_config.observe_seconds
    console.print(f"[cyan]Observing for {observe_secs}s...[/cyan]")
    wait_with_progress(observe_secs, "Observing")

    return success

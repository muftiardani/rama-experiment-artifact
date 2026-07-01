import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Optional

from rich.console import Console

from .config import Context
from .utils.paths import run_dir as _out_dir

console = Console()


@dataclass
class K6Process:
    out: Path
    process: Optional[subprocess.Popen]
    stdout_file: Optional[IO[str]] = None
    stderr_file: Optional[IO[str]] = None
    dry_run: bool = False

    def wait(self, timeout: Optional[int] = None) -> bool:
        if self.dry_run:
            return True
        if self.process is None:
            return False

        timed_out = False
        try:
            returncode = self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            # Tulis finished_at di finally agar semua exit path — sukses, timeout,
            # maupun exception tak terduga dari process.wait() — selalu tercatat.
            _update_k6_env_metadata(self.out, finished_at=datetime.now(timezone.utc).isoformat())
            self._close_files()
        if timed_out:
            return False
        if returncode not in (0, 99):
            console.print(f"[red]k6 exited with code {returncode}[/red]")
            return False
        if returncode == 99:
            console.print("[yellow]k6: satu atau lebih threshold dilanggar (data tetap valid)[/yellow]")

        console.print(f"[green]k6 completed -> {self.out}[/green]")
        return True

    def terminate(self, grace_seconds: int = 10) -> None:
        if self.dry_run or self.process is None:
            self._close_files()
            return
        if self.process.poll() is None:
            console.print("[yellow]Terminating k6 process for failed/timed-out run[/yellow]")
            self.process.terminate()
            try:
                self.process.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                self.process.kill()
                try:
                    self.process.wait(timeout=grace_seconds)
                except subprocess.TimeoutExpired:
                    pass  # Proses dalam D-state/zombie — lanjutkan cleanup
        _update_k6_env_metadata(self.out, finished_at=datetime.now(timezone.utc).isoformat())
        self._close_files()

    def _close_files(self) -> None:
        for f in (self.stdout_file, self.stderr_file):
            if f and not f.closed:
                f.close()


def start_k6(
    ctx: Context,
    scenario_id: str,
    condition: str,
    run: int,
    load_generator: str = "external",
) -> Optional[K6Process]:
    manifest = ctx.manifest
    if manifest.load_generator.run_on_vps:
        console.print("[red]k6 run_on_vps=true belum didukung oleh k6_runner lokal[/red]")
        return None

    scenario = manifest.scenario(scenario_id)
    if scenario is None:
        console.print(f"[red]Scenario '{scenario_id}' not found in manifest[/red]")
        return None

    out = _out_dir(scenario_id, condition, run)
    out.mkdir(parents=True, exist_ok=True)

    token = ctx.access_token()
    if not token:
        console.print("[red]ACCESS_TOKEN is required to start k6[/red]")
        return None
    rt = manifest.runtime
    target_url = rt.backend_url.rstrip("/").replace("/api", "") if rt.backend_url else "http://localhost:8080"
    request_timeout_seconds = manifest.global_config.request_timeout_seconds

    env = os.environ.copy()
    env.update({
        "SCENARIO": scenario_id,
        "CONDITION": condition,
        "RUN": str(run),
        "ACCESS_TOKEN": token,
        "TARGET_BASE_URL": target_url,
        "BASE_URL": target_url,
        "K6_MAX_VU": str(manifest.global_config.k6_max_vu),
        "REQUEST_TIMEOUT_MS": str(request_timeout_seconds * 1000),
    })

    summary_path = out / "k6_summary.json"
    stdout_path = out / "k6_stdout.log"
    stderr_path = out / "k6_stderr.log"

    k6_script = scenario.k6_script
    if not Path(k6_script).exists():
        console.print(f"[red]k6 script not found: {k6_script}[/red]")
        return None

    cmd = [
        "k6", "run",
        "--summary-export", str(summary_path),
        k6_script,
    ]

    console.print(f"[cyan]Starting k6: {scenario_id}/{condition}/run{run}[/cyan]")
    lg_location = ctx.manifest.load_generator.location

    if ctx.dry_run:
        console.print(f"[dim]DRY RUN: {' '.join(cmd)}[/dim]")
        _save_k6_env_metadata(
            out,
            target_url,
            token,
            load_generator_location=lg_location,
            run_on_vps=manifest.load_generator.run_on_vps,
            request_timeout_seconds=request_timeout_seconds,
            dry_run=True,
        )
        return K6Process(out=out, process=None, dry_run=True)

    started_at = datetime.now(timezone.utc).isoformat()
    _save_k6_env_metadata(
        out,
        target_url,
        token,
        load_generator_location=lg_location,
        run_on_vps=manifest.load_generator.run_on_vps,
        request_timeout_seconds=request_timeout_seconds,
        started_at=started_at,
    )

    fout = stdout_path.open("w")
    ferr = stderr_path.open("w")
    try:
        process = subprocess.Popen(cmd, env=env, stdout=fout, stderr=ferr)
    except Exception as exc:
        fout.close()
        ferr.close()
        console.print(f"[red]Failed to start k6: {exc}[/red]")
        return None

    return K6Process(out=out, process=process, stdout_file=fout, stderr_file=ferr)


def run_k6(
    ctx: Context,
    scenario_id: str,
    condition: str,
    run: int,
    load_generator: str = "external",
) -> bool:
    handle = start_k6(ctx, scenario_id, condition, run, load_generator)
    if handle is None:
        return False
    return handle.wait(timeout=1800)


def _save_k6_env_metadata(
    out: Path,
    target_url: str,
    token: str,
    load_generator_location: str = "laptop",
    run_on_vps: bool = False,
    request_timeout_seconds: int = 90,
    started_at: str = "",
    dry_run: bool = False,
) -> None:
    import socket
    import subprocess as sp

    k6_ver = ""
    try:
        r = sp.run(["k6", "version"], capture_output=True, text=True, timeout=5)
        k6_ver = r.stdout.strip()
    except Exception:
        pass

    meta = {
        "load_generator_location": load_generator_location,
        "run_on_vps": run_on_vps,
        "target_base_url": target_url,
        "request_timeout_seconds": request_timeout_seconds,
        "request_timeout_ms": request_timeout_seconds * 1000,
        "k6_version": k6_ver,
        "laptop_hostname": socket.gethostname(),
        "started_at": started_at,
        "finished_at": "",
        "dry_run": dry_run,
    }
    (out / "k6_environment.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _update_k6_env_metadata(out: Path, finished_at: str) -> None:
    path = out / "k6_environment.json"
    if not path.exists():
        return
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta["finished_at"] = finished_at
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

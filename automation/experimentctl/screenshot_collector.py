import os
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()

SCREENSHOTS_DIR = Path("experiments/evidence/screenshots")

_GRAFANA_DASHBOARD_URL = "http://127.0.0.1:13001/d/temandifa-resilience/temandifa-observability-dashboard"
_GRAFANA_USERNAME = ""
_GRAFANA_PASSWORD = ""
_BROWSER_TIMEOUT_MS = 30000


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _playwright_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except Exception:
        console.print(
            "[yellow]playwright tidak terinstall — skip screenshot "
            "(pip install playwright && python -m playwright install chromium)[/yellow]"
        )
        return False


def _run_time_range_ms(
    scenario: str, condition: str, run: int
) -> tuple[Optional[int], Optional[int]]:
    dsn = _env("POSTGRES_DSN_TUNNEL", "")
    if not dsn:
        return None, None
    try:
        import psycopg2
        conn = psycopg2.connect(dsn, connect_timeout=5)
        cur = conn.cursor()
        cur.execute(
            "SELECT started_at, ended_at FROM experiment_runs "
            "WHERE scenario=%s AND condition=%s AND run_number=%s "
            "ORDER BY id DESC LIMIT 1",
            (scenario, condition, run),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None, None
        started_at, ended_at = row
        # Buffer 30s sebelum start dan 60s setelah end agar semua panel terisi
        import datetime
        buf_before = datetime.timedelta(seconds=30)
        buf_after  = datetime.timedelta(seconds=60)
        from_ms = int((started_at - buf_before).timestamp() * 1000)
        to_ms   = int(((ended_at or started_at) + buf_after).timestamp() * 1000)
        return from_ms, to_ms
    except Exception:
        return None, None


def capture_grafana(
    output: str,
    url: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    scenario: Optional[str] = None,
    condition: Optional[str] = None,
    run: Optional[int] = None,
) -> bool:
    """Screenshot halaman Grafana dashboard ke PNG.

    URL otomatis diberi:
    - var-scenario/condition/run -> filter panel ke run aktif
    - from/to (unix ms dari DB) -> time range tepat sesuai durasi run
    - kiosk -> sembunyikan navbar untuk screenshot bersih
    """
    if not _playwright_available():
        return False
    from playwright.sync_api import sync_playwright

    base_url = url or _env("GRAFANA_DASHBOARD_URL", _GRAFANA_DASHBOARD_URL)
    params = []
    if scenario:
        params.append(f"var-scenario={scenario}")
    if condition:
        params.append(f"var-condition={condition}")
    if run:
        params.append(f"var-run={run}")

    # Time range dari DB — fallback ke "last 30m" jika tidak tersedia
    if scenario and condition and run:
        from_ms, to_ms = _run_time_range_ms(scenario, condition, run)
        if from_ms and to_ms:
            params.append(f"from={from_ms}&to={to_ms}")

    # Kiosk mode — sembunyikan navbar Grafana
    params.append("kiosk")

    url = f"{base_url}?{'&'.join(params)}"

    username = username or _env("GRAFANA_USERNAME", _GRAFANA_USERNAME)
    password = password or _env("GRAFANA_PASSWORD", _GRAFANA_PASSWORD)
    timeout = int(_env("SCREENSHOT_BROWSER_TIMEOUT_MS", str(_BROWSER_TIMEOUT_MS)))

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            # Viewport lebar dulu (normal) untuk login
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            # Navigasi awal: pakai domcontentloaded agar tidak timeout di dashboard berat
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            page.wait_for_timeout(2000)
            if username and password and "login" in page.url:
                try:
                    page.wait_for_selector('input[name="user"], input[name="username"]', timeout=15000)
                    sel = 'input[name="user"]' if page.query_selector('input[name="user"]') else 'input[name="username"]'
                    page.fill(sel, username)
                    page.fill('input[name="password"]', password)
                    page.click('button[type="submit"]')
                    page.wait_for_load_state("domcontentloaded", timeout=timeout)
                    page.wait_for_timeout(2000)
                except Exception:
                    pass
            # Grafana paksa "Update your password" setelah login pertama
            if any(kw in page.url for kw in ["/user/password", "change-password", "update-password"]):
                try:
                    skip_btn = page.query_selector('button:has-text("Skip"), a:has-text("Skip")')
                    if skip_btn:
                        skip_btn.click()
                        page.wait_for_timeout(1000)
                except Exception:
                    pass
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                page.wait_for_timeout(2000)
            elif "login" not in page.url and page.url != url:
                # Setelah login berhasil, Grafana kadang redirect ke home bukan redirectTo
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                page.wait_for_timeout(2000)
            if username and password and "login" in page.url:
                try:
                    page.wait_for_selector('input[name="user"], input[name="username"]', timeout=10000)
                    sel = 'input[name="user"]' if page.query_selector('input[name="user"]') else 'input[name="username"]'
                    page.fill(sel, username)
                    page.fill('input[name="password"]', password)
                    page.click('button[type="submit"]')
                    page.wait_for_load_state("domcontentloaded", timeout=timeout)
                    page.wait_for_timeout(3000)
                    if "login" not in page.url and page.url != url:
                        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                        page.wait_for_timeout(2000)
                except Exception:
                    pass
            # Resize ke viewport sangat tinggi -> semua panel IntersectionObserver terpicu
            page.set_viewport_size({"width": 1600, "height": 8000})
            page.wait_for_timeout(2000)
            try:
                page.wait_for_selector('.panel-container, [class*="panel-"]', timeout=10000)
            except Exception:
                pass
            try:
                page.wait_for_function(
                    "() => !document.body.innerText.includes('Loading plugin panel')",
                    timeout=20000,
                )
            except Exception:
                pass
            page.wait_for_timeout(1500)
            # Ukur bottom panel terbawah SETELAH semua render -> resize viewport ke tinggi tepat
            content_h = page.evaluate("""
                () => {
                    const panels = document.querySelectorAll('.panel-container, [class*="react-grid-item"]');
                    if (!panels.length) return document.body.scrollHeight;
                    let maxBottom = 0;
                    panels.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        if (rect.bottom > maxBottom) maxBottom = rect.bottom;
                    });
                    return Math.ceil(maxBottom) + 40;
                }
            """) or 900
            content_h = min(max(int(content_h), 900), 12000)
            page.set_viewport_size({"width": 1600, "height": content_h})
            page.wait_for_timeout(500)
            page.screenshot(path=str(out), full_page=False)
            browser.close()
        console.print(f"[green]Grafana screenshot: {out}[/green]")
        return True
    except Exception as e:
        console.print(f"[yellow]Grafana screenshot gagal: {e}[/yellow]")
        return False


def capture_prometheus(output: str, url: Optional[str] = None) -> bool:
    if not _playwright_available():
        return False
    from playwright.sync_api import sync_playwright

    default_base = _env("PROMETHEUS_URL", "http://127.0.0.1:19090")
    url = url or f"{default_base.rstrip('/')}/targets"
    timeout = int(_env("SCREENSHOT_BROWSER_TIMEOUT_MS", str(_BROWSER_TIMEOUT_MS)))

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1600, "height": 1200})
            # Prometheus UI terus polling AJAX — gunakan "load" bukan "networkidle"
            page.goto(url, wait_until="load", timeout=timeout)
            page.wait_for_timeout(2000)  # beri waktu render table targets
            page.screenshot(path=str(out), full_page=True)
            browser.close()
        console.print(f"[green]Prometheus screenshot: {out}[/green]")
        return True
    except Exception as e:
        console.print(f"[yellow]Prometheus screenshot gagal: {e}[/yellow]")
        return False


def render_text_to_png(input_txt: str, output_png: str) -> bool:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        console.print(
            "[yellow]Pillow tidak terinstall — skip render "
            "(pip install Pillow)[/yellow]"
        )
        return False

    try:
        text = Path(input_txt).read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        width = 1600
        line_height = 20
        padding = 30
        height = padding * 2 + max(1, len(lines)) * line_height

        img = Image.new("RGB", (width, height), (30, 30, 30))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("DejaVuSansMono.ttf", 14)
        except Exception:
            font = ImageFont.load_default()

        y = padding
        for line in lines:
            draw.text((padding, y), line[:220], fill=(200, 200, 200), font=font)
            y += line_height

        out = Path(output_png)
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(out))
        console.print(f"[green]Rendered text to PNG: {out}[/green]")
        return True
    except Exception as e:
        console.print(f"[yellow]render_text_to_png gagal: {e}[/yellow]")
        return False

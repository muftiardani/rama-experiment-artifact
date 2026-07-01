"""
build_summary.py — Pipeline postprocessing lengkap.

Menjalankan seluruh tahap secara berurutan:
1. export_requests.py (dari DB ke CSV)
2. compute_latency.py
3. compute_response_category.py
4. compute_pa.py
5. compute_tfs.py
6. compute_ttr.py
7. compute_slo_violation.py
8. Gabungkan ke final_summary.csv

Penggunaan:
    python experiments/postprocess/build_summary.py

Atau dengan filter:
    SCENARIO=A1 CONDITION=treatment RUN=1 python experiments/postprocess/build_summary.py
"""

import csv
import os
import subprocess
import sys


POSTPROCESS_DIR = os.path.dirname(os.path.abspath(__file__))
PROCESSED_DIR = "experiments/data/processed"
RAW_FAULT_EVENTS_CSV = os.path.join(PROCESSED_DIR, "all_fault_events.csv")
# Kolom ini HARUS identik dengan kolom yang di-SELECT di export_fault_events() (baris ~79-81).
# export_fault_events() menggunakan cur.description agar otomatis sesuai skema DB,
# sedangkan write_empty_fault_events() butuh daftar ini untuk header fallback.
# Perbarui kedua tempat setiap kali kolom fault_events berubah.
FAULT_EVENT_FIELDNAMES = [
    "id",
    "experiment_run_id",
    "scenario",
    "condition",
    "run_number",
    "event_type",
    "target_service",
    "event_time",
    "notes",
]


def _filters():
    scenario = os.environ.get("SCENARIO", "").strip()
    condition = os.environ.get("CONDITION", "").strip()
    run = os.environ.get("RUN", "").strip()
    return scenario, condition, run


def run_step(step_name, cmd):
    print(f"\n{'='*60}")
    print(f"[BUILD] {step_name}")
    print(f"{'='*60}")
    result = subprocess.run([sys.executable] + cmd, capture_output=False)
    if result.returncode != 0:
        raise RuntimeError(f"{step_name} gagal dengan exit code {result.returncode}")


def export_fault_events():
    """Ekspor fault_events dari DB (parallel dengan request_logs)."""
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        print("[ERROR] psycopg2 tidak tersedia. Tidak bisa ekspor fault_events.")
        return False

    db_dsn = (
        os.environ.get("DB_DSN")
        or os.environ.get("POSTGRES_DSN")
        or os.environ.get("POSTGRES_DSN_TUNNEL")
        or "postgresql://postgres:postgres@localhost:5432/temandifa"
    )
    try:
        conn = psycopg2.connect(db_dsn)
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        scenario, condition, run = _filters()
        query = """
            SELECT fe.id, fe.experiment_run_id, fe.scenario, fe.condition,
                   fe.run_number, fe.event_type, fe.target_service,
                   fe.event_time, fe.notes
            FROM fault_events fe
            WHERE 1=1
        """
        params = []
        if scenario:
            query += " AND fe.scenario = %s"
            params.append(scenario)
        if condition:
            query += " AND fe.condition = %s"
            params.append(condition)
        if run:
            query += " AND fe.run_number = %s"
            params.append(int(run))
        query += " ORDER BY fe.event_time"
        cur.execute(query, params)
        rows = cur.fetchall()
        os.makedirs(PROCESSED_DIR, exist_ok=True)
        with open(RAW_FAULT_EVENTS_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([desc[0] for desc in cur.description])
            writer.writerows(rows)
        print(f"[BUILD] fault_events ekspor {len(rows)} baris -> {RAW_FAULT_EVENTS_CSV}")
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"[ERROR] Gagal ekspor fault_events: {e}")
        return False


def write_empty_fault_events():
    """Buat CSV fault_events kosong agar TFS/TTR tetap menghasilkan summary kosong.

    Tidak menimpa file yang sudah ada dan tidak kosong — data valid dari run sebelumnya
    dipertahankan agar pipeline tidak terdegradasi akibat kegagalan DB transien.
    """
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    if os.path.exists(RAW_FAULT_EVENTS_CSV) and os.path.getsize(RAW_FAULT_EVENTS_CSV) > 0:
        print(f"[BUILD] fault_events sudah ada ({RAW_FAULT_EVENTS_CSV}) — tidak ditimpa.")
        return
    with open(RAW_FAULT_EVENTS_CSV, "w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=FAULT_EVENT_FIELDNAMES).writeheader()
    print(f"[BUILD] fault_events kosong -> {RAW_FAULT_EVENTS_CSV}")

def merge_final(out_path):
    sources = {
        "pa": os.path.join(PROCESSED_DIR, "partial_availability_summary.csv"),
        "latency": os.path.join(PROCESSED_DIR, "latency_summary.csv"),
        "slo": os.path.join(PROCESSED_DIR, "slo_violation_summary.csv"),
        "tfs": os.path.join(PROCESSED_DIR, "tfs_summary.csv"),
        "ttr": os.path.join(PROCESSED_DIR, "ttr_summary.csv"),
    }

    # Baca PA sebagai basis (berisi semua (scenario, condition, run))
    pa_path = sources["pa"]
    if not os.path.exists(pa_path):
        print("[WARNING] partial_availability_summary.csv tidak ditemukan. Final summary tidak dibuat.")
        return

    with open(pa_path, newline="", encoding="utf-8-sig") as f:
        base = {(r["scenario"], r["condition"], r["run_number"]): dict(r) for r in csv.DictReader(f)}

    def merge(path, fields, prefix=""):
        if not os.path.exists(path):
            return
        with open(path, newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                key = (row["scenario"], row["condition"], row["run_number"])
                if key in base:
                    for field in fields:
                        base[key][f"{prefix}{field}"] = row.get(field, "")
                else:
                    print(f"[WARNING] merge: key {key} tidak ada di PA base — baris dari {os.path.basename(path)} dibuang")

    merge(sources["latency"], ["p95_ms", "p99_ms", "iqr_ms", "mean_ms", "median_ms"], "")
    merge(sources["slo"], ["slo_violation_score", "violation_details"], "")
    merge(sources["tfs"], ["tfs_seconds"], "")
    merge(sources["ttr"], ["ttr_seconds"], "")
    merge(os.path.join(PROCESSED_DIR, "throughput_summary.csv"), ["throughput_rps", "total_requests"], "")

    all_rows = list(base.values())
    if not all_rows:
        return

    # Tambah pair_id = "{scenario}-{run_number}" untuk analisis Wilcoxon berpasangan
    for row in all_rows:
        row["pair_id"] = f"{row.get('scenario', '')}-{row.get('run_number', '')}"

    # Kumpulkan semua fieldnames dari semua baris (tiap skenario bisa punya kolom berbeda)
    all_fields = list(dict.fromkeys(k for row in all_rows for k in row.keys()))
    for row in all_rows:
        for f in all_fields:
            row.setdefault(f, "")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=all_fields)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\n[BUILD] Final summary ({len(all_rows)} baris) -> {out_path}")


def main():
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    scenario, condition, run = _filters()

    export_cmd = [
        os.path.join(POSTPROCESS_DIR, "export_requests.py"),
        "--out", os.path.join(PROCESSED_DIR, "all_request_logs.csv"),
    ]
    if scenario:
        export_cmd += ["--scenario", scenario]
    if condition:
        export_cmd += ["--condition", condition]
    if run:
        export_cmd += ["--run", run]
    run_step("Export request_logs", export_cmd)
    if not export_fault_events():
        print("[WARNING] Ekspor fault_events gagal (psycopg2 tidak tersedia atau DB tidak terjangkau).")
        print("[WARNING] Melanjutkan pipeline dengan fault_events kosong — TFS/TTR akan N/A.")
        print("[WARNING] PENYEBAB N/A: data hilang akibat kegagalan DB, BUKAN karena tidak ada fault.")
        print("[WARNING] Tandai baris N/A di final_summary.csv sebagai 'data_missing' bukan 'no_fault'.")
        write_empty_fault_events()


    all_req = os.path.join(PROCESSED_DIR, "all_request_logs.csv")

    run_step("Compute latency", [
        os.path.join(POSTPROCESS_DIR, "compute_latency.py"),
        "--input", all_req,
        "--out", os.path.join(PROCESSED_DIR, "latency_summary.csv"),
    ])

    run_step("Compute response category", [
        os.path.join(POSTPROCESS_DIR, "compute_response_category.py"),
        "--input", all_req,
        "--out", os.path.join(PROCESSED_DIR, "response_category_summary.csv"),
    ])

    run_step("Compute PA", [
        os.path.join(POSTPROCESS_DIR, "compute_pa.py"),
        "--input", os.path.join(PROCESSED_DIR, "response_category_summary.csv"),
        "--out", os.path.join(PROCESSED_DIR, "partial_availability_summary.csv"),
    ])

    run_step("Compute TFS", [
        os.path.join(POSTPROCESS_DIR, "compute_tfs.py"),
        "--requests", all_req,
        "--faults", RAW_FAULT_EVENTS_CSV,
        "--out", os.path.join(PROCESSED_DIR, "tfs_summary.csv"),
    ])

    run_step("Compute TTR", [
        os.path.join(POSTPROCESS_DIR, "compute_ttr.py"),
        "--requests", all_req,
        "--faults", RAW_FAULT_EVENTS_CSV,
        "--out", os.path.join(PROCESSED_DIR, "ttr_summary.csv"),
    ])

    run_step("Compute k6 throughput", [
        os.path.join(POSTPROCESS_DIR, "compute_k6_throughput.py"),
        "--raw-dir", "experiments/data/raw",
        "--out", os.path.join(PROCESSED_DIR, "throughput_summary.csv"),
    ])

    run_step("Compute SLO Violation", [
        os.path.join(POSTPROCESS_DIR, "compute_slo_violation.py"),
        "--latency", os.path.join(PROCESSED_DIR, "latency_summary.csv"),
        "--category", os.path.join(PROCESSED_DIR, "response_category_summary.csv"),
        "--pa", os.path.join(PROCESSED_DIR, "partial_availability_summary.csv"),
        "--out", os.path.join(PROCESSED_DIR, "slo_violation_summary.csv"),
    ])

    # Catatan: pipeline produksi menulis ke experiments/results/ di VPS loadgen,
    # kemudian hasilnya dipindahkan ke experiments/processed/ untuk publikasi artefak.
    results_dir = "experiments/results"
    os.makedirs(results_dir, exist_ok=True)
    merge_final(os.path.join(results_dir, "final_summary.csv"))

    print("\n[BUILD] Selesai. Cek experiments/results/")


if __name__ == "__main__":
    main()

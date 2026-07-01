"""
export_requests.py — Ekspor request_logs dari PostgreSQL ke CSV.

Penggunaan:
    python experiments/postprocess/export_requests.py \
        --scenario A1 --condition treatment --run 1 \
        --out experiments/data/raw/A1/treatment/run-1/request_logs.csv

Atau ekspor semua:
    python experiments/postprocess/export_requests.py \
        --out experiments/data/processed/all_request_logs.csv
"""

import argparse
import csv
import os
import sys

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2 tidak terinstal. Jalankan: pip install psycopg2-binary")
    sys.exit(1)

DB_DSN = (
    os.environ.get("DB_DSN")
    or os.environ.get("POSTGRES_DSN")
    or os.environ.get("POSTGRES_DSN_TUNNEL")
    or "postgresql://postgres:postgres@localhost:5432/temandifa"
)


def export(scenario=None, condition=None, run=None, out_path="request_logs.csv"):
    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    query = """
        SELECT
            rl.id,
            rl.experiment_run_id,
            er.scenario,
            er.condition,
            er.run_number,
            rl.request_id,
            rl.trace_id,
            rl.endpoint,
            rl.latency_ms,
            rl.status_code,
            rl.grpc_status,
            rl.response_category,
            rl.fallback_active,
            rl.fallback_reason,
            rl.degraded_services,
            rl.error_type,
            rl.created_at
        FROM request_logs rl
        INNER JOIN experiment_runs er ON rl.experiment_run_id = er.id
        WHERE 1=1
    """
    params = []
    if scenario:
        query += " AND er.scenario = %s"
        params.append(scenario)
    if condition:
        query += " AND er.condition = %s"
        params.append(condition)
    if run is not None:
        query += " AND er.run_number = %s"
        params.append(run)
    query += " ORDER BY rl.created_at"

    cur.execute(query, params)
    rows = cur.fetchall()

    os.makedirs(os.path.dirname(out_path) if os.path.dirname(out_path) else ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([desc[0] for desc in cur.description])
        writer.writerows(rows)

    print(f"Ekspor {len(rows)} baris ke: {out_path}")
    cur.close()
    conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default=None)
    parser.add_argument("--condition", default=None)
    parser.add_argument("--run", type=int, default=None)
    parser.add_argument("--out", default="experiments/data/processed/all_request_logs.csv")
    args = parser.parse_args()
    export(args.scenario, args.condition, args.run, args.out)


if __name__ == "__main__":
    main()

# Data Mentah — Ketersediaan Sebagian

Data mentah lengkap 180 run (9 skenario × 2 kondisi × 10 repetisi) **tidak** disertakan penuh pada repository ini. Sebagai gantinya, 11 folder run representatif (1 per kombinasi skenario × kondisi yang menjadi rujukan utama pada naskah skripsi) disertakan sebagai sampel, sudah disanitasi.

## Sampel yang Tersedia

| Skenario | Kondisi | Run |
|---|---|---|
| SS | treatment | run1 |
| A1 | treatment | run1 |
| A2 | treatment | run1 |
| A3 | treatment | run1 |
| B1 | treatment | run1 |
| B2 | static_resilience | run1 |
| B2 | treatment | run1 |
| B3 | treatment | run1 |
| C1 | treatment | run1 |
| C2 | static_resilience | run1 |
| C2 | treatment | run1 |

Setiap folder memuat artefak lengkap per run: log aplikasi (`backend.log`, `vision.log`, `ocr.log`, `speech.log`), ekspor database (`db_experiment_runs.csv`, `db_fault_events.csv`, `db_request_logs.csv`), snapshot kontainer (`docker_ps.txt`, `docker_stats.txt`, `snapshot_before/`, `snapshot_after/`), metadata k6 (`k6_environment.json`, `k6_summary.json`), dan probe jaringan (`network_probe_before.json`, `network_probe_after.json`).

Log transisi state gabungan seluruh 180 run tersedia di `experiments/logs/automation/state_events.jsonl`.

## Sanitasi yang Diterapkan

IP privat Docker (`172.18.0.x`) dan IP VPC internal (`10.11.2.184`) diganti `[IP-DISAMARKAN]` di seluruh file sampel. Tidak ada token, password, atau domain privat yang ditemukan pada data mentah (kredensial selalu dikonfigurasi via environment variable, tidak pernah ter-log).

## Sisa 169 Run Lainnya

Tidak disertakan karena ukuran total data mentah 180 run melebihi batas praktis repository ini.

## Alternatif

Jika diperlukan untuk keperluan akademik:

1. Lihat `raw-index.csv` untuk daftar run yang tersedia beserta statusnya.
2. Data agregat tersedia di `experiments/processed/final_summary.csv`.
3. Data mentah lengkap yang sudah disanitasi akan tersedia sebagai release asset opsional (`rama-raw-data-sanitized-v1.0.zip`) setelah proses sanitasi selesai.

## Kontak

Hubungi melalui issue pada repository ini untuk pertanyaan terkait akses data.

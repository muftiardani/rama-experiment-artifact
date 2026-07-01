# Automation

Direktori ini berisi manifest eksperimen dan skrip eksperimen terpilih yang telah disanitasi.

## manifests/

| File | Deskripsi |
|---|---|
| `vps-main-180.yaml` | Manifest eksperimen utama: 9 skenario × 2 kondisi × 10 repetisi |
| `vps-pilot.yaml` | Manifest eksperimen pilot: 4 skenario × 2 kondisi × 1 repetisi |

## experimentctl/

Subset skrip experimentctl yang relevan untuk audit metodologi:

| File | Fungsi |
|---|---|
| `runner.py` | State machine eksekusi per-run (deploy → k6 → fault → recovery → validate) |
| `fault_scheduler.py` | Injeksi fault berdasarkan tipe (cpu/memory/stop/cascade) |
| `invalidator.py` | Aturan validasi run — menentukan VALID/INVALID berdasarkan 15+ kriteria |
| `validator.py` | Validasi konfigurasi manifest dan konsistensi data |
| `statistical_analyzer.py` | Uji Wilcoxon signed-rank + koreksi Holm-Bonferroni untuk 9 skenario × 7 metrik |
| `state_machine.py` | Definisi enum State (fase run) dan RunStatus (hasil run) |
| `k6_runner.py` | Menjalankan k6 dari laptop sebagai external load generator; menulis k6_environment.json |
| `screenshot_collector.py` | Mengambil screenshot Grafana/Prometheus via Playwright; render teks ke PNG |

Catatan: skrip ini bergantung pada `Context` dan konfigurasi runtime yang tidak dipublikasikan. Skrip ditampilkan untuk audit metodologi, bukan untuk eksekusi langsung.

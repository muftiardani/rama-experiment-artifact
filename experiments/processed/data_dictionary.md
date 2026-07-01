# Kamus Data — Hasil Eksperimen RAMA

Dokumen ini mendefinisikan kolom pada semua file CSV di folder `experiments/processed/`.

## final_summary.csv

Satu baris per run eksperimen (180 baris = 9 skenario × 2 kondisi × 10 repetisi).

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `scenario` | string | ID skenario: `SS`, `A1`, `A2`, `A3`, `B1`, `B2`, `B3`, `C1`, `C2` |
| `condition` | string | Kondisi: `static_resilience` (SRB) atau `treatment` (RAMA) |
| `run_number` | int | Nomor repetisi (1–10) |
| `total` | int | Total permintaan k6 selama run |
| `full` | int | Permintaan dengan respons penuh (HTTP 200 + semua model berhasil) |
| `partial` | int | Permintaan dengan respons parsial (sebagian model berhasil) |
| `failure` | int | Permintaan gagal (HTTP 5xx atau timeout) |
| `partial_availability` | float | `(full + partial) / total` — rasio ketersediaan parsial (0–1) |
| `partial_availability_pct` | float | `partial_availability × 100` (%) |
| `error_rate_percent` | float | `failure / total × 100` (%) |
| `p95_ms` | float | Latensi persentil ke-95 (milidetik) |
| `p99_ms` | float | Latensi persentil ke-99 (milidetik) |
| `iqr_ms` | float | Interquartile range latensi (milidetik) |
| `mean_ms` | float | Rata-rata latensi (milidetik) |
| `median_ms` | float | Median latensi (milidetik) |
| `slo_violation_score` | float | Skor komposit pelanggaran SLO (0 = tidak ada pelanggaran) |
| `violation_details` | string | Deskripsi pelanggaran SLO (p95 > 30.000 ms, dsb.) |
| `tfs_seconds` | float | Time-to-Fallback Stabilization — detik hingga fallback stabil setelah fault |
| `ttr_seconds` | float | Time-to-Recovery — detik hingga sistem kembali ke operasi penuh |
| `throughput_rps` | float | Throughput rata-rata (requests per second) |
| `total_requests` | int | Alias `total` (duplikat untuk kompatibilitas) |
| `pair_id` | string | Identifier pasangan run: `{scenario}-{run_number}` |

## statistical_tests.csv

Hasil uji statistik Wilcoxon signed-rank per pasangan metrik (63 baris = 9 skenario × 7 metrik).

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `scenario` | string | ID skenario |
| `metric` | string | Nama metrik internal (misal `partial_availability_pct`) |
| `metric_label` | string | Label deskriptif (misal `PA (%)`) |
| `direction` | string | Arah yang lebih baik: `higher` atau `lower` |
| `test_method` | string | Metode uji: `wilcoxon` |
| `n_pairs` | int | Jumlah pasangan (selalu 10) |
| `w_stat` | float | Statistik W Wilcoxon |
| `u_stat` | float | Statistik U Mann-Whitney (ekuivalen) — tidak diisi; Wilcoxon signed-rank dipakai karena data berpasangan |
| `p_value` | float | Nilai p sebelum koreksi multipel |
| `effect_size_r` | float | Ukuran efek r (rank-biserial correlation) |
| `sr_median` | float | Median kondisi static_resilience (SRB) |
| `tr_median` | float | Median kondisi treatment (RAMA) |
| `relative_change_pct` | float | `(tr_median − sr_median) / sr_median × 100` (%) |
| `improved` | bool | `True` jika RAMA lebih baik sesuai arah metrik |
| `p_adj_holm` | float | Nilai p setelah koreksi Holm-Bonferroni |
| `significant` | bool | `True` jika `p_adj_holm < 0,05` |

## paired_summary.csv

Delta per pasangan run (90 baris = 9 skenario × 10 repetisi).

Setiap baris mewakili satu pasangan run (run_number yang sama dari kedua kondisi). Kolom `static_*` berisi nilai kondisi static_resilience, `treatment_*` berisi nilai kondisi treatment, dan `delta_*` berisi selisihnya.

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `scenario` | string | ID skenario |
| `run_number` | int | Nomor repetisi (1–10) |
| `pair_id` | string | Identifier pasangan: `{scenario}-{run_number}` |
| `static_p95_ms` | float | Latensi p95 kondisi static_resilience (ms) |
| `treatment_p95_ms` | float | Latensi p95 kondisi treatment (ms) |
| `delta_p95_ms` | float | Selisih p95: treatment − static (ms) |
| `delta_p95_percent` | float | Selisih p95 relatif (%) |
| `static_error_rate_percent` | float | Error rate kondisi static_resilience (%) |
| `treatment_error_rate_percent` | float | Error rate kondisi treatment (%) |
| `delta_error_rate_pp` | float | Selisih error rate (percentage point) |
| `static_pa_percent` | float | Partial availability kondisi static_resilience (%) |
| `treatment_pa_percent` | float | Partial availability kondisi treatment (%) |
| `delta_pa_pp` | float | Selisih PA (percentage point) |
| `static_tfs_seconds` | float | TFS kondisi static_resilience (s) |
| `treatment_tfs_seconds` | float | TFS kondisi treatment (s) |
| `delta_tfs_seconds` | float | Selisih TFS (s) |
| `static_ttr_seconds` | float | TTR kondisi static_resilience (s) |
| `treatment_ttr_seconds` | float | TTR kondisi treatment (s) |
| `delta_ttr_seconds` | float | Selisih TTR (s) |
| `static_slo_score` | float | Skor SLO kondisi static_resilience |
| `treatment_slo_score` | float | Skor SLO kondisi treatment |
| `delta_slo_score` | float | Selisih skor SLO |

## Catatan Presisi Float

Nilai float Python 64-bit dapat menghasilkan pembulatan artefak pada desimal terakhir. Contoh: `7.635` tersimpan sebagai `7.634999...` sehingga dibulatkan ke `7.63` (bukan `7.64`). Ini bukan kesalahan data — gunakan pembulatan Python standar (`round(x, 2)`) untuk konsistensi.

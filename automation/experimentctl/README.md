# experimentctl — Subset untuk Audit Metodologi

File-file berikut dipilih karena secara langsung membuktikan mekanisme eksperimen RAMA:

- **`runner.py`** — Mengimplementasikan state machine per-run: deploy kondisi, jalankan k6 (concurrent dengan fault), tunggu recovery, inline invalidation. Bagian kunci: guard `RunStatus.RUNNING` sebelum set `FAILED_K6`, timeout k6 1800s.
- **`fault_scheduler.py`** — Menjalankan injeksi fault sesuai tipe skenario. Menjamin `fault_finished` selalu tercatat via try-finally meski terjadi exception.
- **`invalidator.py`** — Mendefinisikan 15+ aturan invalidasi run (request count, fault events, OOM, DB precheck, network probe, dsb.). Aturan ini menentukan apakah sebuah run dihitung VALID dalam analisis.
- **`validator.py`** — Memvalidasi konsistensi data hasil eksperimen sebelum analisis statistik.
- **`statistical_analyzer.py`** — Menjalankan uji Wilcoxon signed-rank dengan koreksi Holm-Bonferroni pada 63 pasangan metrik (9 skenario × 7 metrik). Menghasilkan `statistical_tests.csv`.
- **`state_machine.py`** — Mendefinisikan enum `State` (fase run: DEPLOY_CONDITION, INJECT_FAULT, RECOVER, dsb.) dan `RunStatus` (SUCCESS, FAILED_K6, INVALID_DATA, dsb.).
- **`k6_runner.py`** — Menjalankan k6 dari laptop sebagai external load generator. Menulis `k6_environment.json` (lokasi, timeout, versi k6) untuk verifikasi invalidator.
- **`screenshot_collector.py`** — Mengambil screenshot Grafana dashboard dan Prometheus /targets via Playwright (headless Chromium). Digunakan untuk mengumpulkan bukti observabilitas per run.

File ini bukan bagian dari package yang dapat dieksekusi langsung — dependensi runtime (`Context`, manifest, SSH client) tidak dipublikasikan.

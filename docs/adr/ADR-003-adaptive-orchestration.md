# ADR-003: Adaptive Orchestration via Rule-Based State Machine

**Status:** Diterima  
**Tanggal:** 2026-04  
**Konteks:** RAMA membutuhkan mekanisme untuk mendeteksi degradasi worker dan menyesuaikan perilaku sistem secara otomatis.

---

## Konteks

Tanpa orkestasi adaptif, backend hanya bisa menunggu timeout gRPC untuk mengetahui bahwa sebuah worker turun — setiap request harus menunggu penuh sebelum diarahkan ke fallback. Pendekatan ini tidak cocok untuk SLO latensi rendah di lingkungan single-node.

Dua pendekatan dipertimbangkan:

1. **Reactive only**: circuit breaker per-request, tanpa background monitoring.
2. **Proactive + reactive** (dipilih): background health-check cycle + circuit breaker per-worker.

## Keputusan

`OrchestratorService` menjalankan loop background (`HealthCheckCycle`) yang secara periodik memanggil endpoint `HealthCheck` gRPC setiap worker (default 15 detik). Hasil health check dipetakan ke tiga status: `HEALTHY`, `DEGRADED`, `UNHEALTHY`.

`SystemState` (status ketiga worker + `FallbackLevel` masing-masing) disimpan di Redis sebagai JSON dengan TTL 5 menit, sehingga state tetap tersedia antar restart container backend tanpa state hilang.

Setiap worker memiliki **circuit breaker** (3-state: `CLOSED`→`OPEN`→`HALF_OPEN`) dengan parameter berbeda antara kondisi `static_resilience` (baseline) dan `treatment` (RAMA) — dikonfigurasi via manifest eksperimen.

Aturan kritis implementasi circuit breaker:

- Health check hanya memanggil `RecordFailure()` — tidak pernah me-reset breaker.
- `RecordFailure()` **tidak memperbarui `lastFailure`** saat state `OPEN`, sehingga timer `ResetTimeout` tidak ter-reset oleh health check periodik (yang akan membuat breaker terjebak `OPEN` selamanya).
- Transisi `OPEN`→`HALF_OPEN` didorong oleh `Allow()` setelah `ResetTimeout` berlalu.
- Transisi `HALF_OPEN`→`CLOSED` hanya dipicu oleh `RecordSuccess()` dari request nyata yang berhasil.

`IsWorkerAvailable(worker)` digunakan oleh `ai_service.go` sebelum setiap panggilan gRPC; mengembalikan `true` selalu pada kondisi baseline (`cbEnabled=false`).

## Konsekuensi

**Positif:**
- Deteksi kegagalan proaktif: breaker terbuka sebelum request pengguna timeout, mengurangi latensi ekor (TFS lebih pendek di skenario B2).
- Redis sebagai shared state memungkinkan backend multi-replica membaca kondisi worker yang sama tanpa race condition.
- Pemisahan health-check failure dan request failure mencegah false recovery: breaker hanya ditutup setelah request nyata berhasil.

**Negatif:**
- Ketergantungan pada Redis: jika Redis turun, `GetCurrentState` gagal dan backend default ke `UNHEALTHY` (fail-safe, bukan fail-open).
- Interval health check 15 detik menghasilkan jendela deteksi hingga 15 detik setelah worker turun sebelum breaker terbuka dari health check — request dalam jendela ini tetap mencoba ke worker yang sudah turun (dikurangi oleh `RecordFailure` dari request yang gagal).

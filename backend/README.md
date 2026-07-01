# Backend (Go) — Source Excerpt

Lima komponen inti mekanisme resiliensi RAMA, diekstrak dari `temandifa-backend/internal/`:

| File | Fungsi |
|---|---|
| `config/config.go` | Konfigurasi eksperimen; validasi konsistensi mode saat startup |
| `services/ai_service.go` | Orkestrasi panggilan ke AI worker (retry, cache, circuit breaker) |
| `services/circuit_breaker.go` | Circuit breaker 3-state (`CLOSED`/`OPEN`/`HALF_OPEN`) |
| `services/fallback_service.go` | Matriks fallback kondisi treatment vs. static_resilience |
| `services/orchestrator.go` | Health check cycle dan state per worker |
| `services/response_classifier.go` | Klasifikasi respons `full`/`partial`/`failure` |

Bukan full buildable codebase — lihat [`REPRODUCIBILITY.md`](../REPRODUCIBILITY.md#catatan-struktur-kode) untuk daftar dependency internal yang tidak dipublikasikan.

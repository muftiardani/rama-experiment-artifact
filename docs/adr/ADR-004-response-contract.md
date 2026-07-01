# ADR-004: Three-Tier Response Contract (full / partial / failure)

**Status:** Diterima  
**Tanggal:** 2026-04  
**Konteks:** RAMA harus mendefinisikan kontrak respons yang eksplisit agar evaluasi partial availability dapat dilakukan secara deterministik dan dapat direplikasi.

---

## Konteks

Sistem multimodal dapat menghasilkan hasil yang "sebagian benar": misalnya vision berhasil tetapi speech gagal. Tanpa kontrak eksplisit, evaluasi ketersediaan menjadi ambigu — apakah respons parsial dihitung sebagai "tersedia" atau "gagal"?

Selain itu, kontrak harus membedakan perilaku antara kondisi eksperimen:
- **Baseline (static_resilience)**: tidak ada context-aware fallback — kegagalan satu worker = kegagalan total.
- **Treatment (RAMA)**: fallback aktif — kegagalan sebagian worker menghasilkan respons parsial, bukan failure.

## Keputusan

`ResponseClassifier` menetapkan tiga kategori respons mutually exclusive:

| Kategori | Kondisi |
|---|---|
| `full` | Semua worker yang diminta berhasil (`successCount == total`) |
| `partial` | Sebagian berhasil, fallback aktif, kondisi = `treatment` |
| `failure` | Semua gagal, atau fallback tidak aktif, atau kondisi = `static_resilience` |

`WorkerOutput` (payload ke klien) memiliki field `status`: `"success"` atau `"unavailable"`. Data per-worker hanya diisi jika status `"success"`.

**Aturan khusus SRB:** Jika kondisi `static_resilience` menghasilkan `partial` (yang tidak seharusnya terjadi karena `FallbackEnabled=false`), kategori dioverride ke `failure` dan `InvalidReason` diisi `INVALID_STATIC_BASELINE_PARTIAL`. Run yang menghasilkan flag ini ditandai invalid oleh `invalidator.py` dan dikecualikan dari analisis statistik.

> **Catatan implementasi:** Kode backend (`config.go`) mendefinisikan konstanta `ExperimentModeAblationBaseline = "baseline"` sebagai alias backward-compatibility untuk `static_resilience`. Konstanta ini digunakan di `response_classifier.go` sehingga kedua nilai kondisi diklasifikasikan identik sebagai SRB. Tidak ada run dengan kondisi `baseline` dalam eksperimen 180 run yang dilaporkan — semua run menggunakan `static_resilience` atau `treatment` sesuai manifest.

`FallbackInput.FallbackEnabled` adalah satu-satunya switch yang membedakan perilaku treatment vs. baseline di layer fallback — dikontrol via environment variable `ENABLE_CONTEXT_AWARE_FALLBACK` yang di-set oleh manifest eksperimen per kondisi.

## Konsekuensi

**Positif:**
- Definisi `partial_availability = (full + partial) / total` menjadi deterministik dan dapat dihitung langsung dari log per-request.
- Aturan SRB (override ke `failure` + `INVALID_STATIC_BASELINE_PARTIAL`) mencegah data korup masuk ke analisis statistik jika ada bug konfigurasi pada run baseline.
- Kontrak yang eksplisit memudahkan audit: setiap respons memiliki `response_category` yang tercatat di log.

**Negatif:**
- Kategori `partial` hanya ada di kondisi treatment — perbandingan langsung distribusi kategori antara kondisi tidak bermakna (baseline selalu `full` atau `failure`).
- Definisi "partial" bergantung pada daftar `RequestedServices` yang dikirim klien, bukan pada ketersediaan absolut worker — jika klien tidak meminta suatu worker, kegagalan worker tersebut tidak tercermin dalam kategori respons.

# Security and Sanitization Policy

Repository ini adalah paket artefak akademik yang telah disanitasi.

## Informasi yang Tidak Dipublikasikan

Repository ini tidak memuat:

- Password.
- Token.
- JWT secret.
- Private key.
- API key.
- IP publik.
- Private IP internal.
- Domain privat.
- URL repository privat.
- Dump database.
- Log mentah penuh yang belum diperiksa.
- Credential dashboard atau server.

## Bentuk Sanitasi

Nilai sensitif diganti dengan:

```
***disamarkan***
[disamarkan]
[IP-DISAMARKAN]
[backend_url disamarkan]
[repositori privat tidak dicantumkan]
[path disamarkan]
```

## Pelaporan Masalah

Jika ditemukan informasi sensitif yang tidak sengaja terbuka, segera laporkan melalui issue pada repository ini. Hapus file terkait, rotate secret pada sistem asli, dan buat commit perbaikan.

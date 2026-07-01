# Skrip Recovery

`start_all.sh` — memulihkan worker setelah fase fault selesai: restart container yang dihentikan/tertekan, polling health check hingga worker siap, dan mencatat event `recovery_started`/`recovery_completed` ke database eksperimen untuk perhitungan TTR.

Dijalankan oleh `automation/experimentctl/runner.py` setelah fase fault selesai, sebelum jendela observasi pasca-recovery dimulai.

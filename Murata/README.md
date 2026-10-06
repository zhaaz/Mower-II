# Murata SCH16T-K01

Integration des Murata-Sensors als Ersatz fuer den KVH DSP-3100.

Der Arduino muss mit 115200 Baud Zeilen in diesem Format senden:

```text
time_us;gyro_z_dps;yaw_raw_deg
```

- `sch16t.py`: serieller Treiber, Zeitstempel-Ueberlauf, Drift und Nullpunkt
- `murata_state.py`: thread-sicher uebertragener Anwendungszustand
- `murata_worker.py`: Queue-basierte Schnittstelle fuer die GUI

Unterstuetzte Worker-Kommandos: `connect`, `disconnect`, `reset_angle`,
`determine_drift`, `cancel_drift`, `set_drift` und `stop`.

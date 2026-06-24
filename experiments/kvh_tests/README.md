# KVH DSP-3100 Test

Experimenteller Teststand fuer den KVH DSP-3100.

## Dateien

- `dsp3100.py` - angepasste Sensorklasse ohne direkte Print-Ausgaben
- `kvh_dsp_state.py` - Statusmodell
- `kvh_dsp_worker.py` - Queue-basierter Worker
- `kvh_test_gui.py` - einfache Tkinter-Test-GUI

## Start

Aus dem Projektroot:

```powershell
python .\experiments\kvh_tests\kvh_test_gui.py
```

## Default

- Port: COM6
- Baudrate: 375000
- seriell: 8 Datenbits, Odd Parity, 1 Stopbit

## Testablauf

1. KVH anschliessen
2. Port eintragen
3. Connect
4. Winkel beobachten
5. Sensor drehen und Rate/Winkel pruefen
6. Winkel 0 testen
7. Drift bestimmen nur bei ruhig stehendem Sensor testen

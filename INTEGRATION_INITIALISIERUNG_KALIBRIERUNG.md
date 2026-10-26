# Integration: Tracker-Standpunkt und Kalibrierungsdialoge

## 1. ZIP entpacken

Im Projektordner in der PyCharm-Konsole:

```powershell
$zip = "$env:USERPROFILE\Downloads\Mower-II-Initialisierung-Kalibrierungsdialoge-v1.zip"
Expand-Archive -LiteralPath $zip -DestinationPath . -Force
```

## 2. Patch prüfen und anwenden

```powershell
git apply --check ".\Mower-II-Initialisierung-Kalibrierungsdialoge-v1.patch"
git apply ".\Mower-II-Initialisierung-Kalibrierungsdialoge-v1.patch"
```

Den zweiten Befehl nur ausführen, wenn die Prüfung keine Fehlermeldung ausgibt.

## 3. Syntax prüfen

```powershell
python -m py_compile App\mower_operator_app.py App\dialogs\system_initialization_dialog.py App\dialogs\marker_offset_calibration_dialog.py
```

Keine Ausgabe bedeutet, dass die Syntax korrekt ist.

## 4. Funktion prüfen

Vor dem Test kontrollieren, ob `config\mower_config.json` im Abschnitt `paths` den gewünschten Standpunkt enthält:

```json
"paths": {
    "tracker_station_file": "data/tracker_station.txt",
    "log_dir": "logs",
    "measurement_plans_dir": "measurement_plans"
}
```

Relative Pfade werden vom Projektverzeichnis aus aufgelöst; absolute Pfade bleiben unverändert.

Bei **System → Initialisieren** erscheint jetzt nach `Tracker UDP starten` der zusätzliche Schritt `Tracker-Standpunkt laden`. Fehlt die Datei oder enthält sie keine gültigen XYZ-Koordinaten, wird die Initialisierung abgebrochen und die Ursache im Status und Log ausgegeben.

Anschließend unter **System → Marker-/Reflektoroffset kalibrieren** prüfen:

- Hinweistext enthält `Der Wagen kann nun wegbewegt werden.`
- Der Button im Vorbereitungsdialog heißt `Weiter` und ist kompakt zentriert.
- Die Fenster `Manuelle Messung P1` bis `P5` sind kleiner.
- `Messen` und `Abbrechen` sind kompakt und zentriert.

## Geänderte Dateien

- `App/mower_operator_app.py`
- `App/dialogs/system_initialization_dialog.py`
- `App/dialogs/marker_offset_calibration_dialog.py`
- `docs/PROJEKTUEBERSICHT.md`

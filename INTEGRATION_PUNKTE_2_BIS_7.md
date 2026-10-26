# Mower II – Integration der Punkte 2 bis 7

Dieses Paket enthält bewusst einen Git-Patch statt vollständiger Python-Dateien. Dadurch bleiben die bereits lokal umgesetzten Änderungen an der Murata-Filterung (Punkt 1) erhalten.

## 1. Aktuellen Stand sichern

Im Projektordner in der PyCharm-Konsole:

```powershell
git status
git add .
git commit -m "Murata-Filterung abgeschlossen"
```

Falls Git meldet, dass nichts zu committen ist, kann direkt mit Schritt 2 fortgefahren werden.

## 2. ZIP in das Projekt entpacken

Wenn die ZIP im Download-Ordner liegt:

```powershell
$zip = "$env:USERPROFILE\Downloads\Mower-II-Punkte-2-bis-7-v1.zip"
Expand-Archive -LiteralPath $zip -DestinationPath . -Force
```

## 3. Patch zunächst prüfen und danach anwenden

```powershell
git apply --check ".\Mower-II-Punkte-2-bis-7.patch"
git apply ".\Mower-II-Punkte-2-bis-7.patch"
```

Der zweite Befehl darf erst ausgeführt werden, wenn der erste keine Fehlermeldung ausgibt. Bei einem Konflikt nichts erzwingen; dadurch bleiben die lokalen Änderungen unverändert.

## 4. Optionale Werte in `config/mower_config.json`

Die Python-Config enthält funktionierende Standardwerte. Damit die neuen Werte bequem in der JSON geändert werden können, diese Einträge im vorhandenen Abschnitt `transformation` ergänzen. Auf ein Komma nach dem vorherigen Eintrag achten:

```json
"calibration_points": [
    ["K1", 100.0, 100.0],
    ["K2", 100.0, 350.0],
    ["K3", 350.0, 350.0],
    ["K4", 400.0, 100.0],
    ["K5", 200.0, 200.0]
],
"calibration_random_radius_mm": 50.0,
"minimum_required_measurements": 4,
"min_geometry_rank": 2,
"allow_scale": true,
"max_scale_deviation": 0.0005
```

`tracker.capture_timeout_s` ist bereits der zentrale Timeoutwert und wird nun auch vom Transformationsablauf verwendet.

## 5. Syntax und Programmstart prüfen

```powershell
python -m py_compile config\mower_config.py Transformation\trafo_workflow.py App\dialogs\trafo_dialog.py App\services\project_file.py App\mower_operator_app.py
python App\mower_operator_app.py
```

Danach insbesondere einmal eine Transformation starten und kontrollieren, dass Kalibrierpunkte, Timeout, Maßstab und Qualitätsfreigabe wie gewünscht arbeiten.

## Enthaltene Änderungen

- Tracker-Messzeitlimit wird aus der Config übernommen.
- Kalibrierpunkte, Zufallsradius und Maßstabsoptionen sind konfigurierbar.
- Zufallspunkte werden vor der Fahrt gegen den XY-Arbeitsraum geprüft.
- Der Maßstab wird gegen `max_scale_deviation` geprüft; außerhalb davon lautet die Bewertung `PRUEFEN (MASSSTAB)`.
- Sicherheits- und Plausibilitätsprüfung der Config beim Programmstart.
- Fehler beim Laden optionaler Programmteile werden nicht mehr lautlos verschluckt, sondern protokolliert.
- Projektdateien speichern einen erweiterten Einstellungs-Snapshot.
- Die Projektübersicht dokumentiert die neuen Einstellungen und Grenzwerte.

# Integration: Z-Homing vor jeder Markierung

## 1. Aktuellen Stand sichern

```powershell
git status
git add .
git commit -m "Stand vor Z-Homing je Markierung sichern"
```

## 2. ZIP im Projektordner entpacken

```powershell
$zip = "$env:USERPROFILE\Downloads\Mower-II-Z-Homing-vor-jeder-Markierung-v1.zip"
Expand-Archive -LiteralPath $zip -DestinationPath . -Force
```

## 3. Patch prüfen und anwenden

```powershell
git apply --check ".\Mower-II-Z-Homing-vor-jeder-Markierung-v1.patch"
git apply ".\Mower-II-Z-Homing-vor-jeder-Markierung-v1.patch"
```

Der zweite Befehl darf erst ausgeführt werden, wenn die Prüfung keine Fehlermeldung ausgibt.

## 4. JSON-Einstellung ergänzen

Im Abschnitt `xyz` der Datei `config\mower_config.json` ergänzen:

```json
"home_z_before_each_marking": true
```

Beispiel für das Ende des Abschnitts:

```json
"tolerance_mm": 0.05,
"home_z_before_transformation": true,
"home_z_before_each_marking": true
```

Wenn der Eintrag fehlt, ist das Z-Homing durch den Python-Standardwert ebenfalls aktiviert. Mit `false` kann es gezielt abgeschaltet werden.

## 5. Prüfung

```powershell
python -m py_compile config\mower_config.py XYZ_Robot\xyz_robot_worker.py App\services\project_file.py App\mower_operator_app.py
python App\mower_operator_app.py
```

Beim Start einer Markierung muss das Programm jetzt jeweils folgende Meldungen protokollieren:

```text
Z-Homing vor Markierung gestartet
Fahre nach Z-Homing vor Markierung auf Z_TRAVEL=... mm
Z-Homing vor Markierung abgeschlossen
```

Danach zwei Markierungen nacheinander testen. Vor beiden Markierungen muss ein separates Z-Homing stattfinden.

## Technischer Umfang

- Z-Homing zentral im XYZ-Worker unmittelbar vor jedem `mark_point`.
- Gilt dadurch auch für Test- und Kalibriermarkierungen.
- Nach dem Homing wird zuerst `Z_TRAVEL` angefahren.
- Bestehendes vollständiges XYZ-Homing bleibt Voraussetzung.
- Configwert wird validiert, im Configfenster angezeigt und im Projekt-Snapshot gespeichert.

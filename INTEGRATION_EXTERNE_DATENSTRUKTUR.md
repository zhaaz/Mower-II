# Integration: externe Datenstruktur und EXE-Build

## 1. Aktuellen Stand sichern

```powershell
git status
git add .
git commit -m "Stand vor externer Datenstruktur sichern"
```

## 2. ZIP entpacken und Patch anwenden

```powershell
$zip = "$env:USERPROFILE\Downloads\Mower-II-Externe-Datenstruktur-v1.zip"
Expand-Archive -LiteralPath $zip -DestinationPath . -Force

git apply --check ".\Mower-II-Externe-Datenstruktur-v1.patch"
git apply ".\Mower-II-Externe-Datenstruktur-v1.patch"
```

Den zweiten `git apply`-Befehl nur ausführen, wenn die Prüfung keine Fehlermeldung ausgibt.

## 3. Bestehende Daten einmalig in die neue Struktur verschieben

Den folgenden Block vollständig im Projektordner ausführen:

```powershell
New-Item -ItemType Directory -Force -Path `
    ".\data\config", `
    ".\data\tracker", `
    ".\data\messungen\kalibrierung", `
    ".\data\messungen\messplaene", `
    ".\data\projekte", `
    ".\data\logs" | Out-Null

if ((Test-Path ".\config\mower_config.json") -and -not (Test-Path ".\data\config\mower_config.json")) {
    Move-Item ".\config\mower_config.json" ".\data\config\mower_config.json"
}

if ((Test-Path ".\data\tracker_station.txt") -and -not (Test-Path ".\data\tracker\tracker_station.txt")) {
    Move-Item ".\data\tracker_station.txt" ".\data\tracker\tracker_station.txt"
}
```

Beim ersten Programmstart werden bekannte alte Pfade in der JSON automatisch aktualisiert. Individuelle COM-Ports, Kalibrierwerte und Schwellwerte bleiben erhalten.

## 4. Syntax und Programmstart prüfen

```powershell
python -m py_compile config\mower_config.py App\mower_operator_app.py App\dialogs\system_initialization_dialog.py App\dialogs\marker_offset_calibration_dialog.py
python App\mower_operator_app.py
```

Unter der Configanzeige muss als Datei jetzt `data\config\mower_config.json` erscheinen.

Wenn der konfigurierte Tracker-Standpunkt fehlt, wird die Initialisierung mit einer Warnung fortgesetzt. ARN-Referenz und ARN-Aktivierung werden in diesem Fall sicher übersprungen.

## 5. EXE bauen

PyInstaller muss nur einmal installiert werden:

```powershell
python -m pip install pyinstaller
```

Danach genügt künftig:

```powershell
.\build_mower_operator.ps1
```

Falls Windows das Skript blockiert:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\build_mower_operator.ps1
```

Die fertige Anwendung liegt anschließend unter:

```text
dist\MowerOperator\MowerOperator.exe
```

Das Buildskript sichert bei einem erneuten Build automatisch den vorhandenen Ordner `dist\MowerOperator\data` und stellt ihn danach wieder her. Einstellungen, Messungen, Projekte und Logs werden deshalb nicht überschrieben.

Eine ausführliche Erklärung steht nach dem Patch in `docs\EXE_ERSTELLEN.md`.

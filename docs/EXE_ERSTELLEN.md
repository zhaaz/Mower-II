# Mower Operator als EXE erstellen

Das PowerShell-Skript `build_mower_operator.ps1` übernimmt den vollständigen Build. Es erzeugt die EXE, legt die externe Datenstruktur an und schützt den Datenordner bei späteren Neubauten.

## Einmalige Vorbereitung

PyCharm öffnen und unten das Terminal starten. Das Terminal muss sich im Projektordner `Mower_II` befinden. PyInstaller einmalig in der virtuellen Umgebung installieren:

```powershell
python -m pip install pyinstaller
```

## EXE bauen

Im Projektordner ausführen:

```powershell
.\build_mower_operator.ps1
```

Falls Windows die Ausführung von PowerShell-Skripten in diesem Terminal blockiert:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\build_mower_operator.ps1
```

`-Scope Process` gilt nur für das aktuell geöffnete Terminal und verändert die dauerhafte Windows-Einstellung nicht.

## Ergebnis

Nach erfolgreichem Build befindet sich die Anwendung hier:

```text
dist\MowerOperator\MowerOperator.exe
```

Der komplette Ordner sieht so aus:

```text
dist\MowerOperator\
├── MowerOperator.exe
├── _internal\
└── data\
    ├── config\mower_config.json
    ├── tracker\tracker_station.txt
    ├── messungen\kalibrierung\
    ├── messungen\messplaene\
    ├── projekte\
    └── logs\
```

Zum Kopieren auf einen anderen Rechner muss immer der vollständige Ordner `dist\MowerOperator` übertragen werden. Die EXE allein reicht nicht.

## Was das Buildskript automatisch macht

1. Es verwendet bevorzugt `.venv\Scripts\python.exe`.
2. Es prüft, ob PyInstaller installiert ist.
3. Falls bereits eine gebaute Anwendung existiert, sichert es deren `data`-Ordner vorübergehend.
4. Es erstellt `MowerOperator.exe` und `_internal` neu.
5. Es stellt den bisherigen `data`-Ordner wieder her.
6. Beim ersten Build erzeugt es die benötigten Datenordner und kopiert Config sowie Trackerdatei aus dem Projekt.

Dadurch bleiben Einstellungen, Projekte, Messungen und Logs auch bei einem erneuten Build erhalten.

## Welche Dateien bearbeitet werden dürfen

- Einstellungen: `data\config\mower_config.json`
- Tracker-Standpunkt: `data\tracker\tracker_station.txt`
- Messpläne: `data\messungen\messplaene\`

Der Ordner `_internal` enthält ausschließlich technische Programmbestandteile und sollte nicht manuell verändert werden.

## Configänderungen nach dem Build

Eine Änderung an der Config im Python-Projekt verändert nicht automatisch die Config einer bereits gebauten EXE. Für die laufende EXE wird diese Datei verwendet:

```text
dist\MowerOperator\data\config\mower_config.json
```

Bei einem erneuten Build bleibt diese vorhandene EXE-Config absichtlich erhalten. So werden maschinenspezifische COM-Ports und Kalibrierwerte nicht überschrieben.

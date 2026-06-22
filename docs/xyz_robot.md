# XYZ-Roboter System – Vollständige Dokumentation

Version: Mai 2026
Basierend auf:

* `xyz_robot.py`
* `xyz_robot_worker.py`
* `xyz_robot_panel_worker.py`
* `xyz_robot_state.py`
* `component_event.py`
* `marker_shapes.py`
* `stroke_font.py`

---

# 1. Systemübersicht

Das System steuert einen XYZ-Markierroboter über serielle Kommunikation mittels G-Code.

Die Hardware basiert auf:

* SKR 3 Controllerboard
* Marlin-artiger Firmware
* serieller Kommunikation via USB
* XYZ-Kinematik
* Markierwerkzeug mit definierter Z-Markierhöhe

Die Software ermöglicht:

* Verbindungsmanagement
* Homing
* absolute und relative Bewegungen
* Positionsabfrage
* Markierung geometrischer Formen
* Textmarkierung mit Stroke-Font
* Punktmarkierung mit Beschriftung
* GUI-Steuerung
* threadbasierte Befehlsverarbeitung

---

# 2. Softwarearchitektur

Das System ist in drei Ebenen aufgebaut.

---

## 2.1 Hardware-Ebene – `XYZRobot`

Datei:

```text
xyz_robot.py
```

Aufgaben:

* serielle Kommunikation
* G-Code Versand
* Positionsverwaltung
* Bewegungslogik
* Sicherheitsprüfungen
* Markierfunktionen
* Geometrieumrechnung

Die Klasse arbeitet vollständig blockierend.

Sie stellt die eigentliche Hardware-API dar.

---

## 2.2 Worker-Ebene – `XYZRobotWorker`

Datei:

```text
xyz_robot_worker.py
```

Aufgaben:

* Threading
* Queue-basierte Befehlsverarbeitung
* Zustandsverwaltung
* Fehlerbehandlung
* Eventsystem
* GUI-Entkopplung

Die GUI kommuniziert niemals direkt mit der Hardwareklasse.

---

## 2.3 GUI-Ebene – `XYZRobotPanelWorker`

Datei:

```text
xyz_robot_panel_worker.py
```

Aufgaben:

* Benutzeroberfläche
* Bedienung
* Loganzeige
* Statusanzeige
* Jogging
* Punktmarkierung

GUI basiert auf:

```python
customtkinter
```

---

# 3. Arbeitsraum

Alle Koordinaten werden in Millimeter angegeben.

---

## 3.1 Achsgrenzen

| Achse | Minimum | Maximum |
| ----- | ------: | ------: |
| X     |     0.0 |   500.0 |
| Y     |     0.0 |   450.0 |
| Z     |   150.0 |   200.0 |

---

# 4. Z-Höhenkonzept

Der Roboter arbeitet mit drei definierten Z-Höhen.

## 4.1 Z_MARK

```python
Z_MARK = 169.0
```

Werkzeug unten.

## 4.2 Z_CLEAR

```python
Z_CLEAR = 172.0
```

Werkzeug leicht angehoben.

## 4.3 Z_TRAVEL

```python
Z_TRAVEL = 178.0
```

Sichere Verfahrhöhe.

---

# 5. Feedrates

Einheit:

```text
mm/min
```

## 5.1 Standardwerte

| Parameter                | Wert |
| ------------------------ | ---: |
| DEFAULT_FEEDRATE_XY      | 6000 |
| DEFAULT_FEEDRATE_Z       |  900 |
| DEFAULT_FEEDRATE_MARKING | 2000 |

---

# 6. Verbindungssystem

## 6.1 Verbindung herstellen

```python
robot = XYZRobot(
    port="COM5",
    baudrate=115200,
    timeout=1.0
)

robot.connect()
```

## 6.2 Verbindung schließen

```python
robot.disconnect()
```

## 6.3 Verbindungsstatus

```python
robot.is_connected
```

---

# 7. G-Code Kommunikation

Die Klasse kommuniziert ausschließlich über:

```python
send_gcode()
```

## 7.1 Ablauf

1. G-Code senden
2. Zeilenweise Antwort lesen
3. Warten auf:

   * `ok`
   * `error`
   * Timeout

---

# 8. Homing

## 8.1 Vollständiges Homing

```python
robot.homing()
```

Sendet:

```gcode
G28
```

Danach:

```python
_is_homed = True
```

## 8.2 Einzelachsen

```python
robot.homing_x()
robot.homing_y()
robot.homing_z()
```

Wichtig:

Diese Methoden setzen NICHT `_is_homed = True`.

---

# 9. Sicherheitslogik

Vor Bewegungen werden Prüfungen durchgeführt.

## 9.1 Homing-Zwang

Vor jeder Bewegung:

```python
_require_homed()
```

## 9.2 Arbeitsraumprüfung

Alle absoluten Zielkoordinaten werden validiert.

## 9.3 Relative Bewegungen

Relative Bewegungen:

1. lesen aktuelle Position
2. berechnen Zielposition
3. prüfen Zielposition

## 9.4 Kreisprüfung

Kreise werden vollständig auf Arbeitsraum geprüft.

---

# 10. Bewegungen

## 10.1 Absolute Bewegung

```python
robot.move_absolute(
    x=100,
    y=200,
    z=180,
    feedrate=6000
)
```

## 10.2 Relative Bewegung

```python
robot.move_relative(
    dx=10,
    dy=-5
)
```

## 10.3 Positionsabfrage

```python
position = robot.get_current_position()
```

Rückgabe:

```python
{
    "X": 100.0,
    "Y": 200.0,
    "Z": 178.0
}
```

---

# 11. Convenience-Methoden

## 11.1 Z-Bewegungen

```python
robot.z_to_mark()
robot.z_to_clear()
robot.z_to_travel()
```

## 11.2 XY Travel

```python
robot.move_xy_travel_absolute(x=100, y=200)
```

## 11.3 XY Marking

```python
robot.move_xy_mark_absolute(x=100, y=200)
```

---

# 12. Linienmarkierung

## 12.1 Gerade Linie

```python
robot.mark_line_absolute(
    start_x=100,
    start_y=100,
    end_x=200,
    end_y=100
)
```

---

# 13. Polyline-Markierung

## 13.1 Polyline

```python
points = [
    (100, 100),
    (120, 100),
    (120, 120),
]

robot.mark_polyline_absolute(points)
```

---

# 14. Markerformen

Definiert in:

```python
MARKER_SHAPES
```

## 14.1 Verfügbare Formen

| Name         | Beschreibung          |
| ------------ | --------------------- |
| none         | keine Form            |
| plus         | Plus                  |
| cross        | diagonales Kreuz      |
| circle_point | Mittelpunktmarkierung |
| plus_circle  | Plus mit Kreis        |

---

# 15. Punktmarkierung

## 15.1 Einfacher Punkt

```python
robot.mark_point(
    x=100,
    y=200,
    size=10,
    shape="plus"
)
```

## 15.2 Punkt mit Beschriftung

```python
robot.mark_point_with_label(
    x=100,
    y=200,
    label="P101",
    marker_size=10,
    marker_shape="plus_circle",
    text_height=8
)
```

---

# 16. Textsystem

## 16.1 Stroke Font

Datei:

```text
stroke_font.py
```

Normierte Koordinaten:

```text
0.0 bis 1.0
```

## 16.2 Text markieren

```python
robot.mark_text(
    text="P101",
    x=100,
    y=100,
    height=8
)
```

## 16.3 Rotation

```python
robot.mark_text(
    text="TEST",
    x=100,
    y=100,
    height=8,
    angle_deg=45
)
```

---

# 17. Kreisbewegungen

## 17.1 Kreis markieren

```python
robot.move_circle_mark(
    x=100,
    y=100,
    radius=20
)
```

## 17.2 Kreisrichtung

| Richtung           | G-Code |
| ------------------ | ------ |
| Uhrzeigersinn      | G2     |
| Gegenuhrzeigersinn | G3     |

---

# 18. Worker-System

Datei:

```text
xyz_robot_worker.py
```

## 18.1 Zweck

Asynchrone Verarbeitung.

Die GUI bleibt responsiv.

## 18.2 Unterstützte Worker-Commands

| Command                | Beschreibung              |
| ---------------------- | ------------------------- |
| connect                | Verbindung herstellen     |
| disconnect             | Verbindung trennen        |
| read_position          | Position lesen            |
| home_all               | Homing                    |
| jog                    | relative Bewegung         |
| move_absolute          | absolute Bewegung         |
| move_absolute_verified | Bewegung mit Verifikation |
| mark_point             | Punkt markieren           |

---

# 19. Zustandsmodell

Datei:

```text
xyz_robot_state.py
```

## 19.1 Felder

| Feld        | Bedeutung          |
| ----------- | ------------------ |
| connected   | verbunden          |
| homed       | referenziert       |
| busy        | Worker beschäftigt |
| status_text | Status             |
| error_text  | Fehler             |
| x/y/z       | Position           |
| port        | COM-Port           |
| baudrate    | Baudrate           |

---

# 20. Eventsystem

Datei:

```text
component_event.py
```

## 20.1 EventLevel

```python
INFO
WARNING
ERROR
```

## 20.2 Loggingformat

```text
[12:34:56] [XYZRobot] [INFO] Verbindung hergestellt
```

---

# 21. GUI

Datei:

```text
xyz_robot_panel_worker.py
```

## 21.1 Funktionen

* COM-Port Auswahl
* Connect/Disconnect
* Homing
* Jogging
* Positionsanzeige
* Markersteuerung
* Logfenster

---

# 22. Typischer Betriebsablauf

## 22.1 Minimalbeispiel

```python
from xyz_robot import XYZRobot

robot = XYZRobot(port="COM5")

try:
    robot.connect()

    robot.homing()

    robot.move_absolute(
        x=100,
        y=200,
        z=178
    )

    robot.mark_point_with_label(
        x=100,
        y=200,
        label="P101",
        marker_shape="plus_circle"
    )

finally:
    robot.disconnect()
```

---

# 23. Wichtige Betriebsregeln

## 23.1 Immer zuerst

```python
connect()
homing()
```

## 23.2 Nie ohne Homing fahren

Die Klasse verhindert das absichtlich.

## 23.3 Vor XY-Fahrten

Immer:

```python
z_to_travel()
```

---

# 24. Bekannte Besonderheiten

## 24.1 move_relative()

Nach relativen Fahrten bleibt die Steuerung in:

```gcode
G91
```

Bis wieder:

```gcode
G90
```

gesetzt wird.

## 24.2 Einzelachsen-Homing

```python
homing_x()
homing_y()
homing_z()
```

setzen NICHT:

```python
_is_homed = True
```

---

# 25. Empfehlungen für Erweiterungen

Geeignete Erweiterungen:

* Bahnplanung
* DXF-Import
* SVG-Import
* Bahnoptimierung
* Werkzeugverwaltung
* Kamerasystem
* G-Code Export
* Simulationsmodus
* Visualisierung

---

# 26. Empfehlung für zukünftige Chats

Wenn dieses System in neuen Chats verwendet wird, sollten mindestens bereitgestellt werden:

1. diese Dokumentation
2. `xyz_robot.py`
3. optional:

   * `marker_shapes.py`
   * `stroke_font.py`

Damit kann die API korrekt verwendet werden für:

* neue Markierfunktionen
* Bewegungsplanung
* GUI-Erweiterungen
* Worker-Erweiterungen
* Fehleranalyse
* G-Code Optimierung
* Automatisierung
* Testprogramme

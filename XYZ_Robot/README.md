# SKR3 / XYZ-Roboter

## Übersicht

Dieses Verzeichnis enthält die Steuerung und GUI des XYZ-Roboters
für den Absteckwagen II.

---

# Dateien

## xyz_robot.py

Hauptklasse zur Steuerung des XYZ-Roboters.

Funktionen:
- Verbindung über Serial
- GCode Kommunikation
- Homing
- absolute / relative Bewegung
- Kreisbewegungen
- Markierung
- Schrift
- Punktmarkierung

Diese Klasse enthält keine GUI.

---

## xyz_robot_panel.py

Einbettbares GUI-Panel (CustomTkinter).

Enthält:
- Verbindung
- Status
- Position
- manuelle Achsbewegung
- Markierung
- Logging

Kann später im Hauptprogramm eingebettet werden.

Klasse:
- XYZRobotPanel(ctk.CTkFrame)

---

## xyz_robot_app.py

Eigenständiges Testprogramm für den XYZ-Roboter.

Startet:
- Hauptfenster
- XYZRobotPanel

Enthält:
- globale Hotkeys

Start:
```bash
python xyz_robot_app.py
```

---

## marker_shapes.py

Definition verschiedener Markerformen.

Aktuell:
- plus
- cross
- circle_point
- plus_circle

---

## stroke_font.py

Stroke-Font Definition für markierte Schrift.

Enthält:
- Linienzüge der Zeichen
- Skalierung erfolgt in xyz_robot.py

---

## skr_simple_test.py

Altes Testprogramm.

Nur für einfache GCode / Verbindungsversuche.
Kann später eventuell entfernt werden.

---

# Architektur

XYZRobot
↓
XYZRobotPanel
↓
XYZRobotApp / später Hauptprogramm

---

# Nächste Schritte

- Worker Thread
- Auto-Refresh Position
- Hauptprogramm
- 2D Arbeitsraumansicht
- Komponentenverwaltung
- Punktliste
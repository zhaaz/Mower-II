# Mower II – Zielarchitektur und nächste Schritte

## Ziel

Mower II soll ein modulares Steuer-, Mess- und Markiersystem
für den Absteckwagen werden.

Das System soll später:

- Roboterachsen steuern
- Lasertrackerdaten empfangen
- Transformationen berechnen
- Punkte im LT-System anfahren
- Markierungen ausführen
- DSP-Drehungen überwachen
- GYEMS-Motoren steuern
- Zustände zentral anzeigen
- Fehler und Messdaten protokollieren

---

# Grundarchitektur

```text
GUI
↓
Workflows / Services
↓
Worker / Receiver
↓
Hardwareklassen
```

Die GUI spricht nicht direkt mit Hardware.

---

# Komponentenarten

## Hardwareklassen

Enthalten nur Geräte-/Protokolllogik.

Beispiele:

```text
XYZRobot
DSP3100
GYEMSMotor
```

---

## Worker / Receiver

Kapseln Threading und Datenströme.

```text
command-driven → Worker
stream-driven  → Receiver
```

Beispiele:

```text
XYZRobotWorker
GYEMSWorker
LasertrackerReceiver
```

---

## Workflows

Beschreiben mehrstufige Abläufe.

Beispiele:

```text
TrafoWorkflow
MarkingWorkflow
HomingWorkflow
```

Workflows:
- laufen getrennt von der GUI
- liefern Statusmeldungen
- sind abbrechbar
- liefern Ergebnisobjekte

---

## Manager / Services

Halten fachlichen Zustand oder Fachlogik.

Beispiele:

```text
TrafoManager
CoordinateMapper
ComponentManager
LogManager
```

---

# Ziel-Dateistruktur

```text
Mower_II/
│
├── XYZ_Robot/
│   ├── xyz_robot.py
│   ├── xyz_robot_worker.py
│   ├── xyz_robot_state.py
│   └── xyz_robot_panel.py
│
├── Lasertracker/
│   ├── lasertracker_receiver.py
│   ├── lasertracker_state.py
│   └── lasertracker_panel.py
│
├── Transformation/
│   ├── helmert_3d.py
│   ├── trafo_manager.py
│   ├── trafo_workflow.py
│   ├── coordinate_mapper.py
│   ├── trafo_gui_test_app.py
│   ├── trafo_workflow_multitest.py
│   ├── README.md
│   └── results/
│
├── Marking/
│   ├── marking_workflow.py
│   ├── marker_offset.py
│   └── marking_panel.py
│
├── DSP/
│   ├── dsp3100.py
│   ├── dsp_worker.py
│   ├── dsp_state.py
│   └── dsp_panel.py
│
├── GYEMS/
│   ├── gyems_motor.py
│   ├── gyems_worker.py
│   ├── gyems_state.py
│   └── gyems_panel.py
│
├── Core/
│   ├── system_state.py
│   ├── component_manager.py
│   ├── log_manager.py
│   └── app_config.py
│
├── GUI/
│   ├── main_app.py
│   ├── status_bar.py
│   └── log_panel.py
│
├── workflows/
│   ├── trafo_multitest_helmert_3d.py
│   ├── trafo_validation_helmert_3d.py
│   └── archive/
│
└── docs/
    └── architecture_roadmap.md
```

---

# Aktueller Stand

## Fertig bzw. weitgehend stabil

```text
XYZ_Robot/
Lasertracker/
Transformation/
```

---

# Transformation

Aktuell vorhanden:

```text
Transformation/
├── helmert_3d.py
├── trafo_manager.py
├── trafo_workflow.py
├── trafo_gui_test_app.py
├── trafo_workflow_multitest.py
└── README.md
```

Die Transformation kann aktuell:

- 5 Kalibrierpunkte messen
- verdeckte Punkte tolerieren
- ab 4 Punkten weiterrechnen
- 4-Punkt-Fallback durchführen
- Timeout behandeln
- abgebrochen werden
- erst nach Benutzerfreigabe gültig gesetzt werden

---

# Transformation gültig / ungültig

Neue Transformationen werden zuerst nur temporär gespeichert.

Ablauf:

```text
TrafoWorkflow berechnet neue Trafo
↓
Benutzer akzeptiert
↓
TrafoManager setzt active_trafo
↓
trafo_valid = True
```

Später:

```text
DSP erkennt Drehung
↓
trafo_manager.invalidate(...)
↓
trafo_valid = False
```

---

# Nächster Entwicklungspfad

---

# Schritt 1 – CoordinateMapper

## Ziel

```text
LT-Zielkoordinate
↓
aktive Trafo
↓
Roboterkoordinate
↓
Arbeitsraumprüfung
```

Datei:

```text
Transformation/coordinate_mapper.py
```

Aufgaben:
- Tracker XYZ → Roboter XYZ
- Tracker XY auf Arbeitsebene → Roboter XY
- Prüfung Arbeitsraum
- Ergebnis mit valid / invalid / reason

---

# Schritt 2 – Punktanfahrt im LT-System

## Ziel

```text
Punkt im Trackerkoordinatensystem eingeben
↓
CoordinateMapper berechnet Roboterziel
↓
XYZ fährt Ziel an
```

Noch ohne Markierung.

---

# Schritt 3 – Markierlogik

## Ziel

```text
Roboter fährt Ziel an
↓
Markierung ausführen
```

Dateien:

```text
Marking/marking_workflow.py
Marking/marking_panel.py
```

---

# Schritt 4 – Reflektor-/Stiftspitzenoffset

## Ziel

```text
Tracker misst Reflektor
aber markiert wird mit Stift/Laser
```

Daher muss der Offset bestimmt und berücksichtigt werden.

Datei:

```text
Marking/marker_offset.py
```

---

# Schritt 5 – DSP integrieren

## Ziel

```text
DSP erkennt Drehung
↓
Trafo wird ungültig
```

Dateien:

```text
DSP/dsp3100.py
DSP/dsp_worker.py
DSP/dsp_state.py
DSP/dsp_panel.py
```

---

# Schritt 6 – GYEMS integrieren

## Ziel

- Motor ansteuern
- State anzeigen
- Fehler behandeln
- später in Workflows einbinden

Dateien:

```text
GYEMS/gyems_motor.py
GYEMS/gyems_worker.py
GYEMS/gyems_state.py
GYEMS/gyems_panel.py
```

---

# Schritt 7 – Hauptprogramm

Erst wenn:
- Trafo stabil
- LT-Punktanfahrt funktioniert
- Markierlogik grundlegend funktioniert

Dann:

```text
GUI/main_app.py
```

mit:
- XYZPanel
- LasertrackerPanel
- TrafoPanel
- MarkingPanel
- DSPPanel
- GYEMSPanel
- LogPanel
- StatusBar

---

# Wichtige Architekturregeln

## GUI spricht nicht direkt mit Hardware

Immer:

```text
GUI
↓
Workflow / Worker
↓
Hardware
```

---

## Mathematik getrennt halten

```text
helmert_3d.py
=
nur Mathematik

trafo_workflow.py
=
Mess-/Ablauflogik
```

---

## Lasertracker ist stream-driven

Der Tracker wird nicht aktiv gesteuert.

Deshalb:
- Receiver + State
- kein klassischer Command-Worker

---

## Transformation erst nach Benutzerfreigabe gültig

Neue Trafo:
- zuerst pending
- erst nach „Übernehmen“ aktiv

---

# Aktuelle Empfehlung

Nicht sofort das Gesamtprogramm bauen.

Empfohlene Reihenfolge:

```text
1. CoordinateMapper
2. LT-Punktanfahrt
3. Markierlogik
4. Offset Reflektor/Stiftspitze
5. DSP
6. GYEMS
7. Hauptprogramm
```

Der aktuelle Stand der Transformation ist stabil genug,
um jetzt die eigentliche Punktnavigation aufzubauen.
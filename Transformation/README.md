# Transformation

Dieses Verzeichnis enthält die komplette Infrastruktur zur Berechnung,
Verwaltung, Validierung und GUI-Integration der räumlichen
Helmert-Transformation zwischen:

```text
Roboterkoordinaten
↔
Lasertrackerkoordinaten
```

Die Transformation basiert auf:
- Quaternionen
- räumlicher Helmert-Transformation
- robustem Workflow
- automatischer Ausreißerbehandlung
- Workflow-/GUI-Integration

---

# Grundlagen / Referenzen

Die mathematische Grundlage der räumlichen Transformation basiert auf:

```text
Michael Lößler:
"Robuste Schätzung der Transformationsparameter
einer räumlichen Helmert-Transformation"
AVN 5/2011
```

Verwendet werden insbesondere:
- Schwerpunktreduktion
- Quaternionen zur Rotationsbestimmung
- räumliche Helmert-Transformation
- Residuen-/Qualitätsbewertung

Die aktuelle Implementierung verwendet:
- Quaternion-basierte Rotationsbestimmung
- geschlossene Lösung ohne iterative Näherungswerte
- automatische Qualitätsprüfung

Die im Paper beschriebenen robusten Verfahren
(Least-Median-Square / Reweighted-Least-Square)
wurden nicht vollständig implementiert.

Stattdessen wird aktuell ein pragmatischer robuster Ansatz verwendet:

```text
5-Punkt-Trafo
↓
falls Qualitätsgrenzen verletzt:
4-Punkt-Kombinationen testen
↓
beste gültige Kombination verwenden
```

Dadurch können:
- einzelne Ausreißer
- verdeckte Punkte
- instabile Trackerpunkte

robust behandelt werden.

---

# Überblick

```text
Transformation/
│
├── helmert_3d.py
├── trafo_manager.py
├── trafo_workflow.py
├── trafo_gui_test_app.py
├── trafo_workflow_multitest.py
│
└── results/
```

---

# Dateien

---

# helmert_3d.py

Enthält die reine Mathematik der räumlichen Helmert-Transformation.

## Funktionen

### estimate_helmert_3d(...)

Berechnet:

```text
Tracker = Translation + Scale * Rotation * Robot
```

unter Verwendung von:
- Quaternionen
- Schwerpunktreduktion
- Eigenwertproblem

## Liefert

```python
Helmert3DResult
```

mit:
- Translation
- Rotation
- Quaternion
- Maßstab
- Residuen
- RMS
- Maximalresidual

## Wichtig

Diese Datei enthält:
- KEINE GUI
- KEIN Threading
- KEIN Hardwarehandling
- KEIN Workflow

Nur Mathematik.

---

# trafo_manager.py

Verwaltet die aktuell aktive Transformation.

## Zustände

```text
active_trafo
pending_trafo
valid / invalid
```

## Workflow

Neue Trafo:

```text
Workflow berechnet Trafo
↓
pending_trafo
↓
Benutzer akzeptiert
↓
active_trafo
```

## Wichtige Funktionen

### set_pending(...)

Speichert eine berechnete Trafo temporär.

### accept_pending()

Aktiviert die pending Trafo.

### invalidate(...)

Markiert die aktive Trafo als ungültig.

Beispiel später:

```python
trafo_manager.invalidate("DSP rotation detected")
```

---

# trafo_workflow.py

Zentrale Workflowlogik zur automatischen Transformationserstellung.

Diese Datei enthält:
- Punktgenerierung
- Robotermessung
- Trackeraufnahme
- Timeoutbehandlung
- Ausreißerbehandlung
- 4-Punkt-Fallback
- Qualitätsprüfung
- Statusmeldungen
- Abbruchlogik

## Ablauf

```text
1. Zufällige Kalibrierpunkte erzeugen
2. Roboter fährt Punkte an
3. Trackerpunkte messen
4. Fehlende Punkte tolerieren
5. Helmert berechnen
6. Falls nötig:
       4-Punkt-Kombinationen testen
7. Ergebnis zurückgeben
```

---

## Robuste Eigenschaften

### Nicht messbare Punkte

Punkte können:
- verdeckt
- instabil
- nicht sichtbar

sein.

Dann:

```text
Timeout
↓
Punkt wird übersprungen
↓
Workflow läuft weiter
```

Solange:

```text
>= minimum_required_measurements
```

vorhanden sind.

---

## 4-Punkt-Fallback

Falls die 5-Punkt-Trafo die Schwellwerte nicht erfüllt:

```text
alle 4-Punkt-Kombinationen testen
↓
beste gültige Kombination verwenden
```

---

## Abbruch

Der Workflow unterstützt:

```python
workflow.cancel()
```

Abbruchpunkte:
- vor Fahrbefehlen
- während Wartephasen
- vor Trackeraufnahme
- nach Trackeraufnahme

---

## Ergebnis

```python
TrafoWorkflowResult
```

enthält:
- success
- status
- message
- trafo
- measurements
- failed_measurements
- excluded_measurement
- candidate_results
- duration_s

---

# trafo_gui_test_app.py

CustomTkinter-Testprogramm zur Integration der Transformation.

## Funktionen

### XYZ verbinden

Verbindet den XYZ-Worker.

### Tracker starten

Startet den UDP-Lasertracker-Receiver.

### Homing

Führt XYZ-Homing aus.

### Start Trafo

Öffnet den Transformationsdialog.

---

# TrafoDialog

Eigenes Fenster für die Transformation.

## Anzeige

- aktueller Status
- Fortschritt
- Logs
- Residuen
- Ausreißer
- Fehlermeldungen
- nicht messbare Punkte

## Buttons

### Abbrechen

Bricht den Workflow kontrolliert ab.

### Trafo übernehmen

Aktiviert die berechnete Transformation.

### Verwerfen

Verwirft die pending Trafo.

---

# trafo_workflow_multitest.py

Regressionstest / Stabilitätstest für den produktiven Workflow.

Wichtig:
Diese Datei nutzt:

```text
TrafoWorkflow
+
TrafoManager
```

also dieselbe Infrastruktur wie die GUI.

---

## Funktionen

Automatischer Testlauf:

```text
1. XYZ verbinden
2. Tracker starten
3. Homing
4. N Transformationen durchführen
5. Ergebnisse exportieren
```

---

## Testet

- stabile Messungen
- verdeckte Punkte
- Timeouts
- 4-Punkt-Fallback
- Workflow-Robustheit
- Qualitätskennzahlen

---

## Ergebnisse

CSV + TXT Export nach:

```text
Transformation/results/workflow_multitest/
```

---

# Designprinzipien

---

# Trennung von Mathematik und Workflow

```text
helmert_3d.py
=
nur Mathematik

trafo_workflow.py
=
Mess-/Ablauflogik
```

---

# Trennung von GUI und Hardware

GUI spricht NICHT direkt mit Hardware.

Sondern:

```text
GUI
↓
Workflow
↓
XYZWorker / LasertrackerReceiver
```

---

# Tracker ist stream-driven

Der Lasertracker:
- wird nicht aktiv gesteuert
- liefert kontinuierliche Messdaten

Deshalb:
- Receiver + State
- kein klassischer Command-Worker

---

# Transformation erst nach Benutzerfreigabe gültig

Neue Transformationen werden:
- zuerst nur pending
- erst nach "Übernehmen" aktiv

Dadurch bleibt eine funktionierende Trafo erhalten,
falls eine neue Messung fehlschlägt.

---

# Integration ins Hauptprogramm / Ausblick

Die Transformation wird später als Teil des Hauptprogramms
des Absteckwagens verwendet.

Geplanter Ablauf:

```text
1. Benutzer startet "Trafo"
2. TrafoWorkflow erzeugt neue Transformation
3. Benutzer akzeptiert Ergebnis
4. TrafoManager setzt active_trafo
5. trafo_valid = True
```

Die aktive Transformation dient anschließend zur Umrechnung:

```text
Trackerkoordinaten
↔
Roboterkoordinaten
```

für:
- automatische Navigation
- Punktanfahrt
- Absteckung
- spätere Visualisierung

---

# Geplante Invalidierung

Die Transformation besitzt später einen Gültigkeitsstatus:

```python
trafo_valid = True / False
```

Bestimmte Ereignisse können die Trafo automatisch ungültig machen:

- DSP erkennt Drehung
- mechanische Veränderung
- Neustart
- Benutzer invalidiert manuell

Dann:

```python
trafo_manager.invalidate(...)
```

und:

```text
trafo_valid = False
```

Bis eine neue Transformation erfolgreich berechnet und übernommen wurde.

---

# Geplante Hauptprogramm-Integration

Die aktuelle GUI-Testanwendung dient nur zur Entwicklung.

Später wird die Transformation integriert in:

```text
Mower II Hauptprogramm
```

mit:
- zentralem Komponentenmanagement
- gemeinsamer GUI
- Visualisierung
- Logging
- DSP/GYEMS/Tracker-Integration
- automatischer Navigation

---

# Geplante zukünftige Erweiterungen

Mögliche spätere Erweiterungen:

- zentrale Konfigurationsdatei
- Persistierung aktiver Transformation
- Trafo-Historie
- automatische Re-Kalibrierung
- Langzeitstabilitätsprüfung
- automatische Qualitätsbewertung
- 2D-/3D-Visualisierung
- automatische Tracker-/DSP-Überwachung
- erweitertes Logging

---

# Aktueller Qualitätsstand

Der Workflow erreicht aktuell typischerweise:

```text
Kalibrier-RMS:
~0.04–0.08 mm

Vorhersage-/Kontrollfehler:
~0.05–0.12 mm
```

unter realen Bedingungen.

Die Transformation arbeitet aktuell robust bei:
- verdeckten Punkten
- einzelnen Ausreißern
- instabilen Messungen
- automatischem Punktfallback

mit:
- 5-Punkt-Kalibrierung
- 4-Punkt-Fallback
- Quaternion-basierter Helmert-Transformation
- automatischer Qualitätsbewertung
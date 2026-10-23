# Mower II – Projektübersicht

Stand: 23.10.2026

## Zweck

Mower II ist die Steuerungssoftware eines mobilen Absteckwagens. Das System übernimmt Sollkoordinaten aus einer Punktdatei, bestimmt die aktuelle Lage des Wagens mithilfe eines Lasertrackers und markiert die Punkte mit einem Stift auf dem Boden.

Die wesentlichen Komponenten sind:

- Lasertracker bzw. SpatialAnalyzer zur Positionsmessung über UDP
- XYZ-Roboter zur Positionierung und Ausführung der Markierung
- Murata SCH16T-K01 mit Arduino Nano ESP32 zur Erfassung von Drehrate und relativem Gierwinkel
- GYEMS-Motor zur automatischen Ausrichtung des Reflektors auf den Lasertracker (ARN)
- Mower-Operator als zentrale Bedienoberfläche

Der Murata ersetzt im aktiven Programm den früher eingesetzten KVH DSP. Alte KVH-Verzeichnisse können noch als Bestand bzw. Referenz im Projekt vorhanden sein.

## Prinzipielles Vorgehen

1. Absteckpunkte und Lasertracker-Station werden geladen.
2. XYZ-Roboter, Lasertracker-UDP, Murata und GYEMS werden verbunden.
3. Der XYZ-Roboter wird referenziert. Beim Murata werden Drift und Nullwinkel bestimmt.
4. Vor der Transformation wird die Z-Achse erneut gehomt und auf `Z_TRAVEL` gefahren, sofern dies in der Config aktiviert ist.
5. Der XYZ-Roboter fährt die Transformationspunkte an. Der Lasertracker misst die zugehörigen Reflektorpositionen.
6. Aus Roboter- und Trackerkoordinaten wird eine räumliche Helmert-Transformation berechnet.
7. Nach Prüfung und Übernahme wird die Transformation gültig. Sollpunkte können damit in Roboterkoordinaten umgerechnet und markiert werden.
8. Ändert sich die Wagenorientierung nach der Transformation stärker als erlaubt, wird die Transformation ungültig und muss wiederholt werden.

Die Transformation verwendet normalerweise fünf Messpunkte. Sind nicht alle Punkte verwendbar oder enthält die Messung einen Ausreißer, kann mit mindestens vier Punkten weitergerechnet werden. Dabei wird die beste zulässige Vierpunktkombination gewählt.

## Programmaufbau

| Bereich | Aufgabe |
| --- | --- |
| `App/` | Hauptoberfläche, Dialoge und anwendungsnahe Services |
| `XYZ_Robot/` | Ansteuerung, Worker und Status des XYZ-Roboters |
| `Lasertracker/` | Empfang und Verarbeitung der UDP-Messdaten |
| `Murata/` | Serielle Kommunikation, Zustand, Drift- und Winkelverarbeitung |
| `GYEMS/` | Ansteuerung des Reflektormotors und ARN-Nachführung |
| `Transformation/` | Helmert-Transformation, Transformationsworkflow und Koordinatenabbildung |
| `config/` | Konfigurationsmodell und benutzerspezifische JSON-Konfiguration |
| `data/` | Stations- und weitere Projektdaten |
| `docs/` | Projektdokumentation |

Grundprinzip der Softwarearchitektur:

```text
GUI → Workflows/Services → Worker/Receiver → Hardwareklassen
```

Die GUI steuert die Hardware damit nicht unmittelbar. Zeitaufwendige Gerätezugriffe und Messabläufe laufen über Worker bzw. Workflows.

## Konfiguration

Die benutzerspezifischen Einstellungen stehen in:

```text
config/mower_config.json
```

Für normale Änderungen wie COM-Ports, Geschwindigkeiten, Markierhöhen oder Pfade wird die JSON-Datei geändert. `mower_config.py` definiert dagegen die verfügbaren Parameter und ihre Standardwerte. Änderungen werden beim Programmstart geladen; nach einer Änderung sollte das Programm neu gestartet werden.

Alle Längenangaben sind grundsätzlich in Millimetern, Winkel in Grad und Winkelgeschwindigkeiten in Grad pro Sekunde angegeben.

| Abschnitt | Inhalt |
| --- | --- |
| `xyz` | COM-Port, Baudrate, Arbeitsraumgrenzen, Fahrgeschwindigkeiten, Positionstoleranz und optionales Z-Homing vor der Transformation |
| `tracker` | UDP-Port, Zeitlimit für Punktmessungen und Reflektorradius; der Transformationsworkflow verwendet `capture_timeout_s` direkt |
| `murata` | COM-Port, Baudrate, Dauer der Driftmessung und Vorzeichen des Winkels |
| `gyems` | COM-Port, Baudrate und Motor-ID |
| `arn` | Regelverstärkung, maximale Motorgeschwindigkeit, Totband, Befehlsintervall und Drehrichtung |
| `marker` | Markierungsform und -größe, Ausrichtung, Nachmessung sowie `Z_MARK`, `Z_CLEAR` und `Z_TRAVEL` |
| `transformation` | Offset, Murata-Grenzwert, Qualitätsgrenzen, Kalibrierpunkte und Maßstabsprüfung der Transformation |
| `paths` | Pfade zur Trackerstation, zu Logs und Messplänen |

Wichtige Hinweise:

- JSON verwendet `true` und `false` in Kleinschreibung.
- Zwischen Einträgen muss ein Komma stehen; hinter dem letzten Eintrag eines Abschnitts nicht.
- Relative Pfade werden vom Projektverzeichnis aus interpretiert. Sie sind für andere Rechner meist geeigneter als absolute Pfade.
- `home_z_before_transformation: true` aktiviert das Z-Homing vor jeder Transformation.

Die Qualitätsgrenzen stehen im Abschnitt `transformation`:

```json
"very_good_rms_mm": 0.05,
"very_good_max_residual_mm": 0.10,
"good_rms_mm": 0.10,
"good_max_residual_mm": 0.20,
"ok_rms_mm": 0.25,
"ok_max_residual_mm": 0.50,
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

Beim Programmstart wird die Konfiguration auf ungültige Werte geprüft. Dazu gehören unter anderem Arbeitsraumgrenzen, Markierhöhen, positive Geschwindigkeiten und Zeiten, die Reihenfolge der Qualitätsgrenzen sowie die Transformationsparameter. Erkannte Fehler werden mit ihrer Ursache angezeigt und in die Logdatei geschrieben.

## Qualität und Freigabe der Transformation

Die Qualität wird aus den Restklaffungen der Transformationspunkte beurteilt:

- **RMS**: mittlere Gesamtgröße der Restklaffungen
- **Max**: größte Restklaffung eines einzelnen verwendeten Punktes

Für jede Qualitätsstufe müssen immer beide Bedingungen erfüllt sein:

| Anzeige | RMS | Maximalrestklaffung |
| --- | ---: | ---: |
| **SEHR GUT** | ≤ 0,05 mm | ≤ 0,10 mm |
| **GUT** | ≤ 0,10 mm | ≤ 0,20 mm |
| **OK** | ≤ 0,25 mm | ≤ 0,50 mm |
| **PRÜFEN** | darüber | darüber bzw. mindestens ein Grenzwert überschritten |

Die Qualitätsanzeige und die technische Freigabe verwenden dieselben Grenzwerte. Eine Transformation wird akzeptiert, wenn sie mindestens die Stufe **OK** erreicht:

```text
RMS ≤ ok_rms_mm UND Maximalrestklaffung ≤ ok_max_residual_mm
```

Mit den Standardwerten werden damit **SEHR GUT**, **GUT** und **OK** freigegeben. Nur **PRÜFEN** wird nicht übernommen. Werden die OK-Grenzen in der Config verändert, ändern sich Qualitätsanzeige und technische Freigabe gemeinsam.

Wenn `allow_scale` aktiviert ist, wird der Maßstab mitgeschätzt. Die Transformation wird jedoch nur akzeptiert, wenn gilt:

```text
|Maßstab - 1,0| ≤ max_scale_deviation
```

Mit dem Standardwert `0.0005` darf der Maßstab höchstens um `0,05 %` von `1,0` abweichen. Bei einer größeren Abweichung lautet die Bewertung **PRÜFEN (MASSSTAB)**. Mit `allow_scale: false` wird eine Transformation ohne Maßstabsfaktor berechnet.

Die Kalibrierpunkte werden innerhalb des konfigurierten Zufallsradius erzeugt. Vor der Fahrt wird jeder Punkt gegen die X-/Y-Arbeitsraumgrenzen geprüft. Kann keine gültige Lage erzeugt werden, wird die Transformation mit einer verständlichen Fehlermeldung beendet.

Eine erfolgreiche Berechnung wird zunächst nur als vorläufiges Ergebnis gehalten. Erst mit **Trafo übernehmen** wird sie aktiv. Die aktive Transformation wird wieder ungültig, wenn sich der Murata-Winkel gegenüber der Transformationslage um mehr als `gyro_invalid_threshold_deg` ändert. Der aktuelle Configwert beträgt `0.03°`.

## Betriebshinweise

- Vor Homing- und Transformationsfahrten muss der Bewegungsraum des XYZ-Roboters frei sein.
- Nach einer mechanischen Bewegung des Wagens ist eine neue Transformation erforderlich.
- Die Markierhöhen müssen nach Änderungen an Stift, Halterung oder Mechanik kontrolliert werden.
- Fehler, Verbindungszustände und Messabläufe werden im Programm und in den Logdateien protokolliert.
- Gespeicherte Projektdateien enthalten einen Snapshot der relevanten XYZ-, Tracker-, Marker-, ARN-, Murata- und Transformationseinstellungen.

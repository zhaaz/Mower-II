# XYZRobot - Funktionskatalog

Kurzübersicht der wichtigsten Funktionen der Klasse `XYZRobot`.

Alle Koordinaten sind in **mm**.  
Alle Geschwindigkeiten sind in **mm/min**.  
Alle Winkel sind in **Grad**.

---

# 1. Grundverwendung

```python
from xyz_robot import XYZRobot

robot = XYZRobot(port="COM5")
robot.connect()
robot.homing()

robot.mark_point_with_label(
    x=100.0,
    y=200.0,
    label="P.1053",
    marker_size=10.0,
    marker_shape="plus_circle",
    text_height=8.0,
    angle_deg=0.0
)

robot.disconnect()
```

---

# 2. Verbindung

## `connect()`

Öffnet die serielle Verbindung zum XYZ-Roboter.

```python
robot.connect()
```

---

## `disconnect()`

Schließt die serielle Verbindung.

```python
robot.disconnect()
```

---

## `is_connected`

Gibt zurück, ob aktuell eine Verbindung besteht.

```python
if robot.is_connected:
    print("Verbunden")
```

---

# 3. Kommunikation

## `send_gcode(command, command_timeout=10.0)`

Sendet einen einzelnen G-Code-Befehl an den Roboter und wartet auf Antwort.

Erwartete Antworten:

- `ok` -> Befehl erfolgreich
- `error` -> Fehler vom Roboter
- Timeout -> Exception

```python
robot.send_gcode("G28")
```

---

# 4. Homing

## `homing(command_timeout=60.0)`

Referenziert alle Achsen.

```python
robot.homing()
```

---

## `homing_x(command_timeout=60.0)`

Referenziert nur die X-Achse.

```python
robot.homing_x()
```

---

## `homing_y(command_timeout=60.0)`

Referenziert nur die Y-Achse.

```python
robot.homing_y()
```

---

## `homing_z(command_timeout=60.0)`

Referenziert nur die Z-Achse.

```python
robot.homing_z()
```

---

# 5. Basisbewegungen

## `move_absolute(x=None, y=None, z=None, feedrate=None, command_timeout=30)`

Fährt absolut zu einer Zielposition.

```python
robot.move_absolute(x=100.0, y=200.0, z=180.0, feedrate=3000.0)
```

---

## `move_relative(dx=None, dy=None, dz=None, feedrate=None, command_timeout=30)`

Fährt relativ zur aktuellen Position.

```python
robot.move_relative(dx=10.0, dy=0.0, dz=0.0, feedrate=3000.0)
```

---

## `z_to_mark()`

Fährt die Z-Achse auf Markierhöhe.

```python
robot.z_to_mark()
```

Verwendet:

```python
Z_MARK = 170.0
```

---

## `z_to_travel()`

Fährt die Z-Achse auf Fahrhöhe.

```python
robot.z_to_travel()
```

Verwendet:

```python
Z_TRAVEL = 180.0
```

---

# 6. XY-Bewegungen

## `move_xy_travel_absolute(x=None, y=None)`

Fährt schnell absolut in XY.

```python
robot.move_xy_travel_absolute(x=100.0, y=200.0)
```

Verwendet:

```python
DEFAULT_FEEDRATE_XY
```

---

## `move_xy_travel_relative(dx=None, dy=None)`

Fährt schnell relativ in XY.

```python
robot.move_xy_travel_relative(dx=10.0, dy=0.0)
```

---

## `move_xy_mark_absolute(x=None, y=None)`

Fährt absolut in XY mit Markiergeschwindigkeit.

```python
robot.move_xy_mark_absolute(x=120.0, y=200.0)
```

Verwendet:

```python
DEFAULT_FEEDRATE_MARKING
```

---

## `move_xy_mark_relative(dx=None, dy=None)`

Fährt relativ in XY mit Markiergeschwindigkeit.

```python
robot.move_xy_mark_relative(dx=5.0, dy=0.0)
```

---

# 7. Positionsabfrage

## `get_current_position()`

Fragt die aktuelle Maschinenposition ab.

```python
pos = robot.get_current_position()

print(pos["X"])
print(pos["Y"])
print(pos["Z"])
```

Rückgabe:

```python
{
    "X": 100.0,
    "Y": 200.0,
    "Z": 180.0
}
```

---

# 8. Linien und Polylinien

## `mark_line_absolute(start_x, start_y, end_x, end_y)`

Markiert eine einzelne Linie zwischen zwei Punkten.

```python
robot.mark_line_absolute(
    start_x=100.0,
    start_y=200.0,
    end_x=120.0,
    end_y=200.0
)
```

Ablauf:

1. Z auf Fahrhöhe
2. Fahrt zum Startpunkt
3. Z auf Markierhöhe
4. Markierfahrt zum Endpunkt
5. Z zurück auf Fahrhöhe

---

## `mark_polyline_absolute(points)`

Markiert einen zusammenhängenden Linienzug.

```python
robot.mark_polyline_absolute([
    (100.0, 200.0),
    (120.0, 200.0),
    (120.0, 220.0),
    (100.0, 220.0)
])
```

Gut geeignet für:

- Zeichen
- Symbole
- Umrisse
- zusammenhängende Markierpfade

---

# 9. Einfache Marker

## `mark_plus(center_x, center_y, length)`

Markiert ein Plus an einer Position.

```python
robot.mark_plus(
    center_x=100.0,
    center_y=200.0,
    length=10.0
)
```

Hinweis:  
Diese Funktion ist noch die einfache ältere Plus-Funktion. Für neue Marker besser `mark_point()` verwenden.

---

# 10. Markerformen

## `mark_shape(shape_name, x, y, size, angle_deg=0.0)`

Markiert eine Markerform aus `marker_shapes.py`.

```python
robot.mark_shape(
    shape_name="plus",
    x=100.0,
    y=200.0,
    size=10.0,
    angle_deg=45.0
)
```

Die Geometrie kommt aus:

```python
MARKER_SHAPES
```

---

## `mark_point(x, y, size=10.0, shape="plus", angle_deg=0.0)`

Markiert einen Punkt mit definierbarer Form.

```python
robot.mark_point(
    x=100.0,
    y=200.0,
    size=10.0,
    shape="plus",
    angle_deg=0.0
)
```

Aktuell vorgesehene Shapes:

```text
plus
cross
circle_point
plus_circle
```

Beispiele:

```python
robot.mark_point(100, 200, size=10, shape="plus")
robot.mark_point(100, 200, size=10, shape="cross")
robot.mark_point(100, 200, size=10, shape="circle_point")
robot.mark_point(100, 200, size=10, shape="plus_circle")
```

---

## Shape: `plus`

Normales Pluszeichen.

```python
robot.mark_point(
    x=100,
    y=200,
    size=10,
    shape="plus"
)
```

---

## Shape: `cross`

Diagonales Kreuz.

```python
robot.mark_point(
    x=100,
    y=200,
    size=10,
    shape="cross"
)
```

---

## Shape: `circle_point`

Kreis mit kleinem Mittelpunkt.

```python
robot.mark_point(
    x=100,
    y=200,
    size=10,
    shape="circle_point"
)
```

Der Kreisradius ist:

```python
radius = size / 2
```

---

## Shape: `plus_circle`

Plus mit zusätzlichem Kreis.

```python
robot.mark_point(
    x=100,
    y=200,
    size=10,
    shape="plus_circle"
)
```

Der Kreisradius ist:

```python
radius = size * 0.7 / 2
```

---

# 11. Punkt mit Beschriftung

## `mark_point_with_label(...)`

Markiert einen Punkt und schreibt eine Punktnummer daneben.

```python
robot.mark_point_with_label(
    x=100.0,
    y=200.0,
    label="P.1053",
    marker_size=10.0,
    marker_shape="plus_circle",
    text_height=8.0,
    text_offset=6.0,
    angle_deg=0.0
)
```

Parameter:

| Parameter | Bedeutung |
|---|---|
| `x` | X-Koordinate des Punktes |
| `y` | Y-Koordinate des Punktes |
| `label` | Punktnummer oder Text |
| `marker_size` | Größe der Markierung |
| `marker_shape` | Markerform |
| `text_height` | Texthöhe |
| `text_offset` | Abstand zwischen Marker und Text |
| `angle_deg` | Drehwinkel von Marker und Text |

Beispiel gedreht:

```python
robot.mark_point_with_label(
    x=100,
    y=200,
    label="P.1053",
    marker_shape="plus_circle",
    angle_deg=45
)
```

---

# 12. Textmarkierung

## `mark_char(char, x, y, height, width=None, angle_deg=0.0)`

Markiert ein einzelnes Zeichen aus dem Stroke-Font.

```python
robot.mark_char(
    char="A",
    x=100.0,
    y=200.0,
    height=10.0,
    angle_deg=0.0
)
```

Die Zeichengeometrie kommt aus:

```python
STROKE_FONT
```

---

## `mark_text(text, x, y, height, char_spacing=0.25, angle_deg=0.0)`

Markiert eine Zeichenkette.

```python
robot.mark_text(
    text="P.1053",
    x=100.0,
    y=200.0,
    height=10.0,
    angle_deg=0.0
)
```

Gedreht:

```python
robot.mark_text(
    text="P.1053",
    x=100.0,
    y=200.0,
    height=10.0,
    angle_deg=90.0
)
```

Hinweise:

- Großbuchstaben werden automatisch verwendet.
- Leerzeichen werden übersprungen und erzeugen Abstand.
- Zeichenbreite ist standardmäßig `height * 0.6`.
- Zeichenabstand wird über `char_spacing` gesteuert.

---

# 13. Kreismarkierung

## `move_circle_mark(x, y, radius, clockwise=False, feedrate=None, command_timeout=30.0)`

Markiert einen Kreis mit G2/G3.

```python
robot.move_circle_mark(
    x=100.0,
    y=200.0,
    radius=5.0
)
```

Parameter:

| Parameter | Bedeutung |
|---|---|
| `x` | Mittelpunkt X |
| `y` | Mittelpunkt Y |
| `radius` | Kreisradius |
| `clockwise` | `True` = G2, `False` = G3 |
| `feedrate` | Markiergeschwindigkeit |
| `command_timeout` | Timeout für G-Code-Befehl |

Beispiel im Uhrzeigersinn:

```python
robot.move_circle_mark(
    x=100,
    y=200,
    radius=5,
    clockwise=True
)
```

---

# 14. Interne Transformationen

Diese Funktionen werden normalerweise nicht direkt von außen aufgerufen.

## `_transform_font_point(...)`

Wandelt einen normierten Fontpunkt in Maschinenkoordinaten um.

Verwendet für:

- Stroke-Font-Zeichen
- Textrotation
- Textskalierung

---

## `_transform_local_point(...)`

Wandelt lokale Markerkoordinaten in Maschinenkoordinaten um.

Verwendet für:

- Markerformen
- Rotation von Markern
- Skalierung von Markern

---

# 15. Interne Hilfsfunktionen

## `_build_move_command(...)`

Erzeugt einen G-Code-Bewegungsbefehl.

Beispiel intern:

```text
G0 X100.0 Y200.0 F6000.0
```

---

## `_parse_position_line(line)`

Liest Positionsdaten aus einer M114-Antwort.

Beispiel:

```text
X:100.00 Y:200.00 Z:180.00
```

---

## `_validate_absolute_position(...)`

Prüft, ob eine Zielposition innerhalb des Arbeitsraums liegt.

Arbeitsraum:

```python
X_MIN = 0.0
X_MAX = 500.0

Y_MIN = 0.0
Y_MAX = 450.0

Z_MIN = 150.0
Z_MAX = 200.0
```

---

## `_calculate_relative_target(...)`

Berechnet die absolute Zielposition für relative Bewegungen.

Wird von `move_relative()` verwendet.

---

## `_check_circle_within_workspace(center_x, center_y, radius)`

Prüft, ob ein vollständiger Kreis innerhalb des Arbeitsraums liegt.

---

# 16. Typische Beispiele

## Punkt mit Plus markieren

```python
robot.mark_point(
    x=100,
    y=200,
    size=10,
    shape="plus"
)
```

---

## Punkt mit Plus und Kreis markieren

```python
robot.mark_point(
    x=100,
    y=200,
    size=10,
    shape="plus_circle"
)
```

---

## Punktnummer schreiben

```python
robot.mark_text(
    text="P.1053",
    x=120,
    y=200,
    height=8
)
```

---

## Punkt mit Punktnummer markieren

```python
robot.mark_point_with_label(
    x=100,
    y=200,
    label="P.1053",
    marker_size=10,
    marker_shape="plus_circle",
    text_height=8,
    text_offset=6,
    angle_deg=0
)
```

---

## Punkt mit gedrehter Punktnummer markieren

```python
robot.mark_point_with_label(
    x=100,
    y=200,
    label="P.1053",
    marker_size=10,
    marker_shape="plus_circle",
    text_height=8,
    text_offset=6,
    angle_deg=45
)
```

---

## Kreis markieren

```python
robot.move_circle_mark(
    x=100,
    y=200,
    radius=5
)
```

---

# 17. Wichtige Hinweise

- Vor Bewegungen sollte der Roboter verbunden sein.
- Vor dem Markieren sollte ein Homing durchgeführt werden.
- Alle Markierfunktionen fahren nach Abschluss wieder auf `Z_TRAVEL`.
- Die Stroke-Font-Zeichen liegen in `stroke_font.py`.
- Die Markerformen liegen in `marker_shapes.py`.
- Neue Zeichen werden in `STROKE_FONT` ergänzt.
- Neue Markerformen werden in `MARKER_SHAPES` ergänzt.
- Die Klasse prüft absolute Zielpositionen gegen den definierten Arbeitsraum.

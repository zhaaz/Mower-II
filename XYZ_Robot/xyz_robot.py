# xyz_robot.py

import serial
import time
import math
import re

from typing import Optional
from XYZ_Robot.stroke_font import STROKE_FONT
from XYZ_Robot.marker_shapes import MARKER_SHAPES

try:
    from config.mower_config import CONFIG
except Exception:
    CONFIG = None

class XYZRobot:
    # --------------------------------------------------
    # Feedrate / Verfahrgeschwindigkeit Achsen mm/min
    # --------------------------------------------------
    DEFAULT_FEEDRATE_XY = 6000.0
    DEFAULT_FEEDRATE_Z = 900.0
    DEFAULT_FEEDRATE_MARKING = 2000.0

    # Fallbackwerte. Produktiv werden die Werte aus CONFIG.marker verwendet.
    Z_MARK = 166.0
    Z_CLEAR = Z_MARK + 5.0
    Z_TRAVEL = Z_MARK + 10.0

    # --------------------------------------------------
    # Arbeitsraum [mm]
    # --------------------------------------------------
    X_MIN = 0.0
    X_MAX = 500.0

    Y_MIN = 0.0
    Y_MAX = 450.0

    Z_MIN = 150.0
    Z_MAX = 200.0

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial: Optional[serial.Serial] = None
        self._is_homed = False
        self._z_mark_override_mm: float | None = None
        self._z_clear_override_mm: float | None = None
        self._z_travel_override_mm: float | None = None


    # --------------------------------------------------
    # Verbindung
    # --------------------------------------------------

    def connect(self) -> None:
        """"Öffnet die serielle Verbindung zum SKR 3."""
        if self.is_connected:
            raise RuntimeError("XYZ Roboter ist bereits verbunden.")

        self._serial = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            timeout=self.timeout
        )

        self._is_homed = False

    def disconnect(self) -> None:
        """Schließt die serielle Verbindung"""
        if self.is_connected:
            self._serial.close()

        self._serial = None
        self._is_homed = False

    @property
    def is_connected(self) -> bool:
        """Gibt zurück, ob eine Verbindung besteht."""
        return self._serial is not None and self._serial.is_open

    # --------------------------------------------------
    # Kommunikation
    # --------------------------------------------------

    def send_gcode(self, command: str, command_timeout: float = 10.0) -> list[str]:
        """
        Sendet einen GCode Befehl und wartet blockierend auf eine Antwort.

        Ende Bedingung:
        - 'ok'    -> Erfolg
        - 'error' -> Exception
        - Timeout -> Exception

        :param command: z.B. "G28" (entspricht homing der Achsen)
        :param command_timeout: Timeout in Sekunden
        :return: Antwort von der Maschine
        """

        if not self.is_connected:
            raise RuntimeError("Keine Verbindung zum XYZ Roboter")

        # G-Code sauber terminieren
        line = command.strip() + "\n"

        # senden
        self._serial.write(line.encode("ascii"))

        start_time = time.monotonic()
        responses: list[str] = []

        while True:
            elapsed = time.monotonic() - start_time
            if elapsed >= command_timeout:
                raise TimeoutError(f"Timeout nach {command_timeout:.1f}s bei Befehl: {command}")

            raw = self._serial.readline()
            text = raw.decode("ascii", errors="replace").strip()

            # ignoriere leere Zeile
            if not text:
                continue

            responses.append(text)

            # Ende bei erfolgreichem Befehl
            if text.lower() == "ok":
                return responses

            if text.lower().startswith("error"):
                raise RuntimeError(f"Fehler vom Roboter {text}")

    # --------------------------------------------------
    # GCODE Methoden
    # --------------------------------------------------

    def homing(self, command_timeout: float = 60.0) -> list[str]:
        response = self.send_gcode("G28", command_timeout=command_timeout)
        self._is_homed = True
        return response

    def homing_x(self, command_timeout: float = 60.0) -> list[str]:
        return self.send_gcode("G28X", command_timeout=command_timeout)

    def homing_y(self, command_timeout: float = 60.0) -> list[str]:
        return self.send_gcode("G28Y", command_timeout=command_timeout)

    def homing_z(self, command_timeout: float = 60.0) -> list[str]:
        return self.send_gcode("G28Z", command_timeout=command_timeout)

    def move_absolute(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        feedrate: float | None = None,
        command_timeout: float = 30
    ) -> list[str]:

        self._require_homed()
        self._validate_absolute_position(x=x, y=y, z=z)
        self.send_gcode("G90", command_timeout=5.0)
        command = self._build_move_command(x=x, y=y, z=z, feedrate=feedrate)
        return self.send_gcode(command, command_timeout=command_timeout)

    def move_relative(
        self,
        dx: float | None = None,
        dy: float | None = None,
        dz: float | None = None,
        feedrate: float | None = None,
        command_timeout: float = 30
    ) -> list[str]:

        self._require_homed()
        target = self._calculate_relative_target(dx, dy, dz)
        self._validate_absolute_position(x=target["X"], y=target["Y"], z=target["Z"])

        self.send_gcode("G91", command_timeout=5.0)
        command = self._build_move_command(x=dx, y=dy, z=dz, feedrate=feedrate)
        return self.send_gcode(command, command_timeout=command_timeout)

    def set_marker_heights(
            self,
            *,
            z_mark_mm: float | None = None,
            z_clear_mm: float | None = None,
            z_travel_mm: float | None = None,
    ) -> None:
        """Setzt die fuer den naechsten Markierbetrieb verwendeten Z-Hoehen.

        Die Dialoge uebergeben diese Werte explizit aus CONFIG.marker. Dadurch
        haengen Kalibrierung und Markierung nicht von versteckten Defaults im
        Roboterobjekt ab. Fehlende CLEAR/TRAVEL-Werte werden aus Z_MARK abgeleitet.
        """

        if z_mark_mm is not None:
            z_mark = float(z_mark_mm)
            self._validate_absolute_position(z=z_mark)
            self._z_mark_override_mm = z_mark

            if z_clear_mm is None:
                z_clear_mm = z_mark + 5.0
            if z_travel_mm is None:
                z_travel_mm = z_mark + 10.0

        if z_clear_mm is not None:
            z_clear = float(z_clear_mm)
            self._validate_absolute_position(z=z_clear)
            self._z_clear_override_mm = z_clear

        if z_travel_mm is not None:
            z_travel = float(z_travel_mm)
            self._validate_absolute_position(z=z_travel)
            self._z_travel_override_mm = z_travel

    def _configured_z_mark(self) -> float:
        if self._z_mark_override_mm is not None:
            return float(self._z_mark_override_mm)
        if CONFIG is not None and hasattr(CONFIG, "marker"):
            return float(getattr(CONFIG.marker, "z_mark_mm", self.Z_MARK))
        return self.Z_MARK

    def _configured_z_clear(self) -> float:
        if self._z_clear_override_mm is not None:
            return float(self._z_clear_override_mm)
        if CONFIG is not None and hasattr(CONFIG, "marker") and hasattr(CONFIG.marker, "z_clear_mm"):
            return float(CONFIG.marker.z_clear_mm)
        return self._configured_z_mark() + 5.0

    def _configured_z_travel(self) -> float:
        if self._z_travel_override_mm is not None:
            return float(self._z_travel_override_mm)
        if CONFIG is not None and hasattr(CONFIG, "marker") and hasattr(CONFIG.marker, "z_travel_mm"):
            return float(CONFIG.marker.z_travel_mm)
        return self._configured_z_mark() + 10.0

    def z_to_mark(self):
        return self.move_absolute(z=self._configured_z_mark(), feedrate=self.DEFAULT_FEEDRATE_Z)

    def z_to_travel(self):
        return self.move_absolute(z=self._configured_z_travel(), feedrate=self.DEFAULT_FEEDRATE_Z)

    def z_to_clear(self):
        return self.move_absolute(z=self._configured_z_clear(), feedrate=self.DEFAULT_FEEDRATE_Z)

    def move_xy_travel_relative(self, dx=None, dy=None):
        return self.move_relative(dx=dx, dy=dy, feedrate=self.DEFAULT_FEEDRATE_XY)

    def move_xy_travel_absolute(self, x=None, y=None):
        return self.move_absolute(x=x, y=y, feedrate=self.DEFAULT_FEEDRATE_XY)

    def move_xy_mark_relative(self, dx=None, dy=None):
        return self.move_relative(dx=dx, dy=dy, feedrate=self.DEFAULT_FEEDRATE_MARKING)

    def move_xy_mark_absolute(self, x=None, y=None):
        return self.move_absolute(x=x, y=y, feedrate=self.DEFAULT_FEEDRATE_MARKING)

    def get_current_position(self) -> dict[str, float]:
        responses = self.send_gcode("M114", command_timeout=5.0)

        for line in responses:
            if "X:" in line and "Y:" in line and "Z:" in line:
                return self._parse_position_line(line)

        raise RuntimeError("Keine Positionsdaten in der Antwort gefunden")


    # --------------------------------------------------
    # Hilfsmethoden
    # --------------------------------------------------

    def _require_homed(self) -> None:
        if not self._is_homed:
            raise RuntimeError("Fahrbefehl nicht erlaubt: Vorher muss ein Homing aller Achsen ausgeführt werden.")

    def _build_move_command(
            self,
            x: float | None = None,
            y: float | None = None,
            z: float | None = None,
            feedrate: float | None = None,
    ) -> str:

        parts = ["G0"]

        if x is not None:
            parts.append(f"X{x}")
        if y is not None:
            parts.append(f"Y{y}")
        if z is not None:
            parts.append(f"Z{z}")
        if feedrate is not None:
            parts.append(f"F{feedrate}")


        if len(parts) == 1:
            raise ValueError("Mindestens eine Achse oder Feedrate muss angegeben werden")

        return " ".join(parts)


    def _parse_position_line(self, line: str) -> dict[str, float]:
        pattern = r"([XYZ]):(-?\d+(?:\.\d+)?)"
        matches = re.findall(pattern, line)

        if not matches:
            raise ValueError(f"Keine gültigen Positionsdaten gefunden: {line}")

        position = {axis: float(value) for axis, value in matches[:3]}

        for axis in ("X", "Y", "Z"):
            if axis not in position:
                raise ValueError(f"Achse {axis} fehlt in der Positionsantwort: {line}")

        return position


    def _validate_absolute_position(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
    ) -> None:
        if x is not None and not (self.X_MIN <= x <= self.X_MAX):
            raise ValueError(f"X={x} außerhalb des Arbeitsraums [{self.X_MIN}, {self.X_MAX}]")

        if y is not None and not (self.Y_MIN <= y <= self.Y_MAX):
            raise ValueError(f"Y={y} außerhalb des Arbeitsraums [{self.Y_MIN}, {self.Y_MAX}]")

        if z is not None and not (self.Z_MIN <= z <= self.Z_MAX):
            raise ValueError(f"Z={z} außerhalb des Arbeitsraums [{self.Z_MIN}, {self.Z_MAX}]")


    def _calculate_relative_target(
            self,
            dx: float | None,
            dy: float | None,
            dz: float | None,
    ) -> dict[str, float]:
        current = self.get_current_position()

        target_x = current["X"] + (dx if dx is not None else 0)
        target_y = current["Y"] + (dy if dy is not None else 0)
        target_z = current["Z"] + (dz if dz is not None else 0)

        return {
            "X": target_x,
            "Y": target_y,
            "Z": target_z,
        }

    def _check_circle_within_workspace(self, center_x: float, center_y: float, radius: float) -> None:
        """
        Prüft, ob ein vollständiger Kreis innerhalb des Arbeitsraums liegt.
        Wirft bei Verletzung eine Exception.
        """
        if radius <= 0:
            raise ValueError(f"Ungültiger Radius: {radius}. Radius muss > 0 sein.")

        if center_x - radius < self.X_MIN:
            raise ValueError("Kreis überschreitet X_MIN.")
        if center_x + radius > self.X_MAX:
            raise ValueError("Kreis überschreitet X_MAX.")
        if center_y - radius < self.Y_MIN:
            raise ValueError("Kreis überschreitet Y_MIN.")
        if center_y + radius > self.Y_MAX:
            raise ValueError("Kreis überschreitet Y_MAX.")

    def _validate_xy_point(self, x: float, y: float) -> None:
        if not (self.X_MIN <= x <= self.X_MAX):
            raise ValueError(f"X={x} außerhalb des Arbeitsraums [{self.X_MIN}, {self.X_MAX}]")

        if not (self.Y_MIN <= y <= self.Y_MAX):
            raise ValueError(f"Y={y} außerhalb des Arbeitsraums [{self.Y_MIN}, {self.Y_MAX}]")

    def _validate_xy_points(self, points: list[tuple[float, float]]) -> None:
        for x, y in points:
            self._validate_xy_point(x, y)

    def _get_text_points(
            self,
            text: str,
            x: float,
            y: float,
            height: float,
            char_spacing: float = 0.25,
            angle_deg: float = 0.0
    ) -> list[tuple[float, float]]:

        width = height * 0.6
        step = width * (1.0 + char_spacing)

        angle_rad = math.radians(angle_deg)

        cursor_x = x
        cursor_y = y

        step_x = step * math.cos(angle_rad)
        step_y = step * math.sin(angle_rad)

        points: list[tuple[float, float]] = []

        for char in text:
            if char == " ":
                cursor_x += step_x
                cursor_y += step_y
                continue

            char = char.upper()

            if char not in STROKE_FONT:
                raise ValueError(f"Zeichen nicht im Stroke-Font definiert: {char}")

            for stroke in STROKE_FONT[char]:
                for px, py in stroke:
                    absolute_x, absolute_y = self._transform_font_point(
                        px=px,
                        py=py,
                        origin_x=cursor_x,
                        origin_y=cursor_y,
                        width=width,
                        height=height,
                        angle_deg=angle_deg
                    )
                    points.append((absolute_x, absolute_y))

            cursor_x += step_x
            cursor_y += step_y

        return points

    def _get_shape_points(
            self,
            shape_name: str,
            x: float,
            y: float,
            size: float,
            angle_deg: float = 0.0
    ) -> list[tuple[float, float]]:

        if shape_name not in MARKER_SHAPES:
            raise ValueError(f"Unbekannte Markerform: {shape_name}")

        points: list[tuple[float, float]] = []

        for stroke in MARKER_SHAPES[shape_name]:
            for local_x, local_y in stroke:
                px, py = self._transform_local_point(
                    local_x=local_x,
                    local_y=local_y,
                    origin_x=x,
                    origin_y=y,
                    size=size,
                    angle_deg=angle_deg
                )
                points.append((px, py))

        return points


    # --------------------------------------------------
    # Markierung
    # --------------------------------------------------


    def mark_line_absolute(self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float
        ) -> None:

        try:
            self.z_to_travel()
            self.move_xy_travel_absolute(x=start_x, y=start_y)
            self.z_to_mark()
            self.move_xy_mark_absolute(x=end_x, y=end_y)
        finally:
            self.z_to_travel()

    def mark_plus(
            self,
            center_x: float,
            center_y: float,
            length: float
    ) -> None:

        # horizontale Linie
        start_h_x = center_x - length/2
        start_h_y = center_y
        end_h_x = center_x + length/2
        end_h_y = center_y

        # vertikale Linie
        start_v_x = center_x
        start_v_y = center_y - length/2
        end_v_x = center_x
        end_v_y = center_y + length/2


        try:
            self.z_to_travel()
            # Linie horizontal
            self.mark_line_absolute(start_h_x, start_h_y, end_h_x, end_h_y)
            # Linie vertikal
            self.mark_line_absolute(start_v_x, start_v_y, end_v_x, end_v_y)

        finally:
            self.z_to_travel()

    def mark_polyline_absolute(
            self,
            points: list[tuple[float, float]],
            clear_after: bool = False
    ) -> None:
        """
        Markiert einen zusammenhängenden Linienzug.

        clear_after=False:
            Am Ende wird nur auf Z_CLEAR gefahren.

        clear_after=True:
            Am Ende wird auf Z_TRAVEL gefahren.
        """

        if len(points) < 2:
            raise ValueError("Eine Polyline braucht mindestens zwei Punkte.")

        self._validate_xy_points(points)
        start_x, start_y = points[0]

        try:
            self.z_to_clear()
            self.move_xy_travel_absolute(x=start_x, y=start_y)
            self.z_to_mark()

            for x, y in points[1:]:
                self.move_xy_mark_absolute(x=x, y=y)

        finally:
            if clear_after:
                self.z_to_travel()
            else:
                self.z_to_clear()

    def mark_char(
            self,
            char: str,
            x: float,
            y: float,
            height: float,
            width: float | None = None,
            angle_deg: float = 0.0
    ) -> None:

        char = char.upper()

        if width is None:
            width = height * 0.6

        if char not in STROKE_FONT:
            raise ValueError(f"Zeichen nicht im Stroke-Font definiert: {char}")

        strokes = STROKE_FONT[char]

        for stroke in strokes:
            absolute_points = []

            for px, py in stroke:
                absolute_x, absolute_y = self._transform_font_point(
                    px=px,
                    py=py,
                    origin_x=x,
                    origin_y=y,
                    width=width,
                    height=height,
                    angle_deg=angle_deg
                )

                absolute_points.append((absolute_x, absolute_y))

            self.mark_polyline_absolute(absolute_points)

    def mark_text(
            self,
            text: str,
            x: float,
            y: float,
            height: float,
            char_spacing: float = 0.25,
            angle_deg: float = 0.0
    ) -> None:

        width = height * 0.6
        step = width * (1.0 + char_spacing)

        angle_rad = math.radians(angle_deg)

        cursor_x = x
        cursor_y = y

        step_x = step * math.cos(angle_rad)
        step_y = step * math.sin(angle_rad)

        try:

            for char in text:
                if char == " ":
                    cursor_x += step_x
                    cursor_y += step_y
                    continue

                self.mark_char(
                    char=char,
                    x=cursor_x,
                    y=cursor_y,
                    height=height,
                    width=width,
                    angle_deg=angle_deg
                )

                cursor_x += step_x
                cursor_y += step_y

        finally:
            self.z_to_travel()


    def _transform_font_point(
        self,
        px: float,
        py: float,
        origin_x: float,
        origin_y: float,
        width: float,
        height: float,
        angle_deg: float = 0.0
    ) -> tuple[float, float]:
        """
        Wandelt einen normierten Fontpunkt in Maschinenkoordinaten um.
        Rotation erfolgt um den Ursprungspunkt x/y des Zeichens.
        """

        # skalieren
        local_x = px * width
        local_y = py * height

        # rotieren
        angle_rad = math.radians(angle_deg)

        rotated_x = local_x * math.cos(angle_rad) - local_y * math.sin(angle_rad)
        rotated_y = local_x * math.sin(angle_rad) + local_y * math.cos(angle_rad)

        # verschieben
        return origin_x + rotated_x, origin_y + rotated_y

    def _transform_local_point(
            self,
            local_x: float,
            local_y: float,
            origin_x: float,
            origin_y: float,
            size: float,
            angle_deg: float = 0.0
    ) -> tuple[float, float]:
        """
        Transformiert lokale Markerkoordinaten in Maschinenkoordinaten.
        Lokale Koordinaten sind typischerweise von -0.5 bis +0.5.
        """

        scaled_x = local_x * size
        scaled_y = local_y * size

        angle_rad = math.radians(angle_deg)

        rotated_x = scaled_x * math.cos(angle_rad) - scaled_y * math.sin(angle_rad)
        rotated_y = scaled_x * math.sin(angle_rad) + scaled_y * math.cos(angle_rad)

        return origin_x + rotated_x, origin_y + rotated_y

    def mark_shape(
            self,
            shape_name: str,
            x: float,
            y: float,
            size: float,
            angle_deg: float = 0.0
    ) -> None:
        """
        Markiert eine definierte Markerform aus MARKER_SHAPES.
        """

        if shape_name not in MARKER_SHAPES:
            raise ValueError(f"Unbekannte Markerform: {shape_name}")

        shape = MARKER_SHAPES[shape_name]

        for stroke in shape:
            absolute_points = []

            for local_x, local_y in stroke:
                px, py = self._transform_local_point(
                    local_x=local_x,
                    local_y=local_y,
                    origin_x=x,
                    origin_y=y,
                    size=size,
                    angle_deg=angle_deg
                )
                absolute_points.append((px, py))

            self.mark_polyline_absolute(absolute_points)

    def mark_point(
            self,
            x: float,
            y: float,
            size: float = 10.0,
            shape: str = "plus",
            angle_deg: float = 0.0
    ) -> None:
        """
        Markiert einen Punkt mit einer definierbaren Markerform.

        shape:
        - "plus"
        - "cross"
        - "circle_point"
        - "plus_circle"
        """

        self.z_to_travel()
        self.move_xy_travel_absolute(x=x, y=y)

        if shape == "circle_point":
            radius = size / 2

            self.move_circle_mark(
                x=x,
                y=y,
                radius=radius
            )

            self.mark_shape(
                shape_name="circle_point",
                x=x,
                y=y,
                size=size,
                angle_deg=angle_deg
            )

            return

        if shape == "plus_circle":
            self.mark_shape(
                shape_name="plus_circle",
                x=x,
                y=y,
                size=size,
                angle_deg=angle_deg
            )

            self.move_circle_mark(
                x=x,
                y=y,
                radius=size * 0.7 / 2
            )

            return

        self.mark_shape(
            shape_name=shape,
            x=x,
            y=y,
            size=size,
            angle_deg=angle_deg
        )

    def mark_point_with_label(
            self,
            x: float,
            y: float,
            label: str,
            marker_size: float = 10.0,
            marker_shape: str = "plus",
            text_height: float = 8.0,
            text_offset: float = 6.0,
            angle_deg: float = 0.0
    ) -> None:

        angle_rad = math.radians(angle_deg)

        label_x = x + (marker_size / 2 + text_offset) * math.cos(angle_rad)
        label_y = y + (marker_size / 2 + text_offset) * math.sin(angle_rad)

        points_to_check: list[tuple[float, float]] = []

        if marker_shape == "circle_point":
            radius = marker_size / 2
            self._check_circle_within_workspace(x, y, radius)
            points_to_check.extend(
                self._get_shape_points("circle_point", x, y, marker_size, angle_deg)
            )

        elif marker_shape == "plus_circle":
            radius = marker_size * 0.7 / 2
            self._check_circle_within_workspace(x, y, radius)
            points_to_check.extend(
                self._get_shape_points("plus_circle", x, y, marker_size, angle_deg)
            )

        else:
            points_to_check.extend(
                self._get_shape_points(marker_shape, x, y, marker_size, angle_deg)
            )

        points_to_check.extend(
            self._get_text_points(
                text=label,
                x=label_x,
                y=label_y,
                height=text_height,
                angle_deg=angle_deg
            )
        )

        self._validate_xy_points(points_to_check)

        self.mark_point(
            x=x,
            y=y,
            size=marker_size,
            shape=marker_shape,
            angle_deg=angle_deg
        )

        self.mark_text(
            text=label,
            x=label_x,
            y=label_y,
            height=text_height,
            angle_deg=angle_deg
        )

    def move_circle_mark(
            self,
            x: float,
            y: float,
            radius: float,
            clockwise: bool = False,
            feedrate: float | None = None,
            command_timeout: float = 30.0
    ) -> None:
        """
        Fährt einen Kreis (G2/G3) mit Markierung (Z unten).

        x, y     = Mittelpunkt
        radius   = Radius in mm
        clockwise = True -> G2, False -> G3
        """

        if radius <= 0:
            raise ValueError("Radius muss > 0 sein")

        self._check_circle_within_workspace(x, y, radius)

        if feedrate is None:
            feedrate = self.DEFAULT_FEEDRATE_MARKING

        # Startpunkt: rechter Rand des Kreises
        start_x = x + radius
        start_y = y

        try:
            # zur Startposition fahren
            self.z_to_travel()
            self.move_xy_travel_absolute(start_x, start_y)

            # Markieren aktivieren
            self.z_to_mark()

            # absolute Positionierung sicherstellen
            self.send_gcode("G90")

            # Kreisrichtung wählen
            gcode = "G2" if clockwise else "G3"

            # I/J = Vektor vom Startpunkt zum Mittelpunkt
            # hier: Mittelpunkt liegt radius nach links → I = -radius, J = 0
            command = f"{gcode} X{start_x} Y{start_y} I{-radius} J0 F{feedrate}"

            self.send_gcode(command, command_timeout=command_timeout)

        finally:
            self.z_to_travel()
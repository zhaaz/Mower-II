# xyz_robot.py
import re

import serial
import time
from typing import Optional

# from PyInstaller.building.splash_templates import position_window


class XYZRobot:
    # --------------------------------------------------
    # Feedrate / Verfahrgeschwindigkeit Achsen mm/min
    # --------------------------------------------------
    DEFAULT_FEEDRATE_XY = 6000.0
    DEFAULT_FEEDRATE_Z = 600.0
    DEFAULT_FEEDRATE_MARKING = 2000.0

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

    def disconnect(self) -> None:
        """Schließt die serielle Verbindung"""
        if self.is_connected:
            self._serial.close()

        self._serial = None

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
                raise TimeoutError(f"Timeout nach {command_timeout:1f}s bei Befehl: {command}")

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
        return self.send_gcode("G28", command_timeout=command_timeout)

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

        target = self._calculate_relative_target(dx, dy, dz)
        self._validate_absolute_position(x=target["X"], y=target["Y"], z=target["Z"])

        self.send_gcode("G91", command_timeout=5.0)
        command = self._build_move_command(x=dx, y=dy, z=dz, feedrate=feedrate)
        return self.send_gcode(command, command_timeout=command_timeout)

    def get_current_position(self) -> dict[str, float]:
        responses = self.send_gcode("M114", command_timeout=5.0)

        for line in responses:
            if "X:" in line and "Y:" in line and "Z:" in line:
                return self._parse_position_line(line)

        raise RuntimeError("Keine Positionsdaten in der Antwort gefunden")


    # --------------------------------------------------
    # Hilfsmethoden
    # --------------------------------------------------

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


    def _parse_position_line(selfself, line: str) -> dict[str, float]:
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


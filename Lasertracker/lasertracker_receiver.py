# lasertracker_receiver.py

import socket
import threading
import time
import math
from typing import Callable

from Lasertracker.lasertracker_state import LasertrackerState, TrackerMeasurement


class LasertrackerReceiver:
    """
    Empfängt Lasertracker-Koordinaten aus einem UDP-Stream,
    z. B. aus Spatial Analyzer / WatchWindow.

    Diese Klasse sendet keine Befehle an den Tracker.
    Sie lauscht nur auf Messdaten.
    """

    def __init__(
            self,
            port: int = 10000,
            bind_ip: str = "0.0.0.0",
            buffer_size: int = 8192,
            stale_threshold_seconds: float = 3.0,
            stable_threshold_mm: float = 0.1,
            stable_required_count: int = 3,
            on_state_changed: Callable[[LasertrackerState], None] | None = None,
            on_log: Callable[[str], None] | None = None,
            on_error: Callable[[str], None] | None = None,
    ):
        self.port = port
        self.bind_ip = bind_ip
        self.buffer_size = buffer_size

        self.state = LasertrackerState(
            stale_threshold_seconds=stale_threshold_seconds,
            stable_threshold_mm=stable_threshold_mm,
            stable_required_count=stable_required_count,
        )

        self.on_state_changed = on_state_changed
        self.on_log = on_log
        self.on_error = on_error

        self.socket: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.running = False

        self._last_receiving_state: bool | None = None
        self._last_stale_state: bool | None = None
        self._last_stable_state: bool | None = None

    # --------------------------------------------------
    # Start / Stop
    # --------------------------------------------------

    def start(self) -> None:
        if self.running:
            return

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.bind_ip, self.port))
            self.socket.settimeout(0.5)

            self.running = True
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

            self._log(f"UDP Receiver gestartet auf {self.bind_ip}:{self.port}")

        except Exception as e:
            self.running = False
            self.socket = None
            self._error(f"UDP Receiver konnte nicht gestartet werden: {e}")

    def stop(self) -> None:
        self.running = False

        if self.socket is not None:
            try:
                self.socket.close()
            except Exception:
                pass

        self.socket = None
        self.state.clear()
        self._notify_state_changed()
        self._log("UDP Receiver gestoppt")

    # --------------------------------------------------
    # Loop
    # --------------------------------------------------

    def _run(self) -> None:
        while self.running:
            now = time.time()

            self.state.update_age(now)
            self._log_state_changes()
            self._notify_state_changed()

            try:
                if self.socket is None:
                    break

                data, addr = self.socket.recvfrom(self.buffer_size)

            except socket.timeout:
                continue

            except OSError:
                break

            except Exception as e:
                self._error(f"UDP Empfangsfehler: {e}")
                continue

            line = self.decode_udp_payload(data)

            try:
                measurement = self.parse_sa_watch_line(line)

                if measurement is not None:
                    self.state.update_measurement(measurement)
                    self._log_state_changes()
                    self._notify_state_changed()

                else:
                    self._log(f"Ungültige Messzeile von {addr[0]}:{addr[1]}: {line}")

            except Exception as e:
                self._error(f"Parse-Fehler: {e}")

    # --------------------------------------------------
    # Parsing
    # --------------------------------------------------

    @staticmethod
    def decode_udp_payload(data: bytes) -> str:
        try:
            return data.decode("utf-8").strip()
        except UnicodeDecodeError:
            return data.decode("latin-1").strip()

    @staticmethod
    def parse_sa_watch_line(line: str) -> TrackerMeasurement | None:
        """
        Erwartet ungefähr:
        '...| X, 3744.50, | Y, 1309.42, | Z, 54.65, | ... Units: (mm) ...'
        """

        parts = [p.strip() for p in line.split("|")]

        x = y = z = None
        unit = None

        for part in parts:
            if not part:
                continue

            if "Units:" in part:
                tail = part.split("Units:", 1)[1].strip().strip(",").strip()
                if tail.startswith("(") and tail.endswith(")"):
                    tail = tail[1:-1].strip()
                unit = tail if tail else "unknown"
                continue

            if part.startswith("X"):
                tokens = [t.strip() for t in part.split(",")]
                if len(tokens) >= 2 and tokens[1]:
                    x = float(tokens[1])
                continue

            if part.startswith("Y"):
                tokens = [t.strip() for t in part.split(",")]
                if len(tokens) >= 2 and tokens[1]:
                    y = float(tokens[1])
                continue

            if part.startswith("Z"):
                tokens = [t.strip() for t in part.split(",")]
                if len(tokens) >= 2 and tokens[1]:
                    z = float(tokens[1])
                continue

        valid = (
            x is not None and y is not None and z is not None
            and math.isfinite(x)
            and math.isfinite(y)
            and math.isfinite(z)
        )

        if not valid:
            return None

        return TrackerMeasurement(
            timestamp=time.time(),
            x=x,
            y=y,
            z=z,
            unit=unit or "unknown",
            raw=line,
        )

    # --------------------------------------------------
    # Logging Zustandswechsel
    # --------------------------------------------------

    def _log_state_changes(self) -> None:
        if self.state.receiving != self._last_receiving_state:
            if self.state.receiving:
                self._log("UDP-Daten werden empfangen")
            else:
                self._log("Keine UDP-Daten werden empfangen")

            self._last_receiving_state = self.state.receiving

        if self.state.stale != self._last_stale_state:
            if self.state.stale:
                self._log("Messdaten sind veraltet / stale")
            else:
                self._log("Messdaten sind aktuell")

            self._last_stale_state = self.state.stale

        if self.state.stable != self._last_stable_state:
            if self.state.stable:
                self._log("Punkt ist stabil")
            else:
                self._log("Punkt ist nicht stabil")

            self._last_stable_state = self.state.stable

    def capture_stable_point(
            self,
            timeout_s: float = 30.0,
            min_age_after_start_s: float = 0.0,
    ) -> TrackerMeasurement:
        """
        Wartet auf einen neuen stabilen Messpunkt.

        Wichtig:
        Es werden nur Messungen berücksichtigt, die nach Start dieser Funktion
        empfangen wurden. Dadurch kann kein alter stabiler Punkt übernommen werden.
        """

        start_time = time.time()

        while time.time() - start_time < timeout_s:
            self.state.update_age(time.time())

            if self.state.stale:
                time.sleep(0.05)
                continue

            recent_points = [
                m for m in self.state.recent_measurements
                if m.timestamp >= start_time + min_age_after_start_s
            ]

            if len(recent_points) >= self.state.stable_required_count:
                points_to_check = recent_points[-self.state.stable_required_count:]

                if self.state.points_are_stable(points_to_check):
                    return points_to_check[-1]

            time.sleep(0.05)

        raise TimeoutError("Timeout: Kein neuer stabiler Lasertracker-Messpunkt.")

    # --------------------------------------------------
    # Callbacks
    # --------------------------------------------------

    def _notify_state_changed(self) -> None:
        if self.on_state_changed:
            self.on_state_changed(self.state)

    def _log(self, text: str) -> None:
        if self.on_log:
            self.on_log(text)

    def _error(self, text: str) -> None:
        if self.on_error:
            self.on_error(text)
"""Serial driver for the Murata SCH16T-K01 Arduino data stream."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

import serial

DEFAULT_BAUDRATE = 115200
MICROS_WRAP = 2 ** 32

LogCallback = Callable[[str], None]


@dataclass(frozen=True)
class SCH16TSnapshot:
    connected: bool
    sensor_time_s: float | None
    raw_yaw_deg: float
    angle_deg: float
    rate_dps: float
    drift_dps: float
    valid_packets: int
    invalid_lines: int
    drift_active: bool
    drift_elapsed_s: float
    drift_duration_s: float
    drift_progress: float
    pending_drift_dps: float | None
    drift_packet_count: int


class SCH16T:
    """Read ``time_us;gyro_z_dps;yaw_raw_deg`` lines from an Arduino.

    The Arduino provides an uncorrected relative yaw. Drift is determined by
    linear regression of yaw over sensor time. ``angle_deg`` is relative to a
    software zero and corrected with the active drift rate.
    """

    def __init__(self, *, on_log: LogCallback | None = None) -> None:
        self.ser: serial.Serial | None = None
        self.thread: threading.Thread | None = None
        self.running = False
        self.lock = threading.RLock()
        self.on_log = on_log

        self._last_time_us: int | None = None
        self._wrap_offset_us = 0
        self.sensor_time_s: float | None = None
        self.raw_yaw_deg = 0.0
        self.raw_rate_dps = 0.0
        self.angle_deg = 0.0
        self.rate_dps = 0.0
        self.valid_packets = 0
        self.invalid_lines = 0

        self._zero_sensor_time_s: float | None = None
        self._zero_raw_yaw_deg = 0.0
        self.drift_dps = 0.0

        self._drift_active = False
        self._drift_duration_s = 0.0
        self._drift_start_sensor_time_s: float | None = None
        self._drift_points: list[tuple[float, float]] = []
        self._pending_drift_dps: float | None = None

    @property
    def connected(self) -> bool:
        return self.ser is not None and bool(getattr(self.ser, "is_open", False)) and self.running

    def connect(self, port: str, baudrate: int = DEFAULT_BAUDRATE) -> None:
        if self.connected:
            return

        connection = serial.Serial(port=port, baudrate=int(baudrate), timeout=0.25)
        connection.reset_input_buffer()
        self.ser = connection
        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
        self._log(f"Murata SCH16T verbunden: {port} @ {baudrate} Baud.")

    def disconnect(self) -> None:
        self.running = False

        # Die serielle Verbindung wird primaer im finally-Block des
        # Lesethreads geschlossen. Insbesondere unter Windows darf close()
        # nicht gleichzeitig aus zwei Threads aufgerufen werden, da PySerial
        # sonst seine Overlapped-I/O-Handles doppelt freigeben kann.
        if self.thread and self.thread.is_alive() and self.thread is not threading.current_thread():
            self.thread.join(timeout=2.0)

        connection = self.ser
        self.ser = None
        if connection is not None and connection.is_open:
            try:
                connection.close()
            except (OSError, AttributeError, serial.SerialException) as exc:
                self._log(f"Hinweis beim Schliessen der Murata-Verbindung: {exc}")
        self._log("Murata-Verbindung geschlossen.")

    def _read_loop(self) -> None:
        try:
            while self.running:
                connection = self.ser
                if connection is None:
                    break

                raw_line = connection.readline()
                if not raw_line:
                    continue

                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or line.startswith("#") or line.startswith("time_us"):
                    continue

                fields = line.split(";")
                if len(fields) != 3:
                    self._count_invalid_line()
                    continue

                try:
                    raw_time_us = int(fields[0])
                    gyro_z_dps = float(fields[1].replace(",", "."))
                    yaw_raw_deg = float(fields[2].replace(",", "."))
                except ValueError:
                    self._count_invalid_line()
                    continue

                sensor_time_s = self._extend_micros(raw_time_us) / 1_000_000.0
                self._handle_sample(sensor_time_s, gyro_z_dps, yaw_raw_deg)
        except (serial.SerialException, OSError) as exc:
            if self.running:
                self._log(f"Murata-Lesefehler: {exc}")
        finally:
            self.running = False
            connection = self.ser
            if connection is not None and connection.is_open:
                try:
                    connection.close()
                except (OSError, AttributeError, serial.SerialException) as exc:
                    self._log(f"Hinweis beim Schliessen des Lesethreads: {exc}")

    def _extend_micros(self, current: int) -> int:
        with self.lock:
            if (
                    self._last_time_us is not None
                    and current < self._last_time_us
                    and self._last_time_us - current > MICROS_WRAP // 2
            ):
                self._wrap_offset_us += MICROS_WRAP
            self._last_time_us = current
            return current + self._wrap_offset_us

    def _count_invalid_line(self) -> None:
        with self.lock:
            self.invalid_lines += 1

    def _handle_sample(self, sensor_time_s: float, gyro_z_dps: float, yaw_raw_deg: float) -> None:
        should_finish_drift = False
        with self.lock:
            self.sensor_time_s = sensor_time_s
            self.raw_yaw_deg = yaw_raw_deg
            self.raw_rate_dps = gyro_z_dps
            self.valid_packets += 1

            if self._zero_sensor_time_s is None:
                self._zero_sensor_time_s = sensor_time_s
                self._zero_raw_yaw_deg = yaw_raw_deg

            elapsed_from_zero = sensor_time_s - self._zero_sensor_time_s
            self.angle_deg = (
                    yaw_raw_deg
                    - self._zero_raw_yaw_deg
                    - self.drift_dps * elapsed_from_zero
            )
            self.rate_dps = gyro_z_dps - self.drift_dps

            if self._drift_active:
                if self._drift_start_sensor_time_s is None:
                    self._drift_start_sensor_time_s = sensor_time_s
                elapsed = sensor_time_s - self._drift_start_sensor_time_s
                self._drift_points.append((elapsed, yaw_raw_deg))
                should_finish_drift = elapsed >= self._drift_duration_s

        if should_finish_drift:
            self._finish_drift_measurement()

    def determine_drift(self, seconds: float) -> None:
        if seconds <= 0.0:
            raise ValueError("Driftdauer muss groesser 0 sein.")
        if self.sensor_time_s is None:
            raise RuntimeError("Noch keine Murata-Messwerte empfangen.")

        with self.lock:
            self._drift_duration_s = float(seconds)
            self._drift_start_sensor_time_s = None
            self._drift_points.clear()
            self._drift_active = True
            self._pending_drift_dps = None
        self._log(f"Driftmessung gestartet: {seconds:.1f} s. Sensor ruhig halten.")

    def _finish_drift_measurement(self) -> None:
        with self.lock:
            if not self._drift_active:
                return
            points = list(self._drift_points)
            self._drift_active = False

            if len(points) < 2:
                self._pending_drift_dps = None
                message = "Driftmessung fehlgeschlagen: zu wenige Messwerte."
            else:
                times = [point[0] for point in points]
                angles = [point[1] for point in points]
                mean_time = sum(times) / len(times)
                mean_angle = sum(angles) / len(angles)
                denominator = sum((value - mean_time) ** 2 for value in times)
                if denominator <= 0.0:
                    self._pending_drift_dps = None
                    message = "Driftmessung fehlgeschlagen: keine Zeitspanne."
                else:
                    drift = sum(
                        (sample_time - mean_time) * (angle - mean_angle)
                        for sample_time, angle in points
                    ) / denominator
                    self._pending_drift_dps = drift
                    message = (
                        f"Driftmessung abgeschlossen: {drift:+.10f} deg/s "
                        f"aus {len(points)} Messwerten."
                    )
        self._log(message)

    def cancel_drift_measurement(self) -> None:
        with self.lock:
            was_active = self._drift_active
            self._drift_active = False
        if was_active:
            self._log("Driftmessung gestoppt.")

    def set_drift(self, drift_dps: float | None = None) -> None:
        with self.lock:
            if drift_dps is None:
                if self._pending_drift_dps is None:
                    raise RuntimeError("Keine abgeschlossene Driftmessung zum Setzen vorhanden.")
                value = float(self._pending_drift_dps)
            else:
                value = float(drift_dps)

            current_angle = self.angle_deg
            self.drift_dps = value
            self._pending_drift_dps = None
            if self.sensor_time_s is not None:
                self._zero_sensor_time_s = self.sensor_time_s
                self._zero_raw_yaw_deg = self.raw_yaw_deg - current_angle
            self.rate_dps = self.raw_rate_dps - self.drift_dps
        self._log(f"Drift gesetzt: {value:+.10f} deg/s.")

    def reset_angle(self) -> None:
        with self.lock:
            if self.sensor_time_s is None:
                raise RuntimeError("Noch keine Murata-Messwerte empfangen.")
            self._zero_sensor_time_s = self.sensor_time_s
            self._zero_raw_yaw_deg = self.raw_yaw_deg
            self.angle_deg = 0.0
        self._log("Murata-Winkel auf 0 gesetzt.")

    def snapshot(self) -> SCH16TSnapshot:
        with self.lock:
            if self._drift_active and self._drift_points:
                elapsed = max(self._drift_points[-1][0], 0.0)
            elif self._pending_drift_dps is not None and self._drift_points:
                elapsed = max(self._drift_points[-1][0], 0.0)
            else:
                elapsed = 0.0

            duration = max(self._drift_duration_s, 0.0)
            progress = max(0.0, min(elapsed / duration, 1.0)) if duration > 0.0 else 0.0
            return SCH16TSnapshot(
                connected=self.connected,
                sensor_time_s=self.sensor_time_s,
                raw_yaw_deg=float(self.raw_yaw_deg),
                angle_deg=float(self.angle_deg),
                rate_dps=float(self.rate_dps),
                drift_dps=float(self.drift_dps),
                valid_packets=int(self.valid_packets),
                invalid_lines=int(self.invalid_lines),
                drift_active=bool(self._drift_active),
                drift_elapsed_s=float(elapsed),
                drift_duration_s=float(duration),
                drift_progress=float(progress),
                pending_drift_dps=self._pending_drift_dps,
                drift_packet_count=len(self._drift_points),
            )

    def _log(self, text: str) -> None:
        if self.on_log is not None:
            self.on_log(text)

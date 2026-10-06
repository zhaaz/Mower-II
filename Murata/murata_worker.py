from __future__ import annotations

import queue
import threading
import time
from typing import Any, Callable

try:
    from .murata_state import MurataState
    from .sch16t import DEFAULT_BAUDRATE, SCH16T
except ImportError:
    from murata_state import MurataState
    from sch16t import DEFAULT_BAUDRATE, SCH16T


EventCallback = Callable[[str], None]
StateCallback = Callable[[MurataState], None]


class MurataWorker:
    """Queue-based worker for the Murata SCH16T serial stream."""

    def __init__(
        self,
        *,
        on_log: EventCallback | None = None,
        on_state_changed: StateCallback | None = None,
        update_interval_s: float = 0.05,
    ) -> None:
        self.on_log = on_log
        self.on_state_changed = on_state_changed
        self.update_interval_s = float(update_interval_s)

        self.sensor: SCH16T | None = None
        self.state = MurataState()
        self.command_queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()

        self.running = False
        self.thread: threading.Thread | None = None
        self.poll_thread: threading.Thread | None = None
        self._last_drift_active = False

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._command_loop, daemon=True)
        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()
        self.poll_thread.start()
        self._log("Murata-Worker gestartet.")
        self._notify_state_changed()

    def stop(self) -> None:
        if self.running:
            self.send_command("stop")

    def send_command(self, command: str, **kwargs: Any) -> None:
        self.command_queue.put((command, kwargs))

    def _command_loop(self) -> None:
        while True:
            command, kwargs = self.command_queue.get()
            if command == "stop":
                self._disconnect_silent()
                self.running = False
                self.state.status_text = "Stopped"
                self._log("Murata-Worker gestoppt.")
                self._notify_state_changed()
                break

            self._set_busy(True)
            try:
                self._execute_command(command, kwargs)
                self.state.error_text = None
            except Exception as exc:
                self.state.error_text = str(exc)
                self.state.status_text = "Error"
                self._log(f"FEHLER: {exc}")
            finally:
                self._set_busy(False)
                self._notify_state_changed()

    def _execute_command(self, command: str, kwargs: dict[str, Any]) -> None:
        if command == "connect":
            self._connect(**kwargs)
        elif command == "disconnect":
            self._disconnect()
        elif command == "reset_angle":
            self._reset_angle()
        elif command == "determine_drift":
            self._determine_drift(**kwargs)
        elif command == "cancel_drift":
            self._cancel_drift()
        elif command == "set_drift":
            self._set_drift(**kwargs)
        else:
            raise ValueError(f"Unbekannter Befehl: {command}")

    def _connect(self, port: str, baudrate: int = DEFAULT_BAUDRATE) -> None:
        self._disconnect_silent()
        self.state.clear_measurement()
        self.state.status_text = "Connecting"
        self._notify_state_changed()

        self.sensor = SCH16T(on_log=self._log)
        self.sensor.connect(port=port, baudrate=int(baudrate))
        self.state.connected = True
        self.state.port = port
        self.state.baudrate = int(baudrate)
        self.state.status_text = "Connected"
        self._update_state_from_sensor()
        self._log(f"Murata SCH16T verbunden: {port} @ {baudrate}.")

    def _disconnect(self) -> None:
        self._disconnect_silent()
        self.state.connected = False
        self.state.status_text = "Not Connected"
        self.state.port = None
        self.state.baudrate = None
        self._last_drift_active = False
        self._log("Murata SCH16T getrennt.")

    def _disconnect_silent(self) -> None:
        sensor = self.sensor
        self.sensor = None
        if sensor is not None:
            try:
                sensor.disconnect()
            except Exception as exc:
                self._log(f"Fehler beim Trennen: {exc}")
        self.state.connected = False

    def _reset_angle(self) -> None:
        self._require_sensor().reset_angle()
        self._update_state_from_sensor()

    def _determine_drift(self, seconds: float) -> None:
        self._require_sensor().determine_drift(float(seconds))
        self._update_state_from_sensor()
        self._last_drift_active = True

    def _cancel_drift(self) -> None:
        self._require_sensor().cancel_drift_measurement()
        self._update_state_from_sensor()
        self._last_drift_active = False

    def _set_drift(self, drift_dps: float | None = None) -> None:
        self._require_sensor().set_drift(drift_dps)
        self._update_state_from_sensor()

    def _poll_loop(self) -> None:
        while self.running:
            self._update_state_from_sensor()
            self._notify_state_changed()
            time.sleep(self.update_interval_s)

    def _update_state_from_sensor(self) -> None:
        sensor = self.sensor
        if sensor is None:
            self.state.connected = False
            return

        snap = sensor.snapshot()
        self.state.connected = snap.connected
        self.state.sensor_time_s = snap.sensor_time_s
        self.state.raw_yaw_deg = snap.raw_yaw_deg
        self.state.angle_deg = snap.angle_deg
        self.state.rate_dps = snap.rate_dps
        self.state.drift_dps = snap.drift_dps
        self.state.valid_packets = snap.valid_packets
        self.state.invalid_lines = snap.invalid_lines
        self.state.skipped_bytes = snap.invalid_lines
        self.state.drift_active = snap.drift_active
        self.state.drift_elapsed_s = snap.drift_elapsed_s
        self.state.drift_duration_s = snap.drift_duration_s
        self.state.drift_progress = snap.drift_progress
        self.state.pending_drift_dps = snap.pending_drift_dps
        self.state.drift_packet_count = snap.drift_packet_count

        if snap.connected and self.state.status_text not in {"Error", "Connecting"}:
            self.state.status_text = "Connected"
        elif not snap.connected and self.state.status_text == "Connected":
            self.state.status_text = "Not Connected"

        if self._last_drift_active and not snap.drift_active:
            self._last_drift_active = False
            if snap.pending_drift_dps is not None:
                self._log("Driftmessung bereit zum Setzen.")
            else:
                self._log("Driftmessung beendet ohne neuen Driftwert.")

    def _require_sensor(self) -> SCH16T:
        if self.sensor is None or not self.sensor.connected:
            raise RuntimeError("Murata SCH16T ist nicht verbunden.")
        return self.sensor

    def _set_busy(self, busy: bool) -> None:
        self.state.busy = busy
        self._notify_state_changed()

    def _notify_state_changed(self) -> None:
        if self.on_state_changed is not None:
            self.on_state_changed(self.state)

    def _log(self, text: str) -> None:
        if self.on_log is not None:
            self.on_log(text)


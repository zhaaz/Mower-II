# experiments/kvh_tests/kvh_dsp_worker.py

from __future__ import annotations

import queue
import threading
import time
from typing import Any, Callable

try:
    from .dsp3100 import DSP3100, DEFAULT_BAUDRATE
    from .kvh_dsp_state import KVHDSPState
except ImportError:
    from dsp3100 import DSP3100, DEFAULT_BAUDRATE
    from kvh_dsp_state import KVHDSPState


EventCallback = Callable[[str], None]
StateCallback = Callable[[KVHDSPState], None]


class KVHDSPWorker:
    """Queue-basierter Worker fuer erste KVH-DSP-Tests.

    Befehle:
        connect(port, baudrate)
        disconnect()
        reset_angle()
        determine_drift(seconds)
        stop()
    """

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

        self.sensor: DSP3100 | None = None
        self.state = KVHDSPState()
        self.command_queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()

        self.running = False
        self.thread: threading.Thread | None = None
        self.poll_thread: threading.Thread | None = None

    def start(self) -> None:
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._command_loop, daemon=True)
        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.thread.start()
        self.poll_thread.start()
        self._log("KVH-DSP-Worker gestartet.")
        self._notify_state_changed()

    def stop(self) -> None:
        if not self.running:
            return
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
                self._log("KVH-DSP-Worker gestoppt.")
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
        else:
            raise ValueError(f"Unbekannter Befehl: {command}")

    def _connect(self, port: str, baudrate: int = DEFAULT_BAUDRATE) -> None:
        self._disconnect_silent()

        self.state.status_text = "Connecting"
        self._notify_state_changed()

        self.sensor = DSP3100(on_log=self._log)
        self.sensor.connect(port=port, baudrate=int(baudrate))

        self.state.connected = True
        self.state.port = port
        self.state.baudrate = int(baudrate)
        self.state.status_text = "Connected"
        self._update_state_from_sensor()
        self._log(f"KVH DSP verbunden: {port} @ {baudrate}.")

    def _disconnect(self) -> None:
        self._disconnect_silent()
        self.state.connected = False
        self.state.status_text = "Not Connected"
        self.state.port = None
        self.state.baudrate = None
        self._log("KVH DSP getrennt.")

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
        sensor = self._require_sensor()
        sensor.reset_angle()
        self._update_state_from_sensor()

    def _determine_drift(self, seconds: float) -> None:
        sensor = self._require_sensor()
        sensor.determine_drift(float(seconds))
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
        self.state.angle_deg = snap.angle_deg
        self.state.rate_dps = snap.rate_dps
        self.state.drift_dps = snap.drift_dps
        self.state.valid_packets = snap.valid_packets
        self.state.skipped_bytes = snap.skipped_bytes
        self.state.drift_active = snap.drift_active
        if snap.connected and self.state.status_text not in {"Error", "Connecting"}:
            self.state.status_text = "Connected"

    def _require_sensor(self) -> DSP3100:
        if self.sensor is None or not self.sensor.connected:
            raise RuntimeError("KVH DSP ist nicht verbunden.")
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

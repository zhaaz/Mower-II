from __future__ import annotations

import queue
import threading
import time
from dataclasses import replace
from typing import Any, Callable

from .component_event import ComponentEvent, EventLevel
from .gyems_rs485 import GyemsRmdRs485, GyemsProtocolError
from .gyems_state import GyemsState


StateCallback = Callable[[GyemsState], None]
EventCallback = Callable[[ComponentEvent], None]


class GyemsWorker:
    """Threaded worker for safe GYEMS/RMD RS-485 testing.

    The Tkinter GUI must never call serial commands directly. Commands are sent
    into this worker and serial I/O runs in the worker thread.
    """

    def __init__(
        self,
        *,
        on_state_changed: StateCallback | None = None,
        on_event: EventCallback | None = None,
        poll_interval_s: float = 0.2,
    ) -> None:
        self.on_state_changed = on_state_changed
        self.on_event = on_event
        self.poll_interval_s = float(poll_interval_s)

        self._commands: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        self._motor: GyemsRmdRs485 | None = None
        self._state = GyemsState()
        self._next_poll_time = 0.0

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._thread_main, daemon=True)
        self._thread.start()
        self._emit_info("GYEMS-Worker gestartet.")

    def stop(self) -> None:
        self._stop_event.set()
        self.send_command("stop_motor")
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None

    def send_command(self, command: str, **kwargs: Any) -> None:
        self._commands.put((command, kwargs))

    def get_state_snapshot(self) -> GyemsState:
        return replace(self._state)

    # --------------------------------------------------
    # Worker loop
    # --------------------------------------------------

    def _thread_main(self) -> None:
        self._publish_state()

        while not self._stop_event.is_set():
            try:
                command, kwargs = self._commands.get(timeout=0.02)
                self._handle_command(command, kwargs)
            except queue.Empty:
                pass
            except Exception as exc:
                self._set_error(f"Worker-Fehler: {exc}")

            self._poll_if_due()

        self._safe_shutdown_and_close()
        self._state.connected = False
        self._state.busy = False
        self._state.status_text = "Stopped"
        self._publish_state()
        self._emit_info("GYEMS-Worker beendet.")

    def _handle_command(self, command: str, kwargs: dict[str, Any]) -> None:
        handlers = {
            "connect": self._cmd_connect,
            "disconnect": self._cmd_disconnect,
            "read_model_info": self._cmd_read_model_info,
            "read_errors": self._cmd_read_errors,
            "clear_errors": self._cmd_clear_errors,
            "read_once": self._cmd_read_once,
            "stop_motor": self._cmd_stop_motor,
            "set_speed": self._cmd_set_speed,
            "move_abs": self._cmd_move_abs,
            "move_relative": self._cmd_move_relative,
            "set_reference_here": self._cmd_set_reference_here,
        }
        handler = handlers.get(command)
        if handler is None:
            self._emit_warning(f"Unbekannter Befehl: {command}")
            return
        handler(**kwargs)

    # --------------------------------------------------
    # Commands
    # --------------------------------------------------

    def _cmd_connect(self, *, port: str, baudrate: int = 115200, motor_id: int = 1, timeout: float = 0.25) -> None:
        self._safe_shutdown_and_close()
        self._state = GyemsState(
            connected=False,
            busy=True,
            status_text="Connecting",
            port=port,
            baudrate=int(baudrate),
            motor_id=int(motor_id),
        )
        self._publish_state()

        try:
            self._motor = GyemsRmdRs485(
                port=str(port),
                motor_id=int(motor_id),
                baudrate=int(baudrate),
                timeout=float(timeout),
                inter_cmd_delay=0.02,
            )
            self._motor.connect()
            self._state.connected = True
            self._state.busy = False
            self._state.status_text = "Connected"
            self._state.error_text = None
            self._emit_info(f"GYEMS verbunden: {port}, ID={int(motor_id)}, Baudrate={int(baudrate)}")
            self._publish_state()
            self._cmd_read_model_info()
            self._cmd_read_once()
        except Exception as exc:
            self._safe_shutdown_and_close()
            self._state.connected = False
            self._state.busy = False
            self._set_error(f"Verbinden fehlgeschlagen: {exc}")

    def _cmd_disconnect(self) -> None:
        self._safe_shutdown_and_close()
        self._state.connected = False
        self._state.busy = False
        self._state.status_text = "Disconnected"
        self._state.clear_measurement()
        self._publish_state()
        self._emit_info("GYEMS getrennt.")

    def _cmd_read_model_info(self) -> None:
        motor = self._require_motor()
        if motor is None:
            return
        try:
            info = motor.read_model_info()
            self._state.model_driver = info.driver
            self._state.model_motor = info.motor
            self._state.hw_version = info.hw_version
            self._state.fw_version = info.fw_version
            self._state.error_text = None
            self._emit_info(
                f"Modellinfo: Driver='{info.driver}', Motor='{info.motor}', HW={info.hw_version}, FW={info.fw_version}"
            )
            self._publish_state()
        except Exception as exc:
            self._register_io_error(f"Modellinfo lesen fehlgeschlagen: {exc}")

    def _cmd_read_errors(self) -> None:
        motor = self._require_motor()
        if motor is None:
            return
        try:
            self._state.error_flags = motor.read_error_flags()
            self._state.error_text = None
            self._emit_info(f"Fehlerflags gelesen: {self._state.error_flags}")
            self._publish_state()
        except Exception as exc:
            self._register_io_error(f"Fehlerflags lesen fehlgeschlagen: {exc}")

    def _cmd_clear_errors(self) -> None:
        motor = self._require_motor()
        if motor is None:
            return
        try:
            motor.clear_error_flags()
            self._state.error_flags = None
            self._state.error_text = None
            self._emit_info("Fehlerflags gelöscht.")
            self._publish_state()
        except Exception as exc:
            self._register_io_error(f"Fehlerflags löschen fehlgeschlagen: {exc}")

    def _cmd_read_once(self) -> None:
        self._read_live_values()

    def _cmd_stop_motor(self) -> None:
        motor = self._require_motor(silent=True)
        if motor is None:
            return
        try:
            # For manual tests, speed 0 is less destructive than shutdown on some controllers.
            motor.set_speed_deg_s(0.0)
            self._state.last_speed_cmd_dps = 0.0
            self._state.status_text = "Stopped"
            self._state.error_text = None
            self._emit_info("Motor gestoppt: Speed=0 deg/s.")
            self._publish_state()
        except Exception as exc:
            self._register_io_error(f"Motor stoppen fehlgeschlagen: {exc}")

    def _cmd_set_speed(self, *, speed_dps: float) -> None:
        motor = self._require_motor()
        if motor is None:
            return
        try:
            speed = self._limit_speed(float(speed_dps))
            motor.set_speed_deg_s(speed)
            self._state.last_speed_cmd_dps = speed
            self._state.status_text = f"Speed {speed:.1f} deg/s"
            self._state.error_text = None
            self._emit_info(f"Geschwindigkeit gesetzt: {speed:.1f} deg/s")
            self._publish_state()
        except Exception as exc:
            self._register_io_error(f"Geschwindigkeit setzen fehlgeschlagen: {exc}")

    def _cmd_move_abs(self, *, angle_deg: float) -> None:
        motor = self._require_motor()
        if motor is None:
            return
        try:
            angle = float(angle_deg)
            motor.move_to_abs_angle_deg(angle)
            self._state.last_abs_target_deg = angle
            self._state.status_text = f"Move abs {angle:.2f} deg"
            self._state.error_text = None
            self._emit_info(f"Absolute Position angefahren: {angle:.2f} deg")
            self._publish_state()
        except Exception as exc:
            self._register_io_error(f"Absolute Position fehlgeschlagen: {exc}")

    def _cmd_move_relative(self, *, delta_deg: float) -> None:
        angle = self._state.angle_deg
        if angle is None:
            self._cmd_read_once()
            angle = self._state.angle_deg
        if angle is None:
            self._emit_warning("Relative Bewegung nicht möglich: aktueller Winkel unbekannt.")
            return
        self._cmd_move_abs(angle_deg=float(angle) + float(delta_deg))

    def _cmd_set_reference_here(self) -> None:
        if self._state.angle_deg is None:
            self._cmd_read_once()
        if self._state.angle_deg is None:
            self._emit_warning("Referenz setzen nicht möglich: aktueller Winkel unbekannt.")
            return
        self._state.reference_offset_deg = float(self._state.angle_deg)
        self._state.update_relative_angle()
        self._emit_info(f"Referenz gesetzt: aktueller Winkel {self._state.reference_offset_deg:.3f} deg = 0.000 deg relativ.")
        self._publish_state()

    # --------------------------------------------------
    # Polling / I/O
    # --------------------------------------------------

    def _poll_if_due(self) -> None:
        if self._motor is None or not self._state.connected:
            return
        now = time.time()
        if now < self._next_poll_time:
            return
        self._next_poll_time = now + self.poll_interval_s
        self._read_live_values()

    def _read_live_values(self) -> None:
        motor = self._require_motor(silent=True)
        if motor is None:
            return
        try:
            angle = motor.read_singleturn_angle_deg()
            status = motor.read_status()

            self._state.angle_deg = float(angle)
            self._state.temperature_C = int(status.temperature_C)
            self._state.torque_current = int(status.torque_current)
            self._state.speed_raw = int(status.speed_raw)
            self._state.encoder_pos = int(status.encoder_pos)
            self._state.status_text = "Connected"
            self._state.error_text = None
            self._state.ok_count += 1
            self._state.update_relative_angle()
            self._publish_state()
        except (TimeoutError, GyemsProtocolError) as exc:
            self._register_io_error(f"Kommunikation: {exc}")
        except Exception as exc:
            self._register_io_error(f"Lesefehler: {exc}")

    def _require_motor(self, *, silent: bool = False) -> GyemsRmdRs485 | None:
        if self._motor is None or not self._state.connected:
            if not silent:
                self._emit_warning("GYEMS ist nicht verbunden.")
            return None
        return self._motor

    def _safe_shutdown_and_close(self) -> None:
        if self._motor is None:
            return
        try:
            if self._motor.is_connected():
                try:
                    self._motor.set_speed_deg_s(0.0)
                except Exception:
                    pass
                self._motor.close()
        finally:
            self._motor = None

    @staticmethod
    def _limit_speed(speed_dps: float, *, max_abs_dps: float = 90.0) -> float:
        return max(-max_abs_dps, min(max_abs_dps, float(speed_dps)))

    # --------------------------------------------------
    # State / events
    # --------------------------------------------------

    def _publish_state(self) -> None:
        if self.on_state_changed is not None:
            try:
                self.on_state_changed(replace(self._state))
            except Exception:
                pass

    def _emit_info(self, message: str) -> None:
        self._emit(EventLevel.INFO, message)

    def _emit_warning(self, message: str) -> None:
        self._emit(EventLevel.WARNING, message)

    def _set_error(self, message: str) -> None:
        self._state.error_text = message
        self._state.status_text = "Error"
        self._state.error_count += 1
        self._publish_state()
        self._emit(EventLevel.ERROR, message)

    def _register_io_error(self, message: str) -> None:
        self._state.error_text = message
        self._state.error_count += 1
        self._publish_state()
        self._emit(EventLevel.WARNING, message)

    def _emit(self, level: EventLevel, message: str) -> None:
        if self.on_event is not None:
            try:
                self.on_event(ComponentEvent(source="GYEMS", level=level, message=message))
            except Exception:
                pass

# xyz_robot_worker.py

import queue
import threading
from typing import Any, Callable

from XYZ_Robot.xyz_robot import XYZRobot
from XYZ_Robot.xyz_robot_state import XYZRobotState
from XYZ_Robot.component_event import ComponentEvent, EventLevel


class XYZRobotWorker:
    COMPONENT_NAME = "XYZRobot"

    def __init__(
            self,
            on_event: Callable[[ComponentEvent], None] | None = None,
            on_state_changed: Callable[[XYZRobotState], None] | None = None,
    ):
        self.robot: XYZRobot | None = None
        self.state = XYZRobotState()

        self.on_event = on_event
        self.on_state_changed = on_state_changed

        self.command_queue: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()

        self.thread: threading.Thread | None = None
        self.running = False

    # --------------------------------------------------
    # Thread
    # --------------------------------------------------

    def start(self) -> None:
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

        self._emit_info("Worker gestartet")
        self._notify_state_changed()

    def stop(self) -> None:
        if not self.running:
            return

        self.running = False
        self.send_command("stop")

    def send_command(self, command: str, **kwargs) -> None:
        self.command_queue.put((command, kwargs))

    # --------------------------------------------------
    # Worker Loop
    # --------------------------------------------------

    def _run(self) -> None:
        while True:
            command, kwargs = self.command_queue.get()

            if command == "stop":
                self._disconnect_silent()
                self._emit_info("Worker gestoppt")
                break

            self._set_busy(True)

            try:
                self._execute_command(command, kwargs)
                self.state.error_text = None

            except Exception as e:
                self.state.error_text = str(e)
                self.state.status_text = "Error"
                self._emit_error(str(e))

            finally:
                self._set_busy(False)
                self._notify_state_changed()

    def _execute_command(self, command: str, kwargs: dict[str, Any]) -> None:
        if command == "connect":
            self._connect(**kwargs)

        elif command == "disconnect":
            self._disconnect()

        elif command == "read_position":
            self._read_position()

        elif command == "home_all":
            self._home_all()

        elif command == "jog":
            self._jog(**kwargs)

        elif command == "move_absolute":
            self._move_absolute(**kwargs)

        elif command == "move_absolute_verified":
            self._move_absolute_verified(**kwargs)

        elif command == "mark_point":
            self._mark_point(**kwargs)

        elif command == "mark_line_absolute":
            self._mark_line_absolute(**kwargs)

        else:
            raise ValueError(f"Unbekannter Befehl: {command}")

    # --------------------------------------------------
    # Commands
    # --------------------------------------------------

    def _connect(self, port: str, baudrate: int) -> None:
        self._emit_info(f"Verbinde mit {port} @ {baudrate}")
        self.state.status_text = "Connecting"
        self._notify_state_changed()

        self.robot = XYZRobot(port=port, baudrate=baudrate)
        self.robot.connect()

        self.state.connected = True
        self.state.homed = False
        self.state.port = port
        self.state.baudrate = baudrate
        self.state.status_text = "Connected"
        self.state.error_text = None

        self._emit_info("Verbindung hergestellt")

        # Verbindung plausibilisieren
        self._read_position()

    def _disconnect(self) -> None:
        self._disconnect_silent()

        self.state.connected = False
        self.state.homed = False
        self.state.status_text = "Not Connected"
        self.state.error_text = None
        self.state.clear_position()

        self._emit_info("Verbindung getrennt")
        self._notify_state_changed()

    def _read_position(self) -> None:
        robot = self._require_robot()

        position = robot.get_current_position()
        self.state.set_position(position)

        self._emit_info(
            f"Position gelesen: "
            f"X={position['X']:.3f}, "
            f"Y={position['Y']:.3f}, "
            f"Z={position['Z']:.3f}"
        )

        self._notify_state_changed()

    def _home_all(self) -> None:
        robot = self._require_robot()

        self.state.status_text = "Homing"
        self._notify_state_changed()
        self._emit_info("Homing gestartet")

        robot.homing()

        self.state.homed = True
        self.state.status_text = "Connected"

        self._emit_info("Homing abgeschlossen")

        self._read_position()

    def _jog(
            self,
            dx: float | None = None,
            dy: float | None = None,
            dz: float | None = None,
            feedrate: float | None = None,
    ) -> None:
        robot = self._require_robot()

        self.state.status_text = "Moving"
        self._notify_state_changed()

        robot.move_relative(
            dx=dx,
            dy=dy,
            dz=dz,
            feedrate=feedrate
        )

        self.state.status_text = "Connected"
        self._read_position()

    def _move_absolute(
            self,
            x: float | None = None,
            y: float | None = None,
            z: float | None = None,
            feedrate: float | None = None,
    ) -> None:
        robot = self._require_robot()

        self.state.status_text = "Moving"
        self._notify_state_changed()

        robot.move_absolute(
            x=x,
            y=y,
            z=z,
            feedrate=feedrate
        )

        self.state.status_text = "Connected"

        self._read_position()

    def _move_absolute_verified(
            self,
            x: float | None = None,
            y: float | None = None,
            z: float | None = None,
            feedrate: float | None = None,
            tolerance_mm: float = 0.05,
    ) -> None:
        robot = self._require_robot()

        self.state.status_text = "Moving"
        self._notify_state_changed()

        # Bewegung ausführen
        robot.move_absolute(
            x=x,
            y=y,
            z=z,
            feedrate=feedrate
        )

        # Istposition lesen
        position = robot.get_current_position()

        self.state.set_position(position)

        # Prüfen
        if x is not None:
            dx = position["X"] - x

            if abs(dx) > tolerance_mm:
                raise RuntimeError(
                    f"X außerhalb Toleranz: "
                    f"Soll={x:.3f}, "
                    f"Ist={position['X']:.3f}, "
                    f"dX={dx:.3f}"
                )

        if y is not None:
            dy = position["Y"] - y

            if abs(dy) > tolerance_mm:
                raise RuntimeError(
                    f"Y außerhalb Toleranz: "
                    f"Soll={y:.3f}, "
                    f"Ist={position['Y']:.3f}, "
                    f"dY={dy:.3f}"
                )

        if z is not None:
            dz = position["Z"] - z

            if abs(dz) > tolerance_mm:
                raise RuntimeError(
                    f"Z außerhalb Toleranz: "
                    f"Soll={z:.3f}, "
                    f"Ist={position['Z']:.3f}, "
                    f"dZ={dz:.3f}"
                )

        self.state.status_text = "Connected"

        self._emit_info(
            f"Position verifiziert: "
            f"X={position['X']:.3f}, "
            f"Y={position['Y']:.3f}, "
            f"Z={position['Z']:.3f}"
        )

        self._notify_state_changed()

    def _mark_point(
            self,
            x: float,
            y: float,
            marker_size: float,
            marker_shape: str,
            label: str | None = None,
            angle_deg: float = 0.0,
            z_mark_mm: float | None = None,
            z_clear_mm: float | None = None,
            z_travel_mm: float | None = None,
    ) -> None:
        robot = self._require_robot()

        self.state.status_text = "Marking"
        self._notify_state_changed()

        if hasattr(robot, "set_marker_heights"):
            robot.set_marker_heights(
                z_mark_mm=z_mark_mm,
                z_clear_mm=z_clear_mm,
                z_travel_mm=z_travel_mm,
            )

        marker_heights = ""
        if z_mark_mm is not None:
            marker_heights = (
                f", Z_MARK={float(z_mark_mm):.3f} mm"
                f", Z_CLEAR={float(z_clear_mm) if z_clear_mm is not None else float(z_mark_mm) + 5.0:.3f} mm"
                f", Z_TRAVEL={float(z_travel_mm) if z_travel_mm is not None else float(z_mark_mm) + 10.0:.3f} mm"
            )

        label_text = str(label).strip() if label is not None else ""
        if label_text:
            self._emit_info(f"Markiere Punkt {label_text}: X={x:.3f}, Y={y:.3f}{marker_heights}")
            robot.mark_point_with_label(
                x=x,
                y=y,
                label=label_text,
                marker_size=marker_size,
                marker_shape=marker_shape,
                angle_deg=angle_deg,
            )
            done_text = f"Punkt {label_text} markiert"
        else:
            self._emit_info(f"Markiere Punkt ohne Beschriftung: X={x:.3f}, Y={y:.3f}{marker_heights}")
            robot.mark_point(
                x=x,
                y=y,
                size=marker_size,
                shape=marker_shape,
                angle_deg=angle_deg,
            )
            done_text = "Punkt ohne Beschriftung markiert"

        self.state.status_text = "Connected"
        self._emit_info(done_text)

        self._read_position()

    def _mark_line_absolute(
            self,
            start_x: float,
            start_y: float,
            end_x: float,
            end_y: float,
    ) -> None:
        robot = self._require_robot()

        self.state.status_text = "Marking"
        self._notify_state_changed()

        self._emit_info(
            f"Markiere Linie: "
            f"X1={start_x:.3f}, Y1={start_y:.3f} -> "
            f"X2={end_x:.3f}, Y2={end_y:.3f}"
        )

        robot.mark_line_absolute(
            start_x=start_x,
            start_y=start_y,
            end_x=end_x,
            end_y=end_y,
        )

        self.state.status_text = "Connected"
        self._emit_info("Linie markiert")

        self._read_position()

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------

    def _require_robot(self) -> XYZRobot:
        if self.robot is None or not self.robot.is_connected:
            raise RuntimeError("XYZ-Roboter ist nicht verbunden.")

        return self.robot

    def _disconnect_silent(self) -> None:
        try:
            if self.robot is not None and self.robot.is_connected:
                self.robot.disconnect()
        finally:
            self.robot = None

    def _set_busy(self, busy: bool) -> None:
        self.state.busy = busy
        self._notify_state_changed()

    def _notify_state_changed(self) -> None:
        if self.on_state_changed:
            self.on_state_changed(self.state)

    def _emit(
            self,
            level: EventLevel,
            message: str,
            data: dict[str, Any] | None = None,
    ) -> None:
        if self.on_event:
            event = ComponentEvent(
                component=self.COMPONENT_NAME,
                level=level,
                message=message,
                data=data,
            )
            self.on_event(event)

    def _emit_info(self, message: str, data: dict[str, Any] | None = None) -> None:
        self._emit(EventLevel.INFO, message, data)

    def _emit_warning(self, message: str, data: dict[str, Any] | None = None) -> None:
        self._emit(EventLevel.WARNING, message, data)

    def _emit_error(self, message: str, data: dict[str, Any] | None = None) -> None:
        self._emit(EventLevel.ERROR, message, data)
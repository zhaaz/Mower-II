# App/dialogs/marker_offset_calibration_dialog.py

from __future__ import annotations

import csv
import queue
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable, Literal

import numpy as np

from config.mower_config import CONFIG, update_marker_to_reflector_robot
from Transformation.marker_offset_calibration import (
    MarkerOffsetCalibrationResult,
    compute_marker_to_reflector_offset,
    format_offset_result,
    make_calibration_sample,
)


StateGetter = Callable[[], Any]
LogFunction = Callable[[str], None]
FinishedCallback = Callable[[], None]

DialogResult = Literal["ok", "measure", "cancel"]


FONT_NORMAL = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SECTION = ("Segoe UI", 11, "bold")
FONT_MONO = ("Consolas", 10)


ROBOT_POINTS: list[tuple[str, float, float, float]] = [
    ("P1", 160.0, 130.0, 180.0),
    ("P2", 330.0, 145.0, 180.0),
    ("P3", 350.0, 265.0, 180.0),
    ("P4", 185.0, 285.0, 180.0),
    ("P5", 255.0, 205.0, 180.0),
]

# Parkposition nach dem Markieren und vor der manuellen CCR-/Nest-Messung.
# Es wird kein neues Homing ausgefuehrt; der Roboter faehrt im bereits
# referenzierten Koordinatensystem auf diese sichere Position.
PARK_X_MM = 10.0
PARK_Y_MM = 10.0


@dataclass
class DialogRequest:
    title: str
    message: str
    mode: Literal["info", "measure"]
    event: threading.Event
    result: DialogResult | None = None


def show_marker_offset_calibration_dialog(
        *,
        parent: tk.Misc,
        xyz_worker: Any,
        tracker_receiver: Any,
        xyz_state_getter: StateGetter,
        on_finished: FinishedCallback | None = None,
        log: LogFunction | None = None,
) -> None:
    """Dialog zur Marker-/Reflektoroffset-Kalibrierung."""

    dialog = MarkerOffsetCalibrationDialog(
        parent=parent,
        xyz_worker=xyz_worker,
        tracker_receiver=tracker_receiver,
        xyz_state_getter=xyz_state_getter,
        on_finished=on_finished,
        external_log=log,
    )
    dialog.show()


class MarkerOffsetCalibrationDialog:
    def __init__(
            self,
            *,
            parent: tk.Misc,
            xyz_worker: Any,
            tracker_receiver: Any,
            xyz_state_getter: StateGetter,
            on_finished: FinishedCallback | None = None,
            external_log: LogFunction | None = None,
    ) -> None:
        self.parent = parent
        self.xyz_worker = xyz_worker
        self.tracker_receiver = tracker_receiver
        self.xyz_state_getter = xyz_state_getter
        self.on_finished = on_finished
        self.external_log = external_log

        self.gui_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.abort_event = threading.Event()
        self.measure_button_event = threading.Event()
        self.workflow_thread: threading.Thread | None = None
        self.workflow_running = False
        self.closed = False

        self.reflector_lt_points: dict[str, np.ndarray] = {}
        self.marker_lt_points: dict[str, np.ndarray] = {}
        self.last_result: MarkerOffsetCalibrationResult | None = None
        self.previous_offset_robot = tuple(float(v) for v in CONFIG.transformation.marker_to_reflector_robot)

        self.window = tk.Toplevel(parent)
        self.window.title("Marker-/Reflektoroffset kalibrieren")
        self.window.minsize(860, 560)
        self.window.transient(parent)
        self.window.grab_set()

        _center_window(parent, self.window, 980, 700)

        self._configure_styles()
        self._build_ui()
        self.window.protocol("WM_DELETE_WINDOW", self.discard_and_close)
        self.window.bind("<Escape>", lambda _event: self.discard_and_close())

    def show(self) -> None:
        self.window.after(100, self.process_gui_queue)
        self.window.after(150, self.start_workflow)

    # --------------------------------------------------
    # UI
    # --------------------------------------------------

    def _configure_styles(self) -> None:
        style = ttk.Style(self.window)
        style.configure("Offset.TLabel", font=FONT_NORMAL)
        style.configure("OffsetBold.TLabel", font=FONT_BOLD)
        style.configure("Offset.TButton", font=FONT_NORMAL, padding=(8, 4))
        style.configure("Offset.TLabelframe.Label", font=FONT_SECTION)

    def _build_ui(self) -> None:
        root = ttk.Frame(self.window, padding=12)
        root.grid(row=0, column=0, sticky="nsew")

        self.window.grid_rowconfigure(0, weight=1)
        self.window.grid_columnconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(3, weight=1)

        status_frame = ttk.LabelFrame(root, text="Status", padding=10, style="Offset.TLabelframe")
        status_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        status_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(status_frame, text="Aktueller Schritt:", style="Offset.TLabel").grid(
            row=0, column=0, padx=(0, 8), pady=3, sticky="w"
        )
        self.status_var = tk.StringVar(value="Vorbereitung...")
        ttk.Label(status_frame, textvariable=self.status_var, style="Offset.TLabel").grid(
            row=0, column=1, pady=3, sticky="ew"
        )

        ttk.Label(status_frame, text="Fortschritt:", style="Offset.TLabel").grid(
            row=1, column=0, padx=(0, 8), pady=3, sticky="w"
        )
        progress_row = ttk.Frame(status_frame)
        progress_row.grid(row=1, column=1, pady=3, sticky="ew")
        progress_row.grid_columnconfigure(0, weight=1)

        self.progress_var = tk.DoubleVar(value=0.0)
        ttk.Progressbar(
            progress_row,
            orient="horizontal",
            mode="determinate",
            variable=self.progress_var,
            maximum=100.0,
        ).grid(row=0, column=0, sticky="ew")

        self.progress_text_var = tk.StringVar(value="0/0")
        ttk.Label(progress_row, textvariable=self.progress_text_var, width=10, style="Offset.TLabel").grid(
            row=0, column=1, padx=(8, 0), sticky="e"
        )

        points_frame = ttk.LabelFrame(root, text="Kalibrierpunkte", padding=10, style="Offset.TLabelframe")
        points_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        points_text = "   ".join(
            f"{label}: X={x:.0f} Y={y:.0f} Z={z:.0f}" for label, x, y, z in ROBOT_POINTS
        )
        ttk.Label(points_frame, text=points_text, style="Offset.TLabel").grid(
            row=0, column=0, sticky="w"
        )

        result_frame = ttk.LabelFrame(root, text="Ergebnis", padding=10, style="Offset.TLabelframe")
        result_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        for col in (1, 3, 5):
            result_frame.grid_columnconfigure(col, weight=1)

        self.result_offset_var = tk.StringVar(value="-")
        self.result_previous_var = tk.StringVar(value=self._format_vector(self.previous_offset_robot))
        self.result_delta_var = tk.StringVar(value="-")
        self.result_rms_var = tk.StringVar(value="-")
        self.result_max_var = tk.StringVar(value="-")
        self.result_std_var = tk.StringVar(value="-")

        ttk.Label(result_frame, text="Neuer Offset:", style="Offset.TLabel").grid(row=0, column=0, padx=(0, 6), pady=2, sticky="w")
        ttk.Label(result_frame, textvariable=self.result_offset_var, style="Offset.TLabel").grid(row=0, column=1, columnspan=5, pady=2, sticky="ew")

        ttk.Label(result_frame, text="Bisher:", style="Offset.TLabel").grid(row=1, column=0, padx=(0, 6), pady=2, sticky="w")
        ttk.Label(result_frame, textvariable=self.result_previous_var, style="Offset.TLabel").grid(row=1, column=1, columnspan=5, pady=2, sticky="ew")

        ttk.Label(result_frame, text="Differenz:", style="Offset.TLabel").grid(row=2, column=0, padx=(0, 6), pady=2, sticky="w")
        ttk.Label(result_frame, textvariable=self.result_delta_var, style="Offset.TLabel").grid(row=2, column=1, columnspan=5, pady=2, sticky="ew")

        ttk.Label(result_frame, text="RMS:", style="Offset.TLabel").grid(row=3, column=0, padx=(0, 6), pady=2, sticky="w")
        ttk.Label(result_frame, textvariable=self.result_rms_var, style="Offset.TLabel").grid(row=3, column=1, padx=(0, 16), pady=2, sticky="ew")
        ttk.Label(result_frame, text="Max:", style="Offset.TLabel").grid(row=3, column=2, padx=(0, 6), pady=2, sticky="w")
        ttk.Label(result_frame, textvariable=self.result_max_var, style="Offset.TLabel").grid(row=3, column=3, padx=(0, 16), pady=2, sticky="ew")
        ttk.Label(result_frame, text="Std:", style="Offset.TLabel").grid(row=3, column=4, padx=(0, 6), pady=2, sticky="w")
        ttk.Label(result_frame, textvariable=self.result_std_var, style="Offset.TLabel").grid(row=3, column=5, pady=2, sticky="ew")

        log_frame = ttk.LabelFrame(root, text="Log", padding=8, style="Offset.TLabelframe")
        log_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 10))
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        self.textbox = ScrolledText(
            log_frame,
            wrap="none",
            height=18,
            font=FONT_MONO,
            background="#ffffff",
            foreground="#111111",
        )
        self.textbox.grid(row=0, column=0, sticky="nsew")

        button_frame = ttk.Frame(root)
        button_frame.grid(row=4, column=0, sticky="ew")
        for col in range(4):
            button_frame.grid_columnconfigure(col, weight=1)

        self.btn_cancel = ttk.Button(
            button_frame,
            text="Abbrechen",
            command=self.cancel_workflow,
            style="Offset.TButton",
        )
        self.btn_cancel.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.btn_repeat = ttk.Button(
            button_frame,
            text="Kalibrierung Wiederholen",
            command=self.repeat_workflow,
            state="disabled",
            style="Offset.TButton",
        )
        self.btn_repeat.grid(row=0, column=1, padx=6, sticky="ew")

        self.btn_discard = ttk.Button(
            button_frame,
            text="Kalibrierung Verwerfen",
            command=self.discard_and_close,
            style="Offset.TButton",
        )
        self.btn_discard.grid(row=0, column=2, padx=6, sticky="ew")

        self.btn_accept = ttk.Button(
            button_frame,
            text="Offset Übernehmen",
            command=self.accept_calibration,
            state="disabled",
            style="Offset.TButton",
        )
        self.btn_accept.grid(row=0, column=3, padx=(6, 0), sticky="ew")

    # --------------------------------------------------
    # Workflow
    # --------------------------------------------------

    def start_workflow(self) -> None:
        if self.workflow_running:
            return

        self._reset_result_display()
        self.abort_event.clear()
        self.measure_button_event.clear()
        self.reflector_lt_points.clear()
        self.marker_lt_points.clear()
        self.workflow_running = True

        self.btn_cancel.configure(state="normal")
        self.btn_repeat.configure(state="disabled")
        self.btn_accept.configure(state="disabled")
        self.btn_discard.configure(state="normal")

        self.workflow_thread = threading.Thread(target=self._workflow_thread_main, daemon=True)
        self.workflow_thread.start()
        self.log("Marker-/Reflektoroffset-Kalibrierung gestartet.")

    def _workflow_thread_main(self) -> None:
        try:
            self._run_workflow()
        except InterruptedError:
            self.log("")
            self.log("Kalibrierung abgebrochen.")
            self.set_status("Kalibrierung abgebrochen.")
        except Exception as exc:
            self.log("")
            self.log(f"FEHLER: {exc}")
            self.set_status(f"Fehler: {exc}")
        finally:
            self.gui_queue.put(("workflow_finished", None))

    def _run_workflow(self) -> None:
        self._validate_runtime_state()

        self.log("Ablauf:")
        self.log("1. Roboter markiert feste Kalibrierpunkte und Reflektor oben wird gemessen.")
        self.log("2. Danach faehrt der Roboter auf Parkposition X=10 mm / Y=10 mm.")
        self.log("3. Danach werden die markierten Punkte manuell mit CCR/Nest gemessen.")
        self.log("4. Aus beiden Messsaetzen wird marker_to_reflector_robot berechnet.")

        self.run_robot_mark_and_reflector_measurement()
        self.check_abort()

        self.move_robot_to_park_position()
        self.check_abort()

        response = self.show_info_dialog_and_wait(
            title="Manuelle Messung vorbereiten",
            message=(
                "Alle Kalibrierpunkte wurden markiert und der obere Reflektor wurde gemessen.\n\n"
                "Der Roboter wurde auf die Parkposition X=10 mm / Y=10 mm gefahren.\n"
                "Der Wagen kann nun bei Bedarf zusaetzlich gesichert werden.\n\n"
                "Im naechsten Schritt werden die Punkte P1 bis P5 manuell mit CCR/Nest gemessen."
            ),
        )
        if response != "ok":
            raise InterruptedError()

        self.check_abort()
        self.run_manual_marker_measurements()
        self.check_abort()

        result = self.compute_result()
        self.last_result = result

        self.log_result(result)
        self.save_result_files(result)
        self.gui_queue.put(("result_ready", result))
        self.set_status("Kalibrierung abgeschlossen. Ergebnis prüfen und ggf. übernehmen.")

    def _validate_runtime_state(self) -> None:
        if self.xyz_worker is None:
            raise RuntimeError("XYZ-Worker ist nicht verfügbar.")
        if self.tracker_receiver is None:
            raise RuntimeError("LasertrackerReceiver ist nicht verfügbar.")
        if not bool(getattr(self.tracker_receiver, "running", False)):
            raise RuntimeError("LasertrackerReceiver läuft nicht.")

        state = self.xyz_state_getter()
        if state is None:
            raise RuntimeError("Kein XYZ-Zustand verfügbar.")
        if not bool(getattr(state, "connected", False)):
            raise RuntimeError("XYZ ist nicht verbunden.")
        if not bool(getattr(state, "homed", False)):
            raise RuntimeError("XYZ-Homing wurde noch nicht durchgeführt.")

    def run_robot_mark_and_reflector_measurement(self) -> None:
        self.log("")
        self.log("=== Schritt 1: Punkte markieren und Reflektor oben messen ===")

        total = len(ROBOT_POINTS) * 3
        step = 0

        for label, x, y, z in ROBOT_POINTS:
            self.check_abort()
            self.log("")
            self.log(f"--- {label} ---")
            self.set_status(f"{label}: fahre Kalibrierpunkt an.")
            step += 1
            self.set_progress(step, total)
            self.log(f"Fahre Kalibrierpunkt: X={x:.3f}, Y={y:.3f}, Z={z:.3f}")
            self.send_robot_command(
                "move_absolute_verified",
                timeout_s=180.0,
                x=x,
                y=y,
                z=z,
                feedrate=CONFIG.xyz.default_feedrate,
                tolerance_mm=CONFIG.xyz.tolerance_mm,
            )

            self.check_abort()
            self.set_status(f"{label}: markiere Punkt.")
            step += 1
            self.set_progress(step, total)
            self.log(
                f"Markiere {label}: {CONFIG.marker.shape}, Größe={CONFIG.marker.size_mm:.3f} mm"
            )
            self.send_robot_command(
                "mark_point",
                timeout_s=180.0,
                x=x,
                y=y,
                label=label,
                marker_size=CONFIG.marker.size_mm,
                marker_shape=CONFIG.marker.shape,
                angle_deg=CONFIG.marker.angle_deg,
            )

            self.check_abort()
            self.set_status(f"{label}: messe oberen Reflektor.")
            step += 1
            self.set_progress(step, total)
            self.log(f"Fahre wieder exakt auf Punktmitte {label}.")
            self.send_robot_command(
                "move_absolute_verified",
                timeout_s=180.0,
                x=x,
                y=y,
                z=z,
                feedrate=CONFIG.xyz.default_feedrate,
                tolerance_mm=CONFIG.xyz.tolerance_mm,
            )
            self.reflector_lt_points[label] = self.capture_tracker_point(f"{label} reflector_lt")

    def move_robot_to_park_position(self) -> None:
        """Faehrt den Roboter nach dem Markieren auf eine sichere Parkposition.

        Wichtig:
            Es wird bewusst kein home_all ausgefuehrt. Die Fahrt erfolgt im
            bereits referenzierten Koordinatensystem ueber move_absolute_verified.
        """

        self.log("")
        self.log("=== Schritt 2: Roboter auf Parkposition fahren ===")

        safe_z = float(getattr(CONFIG.xyz, "z_max", 200.0))
        feedrate = float(getattr(CONFIG.xyz, "default_feedrate", 6000.0))
        tolerance_mm = float(getattr(CONFIG.xyz, "tolerance_mm", 0.05))

        state = self.xyz_state_getter()
        current_x = getattr(state, "x", None) if state is not None else None
        current_y = getattr(state, "y", None) if state is not None else None

        self.set_status("Fahre Roboter auf sichere Z-Parkhoehe.")

        if current_x is not None and current_y is not None:
            self.log(
                f"Fahre zuerst auf sichere Z-Hoehe: "
                f"X={float(current_x):.3f}, Y={float(current_y):.3f}, Z={safe_z:.3f}"
            )
            self.send_robot_command(
                "move_absolute_verified",
                timeout_s=180.0,
                x=float(current_x),
                y=float(current_y),
                z=safe_z,
                feedrate=feedrate,
                tolerance_mm=tolerance_mm,
            )
        else:
            self.log(
                "Aktuelle XY-Position nicht sicher bekannt; "
                "fahre direkt auf Parkposition mit sicherer Z-Hoehe."
            )

        self.check_abort()
        self.set_status(f"Fahre Parkposition X={PARK_X_MM:.1f} / Y={PARK_Y_MM:.1f} an.")
        self.log(
            f"Fahre Parkposition: X={PARK_X_MM:.3f}, "
            f"Y={PARK_Y_MM:.3f}, Z={safe_z:.3f}"
        )
        self.send_robot_command(
            "move_absolute_verified",
            timeout_s=180.0,
            x=PARK_X_MM,
            y=PARK_Y_MM,
            z=safe_z,
            feedrate=feedrate,
            tolerance_mm=tolerance_mm,
        )

        self.log("Parkposition erreicht. Manuelle Messung kann vorbereitet werden.")

    def run_manual_marker_measurements(self) -> None:
        self.log("")
        self.log("=== Schritt 3: Manuelle Messung der markierten Punkte ===")

        total = len(ROBOT_POINTS)
        for index, (label, _, _, _) in enumerate(ROBOT_POINTS, start=1):
            self.check_abort()
            self.set_status(f"Bitte CCR/Nest auf {label} setzen und messen.")
            self.set_progress(index - 1, total)
            self.measure_button_event.clear()

            response = self.show_measure_dialog_and_wait(label)
            if response == "cancel":
                raise InterruptedError()

            self.check_abort()
            self.log("")
            self.log(f"Manuelle Messung {label}: CCR/Nest wird gemessen.")

            marker_lt_ccr = self.capture_tracker_point(f"{label} marker_lt CCR center")
            marker_lt = marker_lt_ccr.copy()

            # Annahme: LT-Z zeigt nach oben; gemessen wird CCR-Zentrum.
            marker_lt[2] -= CONFIG.tracker.ccr_radius_mm
            self.marker_lt_points[label] = marker_lt

            self.log(
                f"{label} marker_lt Bodenpunkt korrigiert: "
                f"X={marker_lt[0]:.6f}, Y={marker_lt[1]:.6f}, Z={marker_lt[2]:.6f}"
            )
            self.set_progress(index, total)

    def compute_result(self) -> MarkerOffsetCalibrationResult:
        samples = []
        for label, x, y, z in ROBOT_POINTS:
            samples.append(
                make_calibration_sample(
                    label=label,
                    robot_marker=[x, y, z],
                    reflector_lt=self.reflector_lt_points[label],
                    marker_lt=self.marker_lt_points[label],
                )
            )
        return compute_marker_to_reflector_offset(samples)

    # --------------------------------------------------
    # Dialog handling
    # --------------------------------------------------

    def show_info_dialog_and_wait(self, title: str, message: str) -> DialogResult:
        request = DialogRequest(title=title, message=message, mode="info", event=threading.Event())
        self.gui_queue.put(("dialog", request))
        while not request.event.wait(timeout=0.1):
            self.check_abort()
        return request.result or "cancel"

    def show_measure_dialog_and_wait(self, label: str) -> DialogResult:
        request = DialogRequest(
            title=f"Manuelle Messung {label}",
            message=(
                f"Bitte CCR/Nest sauber auf {label} setzen.\n\n"
                "Wenn der Reflektor stabil auf der Markierung sitzt, Messen drücken."
            ),
            mode="measure",
            event=threading.Event(),
        )
        self.gui_queue.put(("dialog", request))
        while not request.event.wait(timeout=0.1):
            self.check_abort()
            if self.measure_button_event.is_set():
                request.result = "measure"
                request.event.set()
                break
        return request.result or "cancel"

    def create_info_dialog(self, request: DialogRequest) -> None:
        dialog = tk.Toplevel(self.window)
        dialog.title(request.title)
        dialog.resizable(False, False)
        dialog.transient(self.window)
        dialog.grab_set()
        _center_window(self.window, dialog, 560, 250)

        frame = ttk.Frame(dialog, padding=14)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)

        ttk.Label(frame, text=request.message, wraplength=520, justify="left", style="Offset.TLabel").grid(
            row=0, column=0, pady=(0, 14), sticky="ew"
        )

        def ok() -> None:
            request.result = "ok"
            request.event.set()
            dialog.destroy()

        ttk.Button(frame, text="OK", command=ok, style="Offset.TButton").grid(
            row=1, column=0, sticky="ew"
        )
        dialog.protocol("WM_DELETE_WINDOW", ok)

    def create_measure_dialog(self, request: DialogRequest) -> None:
        dialog = tk.Toplevel(self.window)
        dialog.title(request.title)
        dialog.resizable(False, False)
        dialog.transient(self.window)
        dialog.grab_set()
        _center_window(self.window, dialog, 560, 270)

        frame = ttk.Frame(dialog, padding=14)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)

        ttk.Label(frame, text=request.message, wraplength=520, justify="left", style="Offset.TLabel").grid(
            row=0, column=0, pady=(0, 14), sticky="ew"
        )

        buttons = ttk.Frame(frame)
        buttons.grid(row=1, column=0, sticky="ew")
        buttons.grid_columnconfigure(0, weight=1)
        buttons.grid_columnconfigure(1, weight=1)

        def measure() -> None:
            request.result = "measure"
            request.event.set()
            dialog.destroy()

        def cancel() -> None:
            request.result = "cancel"
            request.event.set()
            dialog.destroy()

        ttk.Button(buttons, text="Messen", command=measure, style="Offset.TButton").grid(
            row=0, column=0, padx=(0, 6), sticky="ew"
        )
        ttk.Button(buttons, text="Abbrechen", command=cancel, style="Offset.TButton").grid(
            row=0, column=1, padx=(6, 0), sticky="ew"
        )
        dialog.protocol("WM_DELETE_WINDOW", cancel)

    # --------------------------------------------------
    # Hardware helpers
    # --------------------------------------------------

    def send_robot_command(self, command: str, timeout_s: float, **kwargs: Any) -> None:
        self.xyz_worker.send_command(command, **kwargs)
        self.wait_robot_done(timeout_s=timeout_s)

    def wait_robot_done(self, timeout_s: float) -> None:
        start = time.time()
        while time.time() - start < timeout_s:
            self.check_abort()
            state = self.xyz_state_getter()
            queue_empty = True
            try:
                queue_empty = self.xyz_worker.command_queue.empty()
            except Exception:
                queue_empty = True

            busy = bool(getattr(state, "busy", False)) if state is not None else False
            error_text = getattr(state, "error_text", "") if state is not None else ""

            if queue_empty and not busy:
                if error_text:
                    raise RuntimeError(str(error_text))
                return
            time.sleep(0.05)
        raise TimeoutError("Timeout beim Warten auf XYZRobotWorker.")

    def capture_tracker_point(self, label: str) -> np.ndarray:
        if self.tracker_receiver is None or not bool(getattr(self.tracker_receiver, "running", False)):
            raise RuntimeError("LasertrackerReceiver läuft nicht.")

        self.log(f"Messe {label} ...")
        measurement = self.tracker_receiver.capture_stable_point(
            timeout_s=CONFIG.tracker.capture_timeout_s,
            min_age_after_start_s=0.1,
        )
        point = np.array([measurement.x, measurement.y, measurement.z], dtype=float)
        self.log(f"{label}: X={point[0]:.6f}, Y={point[1]:.6f}, Z={point[2]:.6f}")
        return point

    # --------------------------------------------------
    # Results
    # --------------------------------------------------

    def log_result(self, result: MarkerOffsetCalibrationResult) -> None:
        previous = np.asarray(self.previous_offset_robot, dtype=float)
        current = result.mean_offset_robot
        delta = current - previous

        self.log("")
        self.log("=" * 80)
        self.log("ERGEBNIS DER KALIBRIERUNG")
        self.log("=" * 80)
        self.log(format_offset_result(result))

        self.log("")
        self.log("Vergleich zur letzten gespeicherten Kalibrierung:")
        self.log(
            f"Letzte Kalibrierung [mm]: X={previous[0]:.6f}, Y={previous[1]:.6f}, Z={previous[2]:.6f}"
        )
        self.log(
            f"Aktuelle Kalibrierung [mm]: X={current[0]:.6f}, Y={current[1]:.6f}, Z={current[2]:.6f}"
        )
        self.log(
            f"Abweichung aktuell - letzte [mm]: dX={delta[0]:.6f}, dY={delta[1]:.6f}, "
            f"dZ={delta[2]:.6f}, |d|={np.linalg.norm(delta):.6f}"
        )

        self.log("")
        self.log("Genauigkeitsmaße der aktuellen Kalibrierung:")
        self.log(
            f"Std [mm]: X={result.std_offset_robot[0]:.6f}, "
            f"Y={result.std_offset_robot[1]:.6f}, Z={result.std_offset_robot[2]:.6f}"
        )
        self.log(f"RMS Offset={result.rms_offset:.6f} mm | Max Abweichung={result.max_deviation:.6f} mm")
        self.log(
            f"Helmert RMS={result.helmert.rms:.6f} mm | Helmert Max={result.helmert.max_residual:.6f} mm | "
            f"Scale={result.helmert.scale:.12f}"
        )

    def save_result_files(self, result: MarkerOffsetCalibrationResult) -> None:
        out_dir = _find_project_root() / "results" / "marker_offset_calibration"
        out_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = out_dir / f"marker_offset_calibration_{timestamp}.csv"
        txt_path = out_dir / f"marker_offset_calibration_{timestamp}.txt"

        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(
                [
                    "label",
                    "robot_x", "robot_y", "robot_z",
                    "reflector_lt_x", "reflector_lt_y", "reflector_lt_z",
                    "marker_lt_x", "marker_lt_y", "marker_lt_z",
                    "offset_robot_x", "offset_robot_y", "offset_robot_z",
                    "deviation_norm",
                ]
            )

            for sample, deviation_norm in zip(result.samples, result.deviation_norms):
                if sample.offset_robot is None:
                    raise RuntimeError(f"Sample {sample.label} hat keinen offset_robot.")
                writer.writerow(
                    [
                        sample.label,
                        *[f"{v:.6f}" for v in sample.robot_marker],
                        *[f"{v:.6f}" for v in sample.reflector_lt],
                        *[f"{v:.6f}" for v in sample.marker_lt],
                        *[f"{v:.6f}" for v in sample.offset_robot],
                        f"{deviation_norm:.6f}",
                    ]
                )

            previous = np.asarray(self.previous_offset_robot, dtype=float)
            current = result.mean_offset_robot
            delta = current - previous

            writer.writerow([])
            writer.writerow(["previous_offset_robot", *[f"{v:.6f}" for v in previous]])
            writer.writerow(["mean_offset_robot", *[f"{v:.6f}" for v in current]])
            writer.writerow(["delta_current_minus_previous", *[f"{v:.6f}" for v in delta]])
            writer.writerow(["delta_norm", f"{np.linalg.norm(delta):.6f}"])
            writer.writerow(["std_offset_robot", *[f"{v:.6f}" for v in result.std_offset_robot]])
            writer.writerow(["rms_offset", f"{result.rms_offset:.6f}"])
            writer.writerow(["max_deviation", f"{result.max_deviation:.6f}"])
            writer.writerow(["helmert_rms", f"{result.helmert.rms:.6f}"])
            writer.writerow(["helmert_max_residual", f"{result.helmert.max_residual:.6f}"])
            writer.writerow(["helmert_scale", f"{result.helmert.scale:.12f}"])

        with txt_path.open("w", encoding="utf-8") as f:
            f.write(format_offset_result(result))
            f.write("\n\n")
            f.write("Letzte gespeicherte Kalibrierung [mm]\n")
            f.write(
                f"X={self.previous_offset_robot[0]:.6f}, "
                f"Y={self.previous_offset_robot[1]:.6f}, "
                f"Z={self.previous_offset_robot[2]:.6f}\n"
            )

        self.log("")
        self.log(f"CSV gespeichert: {csv_path}")
        self.log(f"TXT gespeichert: {txt_path}")

    def update_result_display(self, result: MarkerOffsetCalibrationResult) -> None:
        previous = np.asarray(self.previous_offset_robot, dtype=float)
        current = result.mean_offset_robot
        delta = current - previous

        self.result_offset_var.set(self._format_vector(current))
        self.result_previous_var.set(self._format_vector(previous))
        self.result_delta_var.set(
            f"dX={delta[0]:.3f}, dY={delta[1]:.3f}, dZ={delta[2]:.3f}, |d|={np.linalg.norm(delta):.3f} mm"
        )
        self.result_rms_var.set(f"{result.rms_offset:.3f} mm")
        self.result_max_var.set(f"{result.max_deviation:.3f} mm")
        self.result_std_var.set(
            f"X={result.std_offset_robot[0]:.3f}, Y={result.std_offset_robot[1]:.3f}, Z={result.std_offset_robot[2]:.3f}"
        )

    def accept_calibration(self) -> None:
        if self.last_result is None:
            return

        vector = tuple(float(v) for v in self.last_result.mean_offset_robot)

        try:
            update_marker_to_reflector_robot(vector)
            CONFIG.transformation.marker_to_reflector_robot = vector
        except Exception as exc:
            self.log(f"FEHLER beim Speichern des Offsets: {exc}")
            messagebox.showerror("Marker-/Reflektoroffset", str(exc), parent=self.window)
            return

        self.previous_offset_robot = vector
        self.log("")
        self.log("Offset wurde dauerhaft in config/mower_config.json gespeichert:")
        self.log(f"  X={vector[0]:.6f}, Y={vector[1]:.6f}, Z={vector[2]:.6f}")

        if self.on_finished:
            self.on_finished()

        self.close()

    # --------------------------------------------------
    # Queue / state
    # --------------------------------------------------

    def process_gui_queue(self) -> None:
        if self.closed:
            return

        try:
            while True:
                kind, payload = self.gui_queue.get_nowait()

                if kind == "log":
                    self._write_log(str(payload))
                elif kind == "status":
                    self.status_var.set(str(payload))
                elif kind == "progress":
                    current, total = payload
                    value = 100.0 * current / total if total else 0.0
                    self.progress_var.set(value)
                    self.progress_text_var.set(f"{current}/{total}")
                elif kind == "dialog":
                    request: DialogRequest = payload
                    if request.mode == "info":
                        self.create_info_dialog(request)
                    elif request.mode == "measure":
                        self.create_measure_dialog(request)
                elif kind == "result_ready":
                    result: MarkerOffsetCalibrationResult = payload
                    self.update_result_display(result)
                    self.btn_accept.configure(state="normal")
                elif kind == "workflow_finished":
                    self.workflow_running = False
                    self.btn_cancel.configure(state="disabled")
                    self.btn_repeat.configure(state="normal")
        except queue.Empty:
            pass

        if not self.closed:
            self.window.after(100, self.process_gui_queue)

    def set_status(self, text: str) -> None:
        self.gui_queue.put(("status", text))

    def set_progress(self, current: int, total: int) -> None:
        self.gui_queue.put(("progress", (current, total)))

    def log(self, text: str) -> None:
        self.gui_queue.put(("log", text))
        if self.external_log:
            self.external_log(f"[Offset] {text}")

    def _write_log(self, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        try:
            self.textbox.insert("end", f"[{timestamp}] {text}\n")
            self.textbox.see("end")
        except Exception:
            pass

    def repeat_workflow(self) -> None:
        if self.workflow_running:
            return
        self.log("")
        self.log("------------------------------------------------------------")
        self.log("KALIBRIERUNG WIRD WIEDERHOLT")
        self.log("------------------------------------------------------------")
        self.start_workflow()

    def cancel_workflow(self) -> None:
        if self.workflow_running:
            self.abort_event.set()
            self.measure_button_event.set()
            self.set_status("Abbruch angefordert...")
            self.log("Abbruch angefordert...")

    def discard_and_close(self) -> None:
        if self.workflow_running:
            self.abort_event.set()
            self.measure_button_event.set()

        if self.on_finished:
            self.on_finished()

        self.close()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.window.grab_release()
        except Exception:
            pass
        self.window.destroy()

    def check_abort(self) -> None:
        if self.abort_event.is_set():
            raise InterruptedError()

    def _reset_result_display(self) -> None:
        self.last_result = None
        self.status_var.set("Vorbereitung...")
        self.progress_var.set(0.0)
        self.progress_text_var.set("0/0")
        self.result_offset_var.set("-")
        self.result_previous_var.set(self._format_vector(self.previous_offset_robot))
        self.result_delta_var.set("-")
        self.result_rms_var.set("-")
        self.result_max_var.set("-")
        self.result_std_var.set("-")

    @staticmethod
    def _format_vector(vector: Any) -> str:
        arr = np.asarray(vector, dtype=float)
        return f"X={arr[0]:.3f}, Y={arr[1]:.3f}, Z={arr[2]:.3f} mm"


def _find_project_root() -> Path:
    file_path = Path(__file__).resolve()
    for parent in file_path.parents:
        if (parent / "config" / "mower_config.py").exists():
            return parent
    return Path.cwd()


def _center_window(parent: tk.Misc, window: tk.Toplevel, width: int, height: int) -> None:
    parent.update_idletasks()

    try:
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
    except Exception:
        parent_x = 0
        parent_y = 0
        parent_w = width
        parent_h = height

    x = parent_x + max((parent_w - width) // 2, 0)
    y = parent_y + max((parent_h - height) // 2, 0)
    window.geometry(f"{width}x{height}+{x}+{y}")

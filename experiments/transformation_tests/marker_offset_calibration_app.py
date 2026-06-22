# Transformation/marker_offset_calibration_app_v2.py

from __future__ import annotations

import csv
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import customtkinter as ctk
import numpy as np

from config.mower_config import CONFIG, update_marker_to_reflector_robot
from Lasertracker.lasertracker_receiver import LasertrackerReceiver
from Transformation.marker_offset_calibration import (
    MarkerOffsetCalibrationResult,
    compute_marker_to_reflector_offset,
    format_offset_result,
    make_calibration_sample,
)
from XYZ_Robot.xyz_robot_state import XYZRobotState
from XYZ_Robot.xyz_robot_worker import XYZRobotWorker


ROBOT_POINTS: list[tuple[str, float, float, float]] = [
    ("P1", 160.0, 130.0, 180.0),
    ("P2", 330.0, 145.0, 180.0),
    ("P3", 350.0, 265.0, 180.0),
    ("P4", 185.0, 285.0, 180.0),
    ("P5", 255.0, 205.0, 180.0),
]


DialogResult = Literal["ok", "measure", "cancel"]


@dataclass
class DialogRequest:
    title: str
    message: str
    mode: Literal["info", "measure"]
    event: threading.Event
    result: DialogResult | None = None


class MarkerOffsetCalibrationAppV2(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Mower II - Marker-/Reflektoroffset Kalibrierung")
        self.geometry("1120x820")

        self.gui_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

        self.abort_event = threading.Event()
        self.measure_button_event = threading.Event()
        self.workflow_thread: threading.Thread | None = None

        self.xyz_state = XYZRobotState()
        self.xyz_worker = XYZRobotWorker(
            on_event=self.on_xyz_event,
            on_state_changed=self.on_xyz_state_changed,
        )
        self.xyz_worker.start()

        self.tracker_receiver: LasertrackerReceiver | None = None

        self.reflector_lt_points: dict[str, np.ndarray] = {}
        self.marker_lt_points: dict[str, np.ndarray] = {}

        self.last_result: MarkerOffsetCalibrationResult | None = None
        self.previous_offset_robot = tuple(
            float(v) for v in CONFIG.transformation.marker_to_reflector_robot
        )

        self.status_var = ctk.StringVar(value="Bereit.")
        self.current_manual_label: str | None = None

        self._build_ui()
        self.after(100, self.process_gui_queue)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # --------------------------------------------------
    # UI
    # --------------------------------------------------

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        title = ctk.CTkLabel(
            self,
            text="Marker-/Reflektoroffset Kalibrierung",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 10), sticky="w")

        left = ctk.CTkFrame(self)
        left.grid(row=1, column=0, padx=(20, 10), pady=(0, 20), sticky="nsew")

        right = ctk.CTkFrame(self)
        right.grid(row=1, column=1, padx=(10, 20), pady=(0, 20), sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)

        self._build_left_panel(left)
        self._build_right_panel(right)

    def _build_left_panel(self, parent: ctk.CTkFrame) -> None:
        ctk.CTkLabel(
            parent,
            text="Ablauf",
            font=ctk.CTkFont(size=17, weight="bold"),
        ).pack(padx=14, pady=(14, 6), anchor="w")

        description = (
            "Diese Kalibrierung bestimmt den Vektor vom markierten Punkt "
            "zum oberen Reflektor im Robotersystem.\n\n"
            "Zuerst markiert der Roboter feste Kalibrierpunkte und misst den "
            "Reflektor oben. Danach wird der Wagen weggeschoben und die "
            "markierten Punkte werden manuell mit Reflektor/Schablone gemessen.\n\n"
            "Am Ende kann der neue Kalibrierwert dauerhaft in die Config "
            "uebernommen werden."
        )

        ctk.CTkLabel(
            parent,
            text=description,
            justify="left",
            wraplength=360,
        ).pack(padx=14, pady=(0, 14), fill="x")

        ctk.CTkLabel(
            parent,
            text="Feste Kalibrierpunkte",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(padx=14, pady=(8, 6), anchor="w")

        points_text = "\n".join(
            f"{label}: X={x:.1f}, Y={y:.1f}, Z={z:.1f}"
            for label, x, y, z in ROBOT_POINTS
        )

        ctk.CTkLabel(
            parent,
            text=points_text,
            justify="left",
            font=ctk.CTkFont(family="Consolas", size=13),
        ).pack(padx=14, pady=(0, 14), anchor="w")

        ctk.CTkLabel(
            parent,
            text="Aktive Konfiguration",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(padx=14, pady=(8, 6), anchor="w")

        self.lbl_config = ctk.CTkLabel(
            parent,
            text=self._format_config_text(),
            justify="left",
            wraplength=360,
        )
        self.lbl_config.pack(padx=14, pady=(0, 14), fill="x")

        self.btn_start = ctk.CTkButton(
            parent,
            text="Kalibrierung starten",
            command=self.start_calibration,
        )
        self.btn_start.pack(padx=14, pady=(18, 6), fill="x")

        self.btn_measure_current = ctk.CTkButton(
            parent,
            text="Kalibrierpunkt mit Nest messen",
            command=self.measure_current_point_from_main_button,
            state="disabled",
        )
        self.btn_measure_current.pack(padx=14, pady=6, fill="x")

        self.btn_abort = ctk.CTkButton(
            parent,
            text="Abbrechen",
            command=self.abort_calibration,
        )
        self.btn_abort.pack(padx=14, pady=6, fill="x")

        self.btn_accept = ctk.CTkButton(
            parent,
            text="Kalibrierung übernehmen",
            command=self.accept_calibration,
            state="disabled",
        )
        self.btn_accept.pack(padx=14, pady=(18, 6), fill="x")

        ctk.CTkLabel(
            parent,
            textvariable=self.status_var,
            justify="left",
            wraplength=360,
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(padx=14, pady=(18, 8), fill="x")

    def _build_right_panel(self, parent: ctk.CTkFrame) -> None:
        self.lbl_result = ctk.CTkLabel(
            parent,
            text="Ergebnis: -",
            justify="left",
            anchor="w",
        )
        self.lbl_result.grid(row=0, column=0, padx=14, pady=(14, 8), sticky="ew")

        ctk.CTkLabel(
            parent,
            text="Log",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=1, column=0, padx=14, pady=(4, 0), sticky="w")

        self.logbox = ctk.CTkTextbox(parent, wrap="none")
        self.logbox.grid(row=2, column=0, padx=14, pady=(8, 14), sticky="nsew")

    # --------------------------------------------------
    # Main buttons
    # --------------------------------------------------

    def start_calibration(self) -> None:
        if self.workflow_thread is not None and self.workflow_thread.is_alive():
            self.log("Kalibrierung laeuft bereits.")
            return

        self.abort_event.clear()
        self.measure_button_event.clear()
        self.reflector_lt_points.clear()
        self.marker_lt_points.clear()
        self.last_result = None
        self.current_manual_label = None

        self.btn_start.configure(state="disabled")
        self.btn_accept.configure(state="disabled")
        self.btn_measure_current.configure(state="disabled")

        self.lbl_result.configure(text="Ergebnis: -")
        self.logbox.delete("1.0", "end")

        self.log("Starte Marker-/Reflektoroffset-Kalibrierung.")
        self.log(
            "Feste Kalibrierpunkte werden angefahren, markiert "
            "und mit Reflektor oben gemessen."
        )

        self.workflow_thread = threading.Thread(
            target=self.run_workflow,
            daemon=True,
        )
        self.workflow_thread.start()

    def measure_current_point_from_main_button(self) -> None:
        self.measure_button_event.set()

    def abort_calibration(self) -> None:
        self.abort_event.set()
        self.measure_button_event.set()
        self.set_status("Abbruch angefordert.")

    def accept_calibration(self) -> None:
        if self.last_result is None:
            self.log("Keine Kalibrierung zum Uebernehmen vorhanden.")
            return

        vector = tuple(float(v) for v in self.last_result.mean_offset_robot)
        update_marker_to_reflector_robot(vector)

        self.previous_offset_robot = vector
        self.lbl_config.configure(text=self._format_config_text(vector_override=vector))

        self.log("")
        self.log("Kalibrierung wurde dauerhaft in config/mower_config.json gespeichert:")
        self.log(f"  X={vector[0]:.6f}, Y={vector[1]:.6f}, Z={vector[2]:.6f}")
        self.set_status("Kalibrierung uebernommen. Andere Programme ggf. neu starten.")

    # --------------------------------------------------
    # Workflow
    # --------------------------------------------------

    def run_workflow(self) -> None:
        try:
            self.connect_xyz_if_needed()
            self.check_abort()

            self.start_tracker_if_needed()
            self.check_abort()

            self.log("Homing ...")
            self.send_robot_command("home_all", timeout_s=180.0)
            self.check_abort()

            self.run_robot_mark_and_reflector_measurement()
            self.check_abort()

            self.log("")
            self.log("Schritt 1 abgeschlossen:")
            self.log("  - Kalibrierpunkte markiert")
            self.log("  - Reflektor oben an allen Punkten gemessen")
            self.log("  - Roboter wird in Home-Position gefahren")

            self.log("")
            self.log("Homing / Wagen sichern ...")
            self.send_robot_command("home_all", timeout_s=180.0)
            self.check_abort()

            response = self.show_info_dialog_and_wait(
                title="Manuelle Messung vorbereiten",
                message=(
                    "Schritt 1 ist abgeschlossen.\n\n"
                    "Kalibrierpunkte wurden markiert und Reflektor oben gemessen. "
                    "Der Wagen kann nun weggeschoben oder gesichert werden.\n\n"
                    "Nächster Schritt: Markierte Punkte manuell messen."
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

            self.queue_gui("result_ready", result)
            self.set_status("Kalibrierung abgeschlossen. Ergebnis pruefen und ggf. uebernehmen.")

        except InterruptedError:
            self.log("")
            self.log("Kalibrierung abgebrochen.")
            self.set_status("Kalibrierung abgebrochen.")

        except Exception as exc:
            self.log("")
            self.log(f"FEHLER: {exc}")
            self.set_status(f"Fehler: {exc}")

        finally:
            self.current_manual_label = None
            self.queue_gui("workflow_finished", None)

    def run_robot_mark_and_reflector_measurement(self) -> None:
        self.log("")
        self.log("=== Schritt 1: Punkte markieren und Reflektor oben messen ===")

        for label, x, y, z in ROBOT_POINTS:
            self.check_abort()

            self.log("")
            self.log(f"--- {label} ---")
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

            self.log(
                f"Markiere {label}: "
                f"{CONFIG.marker.shape}, "
                f"Groesse={CONFIG.marker.size_mm:.3f} mm"
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

            self.log(f"Fahre wieder exakt auf Punktmitte {label}")

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

            self.log(f"Messe oberen Reflektor fuer {label}")
            self.reflector_lt_points[label] = self.capture_tracker_point(
                f"{label} reflector_lt"
            )

    def run_manual_marker_measurements(self) -> None:
        self.log("")
        self.log("=== Schritt 2: Manuelle Messung der markierten Punkte ===")

        for label, _, _, _ in ROBOT_POINTS:
            self.check_abort()
            self.current_manual_label = label
            self.measure_button_event.clear()

            response = self.show_measure_dialog_and_wait(label)

            if response == "cancel":
                raise InterruptedError()

            self.check_abort()

            self.log("")
            self.log(f"Manuelle Messung {label}: Reflektor/Schablone wird gemessen.")

            marker_lt_ccr = self.capture_tracker_point(
                f"{label} marker_lt CCR center"
            )

            marker_lt = marker_lt_ccr.copy()

            # Annahme: Lasertracker ist lotrecht aufgestellt, LT-Z zeigt nach oben.
            marker_lt[2] -= CONFIG.tracker.ccr_radius_mm

            self.marker_lt_points[label] = marker_lt

            self.log(
                f"{label} marker_lt Bodenpunkt korrigiert: "
                f"X={marker_lt[0]:.6f}, "
                f"Y={marker_lt[1]:.6f}, "
                f"Z={marker_lt[2]:.6f}"
            )

        self.current_manual_label = None

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
        request = DialogRequest(
            title=title,
            message=message,
            mode="info",
            event=threading.Event(),
        )

        self.queue_gui("dialog", request)

        while not request.event.wait(timeout=0.1):
            self.check_abort()

        return request.result or "cancel"

    def show_measure_dialog_and_wait(self, label: str) -> DialogResult:
        request = DialogRequest(
            title=f"Manuelle Messung {label}",
            message=(
                f"Bitte Reflektor mit Schablone auf {label} setzen.\n\n"
                "Wenn der Reflektor sauber auf der Markierung sitzt, "
                "Messen druecken."
            ),
            mode="measure",
            event=threading.Event(),
        )

        self.set_status(f"Bitte Reflektor auf {label} setzen und messen.")
        self.queue_gui("manual_measure_active", label)
        self.queue_gui("dialog", request)

        while not request.event.wait(timeout=0.1):
            self.check_abort()

            if self.measure_button_event.is_set():
                request.result = "measure"
                request.event.set()
                break

        self.queue_gui("manual_measure_inactive", None)

        return request.result or "cancel"

    def create_info_dialog(self, request: DialogRequest) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title(request.title)
        self.center_dialog(dialog, 560, 280)
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text=request.title,
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(padx=24, pady=(24, 10), anchor="w")

        ctk.CTkLabel(
            dialog,
            text=request.message,
            justify="left",
            wraplength=460,
        ).pack(padx=24, pady=10, fill="x")

        def ok() -> None:
            request.result = "ok"
            request.event.set()
            dialog.destroy()

        ctk.CTkButton(
            dialog,
            text="OK",
            command=ok,
        ).pack(padx=24, pady=(20, 24), fill="x")

        dialog.protocol("WM_DELETE_WINDOW", ok)

    def create_measure_dialog(self, request: DialogRequest) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title(request.title)
        self.center_dialog(dialog, 560, 280)
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text=request.title,
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(padx=24, pady=(24, 10), anchor="w")

        ctk.CTkLabel(
            dialog,
            text=request.message,
            justify="left",
            wraplength=460,
        ).pack(padx=24, pady=10, fill="x")

        button_frame = ctk.CTkFrame(dialog)
        button_frame.pack(padx=24, pady=(20, 24), fill="x")
        button_frame.grid_columnconfigure((0, 1), weight=1)

        def measure() -> None:
            request.result = "measure"
            request.event.set()
            dialog.destroy()

        def cancel() -> None:
            request.result = "cancel"
            request.event.set()
            dialog.destroy()

        ctk.CTkButton(
            button_frame,
            text="Messen",
            command=measure,
        ).grid(row=0, column=0, padx=(0, 8), pady=10, sticky="ew")

        ctk.CTkButton(
            button_frame,
            text="Abbrechen",
            command=cancel,
        ).grid(row=0, column=1, padx=(8, 0), pady=10, sticky="ew")

        dialog.protocol("WM_DELETE_WINDOW", cancel)

    # --------------------------------------------------
    # Hardware helpers
    # --------------------------------------------------

    def connect_xyz_if_needed(self) -> None:
        if self.xyz_state.connected:
            self.log("XYZ ist bereits verbunden.")
            return

        self.log(f"Verbinde XYZ: {CONFIG.xyz.port} @ {CONFIG.xyz.baudrate}")

        self.send_robot_command(
            "connect",
            timeout_s=30.0,
            port=CONFIG.xyz.port,
            baudrate=CONFIG.xyz.baudrate,
        )

    def start_tracker_if_needed(self) -> None:
        if self.tracker_receiver is not None and self.tracker_receiver.running:
            self.log("LasertrackerReceiver laeuft bereits.")
            return

        self.log(f"Starte LasertrackerReceiver auf UDP-Port {CONFIG.tracker.udp_port}")

        self.tracker_receiver = LasertrackerReceiver(
            port=CONFIG.tracker.udp_port,
            on_state_changed=None,
            on_log=lambda text: self.log(f"Tracker: {text}"),
            on_error=lambda text: self.log(f"Tracker FEHLER: {text}"),
        )

        self.tracker_receiver.start()
        time.sleep(0.5)

        if not self.tracker_receiver.running:
            raise RuntimeError("LasertrackerReceiver konnte nicht gestartet werden.")

    def send_robot_command(
        self,
        command: str,
        timeout_s: float,
        **kwargs: Any,
    ) -> None:
        self.xyz_worker.send_command(command, **kwargs)
        self.wait_robot_done(timeout_s=timeout_s)

    def wait_robot_done(self, timeout_s: float) -> None:
        start = time.time()

        while time.time() - start < timeout_s:
            self.check_abort()

            if self.xyz_worker.command_queue.empty() and not self.xyz_state.busy:
                if self.xyz_state.error_text:
                    raise RuntimeError(self.xyz_state.error_text)
                return

            time.sleep(0.05)

        raise TimeoutError("Timeout beim Warten auf XYZRobotWorker.")

    def capture_tracker_point(self, label: str) -> np.ndarray:
        if self.tracker_receiver is None or not self.tracker_receiver.running:
            raise RuntimeError("LasertrackerReceiver laeuft nicht.")

        self.log(f"Messe {label} ...")

        measurement = self.tracker_receiver.capture_stable_point(
            timeout_s=CONFIG.tracker.capture_timeout_s,
            min_age_after_start_s=0.1,
        )

        point = np.array([measurement.x, measurement.y, measurement.z], dtype=float)

        self.log(
            f"{label}: "
            f"X={point[0]:.6f}, "
            f"Y={point[1]:.6f}, "
            f"Z={point[2]:.6f}"
        )

        return point

    # --------------------------------------------------
    # Results
    # --------------------------------------------------

    def evaluate_quality(
        self,
        result: MarkerOffsetCalibrationResult,
    ) -> tuple[str, str]:
        if result.rms_offset <= 0.5 and result.max_deviation <= 1.0:
            return "GUT", "Kalibrierung ist plausibel."

        if result.rms_offset <= 1.0 and result.max_deviation <= 2.0:
            return "PRUEFEN", "Kalibrierung ist nutzbar, sollte aber geprueft werden."

        return "SCHLECHT", "Kalibrierung ist auffaellig. Nicht ungeprueft uebernehmen."

    def log_result(self, result: MarkerOffsetCalibrationResult) -> None:
        previous = np.asarray(self.previous_offset_robot, dtype=float)
        current = result.mean_offset_robot
        delta = current - previous

        quality, quality_message = self.evaluate_quality(result)

        self.log("")
        self.log("------------------------------------------------------------")
        self.log("ERGEBNIS DER KALIBRIERUNG")
        self.log("------------------------------------------------------------")
        self.log(format_offset_result(result))

        self.log("")
        self.log("Vergleich zur letzten gespeicherten Kalibrierung:")
        self.log(
            f"Letzte Config [mm]:   "
            f"X={previous[0]:.6f}, Y={previous[1]:.6f}, Z={previous[2]:.6f}"
        )
        self.log(
            f"Aktuell [mm]:         "
            f"X={current[0]:.6f}, Y={current[1]:.6f}, Z={current[2]:.6f}"
        )
        self.log(
            f"Differenz [mm]:       "
            f"dX={delta[0]:.6f}, dY={delta[1]:.6f}, dZ={delta[2]:.6f}, "
            f"|d|={np.linalg.norm(delta):.6f}"
        )

        self.log("")
        self.log("Genauigkeitsmasse:")
        self.log(
            f"Std [mm]:             "
            f"X={result.std_offset_robot[0]:.6f}, "
            f"Y={result.std_offset_robot[1]:.6f}, "
            f"Z={result.std_offset_robot[2]:.6f}"
        )
        self.log(f"RMS Offset:           {result.rms_offset:.6f} mm")
        self.log(f"Max Abweichung:       {result.max_deviation:.6f} mm")
        self.log(f"Helmert RMS:          {result.helmert.rms:.6f} mm")
        self.log(f"Helmert Max:          {result.helmert.max_residual:.6f} mm")
        self.log(f"Helmert Scale:        {result.helmert.scale:.12f}")

        self.log("")
        self.log(f"Qualitaetsbewertung: {quality}")
        self.log(quality_message)

    def save_result_files(self, result: MarkerOffsetCalibrationResult) -> None:
        out_dir = Path("marker_offset_calibration_results")
        out_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = out_dir / f"marker_offset_calibration_{timestamp}.csv"
        txt_path = out_dir / f"marker_offset_calibration_{timestamp}.txt"

        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(
                [
                    "label",
                    "robot_x",
                    "robot_y",
                    "robot_z",
                    "reflector_lt_x",
                    "reflector_lt_y",
                    "reflector_lt_z",
                    "marker_lt_x",
                    "marker_lt_y",
                    "marker_lt_z",
                    "offset_robot_x",
                    "offset_robot_y",
                    "offset_robot_z",
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

    # --------------------------------------------------
    # GUI queue / callbacks
    # --------------------------------------------------

    def on_xyz_event(self, event) -> None:
        text = f"[{event.component}] [{event.level.name}] {event.message}"
        self.queue_gui("log", text)

    def on_xyz_state_changed(self, state: XYZRobotState) -> None:
        self.xyz_state = state

    def process_gui_queue(self) -> None:
        try:
            while True:
                kind, payload = self.gui_queue.get_nowait()

                if kind == "log":
                    self._write_log(str(payload))

                elif kind == "status":
                    self.status_var.set(str(payload))

                elif kind == "dialog":
                    request: DialogRequest = payload
                    if request.mode == "info":
                        self.create_info_dialog(request)
                    elif request.mode == "measure":
                        self.create_measure_dialog(request)

                elif kind == "manual_measure_active":
                    label = payload
                    self.btn_measure_current.configure(
                        text=f"{label} mit Nest messen",
                        state="normal",
                    )

                elif kind == "manual_measure_inactive":
                    self.btn_measure_current.configure(
                        text="Kalibrierpunkt mit Nest messen",
                        state="disabled",
                    )

                elif kind == "result_ready":
                    result: MarkerOffsetCalibrationResult = payload
                    self.update_result_label(result)

                    quality, quality_message = self.evaluate_quality(result)

                    if quality in ("GUT", "PRUEFEN"):
                        self.btn_accept.configure(state="normal")
                    else:
                        self.btn_accept.configure(state="disabled")
                        self.log("")
                        self.log(
                            "Uebernahme deaktiviert, weil die "
                            "Kalibrierqualitaet SCHLECHT ist."
                        )
                        self.log(quality_message)

                elif kind == "workflow_finished":
                    self.btn_start.configure(state="normal")
                    self.btn_measure_current.configure(
                        text="Kalibrierpunkt mit Nest messen",
                        state="disabled",
                    )

        except queue.Empty:
            pass

        self.after(100, self.process_gui_queue)

    def queue_gui(self, kind: str, payload: Any) -> None:
        self.gui_queue.put((kind, payload))

    def log(self, text: str) -> None:
        self.queue_gui("log", text)

    def set_status(self, text: str) -> None:
        self.queue_gui("status", text)

    def _write_log(self, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.logbox.insert("end", f"[{timestamp}] {text}\n")
        self.logbox.see("end")

    def update_result_label(self, result: MarkerOffsetCalibrationResult) -> None:
        previous = np.asarray(self.previous_offset_robot, dtype=float)
        current = result.mean_offset_robot
        delta = current - previous
        quality, _ = self.evaluate_quality(result)

        self.lbl_result.configure(
            text=(
                "Ergebnis:\n\n"
                "Aktuelle Kalibrierung [mm]\n"
                f"  X = {current[0]:.3f}\n"
                f"  Y = {current[1]:.3f}\n"
                f"  Z = {current[2]:.3f}\n\n"
                "Abweichung zur gespeicherten Config [mm]\n"
                f"  dX = {delta[0]:.3f}\n"
                f"  dY = {delta[1]:.3f}\n"
                f"  dZ = {delta[2]:.3f}\n"
                f"  |d| = {np.linalg.norm(delta):.3f}\n\n"
                "Qualitaet\n"
                f"  Bewertung = {quality}\n"
                f"  RMS = {result.rms_offset:.3f} mm\n"
                f"  Max = {result.max_deviation:.3f} mm"
            )
        )

    def _format_config_text(
        self,
        vector_override: tuple[float, float, float] | None = None,
    ) -> str:
        vector = vector_override or tuple(CONFIG.transformation.marker_to_reflector_robot)

        return (
            f"XYZ: {CONFIG.xyz.port} @ {CONFIG.xyz.baudrate}\n"
            f"Tracker UDP: {CONFIG.tracker.udp_port}\n"
            f"Feedrate: {CONFIG.xyz.default_feedrate:.1f} mm/min\n"
            f"Marker: {CONFIG.marker.shape}, {CONFIG.marker.size_mm:.1f} mm\n"
            f"CCR-Radius: {CONFIG.tracker.ccr_radius_mm:.3f} mm\n"
            f"Gespeicherter Offset:\n"
            f"  X={vector[0]:.3f}, Y={vector[1]:.3f}, Z={vector[2]:.3f}"
        )

    # --------------------------------------------------
    # Abort / close
    # --------------------------------------------------

    def check_abort(self) -> None:
        if self.abort_event.is_set():
            raise InterruptedError()

    def on_close(self) -> None:
        self.abort_event.set()
        self.measure_button_event.set()

        try:
            if self.tracker_receiver is not None:
                self.tracker_receiver.stop()

            self.xyz_worker.stop()

        finally:
            self.destroy()

    def center_dialog(self, dialog: ctk.CTkToplevel, width: int, height: int) -> None:
        dialog.update_idletasks()

        parent_x = self.winfo_x()
        parent_y = self.winfo_y()
        parent_w = self.winfo_width()
        parent_h = self.winfo_height()

        x = parent_x + (parent_w - width) // 2
        y = parent_y + (parent_h - height) // 2

        dialog.geometry(f"{width}x{height}+{x}+{y}")


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = MarkerOffsetCalibrationAppV2()
    app.mainloop()
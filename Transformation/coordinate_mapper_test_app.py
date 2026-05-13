# Transformation/coordinate_mapper_test_app.py

from __future__ import annotations

import sys
from pathlib import Path
import threading
import queue
import time
import customtkinter as ctk

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from XYZ_Robot.xyz_robot_worker import XYZRobotWorker
from XYZ_Robot.xyz_robot_state import XYZRobotState
from XYZ_Robot.marker_shapes import MARKER_SHAPES

from Lasertracker.lasertracker_receiver import LasertrackerReceiver
from Lasertracker.lasertracker_state import LasertrackerState

from Transformation.trafo_manager import TrafoManager
from Transformation.trafo_workflow import TrafoWorkflow, TrafoWorkflowConfig
from Transformation.coordinate_mapper import CoordinateMapper, RobotWorkspace


# ============================================================
# KONFIGURATION
# ============================================================

XYZ_PORT = "COM5"
XYZ_BAUDRATE = 115200
TRACKER_UDP_PORT = 10000

TRACKER_STALE_THRESHOLD_S = 5.0
TRACKER_STABLE_THRESHOLD_MM = 0.1
TRACKER_STABLE_REQUIRED_COUNT = 3

TRAFO_CAPTURE_TIMEOUT_S = 10.0

WORKSPACE_X_MIN = 0.0
WORKSPACE_X_MAX = 500.0
WORKSPACE_Y_MIN = 0.0
WORKSPACE_Y_MAX = 500.0

XYZ_FEEDRATE = 6000.0
XYZ_POSITION_TOLERANCE_MM = 0.05

DEFAULT_MARKER_LABEL = "P"
DEFAULT_MARKER_SIZE = 5.0
DEFAULT_MARKER_SHAPE = "plus"
DEFAULT_MARKER_ANGLE_DEG = 0.0


# ============================================================
# APP
# ============================================================

class CoordinateMapperTestApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Mower II - Coordinate Mapper Test")
        self.geometry("980x820")

        self.xyz_state = XYZRobotState()
        self.tracker_state = None

        self.trafo_manager = TrafoManager()

        self.workspace = RobotWorkspace(
            x_min=WORKSPACE_X_MIN,
            x_max=WORKSPACE_X_MAX,
            y_min=WORKSPACE_Y_MIN,
            y_max=WORKSPACE_Y_MAX,
        )

        self.mapper = CoordinateMapper(
            trafo_manager=self.trafo_manager,
            workspace=self.workspace,
        )

        self.last_mapping_result = None

        self.gui_queue = queue.Queue()

        self.xyz_worker = XYZRobotWorker(
            on_event=self.on_xyz_event,
            on_state_changed=self.on_xyz_state_changed,
        )
        self.xyz_worker.start()

        self.tracker_receiver = None

        self._build_ui()

        self.after(100, self.process_gui_queue)
        self.after(500, self.update_status_labels)

    # --------------------------------------------------------
    # UI
    # --------------------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(6, weight=1)

        title = ctk.CTkLabel(
            self,
            text="Mower II - Coordinate Mapper Test",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        title.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        # ----------------------------------------------------
        # Hardware Buttons
        # ----------------------------------------------------

        button_frame = ctk.CTkFrame(self)
        button_frame.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        button_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.btn_connect_xyz = ctk.CTkButton(
            button_frame,
            text="XYZ verbinden",
            command=self.connect_xyz,
        )
        self.btn_connect_xyz.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        self.btn_start_tracker = ctk.CTkButton(
            button_frame,
            text="Tracker starten",
            command=self.start_tracker,
        )
        self.btn_start_tracker.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        self.btn_homing = ctk.CTkButton(
            button_frame,
            text="Homing",
            command=self.start_homing,
        )
        self.btn_homing.grid(row=0, column=2, padx=10, pady=10, sticky="ew")

        self.btn_trafo = ctk.CTkButton(
            button_frame,
            text="Start Trafo",
            command=self.open_trafo_dialog,
        )
        self.btn_trafo.grid(row=0, column=3, padx=10, pady=10, sticky="ew")

        # ----------------------------------------------------
        # Status
        # ----------------------------------------------------

        status_frame = ctk.CTkFrame(self)
        status_frame.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        status_frame.grid_columnconfigure(0, weight=1)

        self.lbl_xyz_status = ctk.CTkLabel(status_frame, text="XYZ: -")
        self.lbl_xyz_status.grid(row=0, column=0, padx=10, pady=5, sticky="w")

        self.lbl_tracker_status = ctk.CTkLabel(status_frame, text="Tracker: -")
        self.lbl_tracker_status.grid(row=1, column=0, padx=10, pady=5, sticky="w")

        self.lbl_trafo_status = ctk.CTkLabel(status_frame, text="Trafo gültig: Nein")
        self.lbl_trafo_status.grid(row=2, column=0, padx=10, pady=5, sticky="w")

        self.lbl_workspace_status = ctk.CTkLabel(
            status_frame,
            text=(
                f"Arbeitsraum: "
                f"X={WORKSPACE_X_MIN:.1f}..{WORKSPACE_X_MAX:.1f}, "
                f"Y={WORKSPACE_Y_MIN:.1f}..{WORKSPACE_Y_MAX:.1f}"
            ),
        )
        self.lbl_workspace_status.grid(row=3, column=0, padx=10, pady=5, sticky="w")

        # ----------------------------------------------------
        # LT Eingabe
        # ----------------------------------------------------

        input_frame = ctk.CTkFrame(self)
        input_frame.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        input_frame.grid_columnconfigure((1, 3), weight=1)

        lbl_input_title = ctk.CTkLabel(
            input_frame,
            text="LT-XY Markierpunkt",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        lbl_input_title.grid(row=0, column=0, columnspan=4, padx=10, pady=(10, 5), sticky="w")

        ctk.CTkLabel(input_frame, text="LT X:").grid(
            row=1, column=0, padx=10, pady=10, sticky="e"
        )

        self.entry_lt_x = ctk.CTkEntry(input_frame)
        self.entry_lt_x.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(input_frame, text="LT Y:").grid(
            row=1, column=2, padx=10, pady=10, sticky="e"
        )

        self.entry_lt_y = ctk.CTkEntry(input_frame)
        self.entry_lt_y.grid(row=1, column=3, padx=10, pady=10, sticky="ew")

        # ----------------------------------------------------
        # Markierparameter
        # ----------------------------------------------------

        marker_frame = ctk.CTkFrame(self)
        marker_frame.grid(row=4, column=0, padx=20, pady=10, sticky="ew")
        marker_frame.grid_columnconfigure((1, 3), weight=1)

        lbl_marker_title = ctk.CTkLabel(
            marker_frame,
            text="Markierparameter",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        lbl_marker_title.grid(row=0, column=0, columnspan=4, padx=10, pady=(10, 5), sticky="w")

        ctk.CTkLabel(marker_frame, text="Label:").grid(
            row=1, column=0, padx=10, pady=10, sticky="e"
        )

        self.entry_marker_label = ctk.CTkEntry(marker_frame)
        self.entry_marker_label.insert(0, DEFAULT_MARKER_LABEL)
        self.entry_marker_label.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(marker_frame, text="Größe [mm]:").grid(
            row=1, column=2, padx=10, pady=10, sticky="e"
        )

        self.entry_marker_size = ctk.CTkEntry(marker_frame)
        self.entry_marker_size.insert(0, str(DEFAULT_MARKER_SIZE))
        self.entry_marker_size.grid(row=1, column=3, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(marker_frame, text="Form:").grid(
            row=2, column=0, padx=10, pady=10, sticky="e"
        )

        marker_shapes = list(MARKER_SHAPES.keys())
        selected_shape = (
            DEFAULT_MARKER_SHAPE
            if DEFAULT_MARKER_SHAPE in marker_shapes
            else marker_shapes[0]
        )

        self.option_marker_shape = ctk.CTkOptionMenu(
            marker_frame,
            values=marker_shapes,
        )
        self.option_marker_shape.set(selected_shape)
        self.option_marker_shape.grid(row=2, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(marker_frame, text="Winkel [deg]:").grid(
            row=2, column=2, padx=10, pady=10, sticky="e"
        )

        self.entry_marker_angle = ctk.CTkEntry(marker_frame)
        self.entry_marker_angle.insert(0, str(DEFAULT_MARKER_ANGLE_DEG))
        self.entry_marker_angle.grid(row=2, column=3, padx=10, pady=10, sticky="ew")

        # ----------------------------------------------------
        # Mapper Buttons
        # ----------------------------------------------------

        action_frame = ctk.CTkFrame(self)
        action_frame.grid(row=5, column=0, padx=20, pady=10, sticky="ew")
        action_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_calculate = ctk.CTkButton(
            action_frame,
            text="Berechnen",
            command=self.calculate_mapping,
        )
        self.btn_calculate.grid(row=0, column=0, padx=8, pady=8, sticky="ew")

        self.btn_move = ctk.CTkButton(
            action_frame,
            text="Anfahren",
            command=self.move_to_last_mapping,
        )
        self.btn_move.grid(row=0, column=1, padx=8, pady=8, sticky="ew")

        self.btn_mark = ctk.CTkButton(
            action_frame,
            text="Markieren",
            command=self.mark_last_mapping,
        )
        self.btn_mark.grid(row=0, column=2, padx=8, pady=8, sticky="ew")

        # ----------------------------------------------------
        # Ergebnis + Log
        # ----------------------------------------------------

        bottom_frame = ctk.CTkFrame(self)
        bottom_frame.grid(row=6, column=0, padx=20, pady=10, sticky="nsew")
        bottom_frame.grid_columnconfigure(0, weight=1)
        bottom_frame.grid_rowconfigure(1, weight=1)

        self.lbl_mapping_result = ctk.CTkLabel(
            bottom_frame,
            text="Mapping-Ergebnis: -",
            justify="left",
            anchor="w",
        )
        self.lbl_mapping_result.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        self.logbox = ctk.CTkTextbox(bottom_frame)
        self.logbox.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # --------------------------------------------------------
    # CALLBACKS
    # --------------------------------------------------------

    def on_xyz_event(self, event):
        self.gui_queue.put(("log", event.format_for_log()))

    def on_xyz_state_changed(self, state: XYZRobotState):
        self.xyz_state = state

    def on_tracker_state_changed(self, state: LasertrackerState):
        self.tracker_state = state

    def on_tracker_log(self, text: str):
        self.gui_queue.put(("log", f"[Lasertracker] {text}"))

    def on_tracker_error(self, text: str):
        self.gui_queue.put(("log", f"[Lasertracker ERROR] {text}"))

    # --------------------------------------------------------
    # BUTTON ACTIONS
    # --------------------------------------------------------

    def connect_xyz(self):
        self.log("Verbinde XYZ...")

        self.xyz_worker.send_command(
            "connect",
            port=XYZ_PORT,
            baudrate=XYZ_BAUDRATE,
        )

    def start_tracker(self):
        if self.tracker_receiver is not None:
            self.log("Tracker läuft bereits.")
            return

        self.log("Starte Lasertracker Receiver...")

        self.tracker_receiver = LasertrackerReceiver(
            port=TRACKER_UDP_PORT,
            stale_threshold_seconds=TRACKER_STALE_THRESHOLD_S,
            stable_threshold_mm=TRACKER_STABLE_THRESHOLD_MM,
            stable_required_count=TRACKER_STABLE_REQUIRED_COUNT,
            on_state_changed=self.on_tracker_state_changed,
            on_log=self.on_tracker_log,
            on_error=self.on_tracker_error,
        )

        self.tracker_receiver.start()

    def start_homing(self):
        self.log("Starte Homing...")
        self.xyz_worker.send_command("home_all")

    def open_trafo_dialog(self):
        if self.tracker_receiver is None:
            self.log("Tracker ist nicht gestartet.")
            return

        dialog = TrafoDialog(
            master=self,
            xyz_worker=self.xyz_worker,
            tracker_receiver=self.tracker_receiver,
            xyz_state_getter=lambda: self.xyz_state,
            trafo_manager=self.trafo_manager,
            on_finished=self.on_trafo_dialog_finished,
        )

        dialog.grab_set()

    def on_trafo_dialog_finished(self):
        self.update_status_labels()

    def calculate_mapping(self):
        try:
            tracker_x = float(self.entry_lt_x.get().replace(",", "."))
            tracker_y = float(self.entry_lt_y.get().replace(",", "."))

        except ValueError:
            self.last_mapping_result = None
            self.log("Ungültige Eingabe für LT X/Y.")
            self.lbl_mapping_result.configure(
                text="Mapping-Ergebnis: Ungültige Eingabe."
            )
            return

        result = self.mapper.tracker_xy_to_robot_target(
            tracker_x=tracker_x,
            tracker_y=tracker_y,
        )

        self.last_mapping_result = result
        self.display_mapping_result(result)

    def move_to_last_mapping(self):
        result = self._get_or_calculate_valid_mapping()

        if result is None:
            return

        self._move_to_mapping_result(result)

    def mark_last_mapping(self):
        result = self._get_or_calculate_valid_mapping()

        if result is None:
            return

        self._mark_mapping_result(result)

    # --------------------------------------------------------
    # MAPPING / MOVE / MARK
    # --------------------------------------------------------

    def _get_or_calculate_valid_mapping(self):
        if self.last_mapping_result is None:
            self.calculate_mapping()

        result = self.last_mapping_result

        if result is None:
            self.log("Kein gültiges Mapping vorhanden.")
            return None

        if not result.success:
            self.log(f"Mapping nicht gültig: {result.message}")
            return None

        if result.robot_target_point is None:
            self.log("Mapping enthält keinen Roboterzielpunkt.")
            return None

        if not result.inside_workspace:
            self.log("Roboterziel liegt außerhalb des Arbeitsraums.")
            return None

        return result

    def _move_to_mapping_result(self, result) -> bool:
        robot_point = result.robot_target_point

        robot_x = float(robot_point[0])
        robot_y = float(robot_point[1])

        self.log(
            f"Fahre Roboterziel an: "
            f"X={robot_x:.3f}, Y={robot_y:.3f}"
        )

        self.xyz_worker.send_command(
            "move_absolute_verified",
            x=robot_x,
            y=robot_y,
            z=None,
            feedrate=XYZ_FEEDRATE,
            tolerance_mm=XYZ_POSITION_TOLERANCE_MM,
        )

        return True

    def _mark_mapping_result(self, result) -> bool:
        robot_point = result.robot_target_point

        robot_x = float(robot_point[0])
        robot_y = float(robot_point[1])

        marker_params = self._get_marker_params()

        if marker_params is None:
            return False

        label, marker_size, marker_shape, angle_deg = marker_params

        self.log(
            f"Markiere Roboterziel: "
            f"Label={label}, "
            f"X={robot_x:.3f}, Y={robot_y:.3f}, "
            f"Shape={marker_shape}, "
            f"Size={marker_size:.3f}, "
            f"Angle={angle_deg:.3f}"
        )

        self.xyz_worker.send_command(
            "mark_point",
            x=robot_x,
            y=robot_y,
            label=label,
            marker_size=marker_size,
            marker_shape=marker_shape,
            angle_deg=angle_deg,
        )

        return True

    def _get_marker_params(self):
        label = self.entry_marker_label.get().strip()

        if not label:
            label = DEFAULT_MARKER_LABEL

        try:
            marker_size = float(
                self.entry_marker_size.get().replace(",", ".")
            )
        except ValueError:
            self.log("Ungültige Markergröße.")
            return None

        if marker_size <= 0:
            self.log("Markergröße muss > 0 sein.")
            return None

        marker_shape = self.option_marker_shape.get()

        if marker_shape not in MARKER_SHAPES:
            self.log(f"Unbekannte Markerform: {marker_shape}")
            return None

        try:
            angle_deg = float(
                self.entry_marker_angle.get().replace(",", ".")
            )
        except ValueError:
            self.log("Ungültiger Markerwinkel.")
            return None

        return label, marker_size, marker_shape, angle_deg

    # --------------------------------------------------------
    # AUSGABE
    # --------------------------------------------------------

    def display_mapping_result(self, result):
        lines = []

        lines.append(f"Status: {'OK' if result.success else 'NICHT OK'}")
        lines.append(f"Meldung: {result.message}")
        lines.append(f"Arbeitsraum: {'OK' if result.inside_workspace else 'NICHT OK'}")

        if result.tracker_marker_point is not None:
            p = result.tracker_marker_point
            lines.append(
                f"LT-Markierpunkt XYZ: "
                f"X={p[0]:.3f}, Y={p[1]:.3f}, Z={p[2]:.3f}"
            )

        if result.tracker_reflector_point is not None:
            p = result.tracker_reflector_point
            lines.append(
                f"LT-Reflektorpunkt XYZ: "
                f"X={p[0]:.3f}, Y={p[1]:.3f}, Z={p[2]:.3f}"
            )

        if result.robot_target_point is not None:
            p = result.robot_target_point
            lines.append(
                f"Roboterziel XYZ: "
                f"X={p[0]:.3f}, Y={p[1]:.3f}, Z={p[2]:.3f}"
            )

        output = "\n".join(lines)

        self.lbl_mapping_result.configure(
            text="Mapping-Ergebnis:\n" + output
        )

        self.log("")
        self.log("Mapping-Ergebnis:")
        for line in lines:
            self.log("  " + line)

    # --------------------------------------------------------
    # GUI UPDATE
    # --------------------------------------------------------

    def process_gui_queue(self):
        try:
            while True:
                kind, payload = self.gui_queue.get_nowait()

                if kind == "log":
                    self.log(payload)

        except queue.Empty:
            pass

        self.after(100, self.process_gui_queue)

    def update_status_labels(self):
        x = self.xyz_state.x
        y = self.xyz_state.y
        z = self.xyz_state.z

        if x is None or y is None:
            xyz_text = f"XYZ: busy={self.xyz_state.busy}"
        else:
            z_val = z if z is not None else 0.0
            xyz_text = (
                f"XYZ: X={x:.3f}, Y={y:.3f}, Z={z_val:.3f}, "
                f"busy={self.xyz_state.busy}"
            )

        self.lbl_xyz_status.configure(text=xyz_text)

        if self.tracker_state is None:
            tracker_text = "Tracker: nicht gestartet / keine Daten"
        else:
            tracker_text = (
                f"Tracker: receiving={self.tracker_state.receiving}, "
                f"stable={self.tracker_state.stable}, "
                f"stale={self.tracker_state.stale}"
            )

        self.lbl_tracker_status.configure(text=tracker_text)

        if self.trafo_manager.valid:
            trafo_text = "Trafo gültig: Ja"

            if self.trafo_manager.marker_plane_lt is not None:
                plane = self.trafo_manager.marker_plane_lt
                nx, ny, nz, _ = plane.as_tuple()
                trafo_text += (
                    f" | MarkerPlane n=({nx:.4f}, {ny:.4f}, {nz:.4f})"
                )

        else:
            reason = self.trafo_manager.invalid_reason
            trafo_text = "Trafo gültig: Nein"
            if reason:
                trafo_text += f" ({reason})"

        self.lbl_trafo_status.configure(text=trafo_text)

        self.after(500, self.update_status_labels)

    def log(self, text: str):
        timestamp = time.strftime("%H:%M:%S")
        self.logbox.insert("end", f"[{timestamp}] {text}\n")
        self.logbox.see("end")

    def on_close(self):
        try:
            if self.tracker_receiver is not None:
                self.tracker_receiver.stop()

            self.xyz_worker.stop()

        finally:
            self.destroy()


# ============================================================
# TRAFO DIALOG
# ============================================================

class TrafoDialog(ctk.CTkToplevel):
    def __init__(
        self,
        master,
        xyz_worker,
        tracker_receiver,
        xyz_state_getter,
        trafo_manager: TrafoManager,
        on_finished=None,
    ):
        super().__init__(master)

        self.title("Transformation")
        self.geometry("800x620")

        self.xyz_worker = xyz_worker
        self.tracker_receiver = tracker_receiver
        self.xyz_state_getter = xyz_state_getter
        self.trafo_manager = trafo_manager
        self.on_finished = on_finished

        self.workflow = None
        self.workflow_thread = None
        self.result = None

        self.gui_queue = queue.Queue()

        self._build_ui()

        self.after(100, self.process_gui_queue)
        self.start_workflow()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.lbl_title = ctk.CTkLabel(
            self,
            text="Transformation läuft...",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        self.lbl_title.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        self.lbl_status = ctk.CTkLabel(self, text="Status: -")
        self.lbl_status.grid(row=1, column=0, padx=20, pady=5, sticky="w")

        self.progress = ctk.CTkProgressBar(self)
        self.progress.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        self.progress.set(0.0)

        self.textbox = ctk.CTkTextbox(self)
        self.textbox.grid(row=3, column=0, padx=20, pady=10, sticky="nsew")

        button_frame = ctk.CTkFrame(self)
        button_frame.grid(row=4, column=0, padx=20, pady=(5, 20), sticky="ew")
        button_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_cancel = ctk.CTkButton(
            button_frame,
            text="Abbrechen",
            command=self.cancel_workflow,
        )
        self.btn_cancel.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        self.btn_accept = ctk.CTkButton(
            button_frame,
            text="Trafo übernehmen",
            command=self.accept_trafo,
            state="disabled",
        )
        self.btn_accept.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        self.btn_discard = ctk.CTkButton(
            button_frame,
            text="Verwerfen / Schließen",
            command=self.discard_and_close,
        )
        self.btn_discard.grid(row=0, column=2, padx=10, pady=10, sticky="ew")

    def start_workflow(self):
        config = TrafoWorkflowConfig(
            tracker_capture_timeout_s=TRAFO_CAPTURE_TIMEOUT_S,
            max_allowed_rms_mm=0.10,
            max_allowed_max_residual_mm=0.15,
            minimum_required_measurements=4,
            allow_scale=True,
            min_geometry_rank=2,
        )

        self.workflow = TrafoWorkflow(
            xyz_worker=self.xyz_worker,
            tracker_receiver=self.tracker_receiver,
            xyz_state_getter=self.xyz_state_getter,
            config=config,
            on_status=lambda text: self.gui_queue.put(("status", text)),
            on_progress=lambda current, total, label: self.gui_queue.put(
                ("progress", (current, total, label))
            ),
            on_log=lambda text: self.gui_queue.put(("log", text)),
        )

        self.workflow_thread = threading.Thread(
            target=self._workflow_thread_main,
            daemon=True,
        )
        self.workflow_thread.start()

    def _workflow_thread_main(self):
        result = self.workflow.run()
        self.gui_queue.put(("result", result))

    def cancel_workflow(self):
        if self.workflow is not None:
            self.workflow.cancel()
            self.log("Abbruch angefordert...")

    def accept_trafo(self):
        if self.result is None:
            return

        self.trafo_manager.set_pending(self.result)
        self.trafo_manager.accept_pending()

        self.log("Trafo wurde übernommen und ist jetzt gültig.")

        if self.on_finished:
            self.on_finished()

        self.destroy()

    def discard_and_close(self):
        self.trafo_manager.clear_pending()

        if self.on_finished:
            self.on_finished()

        self.destroy()

    def process_gui_queue(self):
        try:
            while True:
                kind, payload = self.gui_queue.get_nowait()

                if kind == "status":
                    self.lbl_status.configure(text=f"Status: {payload}")
                    self.log(payload)

                elif kind == "progress":
                    current, total, label = payload
                    value = current / total if total else 0.0
                    self.progress.set(value)
                    self.log(f"Fortschritt {current}/{total}: {label}")

                elif kind == "log":
                    self.log(payload)

                elif kind == "result":
                    self.handle_result(payload)

        except queue.Empty:
            pass

        self.after(100, self.process_gui_queue)

    def handle_result(self, result):
        self.result = result

        self.btn_cancel.configure(state="disabled")

        self.log("")
        self.log("=" * 60)
        self.log("ERGEBNIS")
        self.log("=" * 60)

        self.log(f"Status: {result.status}")
        self.log(f"Meldung: {result.message}")
        self.log(f"Dauer: {result.duration_s:.2f} s")

        if result.error:
            self.log(f"Fehler: {result.error}")

        if result.failed_measurements:
            self.log("")
            self.log("Nicht messbare Punkte:")

            for failed in result.failed_measurements:
                self.log(
                    f"{failed['name']}: "
                    f"X={failed['robot_target_x']:.3f}, "
                    f"Y={failed['robot_target_y']:.3f} | "
                    f"{failed['reason']}"
                )

        if result.trafo is not None:
            self.log("")
            self.log(result.trafo.format_summary())

            self.log("")
            self.log("Restklaffungen verwendeter Punkte:")

            for m, v, vn in zip(
                result.used_measurements,
                result.trafo.residuals,
                result.trafo.residual_norms,
            ):
                self.log(
                    f"{m['name']}: "
                    f"vx={v[0]: .4f}, "
                    f"vy={v[1]: .4f}, "
                    f"vz={v[2]: .4f}, "
                    f"|v|={vn:.4f} mm"
                )

        if result.reflector_plane_lt is not None:
            self.log("")
            self.log(result.reflector_plane_lt.format_summary("Reflektorebene LT"))

        if result.marker_plane_lt is not None:
            self.log("")
            self.log(result.marker_plane_lt.format_summary("Markierebene LT"))

        if result.marker_to_reflector_lt is not None:
            v = result.marker_to_reflector_lt
            self.log("")
            self.log(
                f"Marker→Reflektor LT: "
                f"dx={v[0]:.3f}, dy={v[1]:.3f}, dz={v[2]:.3f}"
            )

        if result.excluded_measurement is not None:
            self.log("")
            self.log(f"Ausgeschlossener Punkt: {result.excluded_measurement['name']}")

        if result.candidate_results:
            self.log("")
            self.log("4-Punkt-Kandidaten:")

            for c in result.candidate_results:
                excluded = (
                    c["excluded_measurement"]["name"]
                    if c["excluded_measurement"] is not None
                    else ", ".join(c.get("excluded_names", []))
                )

                if c["trafo"] is None:
                    self.log(f"ohne {excluded}: FEHLER - {c.get('error')}")
                    continue

                trafo = c["trafo"]
                status = "OK" if c["ok"] else "nicht OK"

                self.log(
                    f"ohne {excluded}: {status} | "
                    f"RMS={trafo.rms:.4f} mm | "
                    f"Max={trafo.max_residual:.4f} mm | "
                    f"Scale={trafo.scale:.9f}"
                )

        if result.success:
            self.lbl_title.configure(text="Transformation erfolgreich")
            self.lbl_status.configure(text="Status: fertig")
            self.btn_accept.configure(state="normal")
        else:
            self.lbl_title.configure(text="Transformation nicht erfolgreich")
            self.lbl_status.configure(text=f"Status: {result.status}")
            self.btn_accept.configure(state="disabled")

    def log(self, text: str):
        self.textbox.insert("end", text + "\n")
        self.textbox.see("end")


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = CoordinateMapperTestApp()
    app.mainloop()
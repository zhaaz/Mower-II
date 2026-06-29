# App/mower_operator_app.py
# Version 18: Projektroot aus Dateipfad der App ermitteln

from __future__ import annotations

import json
import math
import os
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any
import tkinter as tk
from tkinter import Menu, filedialog, messagebox, simpledialog, ttk

import customtkinter as ctk

def find_project_root() -> Path:
    """
    Ermittelt den Projektroot aus dem Speicherort dieser Datei.

    Erwartete Lage:
        Mower_II/App/mower_operator_app.py

    Damit ist der Pfad unabhaengig vom aktuellen Arbeitsverzeichnis
    der PyCharm-Run-Configuration.
    """
    app_file = Path(__file__).resolve()

    for parent in app_file.parents:
        if (parent / "config" / "mower_config.py").exists():
            return parent

    # Fallback fuer den normalen Fall: App/mower_operator_app.py
    return app_file.parents[1]


PROJECT_ROOT = find_project_root()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from config.mower_config import CONFIG
except Exception:
    CONFIG = None

from App.map_view import MapView
from App.stakeout_point import StakeoutPoint, create_demo_points, load_points_from_txt

try:
    from App.ui.classic_style import (
        apply_classic_style,
        FONT_FAMILY,
        FONT_NORMAL,
        FONT_BOLD,
        FONT_SECTION,
        FONT_TITLE,
        FONT_MONO,
    )
except Exception:
    apply_classic_style = None
    FONT_FAMILY = "Segoe UI"
    FONT_NORMAL = ("Segoe UI", 9)
    FONT_BOLD = ("Segoe UI", 9, "bold")
    FONT_SECTION = ("Segoe UI", 10, "bold")
    FONT_TITLE = ("Segoe UI", 12, "bold")
    FONT_MONO = ("Consolas", 9)

try:
    from App.dialogs.xyz_connect_dialog import show_xyz_connect_dialog
except Exception:
    show_xyz_connect_dialog = None

try:
    from App.dialogs.xyz_manual_move_dialog import show_xyz_manual_move_dialog
except Exception:
    show_xyz_manual_move_dialog = None

try:
    from App.services.project_io import write_project_file
except Exception:
    write_project_file = None

try:
    from XYZ_Robot.xyz_robot_worker import XYZRobotWorker
except Exception:
    XYZRobotWorker = None

try:
    from KVH_DSP.kvh_dsp_worker import KVHDSPWorker
except Exception:
    KVHDSPWorker = None

try:
    from Lasertracker.lasertracker_receiver import LasertrackerReceiver
except Exception:
    LasertrackerReceiver = None

try:
    from App.dialogs.trafo_dialog import show_trafo_dialog
except Exception:
    show_trafo_dialog = None

try:
    from App.dialogs.marker_offset_calibration_dialog import show_marker_offset_calibration_dialog
except Exception:
    show_marker_offset_calibration_dialog = None

try:
    from App.dialogs.marker_height_calibration_dialog import show_marker_height_calibration_dialog
except Exception:
    show_marker_height_calibration_dialog = None

try:
    from App.dialogs.point_marking_dialog import show_point_marking_dialog
except Exception:
    show_point_marking_dialog = None

try:
    from App.dialogs.system_initialization_dialog import show_system_initialization_dialog
except Exception:
    show_system_initialization_dialog = None

try:
    from App.dialogs.kvh_drift_dialog import show_kvh_drift_dialog
except Exception:
    show_kvh_drift_dialog = None

try:
    from Transformation.trafo_manager import TrafoManager
except Exception:
    TrafoManager = None

try:
    from Transformation.coordinate_mapper import CoordinateMapper, RobotWorkspace
except Exception:
    CoordinateMapper = None
    RobotWorkspace = None

try:
    from App.services.map_visualization import build_map_visualization_state
except Exception:
    build_map_visualization_state = None


def project_path(relative_path: str | Path) -> Path:
    """
    Wandelt einen relativen Projektpfad aus der Config in einen absoluten Pfad um.
    Absolute Pfade bleiben unveraendert.
    """
    path = Path(relative_path)

    if path.is_absolute():
        return path

    return PROJECT_ROOT / path


def get_tracker_station_file() -> Path:
    """
    Liefert den konfigurierten Pfad zur Trackerstationsdatei.
    Fallback: data/tracker_station.txt
    """
    if CONFIG is not None and hasattr(CONFIG, "paths"):
        return project_path(CONFIG.paths.tracker_station_file)

    return PROJECT_ROOT / "data" / "tracker_station.txt"


class OperatorMapView(MapView):
    """Helle Kartenansicht fuer die klassische Operator-Oberflaeche."""

    COLOR_CANVAS = "#eeeeee"
    COLOR_GRID = "#d6d6d6"
    COLOR_AXIS = "#b8b8b8"
    COLOR_TEXT = "#222222"
    COLOR_BUTTON = "#f7f7f7"
    COLOR_BUTTON_BORDER = "#9e9e9e"
    COLOR_WORKSPACE_FILL = "#eaf6fb"
    COLOR_WORKSPACE_OUTLINE = "#0086a8"

    def _draw_background_grid(self) -> None:
        import math

        canvas_w = max(self.canvas.winfo_width(), 1)
        canvas_h = max(self.canvas.winfo_height(), 1)

        self.canvas.create_rectangle(0, 0, canvas_w, canvas_h, fill=self.COLOR_CANVAS, outline="")

        grid_mm = self._nice_length(max(50.0, 80.0 / max(self.scale_px_per_mm, 0.001)))

        left_world, top_world = self.screen_to_world(0, 0)
        right_world, bottom_world = self.screen_to_world(canvas_w, canvas_h)

        min_x = min(left_world, right_world)
        max_x = max(left_world, right_world)
        min_y = min(bottom_world, top_world)
        max_y = max(bottom_world, top_world)

        start_x = math.floor(min_x / grid_mm) * grid_mm
        end_x = math.ceil(max_x / grid_mm) * grid_mm
        start_y = math.floor(min_y / grid_mm) * grid_mm
        end_y = math.ceil(max_y / grid_mm) * grid_mm

        x = start_x
        while x <= end_x:
            sx1, sy1 = self.world_to_screen(x, min_y)
            sx2, sy2 = self.world_to_screen(x, max_y)
            fill = self.COLOR_AXIS if abs(x) < 1e-9 else self.COLOR_GRID
            width = 2 if abs(x) < 1e-9 else 1
            self.canvas.create_line(sx1, sy1, sx2, sy2, fill=fill, width=width)
            x += grid_mm

        y = start_y
        while y <= end_y:
            sx1, sy1 = self.world_to_screen(min_x, y)
            sx2, sy2 = self.world_to_screen(max_x, y)
            fill = self.COLOR_AXIS if abs(y) < 1e-9 else self.COLOR_GRID
            width = 2 if abs(y) < 1e-9 else 1
            self.canvas.create_line(sx1, sy1, sx2, sy2, fill=fill, width=width)
            y += grid_mm

    def _draw_robot_workspace(self) -> None:
        if not self.robot_workspace_polygon:
            return

        coords: list[float] = []
        for x, y in self.robot_workspace_polygon:
            sx, sy = self.world_to_screen(x, y)
            coords.extend([sx, sy])

        if len(coords) >= 6:
            self.canvas.create_polygon(
                *coords,
                fill=self.COLOR_WORKSPACE_FILL,
                outline=self.COLOR_WORKSPACE_OUTLINE,
                width=2,
                stipple="gray12",
            )

    def _draw_tracker(self) -> None:
        if self.tracker_position is None:
            return

        x, y = self.tracker_position
        sx, sy = self.world_to_screen(x, y)
        r = 10

        self.canvas.create_oval(sx - r, sy - r, sx + r, sy + r, outline="#f57c00", width=2)
        self.canvas.create_line(sx - 14, sy, sx + 14, sy, fill="#f57c00", width=2)
        self.canvas.create_line(sx, sy - 14, sx, sy + 14, fill="#f57c00", width=2)
        self.canvas.create_text(
            sx + 14,
            sy - 14,
            text="Lasertracker",
            fill="#f57c00",
            anchor="sw",
            font=("Segoe UI", 9),
        )

    def _draw_points(self) -> None:
        for point in self.points:
            sx, sy = self.world_to_screen(point.x, point.y)

            radius = 6
            fill = "#1976d2"
            outline = "#ffffff"
            width = 1

            if point.reachable:
                fill = "#2e7d32"
                outline = "#ffffff"
                width = 2

            if point.marked:
                fill = "#9e9e9e"
                outline = "#616161"
                width = 1

            if point.selected:
                outline = "#f9a825"
                width = 3
                radius = 8

            self.canvas.create_oval(
                sx - radius,
                sy - radius,
                sx + radius,
                sy + radius,
                fill=fill,
                outline=outline,
                width=width,
            )

            self.canvas.create_text(
                sx + 10,
                sy - 10,
                text=point.name,
                fill=self.COLOR_TEXT,
                anchor="sw",
                font=("Segoe UI", 9),
            )

    def _draw_scale_bar(self) -> None:
        canvas_w = max(self.canvas.winfo_width(), 1)
        canvas_h = max(self.canvas.winfo_height(), 1)

        visible_width_mm = canvas_w / max(self.scale_px_per_mm, 0.001)
        length_mm = self._nice_length(visible_width_mm / 5.0)
        length_px = length_mm * self.scale_px_per_mm

        x2 = canvas_w - 28
        y = canvas_h - 28
        x1 = x2 - length_px

        self.canvas.create_line(x1, y, x2, y, fill=self.COLOR_TEXT, width=3)
        self.canvas.create_line(x1, y - 5, x1, y + 5, fill=self.COLOR_TEXT, width=2)
        self.canvas.create_line(x2, y - 5, x2, y + 5, fill=self.COLOR_TEXT, width=2)
        self.canvas.create_text(
            (x1 + x2) / 2.0,
            y - 10,
            text=f"{length_mm:g} mm",
            fill=self.COLOR_TEXT,
            anchor="s",
            font=("Segoe UI", 9),
        )

    def _draw_view_buttons(self) -> None:
        button_specs = [
            ("+", "zoom_in"),
            ("-", "zoom_out"),
            ("[]", "zoom_all"),
        ]

        x0 = max(self.canvas.winfo_width() - 112, 8)
        y0 = 10
        size = 28
        gap = 6

        for index, (label, tag_name) in enumerate(button_specs):
            x1 = x0 + index * (size + gap)
            y1 = y0
            x2 = x1 + size
            y2 = y1 + size
            tag = f"view_button_{tag_name}"

            self.canvas.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                fill=self.COLOR_BUTTON,
                outline=self.COLOR_BUTTON_BORDER,
                width=1,
                tags=("view_button", tag),
            )
            self.canvas.create_text(
                (x1 + x2) / 2.0,
                (y1 + y2) / 2.0,
                text=label,
                fill=self.COLOR_TEXT,
                font=("Segoe UI", 10, "bold"),
                tags=("view_button", tag),
            )


class MowerOperatorApp(ctk.CTk):
    """
    Klassische Bedienoberflaeche fuer das Mower-Abstecksystem.

    Ziel dieser Version:
        - helle/graue Windows-artige Bedienoberflaeche
        - Standard-Menueleiste statt eigener MenuBand
        - Punktliste links
        - 2D-Ansicht in der Mitte
        - Status und Live-Werte rechts
        - aktuelle Aktion unten

    Die Hardwarelogik ist bewusst so gehalten, dass vorhandene Dialoge und
    spaetere echte Komponenten schrittweise eingehangen werden koennen.
    """

    COLOR_BG = "#f2f2f2"
    COLOR_PANEL = "#ffffff"
    COLOR_PANEL_ALT = "#f7f7f7"
    COLOR_BORDER = "#c8c8c8"
    COLOR_TEXT = "#111111"
    COLOR_MUTED = "#555555"
    COLOR_GREEN = "#1f9d55"
    COLOR_RED = "#c62828"
    COLOR_YELLOW = "#d6a100"

    def __init__(self) -> None:
        super().__init__()

        if apply_classic_style is not None:
            apply_classic_style(self)

        self.title("Mower II - Abstecksystem")
        self.geometry("1500x880")
        self.minsize(1200, 720)
        self.configure(fg_color=self.COLOR_BG)

        self.points: list[StakeoutPoint] = []
        self.selected_point_name: str | None = None
        self.project_path: Path | None = None

        logs_dir = PROJECT_ROOT / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file_path = logs_dir / f"mower_operator_{timestamp}.log"

        # Komponentenstatus
        self.xyz_ready = False
        self.tracker_ready = False
        self.drehmotor_ready = False
        self.gyro_ready = False

        # Systemstatus
        self.homing_done = False
        self.trafo_valid = False
        self.arn_active = False
        self.tracker_data_current = False

        # Lasertrackerkoordinaten
        self.tracker_station_xyz: tuple[float, float, float] | None = None
        self.current_lt_measurement_xyz: tuple[float, float, float] | None = None
        # Letzte gueltige Reflektormessung fuer die Live-Kartenpose.
        # Wenn die Tracker-Messung kurzzeitig ausfaellt, darf die Karte nicht
        # auf die statische Transformationspose zurueckspringen. Stattdessen
        # bleibt die letzte bekannte Reflektorposition als Anker erhalten.
        self.last_live_reflector_lt_xyz: tuple[float, float, float] | None = None

        # Kompatibilitaet zu bisherigen Namen aus der V3/V5-Oberflaeche
        self.xyz_connected = False
        self.tracker_started = False
        self.skr_connected = False
        self.gyems_connected = False

        # Spaetere echte Komponenten koennen hier gesetzt werden.
        self.xyz_worker: Any | None = None
        self.xyz_state: Any | None = None
        self.tracker_receiver: Any | None = None
        self.tracker_state: Any | None = None
        self.gyro_worker: Any | None = None
        self.gyro_state: Any | None = None

        # Orientierung der Wagen-/Roboter-X-Achse im Lasertracker-XY-System.
        # Referenz kommt aus der aktiven Transformation; der KVH liefert danach
        # nur die relative Winkeländerung seit dem Nullsetzen.
        self.gyro_reference_angle_deg: float | None = None
        self.gyro_lt_reference_orientation_deg: float | None = None

        # Live-Kartenupdate: Sensoren laufen schneller, die Anzeige wird
        # bewusst auf ca. 5 Hz begrenzt.
        self.map_update_interval_ms = 200
        self._last_map_update_time_s = 0.0
        self._pending_map_update_after_id: str | None = None

        if TrafoManager is not None:
            self.trafo_manager = TrafoManager()
        else:
            self.trafo_manager = None

        self.status_indicators: dict[str, ctk.CTkLabel] = {}

        self._build_ui()
        self._apply_demo_scene()
        self.refresh_points()
        self.set_current_action("Bereit.")
        self.update_status()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # --------------------------------------------------
    # UI
    # --------------------------------------------------


    def _configure_operator_tree_styles(self) -> None:
        style = ttk.Style(self)
        style.configure(
            "Operator.Treeview",
            font=FONT_NORMAL,
            rowheight=25,
            background="#ffffff",
            fieldbackground="#ffffff",
            foreground=self.COLOR_TEXT,
        )
        style.configure(
            "Operator.Treeview.Heading",
            font=FONT_BOLD,
            background="#f0f0f0",
            foreground=self.COLOR_TEXT,
        )
        style.map(
            "Operator.Treeview",
            background=[("selected", "#d9eaff")],
            foreground=[("selected", self.COLOR_TEXT)],
        )

    def _build_ui(self) -> None:
        self._configure_operator_tree_styles()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        self._build_standard_menu()
        self._build_main_area()
        self._build_action_bar()

    def _build_standard_menu(self) -> None:
        menu_bar = Menu(self)

        file_menu = Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="Punkte laden...", command=self.load_points_dialog)
        file_menu.add_command(label="Punkte löschen...", command=self.clear_points_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Projekt speichern", command=self.save_project)
        file_menu.add_command(label="Projekt speichern unter...", command=self.save_project_as)
        file_menu.add_separator()
        file_menu.add_command(label="Log oeffnen", command=self.open_log_file)
        file_menu.add_separator()
        file_menu.add_command(label="Beenden", command=self.on_close)
        menu_bar.add_cascade(label="Datei", menu=file_menu)

        xyz_menu = Menu(menu_bar, tearoff=False)
        xyz_menu.add_command(label="Verbinden", command=self.connect_xyz)
        xyz_menu.add_command(label="Trennen", command=self.disconnect_xyz)
        xyz_menu.add_separator()
        xyz_menu.add_command(label="Homing", command=self.home_xyz)
        xyz_menu.add_command(label="Fahre zu Position...", command=self.move_xyz_to_position_dialog)
        xyz_menu.add_command(label="Position lesen", command=self.read_xyz_position)
        menu_bar.add_cascade(label="XYZ", menu=xyz_menu)

        tracker_menu = Menu(menu_bar, tearoff=False)
        tracker_menu.add_command(label="UDP-Empfang starten", command=self.start_tracker)
        tracker_menu.add_command(label="UDP-Empfang stoppen", command=self.stop_tracker)
        tracker_menu.add_separator()
        tracker_menu.add_command(label="Station laden", command=self.load_tracker_station_default)
        tracker_menu.add_command(label="Station aus Datei wählen...", command=self.load_tracker_position_dialog)
        menu_bar.add_cascade(label="Tracker", menu=tracker_menu)

        motor_menu = Menu(menu_bar, tearoff=False)
        motor_menu.add_command(label="Verbinden", command=self.connect_drehmotor)
        motor_menu.add_command(label="Trennen", command=self.disconnect_drehmotor)
        motor_menu.add_separator()
        motor_menu.add_command(label="Referenz setzen", command=self.drehmotor_set_reference)
        motor_menu.add_separator()
        motor_menu.add_command(label="Status anzeigen", command=self.show_drehmotor_status)
        menu_bar.add_cascade(label="Drehmotor", menu=motor_menu)

        gyro_menu = Menu(menu_bar, tearoff=False)
        gyro_menu.add_command(label="Verbinden", command=self.connect_gyro)
        gyro_menu.add_command(label="Trennen", command=self.disconnect_gyro)
        gyro_menu.add_separator()
        gyro_menu.add_command(label="Winkel auf 0 setzen", command=self.reset_gyro_angle)
        gyro_menu.add_command(label="Drift bestimmen", command=self.determine_gyro_drift)
        gyro_menu.add_separator()
        gyro_menu.add_command(label="Status anzeigen", command=self.show_gyro_status)
        menu_bar.add_cascade(label="Gyro", menu=gyro_menu)

        system_menu = Menu(menu_bar, tearoff=False)
        system_menu.add_command(label="Initialisieren", command=self.initialize_system)
        system_menu.add_separator()
        system_menu.add_command(label="Transformation starten", command=self.start_transformation)
        system_menu.add_command(label="Marker-/Reflektoroffset kalibrieren", command=self.offset_calibration)
        system_menu.add_command(label="Markerhoehe kalibrieren", command=self.calibrate_marker_height)
        system_menu.add_command(label="Punkte markieren", command=self.mark_points_dialog)
        system_menu.add_separator()
        system_menu.add_command(label="ARN aktivieren", command=self.activate_arn)
        system_menu.add_command(label="ARN deaktivieren", command=self.deactivate_arn)
        system_menu.add_separator()
        system_menu.add_command(label="Aktive Config anzeigen", command=self.show_active_config)
        system_menu.add_command(label="Config neu laden", command=self.reload_config)
        menu_bar.add_cascade(label="System", menu=system_menu)

        view_menu = Menu(menu_bar, tearoff=False)
        view_menu.add_command(label="Karte aktualisieren", command=lambda: self.refresh_points(keep_map_view=True))
        menu_bar.add_cascade(label="Ansicht", menu=view_menu)

        self.configure(menu=menu_bar)

    def _build_main_area(self) -> None:
        main = ctk.CTkFrame(
            self,
            fg_color=self.COLOR_BG,
            corner_radius=0,
        )
        main.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        main.grid_columnconfigure(0, weight=0)
        main.grid_columnconfigure(1, weight=1)
        main.grid_columnconfigure(2, weight=0)
        main.grid_rowconfigure(0, weight=1)

        self._build_point_list_panel(main)
        self._build_map_panel(main)
        self._build_right_panel(main)

    def _panel(self, parent: Any) -> ctk.CTkFrame:
        return ctk.CTkFrame(
            parent,
            fg_color=self.COLOR_PANEL,
            border_width=1,
            border_color=self.COLOR_BORDER,
            corner_radius=0,
        )

    def _section_title(self, parent: Any, text: str, row: int) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            text_color=self.COLOR_TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold"),
            anchor="w",
        ).grid(row=row, column=0, columnspan=3, padx=10, pady=(8, 3), sticky="ew")

    def _build_point_list_panel(self, parent: ctk.CTkFrame) -> None:
        panel = self._panel(parent)
        panel.grid(row=0, column=0, padx=(0, 8), pady=0, sticky="nsew")
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        panel.configure(width=360)
        panel.grid_propagate(False)

        ctk.CTkLabel(
            panel,
            text="Punktliste",
            text_color=self.COLOR_TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=12, pady=(12, 4), sticky="ew")

        self.lbl_point_count = ctk.CTkLabel(panel, text="0 Punkte", text_color=self.COLOR_MUTED, anchor="w")
        self.lbl_point_count.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")

        list_container = tk.Frame(
            panel,
            bg=self.COLOR_PANEL_ALT,
            highlightthickness=1,
            highlightbackground=self.COLOR_BORDER,
            bd=0,
        )
        list_container.grid(row=2, column=0, padx=12, pady=8, sticky="nsew")
        list_container.grid_rowconfigure(0, weight=1)
        list_container.grid_columnconfigure(0, weight=1)

        self.point_tree = ttk.Treeview(
            list_container,
            columns=("name", "status", "shape", "remark"),
            show="headings",
            selectmode="browse",
            height=18,
            style="Operator.Treeview",
        )
        self.point_tree.heading("name", text="Punkt")
        self.point_tree.heading("status", text="Status")
        self.point_tree.heading("shape", text="Typ")
        self.point_tree.heading("remark", text="Bemerkung")

        self.point_tree.column("name", width=70, minwidth=55, stretch=False, anchor="w")
        self.point_tree.column("status", width=82, minwidth=70, stretch=False, anchor="w")
        self.point_tree.column("shape", width=62, minwidth=48, stretch=False, anchor="center")
        self.point_tree.column("remark", width=120, minwidth=80, stretch=True, anchor="w")

        self.point_tree.grid(row=0, column=0, sticky="nsew")
        self.point_tree.bind("<<TreeviewSelect>>", self.on_point_tree_selected)
        self.point_tree.bind("<Double-1>", self.on_point_tree_double_click)

        scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.point_tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.point_tree.configure(yscrollcommand=scrollbar.set)

        details_frame = tk.Frame(
            panel,
            bg=self.COLOR_PANEL,
            highlightthickness=1,
            highlightbackground=self.COLOR_BORDER,
            bd=0,
        )
        details_frame.grid(row=3, column=0, padx=12, pady=(6, 12), sticky="ew")
        details_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            details_frame,
            text="Ausgewählter Punkt",
            text_color=self.COLOR_TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=8, pady=(7, 2), sticky="ew")

        self.point_detail_body = tk.Frame(
            details_frame,
            bg=self.COLOR_PANEL,
            highlightthickness=0,
            bd=0,
        )
        self.point_detail_body.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="ew")
        self.point_detail_body.grid_columnconfigure(0, weight=0, minsize=92)
        self.point_detail_body.grid_columnconfigure(1, weight=1)

        self.point_detail_value_labels: dict[str, ctk.CTkLabel] = {}
        detail_rows = [
            ("name", "Punktnummer:"),
            ("coordinates", "Koordinaten:"),
            ("status", "Status:"),
            ("marker", "Markierung:"),
            ("remark", "Bemerkung:"),
        ]

        for detail_row, (key, label_text) in enumerate(detail_rows):
            ctk.CTkLabel(
                self.point_detail_body,
                text=label_text,
                text_color=self.COLOR_TEXT,
                anchor="w",
                justify="left",
                font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            ).grid(row=detail_row, column=0, padx=(0, 10), pady=0, sticky="w")

            value_label = ctk.CTkLabel(
                self.point_detail_body,
                text="-",
                text_color=self.COLOR_TEXT,
                anchor="w",
                justify="left",
                font=ctk.CTkFont(family=FONT_FAMILY, size=12),
                wraplength=235,
            )
            value_label.grid(row=detail_row, column=1, padx=0, pady=0, sticky="ew")
            self.point_detail_value_labels[key] = value_label

    def _build_map_panel(self, parent: ctk.CTkFrame) -> None:
        panel = self._panel(parent)
        panel.grid(row=0, column=1, padx=8, pady=0, sticky="nsew")
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        # In der Operator-Oberflaeche bleibt der Kartenbereich bewusst ruhig:
        # keine zusaetzliche Ueberschrift und keine zweite Auswahl-Anzeige,
        # da diese Informationen bereits in der Punktliste stehen.
        self.lbl_selected_point = None

        self.map_view = OperatorMapView(panel, on_point_selected=self.select_point_by_name)
        self.map_view.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

    def _build_right_panel(self, parent: ctk.CTkFrame) -> None:
        panel = self._panel(parent)
        panel.grid(row=0, column=2, padx=(8, 0), pady=0, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(2, weight=1)
        panel.configure(width=330)
        panel.grid_propagate(False)

        self.status_indicators: dict[str, ctk.CTkLabel] = {}
        self.status_text_labels: dict[str, ctk.CTkLabel] = {}
        self.live_value_labels: dict[str, ctk.CTkLabel] = {}

        components = self._status_card(panel, title="Komponenten", row=0)
        self._add_status_row(components, row=0, key="xyz", label="XYZ-Roboter")
        self._add_status_row(components, row=1, key="tracker", label="Lasertracker")
        self._add_status_row(components, row=2, key="gyro", label="Gyro / KVH")
        self._add_status_row(components, row=3, key="drehmotor", label="Drehmotor / GYEMS")

        system = self._status_card(panel, title="Systemzustände", row=1)
        self._add_status_row(system, row=0, key="homing", label="Homing")
        self._add_status_row(system, row=1, key="trafo", label="Transformation")
        self._add_status_row(system, row=2, key="trackerdaten", label="Trackerdaten")
        self._add_status_row(system, row=3, key="arn", label="Reflektornachf.")

        live = self._status_card(panel, title="Live-Werte", row=2, sticky="nsew")
        live.grid_rowconfigure(14, weight=1)
        self._add_live_section_label(live, row=0, text="XYZ-Roboter")
        self._add_live_value_row(live, row=1, key="xyz_x", label="X")
        self._add_live_value_row(live, row=2, key="xyz_y", label="Y")
        self._add_live_value_row(live, row=3, key="xyz_z", label="Z")

        self._add_live_section_label(live, row=4, text="Lasertracker")
        self._add_tracker_live_table(live, start_row=5)

        self._add_live_section_label(live, row=10, text="Gyro / KVH")
        self._add_live_value_row(live, row=11, key="gyro_angle", label="Winkel")
        self._add_live_value_row(live, row=12, key="gyro_orientation_lt", label="Orientierung LT")
        self._add_live_value_row(live, row=13, key="gyro_drift", label="Drift")

    def _status_card(
            self,
            parent: ctk.CTkFrame,
            *,
            title: str,
            row: int,
            sticky: str = "ew",
    ) -> tk.Frame:
        card = tk.Frame(
            parent,
            bg=self.COLOR_PANEL,
            highlightthickness=1,
            highlightbackground=self.COLOR_BORDER,
            bd=0,
        )
        card.grid(row=row, column=0, padx=12, pady=(8 if row == 0 else 6, 6), sticky=sticky)
        card.grid_columnconfigure(1, weight=1)
        card.grid_columnconfigure(2, weight=0)

        ctk.CTkLabel(
            card,
            text=title,
            text_color=self.COLOR_TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=3, padx=10, pady=(8, 5), sticky="ew")

        content = tk.Frame(card, bg=self.COLOR_PANEL, highlightthickness=0, bd=0)
        content.grid(row=1, column=0, columnspan=3, padx=10, pady=(0, 9), sticky="nsew")
        content.grid_columnconfigure(0, weight=0, minsize=24)
        content.grid_columnconfigure(1, weight=1)
        content.grid_columnconfigure(2, weight=0, minsize=105)
        return content

    def _add_status_row(self, parent: tk.Frame, row: int, key: str, label: str) -> None:
        indicator = ctk.CTkLabel(
            parent,
            text="●",
            text_color="#9e9e9e",
            width=20,
            height=20,
            font=ctk.CTkFont(family=FONT_FAMILY, size=18, weight="bold"),
        )
        indicator.grid(row=row, column=0, padx=(0, 6), pady=1, sticky="w")

        ctk.CTkLabel(
            parent,
            text=label,
            text_color=self.COLOR_TEXT,
            anchor="w",
            height=20,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
        ).grid(row=row, column=1, padx=(0, 8), pady=1, sticky="ew")

        value = ctk.CTkLabel(
            parent,
            text="-",
            text_color=self.COLOR_MUTED,
            anchor="e",
            height=20,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
        )
        value.grid(row=row, column=2, padx=0, pady=1, sticky="e")

        self.status_indicators[key] = indicator
        self.status_text_labels[key] = value

    def _add_live_section_label(self, parent: tk.Frame, row: int, text: str) -> None:
        ctk.CTkLabel(
            parent,
            text=text,
            text_color=self.COLOR_TEXT,
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
        ).grid(row=row, column=0, columnspan=3, padx=0, pady=(7 if row else 0, 2), sticky="ew")

    def _add_live_value_row(self, parent: tk.Frame, row: int, key: str, label: str) -> None:
        ctk.CTkLabel(
            parent,
            text=label,
            text_color=self.COLOR_TEXT,
            anchor="w",
            height=19,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
        ).grid(row=row, column=0, padx=(0, 8), pady=0, sticky="w")

        value = ctk.CTkLabel(
            parent,
            text="-",
            text_color=self.COLOR_TEXT,
            anchor="w",
            height=19,
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        value.grid(row=row, column=1, columnspan=2, padx=0, pady=0, sticky="ew")
        self.live_value_labels[key] = value

    def _add_tracker_live_table(self, parent: tk.Frame, start_row: int) -> None:
        parent.grid_columnconfigure(1, weight=1)
        parent.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            parent,
            text="",
            text_color=self.COLOR_TEXT,
            anchor="w",
            height=19,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12),
        ).grid(row=start_row, column=0, padx=(0, 8), pady=0, sticky="w")

        ctk.CTkLabel(
            parent,
            text="Messung",
            text_color=self.COLOR_TEXT,
            anchor="w",
            height=19,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
        ).grid(row=start_row, column=1, padx=(0, 12), pady=0, sticky="ew")

        ctk.CTkLabel(
            parent,
            text="Station",
            text_color=self.COLOR_TEXT,
            anchor="w",
            height=19,
            font=ctk.CTkFont(family=FONT_FAMILY, size=12, weight="bold"),
        ).grid(row=start_row, column=2, padx=0, pady=0, sticky="ew")

        for offset, axis in enumerate(("X", "Y", "Z"), start=1):
            ctk.CTkLabel(
                parent,
                text=axis,
                text_color=self.COLOR_TEXT,
                anchor="w",
                height=19,
                font=ctk.CTkFont(family=FONT_FAMILY, size=12),
            ).grid(row=start_row + offset, column=0, padx=(0, 8), pady=0, sticky="w")

            measurement_value = ctk.CTkLabel(
                parent,
                text="-",
                text_color=self.COLOR_TEXT,
                anchor="w",
                height=19,
                font=ctk.CTkFont(family="Consolas", size=12),
            )
            measurement_value.grid(row=start_row + offset, column=1, padx=(0, 12), pady=0, sticky="ew")
            self.live_value_labels[f"tracker_measurement_{axis.lower()}"] = measurement_value

            station_value = ctk.CTkLabel(
                parent,
                text="-",
                text_color=self.COLOR_TEXT,
                anchor="w",
                height=19,
                font=ctk.CTkFont(family="Consolas", size=12),
            )
            station_value.grid(row=start_row + offset, column=2, padx=0, pady=0, sticky="ew")
            self.live_value_labels[f"tracker_station_{axis.lower()}"] = station_value

    def _build_action_bar(self) -> None:
        bar = ctk.CTkFrame(
            self,
            fg_color="#e9e9e9",
            border_width=1,
            border_color=self.COLOR_BORDER,
            corner_radius=0,
        )
        bar.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")
        bar.grid_columnconfigure(0, weight=0)
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            bar,
            text="Aktuelle Aktion:",
            text_color=self.COLOR_TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=(10, 6), pady=6, sticky="w")

        self.lbl_current_action = ctk.CTkLabel(
            bar,
            text="Bereit.",
            text_color=self.COLOR_TEXT,
            anchor="w",
        )
        self.lbl_current_action.grid(row=0, column=1, padx=(0, 10), pady=6, sticky="ew")

    # --------------------------------------------------
    # Datei
    # --------------------------------------------------

    def load_points_dialog(self) -> None:
        self.set_current_action("Punktdatei wird geladen...")
        file_path = filedialog.askopenfilename(
            title="Punktdatei laden",
            filetypes=[
                ("Punktdateien", "*.txt *.csv"),
                ("Textdateien", "*.txt"),
                ("CSV-Dateien", "*.csv"),
                ("Alle Dateien", "*.*"),
            ],
        )

        if not file_path:
            self.set_current_action("Bereit.")
            return

        try:
            self.points = load_points_from_txt(file_path)
        except Exception as exc:
            self.log(f"FEHLER beim Laden der Punktdatei: {exc}")
            messagebox.showerror("Punktdatei", str(exc), parent=self)
            self.set_current_action("Fehler beim Laden der Punktdatei.")
            return

        self.selected_point_name = self.points[0].name if self.points else None
        self._apply_demo_scene()
        self.refresh_points()
        self.log(f"Punktdatei geladen: {file_path}")
        self.set_current_action("Punktdatei geladen.")

    def clear_points_dialog(self) -> None:
        if not self.points:
            self.log("Punkte löschen: keine Punkte geladen.")
            self.set_current_action("Keine Punkte geladen.")
            return

        confirmed = messagebox.askyesno(
            "Punkte löschen",
            "Punkte wirklich löschen?",
            parent=self,
        )

        if not confirmed:
            self.set_current_action("Punkte löschen abgebrochen.")
            return

        count = len(self.points)
        self.points = []
        self.selected_point_name = None
        self._apply_demo_scene()
        self.refresh_points()
        self.log(f"Punktliste gelöscht: {count} Punkt(e) entfernt.")
        self.set_current_action("Punktliste gelöscht.")

    def save_project(self) -> None:
        if self.project_path is None:
            self.save_project_as()
            return
        self._write_project_file(self.project_path)

    def save_project_as(self) -> None:
        file_path = filedialog.asksaveasfilename(
            title="Projekt speichern unter",
            defaultextension=".json",
            filetypes=[
                ("Mower-Projekt", "*.json"),
                ("Alle Dateien", "*.*"),
            ],
        )
        if not file_path:
            return
        self.project_path = Path(file_path)
        self._write_project_file(self.project_path)

    def _write_project_file(self, path: Path) -> None:
        self.set_current_action("Projekt wird gespeichert...")

        if write_project_file is not None:
            try:
                write_project_file(
                    path=path,
                    points=self.points,
                    status=self._build_project_status(),
                )
                self.log(f"Projekt gespeichert: {path}")
                self.set_current_action("Projekt gespeichert.")
                return
            except Exception as exc:
                self.log(f"Projekt konnte nicht ueber project_io gespeichert werden: {exc}")

        data = {
            "version": 2,
            "ui": "operator",
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "points": [
                {
                    "name": p.name,
                    "x": p.x,
                    "y": p.y,
                    "z": p.z,
                    "marker_code": getattr(p, "marker_code", 1),
                    "marker_shape": getattr(p, "marker_shape", "plus"),
                    "remark": getattr(p, "remark", ""),
                    "marked": p.marked,
                    "reachable": p.reachable,
                    "last_robot_x": p.last_robot_x,
                    "last_robot_y": p.last_robot_y,
                    "residual_mm": p.residual_mm,
                }
                for p in self.points
            ],
            "status": self._build_project_status(),
        }
        path.write_text(json.dumps(data, indent=4), encoding="utf-8")
        self.log(f"Projekt gespeichert: {path}")
        self.set_current_action("Projekt gespeichert.")

    def _build_project_status(self) -> dict[str, Any]:
        return {
            "xyz_ready": self.xyz_ready,
            "tracker_ready": self.tracker_ready,
            "drehmotor_ready": self.drehmotor_ready,
            "gyro_ready": self.gyro_ready,
            "homing_done": self.homing_done,
            "trafo_valid": self.trafo_valid,
            "arn_active": self.arn_active,
            "tracker_data_current": self.tracker_data_current,
            "tracker_station_xyz": self.tracker_station_xyz,
            "current_lt_measurement_xyz": self.current_lt_measurement_xyz,
        }

    def open_log_file(self) -> None:
        self.log("Logdatei wird geoeffnet.")
        try:
            if hasattr(os, "startfile"):
                os.startfile(self.log_file_path)  # type: ignore[attr-defined]
            else:
                webbrowser.open(self.log_file_path.as_uri())
        except Exception as exc:
            self.log(f"Logdatei konnte nicht geoeffnet werden: {exc}")
            messagebox.showerror("Log oeffnen", str(exc), parent=self)

    def on_close(self) -> None:
        try:
            if self.tracker_receiver is not None and hasattr(self.tracker_receiver, "stop"):
                self.tracker_receiver.stop()
        except Exception:
            pass

        try:
            if self.xyz_worker is not None:
                if hasattr(self.xyz_worker, "stop"):
                    self.xyz_worker.stop()
                elif hasattr(self.xyz_worker, "shutdown"):
                    self.xyz_worker.shutdown()
        except Exception:
            pass

        try:
            if self.gyro_worker is not None and hasattr(self.gyro_worker, "stop"):
                self.gyro_worker.stop()
        except Exception:
            pass

        self.destroy()

    # --------------------------------------------------
    # XYZ
    # --------------------------------------------------

    def _ensure_xyz_worker(self) -> bool:
        """Erzeugt den XYZ-Worker bei Bedarf.

        Passend zur aktuellen Worker-Schnittstelle:
            XYZRobotWorker(on_event=..., on_state_changed=...)
            worker.start()
            worker.send_command(command, **kwargs)
        """
        if self.xyz_worker is not None:
            return True

        if XYZRobotWorker is None:
            self.log("XYZRobotWorker konnte nicht importiert werden.")
            messagebox.showerror(
                "XYZ",
                "XYZRobotWorker konnte nicht importiert werden.",
                parent=self,
            )
            return False

        try:
            self.xyz_worker = XYZRobotWorker(
                on_event=self.on_xyz_event,
                on_state_changed=self.on_xyz_state_changed,
            )

            self.xyz_worker.start()

            self.log("XYZ-Worker initialisiert.")
            return True

        except Exception as exc:
            self.xyz_worker = None
            self.log(f"XYZ-Worker konnte nicht initialisiert werden: {exc}")
            messagebox.showerror("XYZ", str(exc), parent=self)
            return False

    def on_xyz_state_changed(self, state: Any) -> None:
        self.xyz_state = state

        def apply_state() -> None:
            self.xyz_ready = bool(getattr(state, "connected", False))
            self.xyz_connected = self.xyz_ready
            self.homing_done = bool(getattr(state, "homed", False))
            self.update_status()
            self.request_live_map_update()

        self.after(0, apply_state)

    def on_xyz_event(self, event: Any) -> None:
        message = str(getattr(event, "message", event))
        level = str(getattr(getattr(event, "level", ""), "name", getattr(event, "level", "")))

        def apply_event() -> None:
            if level.upper() == "ERROR":
                self.log(f"XYZ FEHLER: {message}")
                self.set_current_action(f"XYZ Fehler: {message}")
            else:
                self.log(f"XYZ: {message}")

                if "Verbindung hergestellt" in message:
                    self.set_current_action("XYZ verbunden.")
                elif "Verbindung getrennt" in message:
                    self.set_current_action("XYZ getrennt.")
                elif "Homing gestartet" in message:
                    self.set_current_action("XYZ-Homing laeuft...")
                elif "Homing abgeschlossen" in message:
                    self.set_current_action("XYZ-Homing abgeschlossen.")
                elif "Position gelesen" in message:
                    self.set_current_action("XYZ-Position gelesen.")

        self.after(0, apply_event)

    def _send_xyz_command(self, command: str, **kwargs: Any) -> bool:
        if not self._ensure_xyz_worker():
            return False

        if self.xyz_worker is None or not hasattr(self.xyz_worker, "send_command"):
            self.log("XYZ-Worker besitzt keine send_command(...)-Schnittstelle.")
            return False

        try:
            self.xyz_worker.send_command(command, **kwargs)
            return True
        except Exception as exc:
            self.log(f"XYZ-Befehl '{command}' konnte nicht gesendet werden: {exc}")
            messagebox.showerror("XYZ", str(exc), parent=self)
            return False

    def connect_xyz(self) -> None:
        self.set_current_action("XYZ wird verbunden...")

        if CONFIG is None:
            messagebox.showerror("XYZ", "CONFIG ist nicht geladen.", parent=self)
            self.set_current_action("Fehler: CONFIG nicht geladen.")
            return

        if show_xyz_connect_dialog is None:
            messagebox.showerror(
                "XYZ",
                "XYZ-Connect-Dialog ist nicht verfügbar.",
                parent=self,
            )
            self.set_current_action("Fehler: XYZ-Connect-Dialog nicht verfügbar.")
            return

        selected_port = show_xyz_connect_dialog(
            parent=self,
            default_port=CONFIG.xyz.port,
            baudrate=CONFIG.xyz.baudrate,
        )

        if not selected_port:
            self.set_current_action("Bereit.")
            return

        self.connect_xyz_with_port(selected_port)


    def connect_xyz_with_port(self, port: str) -> None:
        if CONFIG is None:
            self.set_current_action("Fehler: CONFIG nicht geladen.")
            return

        self.log(f"XYZ verbinden: Port={port}, Baudrate={CONFIG.xyz.baudrate}")
        ok = self._send_xyz_command(
            "connect",
            port=port,
            baudrate=CONFIG.xyz.baudrate,
        )

        if ok:
            self.set_current_action("XYZ-Verbindung wird aufgebaut...")
        else:
            self.set_current_action("XYZ-Verbindung fehlgeschlagen.")

    def disconnect_xyz(self) -> None:
        self.set_current_action("XYZ wird getrennt...")
        ok = self._send_xyz_command("disconnect")

        if ok:
            self.log("XYZ trennen angefordert.")
            self.set_current_action("XYZ-Trennung angefordert.")
        else:
            self.set_current_action("XYZ-Trennung fehlgeschlagen.")

        # UI-Zustand direkt zuruecksetzen; falls der Worker danach noch einen
        # State sendet, wird dieser durch on_xyz_state_changed uebernommen.
        self.xyz_ready = False
        self.xyz_connected = False
        self.homing_done = False
        self.update_status()

    def home_xyz(self) -> None:
        self.set_current_action("XYZ-Homing wird durchgefuehrt...")

        if not self.xyz_ready:
            self.log("XYZ-Homing nicht moeglich: XYZ ist nicht verbunden.")
            messagebox.showwarning("XYZ Homing", "XYZ ist nicht verbunden.", parent=self)
            self.set_current_action("Homing nicht moeglich: XYZ nicht verbunden.")
            return

        ok = self._send_xyz_command("home_all")
        if ok:
            self.log("XYZ Homing angefordert.")
            self.set_current_action("XYZ-Homing laeuft...")
        else:
            self.set_current_action("XYZ-Homing konnte nicht gestartet werden.")

    def move_xyz_to_position_dialog(self) -> None:
        self.set_current_action("XYZ manuell bewegen...")

        if not self.xyz_ready:
            self.log("XYZ-Bewegungsdialog nicht moeglich: XYZ ist nicht verbunden.")
            messagebox.showwarning("XYZ bewegen", "XYZ ist nicht verbunden.", parent=self)
            self.set_current_action("XYZ-Bewegung nicht moeglich: XYZ nicht verbunden.")
            return

        if show_xyz_manual_move_dialog is None:
            messagebox.showerror(
                "XYZ",
                "XYZ-Bewegungsdialog ist nicht verfügbar.",
                parent=self,
            )
            self.set_current_action("Fehler: XYZ-Bewegungsdialog nicht verfügbar.")
            return

        show_xyz_manual_move_dialog(
            parent=self,
            config=CONFIG,
            xyz_state_getter=lambda: self.xyz_state,
            send_xyz_command=self._send_xyz_command,
            read_xyz_position=self.read_xyz_position,
            log=self.log,
            set_current_action=self.set_current_action,
        )
        self.set_current_action("Bereit.")

    def read_xyz_position(self) -> None:
        self.set_current_action("XYZ-Position wird gelesen...")

        if not self.xyz_ready:
            self.log("XYZ-Position lesen nicht moeglich: XYZ ist nicht verbunden.")
            messagebox.showwarning("XYZ", "XYZ ist nicht verbunden.", parent=self)
            self.set_current_action("XYZ-Position lesen nicht moeglich.")
            return

        ok = self._send_xyz_command("read_position")
        if ok:
            self.log("XYZ Position lesen angefordert.")
            self.set_current_action("XYZ-Position wird gelesen...")
        else:
            self.set_current_action("XYZ-Position konnte nicht gelesen werden.")

    # --------------------------------------------------
    # Tracker
    # --------------------------------------------------

    def start_tracker(self) -> None:
        self.set_current_action("Tracker UDP-Empfang wird gestartet...")

        if CONFIG is None:
            messagebox.showerror("Tracker", "CONFIG ist nicht geladen.", parent=self)
            self.set_current_action("Fehler: CONFIG nicht geladen.")
            return

        if LasertrackerReceiver is None:
            messagebox.showerror(
                "Tracker",
                "LasertrackerReceiver konnte nicht importiert werden.",
                parent=self,
            )
            self.set_current_action("Fehler: LasertrackerReceiver nicht verfügbar.")
            return

        if self.tracker_receiver is not None and getattr(self.tracker_receiver, "running", False):
            self.log("Tracker UDP-Empfang läuft bereits.")
            self.set_current_action("Tracker UDP-Empfang läuft bereits.")
            return

        try:
            self.tracker_receiver = LasertrackerReceiver(
                port=CONFIG.tracker.udp_port,
                bind_ip="0.0.0.0",
                on_state_changed=self.on_tracker_state_changed,
                on_log=self.on_tracker_log,
                on_error=self.on_tracker_error,
            )
            self.tracker_receiver.start()

        except Exception as exc:
            self.tracker_receiver = None
            self.tracker_state = None
            self.tracker_ready = False
            self.tracker_started = False
            self.tracker_data_current = False
            self.current_lt_measurement_xyz = None
            self.last_live_reflector_lt_xyz = None
            self.log(f"Tracker UDP-Empfang konnte nicht gestartet werden: {exc}")
            messagebox.showerror("Tracker", str(exc), parent=self)
            self.set_current_action("Tracker UDP-Empfang konnte nicht gestartet werden.")
            self.update_status()
            return

        if self.tracker_receiver is not None and getattr(self.tracker_receiver, "running", False):
            self.tracker_ready = True
            self.tracker_started = True
            self.tracker_data_current = False
            self.log(f"Tracker UDP-Empfang gestartet auf Port {CONFIG.tracker.udp_port}.")
            self.set_current_action("Tracker UDP-Empfang gestartet.")
        else:
            self.tracker_ready = False
            self.tracker_started = False
            self.tracker_data_current = False
            self.current_lt_measurement_xyz = None
            self.last_live_reflector_lt_xyz = None
            self.set_current_action("Tracker UDP-Empfang nicht gestartet.")

        self.update_status()

    def stop_tracker(self) -> None:
        self.set_current_action("Tracker UDP-Empfang wird gestoppt...")

        try:
            if self.tracker_receiver is not None:
                self.tracker_receiver.stop()
        except Exception as exc:
            self.log(f"Tracker UDP-Empfang konnte nicht gestoppt werden: {exc}")

        self.tracker_receiver = None
        self.tracker_state = None

        self.tracker_ready = False
        self.tracker_started = False
        self.tracker_data_current = False
        self.current_lt_measurement_xyz = None
        self.last_live_reflector_lt_xyz = None

        self.log("Tracker UDP-Empfang gestoppt.")
        self.set_current_action("Tracker UDP-Empfang gestoppt.")
        self.update_status()

    def on_tracker_state_changed(self, state: Any) -> None:
        self.tracker_state = state

        def apply_state() -> None:
            receiver_running = (
                self.tracker_receiver is not None
                and getattr(self.tracker_receiver, "running", False)
            )

            self.tracker_ready = bool(receiver_running)
            self.tracker_started = self.tracker_ready

            data_valid = bool(getattr(state, "data_valid", False))
            stale = bool(getattr(state, "stale", True))

            self.tracker_data_current = data_valid and not stale

            x = getattr(state, "x", None)
            y = getattr(state, "y", None)
            z = getattr(state, "z", None)

            if self.tracker_data_current and x is not None and y is not None and z is not None:
                measurement = (float(x), float(y), float(z))
                self.current_lt_measurement_xyz = measurement
                self.last_live_reflector_lt_xyz = measurement
            elif not data_valid:
                self.current_lt_measurement_xyz = None
                # last_live_reflector_lt_xyz bewusst behalten: Bei kurzzeitigem
                # Trackerverlust soll die Karte auf der letzten realen Pose
                # stehen bleiben und nicht auf die Transformationspose springen.

            self.update_status()
            self.request_live_map_update()

        self.after(0, apply_state)

    def on_tracker_log(self, text: str) -> None:
        def apply_log() -> None:
            self.log(f"Tracker: {text}")

            if "UDP Receiver gestartet" in text:
                self.set_current_action("Tracker UDP-Empfang gestartet.")
            elif "UDP-Daten werden empfangen" in text:
                self.set_current_action("Trackerdaten werden empfangen.")
            elif "Messdaten sind aktuell" in text:
                self.set_current_action("Trackerdaten aktuell.")
            elif "Messdaten sind veraltet" in text:
                self.set_current_action("Trackerdaten veraltet.")
            elif "UDP Receiver gestoppt" in text:
                self.set_current_action("Tracker UDP-Empfang gestoppt.")

        self.after(0, apply_log)

    def on_tracker_error(self, text: str) -> None:
        def apply_error() -> None:
            self.log(f"Tracker FEHLER: {text}")
            self.set_current_action(f"Tracker Fehler: {text}")
            self.tracker_data_current = False
            self.update_status()

        self.after(0, apply_error)

    def load_tracker_station_default(self) -> None:
        self._load_tracker_station_from_path(get_tracker_station_file())

    def load_tracker_position_dialog(self) -> None:
        self.set_current_action("Trackerstation wird geladen...")
        file_path = filedialog.askopenfilename(
            title="Trackerstation aus Datei laden",
            initialdir=str(get_tracker_station_file().parent),
            initialfile=get_tracker_station_file().name,
            filetypes=[
                ("Textdateien", "*.txt *.csv"),
                ("Alle Dateien", "*.*"),
            ],
        )
        if not file_path:
            self.set_current_action("Bereit.")
            return

        self._load_tracker_station_from_path(Path(file_path))

    def _load_tracker_station_from_path(self, path: Path) -> None:
        self.set_current_action("Trackerstation wird geladen...")

        try:
            x, y, z = self._read_tracker_xyz_from_file(path)
        except Exception as exc:
            self.log(f"Trackerstation konnte nicht geladen werden: {exc}")
            messagebox.showerror("Trackerstation", str(exc), parent=self)
            self.set_current_action("Trackerstation konnte nicht geladen werden.")
            return

        self.tracker_station_xyz = (x, y, z)
        self.update_map_visualization(keep_view=True)
        self.log(f"Trackerstation geladen: X={x:.3f}, Y={y:.3f}, Z={z:.3f} aus {path}")
        self.set_current_action("Trackerstation geladen.")
        self.update_status()

    @staticmethod
    def _read_tracker_xyz_from_file(path: Path) -> tuple[float, float, float]:
        if not path.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {path}")

        text = path.read_text(encoding="utf-8")

        for line_number, line in enumerate(text.splitlines(), start=1):
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue

            # Erwartetes Standardformat aus dem SA Measurement Plan:
            #   0.000000,0.000000,0.000000
            # Robustheit: auch Leerzeichen, Semikolon und Tabulatoren zulassen.
            parts = raw.replace(",", " ").replace(";", " ").replace("\t", " ").split()

            numeric_values: list[float] = []
            for part in parts:
                try:
                    numeric_values.append(float(part))
                except ValueError:
                    continue

            if len(numeric_values) >= 3:
                return numeric_values[0], numeric_values[1], numeric_values[2]

            raise ValueError(
                f"Zeile {line_number}: keine gültigen X/Y/Z-Koordinaten gefunden. "
                "Erwartet wird z. B. 0.000000,0.000000,0.000000"
            )

        raise ValueError(f"Datei enthält keine Trackerstation: {path}")

    def show_tracker_status(self) -> None:
        if self.tracker_state is None:
            self.log(
                "Tracker Status: "
                f"UDP={'gestartet' if self.tracker_ready else 'gestoppt'}, "
                f"Station={self._format_xyz(self.tracker_station_xyz)}, "
                f"Messung={self._format_xyz(self.current_lt_measurement_xyz)}"
            )
            return

        state = self.tracker_state
        age = getattr(state, "data_age_seconds", None)
        age_text = "-" if age is None else f"{float(age):.2f}s"

        self.log(
            "Tracker Status: "
            f"UDP={'gestartet' if self.tracker_ready else 'gestoppt'}, "
            f"receiving={getattr(state, 'receiving', False)}, "
            f"valid={getattr(state, 'data_valid', False)}, "
            f"stale={getattr(state, 'stale', True)}, "
            f"stable={getattr(state, 'stable', False)}, "
            f"age={age_text}, "
            f"count={getattr(state, 'measurement_count', 0)}, "
            f"Station={self._format_xyz(self.tracker_station_xyz)}, "
            f"Messung={self._format_xyz(self.current_lt_measurement_xyz)}"
        )

    # --------------------------------------------------
    # Drehmotor / Gyro
    # --------------------------------------------------

    def connect_drehmotor(self) -> None:
        self.set_current_action("Drehmotor wird verbunden...")
        self.drehmotor_ready = True
        self.skr_connected = True
        self.log("Drehmotor verbunden. Hinweis: In dieser Erstversion als Status gesetzt.")
        self.set_current_action("Drehmotor verbunden.")
        self.update_status()

    def disconnect_drehmotor(self) -> None:
        self.set_current_action("Drehmotor wird getrennt...")
        self.drehmotor_ready = False
        self.skr_connected = False
        self.log("Drehmotor getrennt.")
        self.set_current_action("Drehmotor getrennt.")
        self.update_status()

    def drehmotor_set_reference(self) -> None:
        self.set_current_action("Drehmotor-Referenz wird gesetzt...")
        self.log("Drehmotor Referenz setzen: noch nicht implementiert.")
        self.set_current_action("Drehmotor-Referenz angefordert.")

    def show_drehmotor_status(self) -> None:
        self.log(f"Drehmotor Status: {'bereit' if self.drehmotor_ready else 'nicht bereit'}")

    def _ensure_gyro_worker(self) -> bool:
        """Erzeugt den KVH-DSP-Worker bei Bedarf."""
        if self.gyro_worker is not None:
            return True

        if KVHDSPWorker is None:
            self.log("KVHDSPWorker konnte nicht importiert werden.")
            messagebox.showerror(
                "Gyro",
                "KVHDSPWorker konnte nicht importiert werden.",
                parent=self,
            )
            return False

        try:
            self.gyro_worker = KVHDSPWorker(
                on_log=self.on_gyro_log,
                on_state_changed=self.on_gyro_state_changed,
            )
            self.gyro_worker.start()
            self.log("KVH-DSP-Worker initialisiert.")
            return True
        except Exception as exc:
            self.gyro_worker = None
            self.log(f"KVH-DSP-Worker konnte nicht initialisiert werden: {exc}")
            messagebox.showerror("Gyro", str(exc), parent=self)
            return False

    def on_gyro_state_changed(self, state: Any) -> None:
        self.gyro_state = state

        def apply_state() -> None:
            self.gyro_ready = bool(getattr(state, "connected", False))
            self.gyems_connected = self.gyro_ready
            self.update_status()
            self.request_live_map_update()

        try:
            self.after(0, apply_state)
        except Exception:
            pass

    def on_gyro_log(self, text: str) -> None:
        def apply_log() -> None:
            self.log(f"Gyro: {text}")
            lower_text = text.lower()
            if "driftmessung abgeschlossen" in lower_text:
                self.set_current_action("KVH DSP Driftmessung abgeschlossen.")
            elif "drift gesetzt" in lower_text:
                self.set_current_action("KVH DSP Driftwert gesetzt.")
            elif "driftmessung gestoppt" in lower_text:
                self.set_current_action("KVH DSP Driftmessung gestoppt.")

        try:
            self.after(0, apply_log)
        except Exception:
            pass

    def connect_gyro(self) -> None:
        self.set_current_action("KVH DSP wird verbunden...")

        if CONFIG is None:
            messagebox.showerror("Gyro", "CONFIG ist nicht geladen.", parent=self)
            self.set_current_action("Fehler: CONFIG nicht geladen.")
            return

        default_port = str(getattr(getattr(CONFIG, "gyro", None), "port", "COM3"))
        baudrate = int(getattr(getattr(CONFIG, "gyro", None), "baudrate", 375000))

        port = simpledialog.askstring(
            "Gyro verbinden",
            "KVH-DSP COM-Port:",
            initialvalue=default_port,
            parent=self,
        )

        if not port:
            self.set_current_action("Bereit.")
            return

        if not self._ensure_gyro_worker():
            self.set_current_action("KVH DSP konnte nicht initialisiert werden.")
            return

        try:
            self.gyro_worker.send_command(
                "connect",
                port=port.strip(),
                baudrate=baudrate,
            )
            self.log(f"KVH DSP verbinden angefordert: {port.strip()} @ {baudrate}.")
            self.set_current_action("KVH DSP Verbindung wird aufgebaut...")
        except Exception as exc:
            self.log(f"KVH DSP verbinden fehlgeschlagen: {exc}")
            messagebox.showerror("Gyro", str(exc), parent=self)
            self.set_current_action("KVH DSP Verbindung fehlgeschlagen.")

    def disconnect_gyro(self) -> None:
        self.set_current_action("KVH DSP wird getrennt...")

        if self.gyro_worker is None:
            self.gyro_ready = False
            self.gyems_connected = False
            self.update_status()
            self.set_current_action("KVH DSP ist bereits getrennt.")
            return

        try:
            self.gyro_worker.send_command("disconnect")
            self.log("KVH DSP trennen angefordert.")
            self.set_current_action("KVH DSP Trennung angefordert.")
        except Exception as exc:
            self.log(f"KVH DSP trennen fehlgeschlagen: {exc}")
            messagebox.showerror("Gyro", str(exc), parent=self)
            self.set_current_action("KVH DSP Trennung fehlgeschlagen.")

    def reset_gyro_angle(self) -> None:
        self.set_current_action("KVH DSP Winkel wird auf 0 gesetzt...")

        if not self._gyro_connected_for_command("Winkel auf 0 setzen"):
            return

        try:
            self.gyro_worker.send_command("reset_angle")
            self.gyro_reference_angle_deg = 0.0
            if self.trafo_valid:
                self._update_gyro_orientation_reference_from_trafo(log_result=False)
            self.log("KVH DSP Winkel auf 0 setzen angefordert.")
            self.set_current_action("KVH DSP Winkel auf 0 gesetzt.")
        except Exception as exc:
            self.log(f"KVH DSP Winkel-Reset fehlgeschlagen: {exc}")
            messagebox.showerror("Gyro", str(exc), parent=self)
            self.set_current_action("KVH DSP Winkel-Reset fehlgeschlagen.")

    def determine_gyro_drift(self) -> None:
        self.set_current_action("KVH DSP Driftmessung wird vorbereitet...")

        if not self._gyro_connected_for_command("Drift bestimmen"):
            return

        if show_kvh_drift_dialog is None:
            self.log("KVH Driftdialog ist nicht verfügbar.")
            messagebox.showerror(
                "Gyro",
                "KVH Driftdialog ist nicht verfügbar.",
                parent=self,
            )
            self.set_current_action("Fehler: KVH Driftdialog nicht verfügbar.")
            return

        default_seconds = float(getattr(getattr(CONFIG, "gyro", None), "default_drift_seconds", 30.0))

        try:
            show_kvh_drift_dialog(
                parent=self,
                state_getter=lambda: self.gyro_state,
                send_gyro_command=self.gyro_worker.send_command,
                default_seconds=default_seconds,
                on_finished=self.on_gyro_drift_finished,
                log=lambda text: self.log(f"Gyro: {text}"),
                set_current_action=self.set_current_action,
            )
        except Exception as exc:
            self.log(f"KVH Driftdialog konnte nicht gestartet werden: {exc}")
            messagebox.showerror("Gyro", str(exc), parent=self)
            self.set_current_action("KVH Driftdialog konnte nicht gestartet werden.")

    def on_gyro_drift_finished(self) -> None:
        self.set_current_action("KVH DSP Driftmessung abgeschlossen.")
        self.update_status()

    def show_gyro_status(self) -> None:
        state = self.gyro_state

        if state is None:
            message = "KVH DSP Status: nicht initialisiert"
            self.log(message)
            messagebox.showinfo("Gyro Status", message, parent=self)
            return

        message = (
            "KVH DSP Status:\n"
            f"  Verbunden: {'ja' if bool(getattr(state, 'connected', False)) else 'nein'}\n"
            f"  Status: {getattr(state, 'status_text', '-')}\n"
            f"  Port: {getattr(state, 'port', '-') or '-'}\n"
            f"  Baudrate: {getattr(state, 'baudrate', '-') or '-'}\n"
            f"  Winkel: {float(getattr(state, 'angle_deg', 0.0)):+.6f} deg\n"
            f"  Rate: {float(getattr(state, 'rate_dps', 0.0)):+.6f} deg/s\n"
            f"  Drift: {float(getattr(state, 'drift_dps', 0.0)):+.10f} deg/s\n"
            f"  Gemessene Drift: {self._format_optional_float(getattr(state, 'pending_drift_dps', None), precision=10, suffix=' deg/s')}\n"
            f"  Drift-Fortschritt: {float(getattr(state, 'drift_progress', 0.0)) * 100.0:.1f}% "
            f"({float(getattr(state, 'drift_elapsed_s', 0.0)):.1f} / "
            f"{float(getattr(state, 'drift_duration_s', 0.0)):.1f} s)\n"
            f"  Gültige Pakete: {int(getattr(state, 'valid_packets', 0))}\n"
            f"  Übersprungene Bytes: {int(getattr(state, 'skipped_bytes', 0))}\n"
            f"  Driftmessung aktiv: {'ja' if bool(getattr(state, 'drift_active', False)) else 'nein'}"
        )
        self.log(
            "KVH DSP Status: "
            f"connected={bool(getattr(state, 'connected', False))}, "
            f"angle={float(getattr(state, 'angle_deg', 0.0)):+.6f} deg, "
            f"rate={float(getattr(state, 'rate_dps', 0.0)):+.6f} deg/s, "
            f"drift={float(getattr(state, 'drift_dps', 0.0)):+.10f} deg/s"
        )
        messagebox.showinfo("Gyro Status", message, parent=self)

    def _gyro_connected_for_command(self, action_name: str) -> bool:
        if self.gyro_worker is None or self.gyro_state is None or not bool(getattr(self.gyro_state, "connected", False)):
            self.log(f"Gyro: {action_name} nicht möglich, KVH DSP ist nicht verbunden.")
            messagebox.showwarning(
                "Gyro",
                "KVH DSP ist nicht verbunden.",
                parent=self,
            )
            self.set_current_action(f"{action_name} nicht möglich: KVH DSP nicht verbunden.")
            return False
        return True

    # --------------------------------------------------
    # System
    # --------------------------------------------------

    def initialize_system(self) -> None:
        self.set_current_action("Systeminitialisierung wird vorbereitet...")

        if CONFIG is None:
            messagebox.showerror("Initialisieren", "CONFIG ist nicht geladen.", parent=self)
            self.set_current_action("Fehler: CONFIG nicht geladen.")
            return

        if show_system_initialization_dialog is None:
            self.log("Initialisierungsdialog ist nicht verfügbar.")
            messagebox.showerror(
                "Initialisieren",
                "Initialisierungsdialog ist nicht verfügbar.",
                parent=self,
            )
            self.set_current_action("Fehler: Initialisierungsdialog nicht verfügbar.")
            return

        if show_trafo_dialog is None:
            self.log("Initialisierung nicht möglich: Trafo-Dialog ist nicht verfügbar.")
            messagebox.showerror(
                "Initialisieren",
                "Trafo-Dialog ist nicht verfügbar.",
                parent=self,
            )
            self.set_current_action("Initialisierung nicht möglich: Trafo-Dialog fehlt.")
            return

        if self.trafo_manager is None:
            self.log("Initialisierung nicht möglich: TrafoManager ist nicht verfügbar.")
            messagebox.showerror(
                "Initialisieren",
                "TrafoManager ist nicht verfügbar.",
                parent=self,
            )
            self.set_current_action("Initialisierung nicht möglich: TrafoManager fehlt.")
            return

        try:
            self.log("Initialisierungsdialog wird geöffnet.")
            self.set_current_action("Systeminitialisierung läuft...")

            show_system_initialization_dialog(
                parent=self,
                config=CONFIG,
                xyz_worker_getter=lambda: self.xyz_worker,
                ensure_xyz_worker=self._ensure_xyz_worker,
                xyz_state_getter=lambda: self.xyz_state,
                send_xyz_command=self._send_xyz_command,
                tracker_receiver_getter=lambda: self.tracker_receiver,
                tracker_data_current_getter=lambda: self.tracker_data_current,
                start_tracker=self.start_tracker,
                gyro_worker_getter=lambda: self.gyro_worker,
                ensure_gyro_worker=self._ensure_gyro_worker,
                gyro_state_getter=lambda: self.gyro_state,
                send_gyro_command=lambda command, **kwargs: self.gyro_worker.send_command(command, **kwargs) if self.gyro_worker is not None else None,
                trafo_manager=self.trafo_manager,
                show_trafo_dialog=show_trafo_dialog,
                on_trafo_finished=self.on_trafo_finished,
                on_finished=self.on_system_initialization_finished,
                log=self.log,
            )

        except Exception as exc:
            self.log(f"Initialisierungsdialog konnte nicht gestartet werden: {exc}")
            messagebox.showerror("Initialisieren", str(exc), parent=self)
            self.set_current_action("Systeminitialisierung konnte nicht gestartet werden.")
            self.update_status()

    def on_system_initialization_finished(self) -> None:
        self.set_current_action("Systeminitialisierung abgeschlossen.")
        self.update_status()

    def start_transformation(self) -> None:
        self.set_current_action("Transformation wird vorbereitet...")

        if show_trafo_dialog is None:
            self.log("Trafo-Dialog ist nicht verfügbar.")
            messagebox.showerror(
                "Transformation",
                "Trafo-Dialog ist nicht verfügbar.",
                parent=self,
            )
            self.set_current_action("Fehler: Trafo-Dialog nicht verfügbar.")
            return

        if self.trafo_manager is None:
            self.log("Transformation nicht möglich: TrafoManager ist nicht verfügbar.")
            messagebox.showerror(
                "Transformation",
                "TrafoManager ist nicht verfügbar.",
                parent=self,
            )
            self.set_current_action("Fehler: TrafoManager nicht verfügbar.")
            return

        if not self.xyz_ready or self.xyz_worker is None:
            self.log("Transformation nicht möglich: XYZ ist nicht verbunden.")
            messagebox.showwarning(
                "Transformation",
                "XYZ ist nicht verbunden.",
                parent=self,
            )
            self.set_current_action("Transformation nicht möglich: XYZ nicht verbunden.")
            return

        if not self.homing_done:
            self.log("Transformation nicht möglich: XYZ-Homing wurde noch nicht durchgeführt.")
            messagebox.showwarning(
                "Transformation",
                "Bitte zuerst XYZ-Homing durchführen.",
                parent=self,
            )
            self.set_current_action("Transformation nicht möglich: Homing fehlt.")
            return

        if not self.tracker_ready or self.tracker_receiver is None:
            self.log("Transformation nicht möglich: Tracker UDP-Empfang läuft nicht.")
            messagebox.showwarning(
                "Transformation",
                "Tracker UDP-Empfang läuft nicht.",
                parent=self,
            )
            self.set_current_action("Transformation nicht möglich: Tracker nicht bereit.")
            return

        if not self.tracker_data_current:
            self.log("Transformation nicht möglich: keine aktuellen Trackerdaten vorhanden.")
            messagebox.showwarning(
                "Transformation",
                "Es sind keine aktuellen Trackerdaten vorhanden.",
                parent=self,
            )
            self.set_current_action("Transformation nicht möglich: keine aktuellen Trackerdaten.")
            return

        try:
            self.log("Transformationsdialog wird geöffnet.")
            self.set_current_action("Transformation läuft...")

            show_trafo_dialog(
                parent=self,
                xyz_worker=self.xyz_worker,
                tracker_receiver=self.tracker_receiver,
                xyz_state_getter=lambda: self.xyz_state,
                trafo_manager=self.trafo_manager,
                on_finished=self.on_trafo_finished,
                log=self.log,
            )

        except Exception as exc:
            self.log(f"Trafo-Dialog konnte nicht gestartet werden: {exc}")
            messagebox.showerror("Transformation", str(exc), parent=self)
            self.set_current_action("Transformation konnte nicht gestartet werden.")
            self.update_status()

    def on_trafo_finished(self) -> None:
        if self.trafo_manager is not None:
            self.trafo_valid = bool(getattr(self.trafo_manager, "valid", False))

        if self.trafo_valid:
            self._update_gyro_orientation_reference_from_trafo(log_result=True)

        self.update_map_visualization(keep_view=False)
        self.set_current_action("Transformation abgeschlossen.")
        self.update_status()

    def offset_calibration(self) -> None:
        self.set_current_action("Marker-/Reflektoroffset-Kalibrierung wird vorbereitet...")

        if show_marker_offset_calibration_dialog is None:
            self.log("Marker-/Reflektoroffset-Dialog ist nicht verfügbar.")
            messagebox.showerror(
                "Marker-/Reflektoroffset",
                "Marker-/Reflektoroffset-Dialog ist nicht verfügbar.",
                parent=self,
            )
            self.set_current_action("Fehler: Offset-Dialog nicht verfügbar.")
            return

        if not self.xyz_ready or self.xyz_worker is None:
            self.log("Offset-Kalibrierung nicht möglich: XYZ ist nicht verbunden.")
            messagebox.showwarning(
                "Marker-/Reflektoroffset",
                "XYZ ist nicht verbunden.",
                parent=self,
            )
            self.set_current_action("Offset-Kalibrierung nicht möglich: XYZ nicht verbunden.")
            return

        if not self.homing_done:
            self.log("Offset-Kalibrierung nicht möglich: XYZ-Homing wurde noch nicht durchgeführt.")
            messagebox.showwarning(
                "Marker-/Reflektoroffset",
                "Bitte zuerst XYZ-Homing durchführen.",
                parent=self,
            )
            self.set_current_action("Offset-Kalibrierung nicht möglich: Homing fehlt.")
            return

        if not self.tracker_ready or self.tracker_receiver is None:
            self.log("Offset-Kalibrierung nicht möglich: Tracker UDP-Empfang läuft nicht.")
            messagebox.showwarning(
                "Marker-/Reflektoroffset",
                "Tracker UDP-Empfang läuft nicht.",
                parent=self,
            )
            self.set_current_action("Offset-Kalibrierung nicht möglich: Tracker nicht bereit.")
            return

        if not self.tracker_data_current:
            self.log("Offset-Kalibrierung nicht möglich: keine aktuellen Trackerdaten vorhanden.")
            messagebox.showwarning(
                "Marker-/Reflektoroffset",
                "Es sind keine aktuellen Trackerdaten vorhanden.",
                parent=self,
            )
            self.set_current_action("Offset-Kalibrierung nicht möglich: keine aktuellen Trackerdaten.")
            return

        try:
            self.log("Marker-/Reflektoroffset-Dialog wird geöffnet.")
            self.set_current_action("Marker-/Reflektoroffset-Kalibrierung läuft...")

            show_marker_offset_calibration_dialog(
                parent=self,
                xyz_worker=self.xyz_worker,
                tracker_receiver=self.tracker_receiver,
                xyz_state_getter=lambda: self.xyz_state,
                on_finished=self.on_marker_offset_calibration_finished,
                log=self.log,
            )

        except Exception as exc:
            self.log(f"Offset-Dialog konnte nicht gestartet werden: {exc}")
            messagebox.showerror("Marker-/Reflektoroffset", str(exc), parent=self)
            self.set_current_action("Offset-Kalibrierung konnte nicht gestartet werden.")
            self.update_status()

    def on_marker_offset_calibration_finished(self) -> None:
        self.set_current_action("Marker-/Reflektoroffset-Kalibrierung abgeschlossen.")
        self.update_status()

    def calibrate_marker_height(self) -> None:
        self.set_current_action("Markerhoehen-Kalibrierung wird vorbereitet...")

        if CONFIG is None:
            messagebox.showerror("Markerhoehe", "CONFIG ist nicht geladen.", parent=self)
            self.set_current_action("Fehler: CONFIG nicht geladen.")
            return

        if show_marker_height_calibration_dialog is None:
            self.log("Markerhoehen-Dialog ist nicht verfügbar.")
            messagebox.showerror(
                "Markerhoehe",
                "Markerhoehen-Dialog ist nicht verfügbar.",
                parent=self,
            )
            self.set_current_action("Fehler: Markerhoehen-Dialog nicht verfügbar.")
            return

        if not self.xyz_ready or self.xyz_worker is None:
            self.log("Markerhoehen-Kalibrierung nicht möglich: XYZ ist nicht verbunden.")
            messagebox.showwarning(
                "Markerhoehe",
                "XYZ ist nicht verbunden.",
                parent=self,
            )
            self.set_current_action("Markerhoehen-Kalibrierung nicht möglich: XYZ nicht verbunden.")
            return

        if not self.homing_done:
            self.log("Markerhoehen-Kalibrierung nicht möglich: XYZ-Homing wurde noch nicht durchgeführt.")
            messagebox.showwarning(
                "Markerhoehe",
                "Bitte zuerst XYZ-Homing durchführen.",
                parent=self,
            )
            self.set_current_action("Markerhoehen-Kalibrierung nicht möglich: Homing fehlt.")
            return

        try:
            self.log("Markerhoehen-Dialog wird geöffnet.")
            self.set_current_action("Markerhoehen-Kalibrierung läuft...")

            show_marker_height_calibration_dialog(
                parent=self,
                config=CONFIG,
                xyz_state_getter=lambda: self.xyz_state,
                send_xyz_command=self._send_xyz_command,
                read_xyz_position=self.read_xyz_position,
                log=self.log,
                set_current_action=self.set_current_action,
                on_finished=self.on_marker_height_calibration_finished,
            )

        except Exception as exc:
            self.log(f"Markerhoehen-Dialog konnte nicht gestartet werden: {exc}")
            messagebox.showerror("Markerhoehe", str(exc), parent=self)
            self.set_current_action("Markerhoehen-Kalibrierung konnte nicht gestartet werden.")
            self.update_status()

    def on_marker_height_calibration_finished(self) -> None:
        self.set_current_action("Markerhoehen-Kalibrierung abgeschlossen.")
        self.update_status()


    def mark_points_dialog(self) -> None:
        self.set_current_action("Punkte markieren wird vorbereitet...")

        if show_point_marking_dialog is None:
            self.log("Punkte-markieren-Dialog ist nicht verfuegbar.")
            messagebox.showerror(
                "Punkte markieren",
                "Punkte-markieren-Dialog ist nicht verfuegbar.",
                parent=self,
            )
            self.set_current_action("Fehler: Punkte-markieren-Dialog nicht verfuegbar.")
            return

        if not self.xyz_ready or self.xyz_worker is None:
            self.log("Punkte markieren nicht moeglich: XYZ ist nicht verbunden.")
            messagebox.showwarning(
                "Punkte markieren",
                "XYZ ist nicht verbunden.",
                parent=self,
            )
            self.set_current_action("Punkte markieren nicht moeglich: XYZ nicht verbunden.")
            return

        if not self.homing_done:
            self.log("Punkte markieren nicht moeglich: XYZ-Homing wurde noch nicht durchgefuehrt.")
            messagebox.showwarning(
                "Punkte markieren",
                "Bitte zuerst XYZ-Homing durchfuehren.",
                parent=self,
            )
            self.set_current_action("Punkte markieren nicht moeglich: Homing fehlt.")
            return

        if self.trafo_manager is None or not bool(getattr(self.trafo_manager, "valid", False)):
            self.log("Punkte markieren nicht moeglich: keine gueltige Transformation vorhanden.")
            messagebox.showwarning(
                "Punkte markieren",
                "Es ist keine gueltige Transformation vorhanden.",
                parent=self,
            )
            self.set_current_action("Punkte markieren nicht moeglich: Trafo ungueltig.")
            return

        if not self.points:
            self.log("Punkte markieren nicht moeglich: keine Punkte geladen.")
            messagebox.showwarning(
                "Punkte markieren",
                "Es sind keine Punkte geladen.",
                parent=self,
            )
            self.set_current_action("Punkte markieren nicht moeglich: keine Punkte geladen.")
            return

        try:
            self.log("Punkte-markieren-Dialog wird geoeffnet.")
            self.set_current_action("Punkte markieren...")

            show_point_marking_dialog(
                parent=self,
                points=self.points,
                xyz_worker=self.xyz_worker,
                xyz_state_getter=lambda: self.xyz_state,
                trafo_manager=self.trafo_manager,
                on_points_changed=lambda: self.refresh_points(keep_map_view=True),
                on_finished=self.on_point_marking_finished,
                log=self.log,
            )

        except Exception as exc:
            self.log(f"Punkte-markieren-Dialog konnte nicht gestartet werden: {exc}")
            messagebox.showerror("Punkte markieren", str(exc), parent=self)
            self.set_current_action("Punkte markieren konnte nicht gestartet werden.")
            self.update_status()

    def on_point_marking_finished(self) -> None:
        self.set_current_action("Punkte markieren abgeschlossen.")
        self.refresh_points(keep_map_view=True)
        self.update_status()

    def activate_arn(self) -> None:
        self.set_current_action("Reflektornachfuehrung wird aktiviert...")
        self.arn_active = True
        self.log("Reflektornachfuehrung aktiviert.")
        self.set_current_action("Reflektornachfuehrung aktiv.")
        self.update_status()

    def deactivate_arn(self) -> None:
        self.set_current_action("Reflektornachfuehrung wird deaktiviert...")
        self.arn_active = False
        self.log("Reflektornachfuehrung deaktiviert.")
        self.set_current_action("Reflektornachfuehrung inaktiv.")
        self.update_status()

    def show_active_config(self) -> None:
        message = "Config konnte nicht geladen werden." if CONFIG is None else self._format_config_text()
        self.log("Aktive Config angezeigt.")
        messagebox.showinfo("Aktive Config", message, parent=self)

    def reload_config(self) -> None:
        self.set_current_action("Config neu laden angefordert...")
        self.log("Config neu laden: noch nicht implementiert. Aktuell wird CONFIG beim Programmstart geladen.")

    # --------------------------------------------------
    # Point handling
    # --------------------------------------------------

    def load_demo_points(self) -> None:
        self.points = create_demo_points()
        self.selected_point_name = self.points[0].name if self.points else None
        self._apply_demo_scene()
        self.refresh_points()
        self.log("Demo-Punkte geladen.")

    def refresh_points(self, *, keep_map_view: bool = False) -> None:
        for point in self.points:
            point.selected = point.name == self.selected_point_name

        self._update_point_list()
        self.update_map_visualization(keep_view=True)
        self.map_view.set_points(self.points, keep_view=keep_map_view)
        self._update_selected_label()
        self._update_point_count_label()

    def _update_point_list(self) -> None:
        if not hasattr(self, "point_tree"):
            return

        current_selection = self.selected_point_name
        for item in self.point_tree.get_children():
            self.point_tree.delete(item)

        for point in self.points:
            remark = str(getattr(point, "remark", "")).strip()
            self.point_tree.insert(
                "",
                "end",
                iid=point.name,
                values=(
                    point.name,
                    self._point_status_display(point),
                    self._marker_shape_symbol(point),
                    remark,
                ),
            )

        if current_selection and any(point.name == current_selection for point in self.points):
            try:
                self.point_tree.selection_set(current_selection)
                self.point_tree.focus(current_selection)
                self.point_tree.see(current_selection)
            except Exception:
                pass

    def on_point_tree_selected(self, _event: tk.Event | None = None) -> None:
        if not hasattr(self, "point_tree"):
            return

        selection = self.point_tree.selection()
        if not selection:
            return

        name = str(selection[0])
        if name == self.selected_point_name:
            return

        if not any(point.name == name for point in self.points):
            return

        self.selected_point_name = name
        for point in self.points:
            point.selected = point.name == self.selected_point_name
        self.map_view.set_points(self.points, keep_view=True)
        self._update_selected_label()
        self.set_current_action(f"Punkt {name} ausgewaehlt.")

    def on_point_tree_double_click(self, _event: tk.Event | None = None) -> None:
        point = self.selected_point()
        if point is not None:
            self.set_current_action(f"Punkt {point.name} ausgewaehlt.")

    def select_point_by_name(self, name: str) -> None:
        if not any(point.name == name for point in self.points):
            return
        self.selected_point_name = name
        self.refresh_points(keep_map_view=True)
        self.set_current_action(f"Punkt {name} ausgewaehlt.")

    def selected_point(self) -> StakeoutPoint | None:
        for point in self.points:
            if point.name == self.selected_point_name:
                return point
        return None

    def _update_selected_label(self) -> None:
        point = self.selected_point()
        if point is None:
            if self.lbl_selected_point is not None:
                self.lbl_selected_point.configure(text="Auswahl: -")
            self._set_point_detail_values(
                name="-",
                coordinates="-",
                status="-",
                marker="-",
                remark="-",
            )
            return

        if self.lbl_selected_point is not None:
            self.lbl_selected_point.configure(text=f"Auswahl: {point.name} | {point.status_text}")

        remark = str(getattr(point, "remark", "")).strip() or "-"
        marker_code = getattr(point, "marker_code", 1)
        marker_shape = str(getattr(point, "marker_shape", "plus")).strip()
        marker_text = self._marker_shape_label(marker_shape)

        self._set_point_detail_values(
            name=str(point.name),
            coordinates=point.xyz_text(),
            status=self._point_status_display(point),
            marker=f"{marker_code} - {marker_text}",
            remark=remark,
        )

    def _set_point_detail_values(
            self,
            *,
            name: str,
            coordinates: str,
            status: str,
            marker: str,
            remark: str,
    ) -> None:
        values = {
            "name": name,
            "coordinates": coordinates,
            "status": status,
            "marker": marker,
            "remark": remark,
        }

        labels = getattr(self, "point_detail_value_labels", {})
        for key, value in values.items():
            label = labels.get(key)
            if label is not None:
                label.configure(text=value)

    @staticmethod
    def _marker_shape_label(marker_shape: str) -> str:
        labels = {
            "plus": "Plus",
            "cross": "Kreuz",
            "circle_point": "Kreis/Punkt",
            "plus_circle": "Plus/Kreis",
            "none": "Keine",
        }
        return labels.get(str(marker_shape).strip(), str(marker_shape).strip() or "-")

    def _marker_shape_symbol(self, point: StakeoutPoint) -> str:
        marker_shape = str(getattr(point, "marker_shape", "plus")).strip()
        symbols = {
            "plus": "+",
            "cross": "X",
            "circle_point": "○",
            "plus_circle": "+○",
            "none": "-",
        }
        return symbols.get(marker_shape, self._marker_shape_label(marker_shape))

    @staticmethod
    def _point_status_display(point: StakeoutPoint) -> str:
        if bool(getattr(point, "marked", False)):
            return "abgesteckt"
        if bool(getattr(point, "reachable", False)):
            return "erreichbar"
        return "nicht erreichbar"

    # --------------------------------------------------
    # Demo scene / reachability placeholder
    # --------------------------------------------------

    def _apply_demo_scene(self) -> None:
        """Aktualisiert die Kartenvisualisierung ohne Demo-Arbeitsbereich.

        Der Name bleibt aus Kompatibilitaetsgruenden erhalten, wird aber nicht mehr
        fuer einen kuenstlichen Rahmen um die Punkte verwendet. Der Arbeitsbereich
        wird nur aus der aktiven Transformation berechnet.
        """

        self.update_map_visualization(keep_view=True)

    def request_live_map_update(self) -> None:
        """Fordert ein gedrosseltes Kartenupdate an.

        Tracker und KVH koennen deutlich schneller Daten liefern als die GUI
        sinnvoll zeichnen sollte. Die Karte wird daher auf die konfigurierte
        Anzeige-Rate begrenzt.
        """

        if not hasattr(self, "map_view"):
            return

        now = time.monotonic()
        interval_s = max(float(getattr(self, "map_update_interval_ms", 200)) / 1000.0, 0.05)
        elapsed_s = now - float(getattr(self, "_last_map_update_time_s", 0.0))

        if elapsed_s >= interval_s:
            self._last_map_update_time_s = now
            self._pending_map_update_after_id = None
            self.update_map_visualization(keep_view=True)
            return

        if getattr(self, "_pending_map_update_after_id", None) is not None:
            return

        delay_ms = max(int((interval_s - elapsed_s) * 1000.0), 1)

        def run_delayed_update() -> None:
            self._pending_map_update_after_id = None
            self._last_map_update_time_s = time.monotonic()
            self.update_map_visualization(keep_view=True)

        try:
            self._pending_map_update_after_id = self.after(delay_ms, run_delayed_update)
        except Exception:
            self._pending_map_update_after_id = None

    def update_map_visualization(self, *, keep_view: bool = True) -> None:
        """Berechnet und zeichnet Arbeitsbereich, Frontpfeil, Reflektor und Marker."""

        if not hasattr(self, "map_view"):
            return

        if self.tracker_station_xyz is not None:
            self.map_view.set_tracker_position((self.tracker_station_xyz[0], self.tracker_station_xyz[1]))
        else:
            self.map_view.set_tracker_position(None)

        if build_map_visualization_state is None or CONFIG is None:
            if hasattr(self.map_view, "set_robot_visualization"):
                self.map_view.set_robot_visualization(
                    workspace_polygon=None,
                    wagon_outline_polygon=None,
                    front_arrow=None,
                    reflector_position=None,
                    marker_position=None,
                )
            else:
                self.map_view.set_robot_workspace_polygon(None)
            return

        live_reflector_lt_xyz = (
            self.current_lt_measurement_xyz
            if self.tracker_data_current
            else self.last_live_reflector_lt_xyz
        )

        state = build_map_visualization_state(
            trafo_manager=self.trafo_manager,
            config=CONFIG,
            xyz_state=self.xyz_state,
            live_reflector_lt_xyz=live_reflector_lt_xyz,
            live_orientation_lt_deg=self._current_gyro_orientation_lt_deg(),
        )

        self._update_live_reachability_from_visualization(state.workspace_polygon)

        if hasattr(self.map_view, "set_robot_visualization"):
            self.map_view.set_robot_visualization(
                workspace_polygon=state.workspace_polygon,
                wagon_outline_polygon=state.wagon_outline_polygon,
                front_arrow=state.front_arrow,
                reflector_position=state.reflector_position,
                marker_position=state.marker_position,
            )
        else:
            self.map_view.set_robot_workspace_polygon(state.workspace_polygon)

        if not keep_view:
            self.map_view.zoom_all()

    def _update_live_reachability_from_visualization(
            self,
            workspace_polygon: list[tuple[float, float]] | None,
    ) -> None:
        """Aktualisiert die Anzeige-Erreichbarkeit aus dem live dargestellten Markierbereich.

        Diese Erreichbarkeit ist bewusst eine Bedien-/Visualisierungshilfe. Sie
        aendert nicht die Transformations- oder Markierlogik, sondern sorgt nur
        dafuer, dass Punktfarben, Punktliste und Zaehler zur aktuell angezeigten
        Kartenpose passen.
        """

        if not self.points:
            return

        changed = False
        for point in self.points:
            marked = bool(getattr(point, "marked", False))

            if marked:
                reachable = False
            elif workspace_polygon:
                try:
                    reachable = self._point_in_polygon(
                        (float(getattr(point, "x")), float(getattr(point, "y"))),
                        workspace_polygon,
                    )
                except Exception:
                    reachable = False
            else:
                reachable = False

            if bool(getattr(point, "reachable", False)) != reachable:
                try:
                    point.reachable = reachable
                    changed = True
                except Exception:
                    pass

        if changed:
            self._update_point_list()
            self._update_point_count_label()
            self._update_selected_label()

    def _update_point_count_label(self) -> None:
        if not hasattr(self, "lbl_point_count"):
            return

        reachable_count = sum(
            1
            for point in self.points
            if bool(getattr(point, "reachable", False)) and not bool(getattr(point, "marked", False))
        )
        marked_count = sum(1 for point in self.points if bool(getattr(point, "marked", False)))
        self.lbl_point_count.configure(
            text=f"{len(self.points)} Punkte | {reachable_count} erreichbar | {marked_count} abgesteckt"
        )

    @staticmethod
    def _point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
        x, y = point
        inside = False
        j = len(polygon) - 1

        for i in range(len(polygon)):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            intersect = ((yi > y) != (yj > y)) and (
                x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
            )
            if intersect:
                inside = not inside
            j = i
        return inside

    # --------------------------------------------------
    # Status / Log
    # --------------------------------------------------

    def set_current_action(self, text: str) -> None:
        self.lbl_current_action.configure(text=text)

    def update_status(self) -> None:
        xyz_error = self._state_error_text(self.xyz_state)
        gyro_error = self._state_error_text(self.gyro_state)

        if xyz_error:
            self._set_status_row("xyz", "Fehler", "error")
        else:
            self._set_status_row("xyz", "verbunden" if self.xyz_ready else "getrennt", "ok" if self.xyz_ready else "error")

        if self.tracker_ready:
            self._set_status_row("tracker", "UDP aktiv", "ok")
        else:
            self._set_status_row("tracker", "UDP aus", "error")

        if gyro_error:
            self._set_status_row("gyro", "Fehler", "error")
        else:
            self._set_status_row("gyro", "verbunden" if self.gyro_ready else "getrennt", "ok" if self.gyro_ready else "neutral")

        self._set_status_row(
            "drehmotor",
            "verbunden" if self.drehmotor_ready else "getrennt",
            "ok" if self.drehmotor_ready else "neutral",
        )

        self._set_status_row(
            "homing",
            "erledigt" if self.homing_done else "offen",
            "ok" if self.homing_done else "neutral",
        )
        self._set_status_row(
            "trafo",
            "gültig" if self.trafo_valid else "ungültig",
            "ok" if self.trafo_valid else "error",
        )

        if self.tracker_data_current:
            tracker_data_text = "aktuell"
            tracker_data_state = "ok"
        elif self.tracker_ready:
            tracker_data_text = "wartet"
            tracker_data_state = "warning"
        else:
            tracker_data_text = "keine Daten"
            tracker_data_state = "error"
        self._set_status_row("trackerdaten", tracker_data_text, tracker_data_state)

        self._set_status_row(
            "arn",
            "aktiv" if self.arn_active else "inaktiv",
            "ok" if self.arn_active else "neutral",
        )

        self._update_live_values()

    def _set_status_row(self, key: str, text: str, state: str) -> None:
        colors = {
            "ok": self.COLOR_GREEN,
            "warning": self.COLOR_YELLOW,
            "error": self.COLOR_RED,
            "neutral": "#8a8a8a",
        }
        text_colors = {
            "ok": self.COLOR_TEXT,
            "warning": self.COLOR_TEXT,
            "error": self.COLOR_TEXT,
            "neutral": self.COLOR_MUTED,
        }

        indicator = self.status_indicators.get(key)
        if indicator is not None:
            indicator.configure(text_color=colors.get(state, "#8a8a8a"))

        label = self.status_text_labels.get(key)
        if label is not None:
            label.configure(text=text, text_color=text_colors.get(state, self.COLOR_TEXT))

    def _update_live_values(self) -> None:
        state = self.xyz_state
        self._set_live_value("xyz_x", self._format_mm_component(getattr(state, "x", None)))
        self._set_live_value("xyz_y", self._format_mm_component(getattr(state, "y", None)))
        self._set_live_value("xyz_z", self._format_mm_component(getattr(state, "z", None)))

        self._set_tracker_live_values(
            prefix="tracker_station",
            values=self.tracker_station_xyz,
        )
        self._set_tracker_live_values(
            prefix="tracker_measurement",
            values=self.current_lt_measurement_xyz,
        )

        gyro = self.gyro_state
        self._set_live_value("gyro_angle", self._format_unsigned_positive_value(self._current_gyro_angle_deg(), precision=3, suffix=" °"))
        self._set_live_value("gyro_orientation_lt", self._format_unsigned_positive_value(self._current_gyro_orientation_lt_deg(), precision=3, suffix=" °"))
        self._set_live_value("gyro_drift", self._format_unsigned_positive_value(getattr(gyro, "drift_dps", None), precision=7, suffix=" °/s"))

    def _update_gyro_orientation_reference_from_trafo(self, *, log_result: bool = False) -> None:
        """Setzt die Orientierungsreferenz aus der aktiven Transformation.

        Die aktive Transformation liefert die Orientierung der Roboter-X-Achse
        im Lasertracker-XY-System. Der KVH-Winkel wird relativ zu diesem
        Zeitpunkt addiert.
        """
        orientation = self._orientation_lt_from_active_trafo()
        if orientation is None:
            self.gyro_lt_reference_orientation_deg = None
            self.gyro_reference_angle_deg = None
            return

        gyro_angle = self._current_gyro_angle_deg()
        if gyro_angle is None:
            gyro_angle = 0.0

        self.gyro_lt_reference_orientation_deg = orientation
        self.gyro_reference_angle_deg = gyro_angle

        if log_result:
            self.log(
                "Gyro-Orientierungsreferenz gesetzt: "
                f"Orientierung LT={orientation:.3f} deg, KVH-Winkel={gyro_angle:.3f} deg."
            )

    def _orientation_lt_from_active_trafo(self) -> float | None:
        if self.trafo_manager is None or not bool(getattr(self.trafo_manager, "valid", False)):
            return None

        trafo = getattr(self.trafo_manager, "active_trafo", None)
        rotation = getattr(trafo, "rotation", None)
        if rotation is None:
            return None

        try:
            # Roboter +X zeigt nach vorne. Die erste Spalte der Rotationsmatrix
            # ist diese Achse im Lasertracker-System.
            vx = float(rotation[0, 0])
            vy = float(rotation[1, 0])
        except Exception:
            try:
                vx = float(rotation[0][0])
                vy = float(rotation[1][0])
            except Exception:
                return None

        angle = math.degrees(math.atan2(vy, vx))
        return self._normalize_angle_360(angle)

    def _current_gyro_orientation_lt_deg(self) -> float | None:
        if self.gyro_lt_reference_orientation_deg is None or self.gyro_reference_angle_deg is None:
            return None
        if self.gyro_state is None:
            return None

        gyro_angle = self._current_gyro_angle_deg()
        if gyro_angle is None:
            return None

        delta = gyro_angle - self.gyro_reference_angle_deg
        return self._normalize_angle_360(self.gyro_lt_reference_orientation_deg + delta)

    def _current_gyro_angle_deg(self) -> float | None:
        """Liefert den KVH-Winkel mit der im System gueltigen Vorzeichenkonvention.

        Der physische Einbau des KVH liefert den positiven Winkel entgegengesetzt
        zum gewuenschten Drehsinn im Lasertracker-/Kartensystem. Deshalb wird das
        Vorzeichen hier zentral korrigiert, statt es in der Config zu fuehren.
        """
        if self.gyro_state is None:
            return None
        try:
            return -float(getattr(self.gyro_state, "angle_deg", 0.0))
        except Exception:
            return None

    @staticmethod
    def _normalize_angle_360(angle_deg: float) -> float:
        value = float(angle_deg) % 360.0
        if value < 0.0:
            value += 360.0
        return value

    def _set_live_value(self, key: str, text: str) -> None:
        label = self.live_value_labels.get(key)
        if label is not None:
            label.configure(text=text)

    def _set_tracker_live_values(
            self,
            *,
            prefix: str,
            values: tuple[float, float, float] | None,
    ) -> None:
        if values is None:
            x_text = y_text = z_text = "-"
        else:
            x, y, z = values
            x_text = self._format_coordinate_value(x)
            y_text = self._format_coordinate_value(y)
            z_text = self._format_coordinate_value(z)

        self._set_live_value(f"{prefix}_x", x_text)
        self._set_live_value(f"{prefix}_y", y_text)
        self._set_live_value(f"{prefix}_z", z_text)

    @staticmethod
    def _state_error_text(state: Any | None) -> str:
        if state is None:
            return ""
        error_text = getattr(state, "error_text", None)
        return str(error_text).strip() if error_text else ""

    @staticmethod
    def _format_mm_component(value: Any) -> str:
        if value is None:
            return "-"
        try:
            return f"{float(value):10.3f} mm"
        except Exception:
            return "-"

    @staticmethod
    def _format_xyz_inline(values: tuple[float, float, float] | None) -> str:
        if values is None:
            return "X=-  Y=-  Z=-"
        x, y, z = values
        return f"X={x:.3f}  Y={y:.3f}  Z={z:.3f}"

    @staticmethod
    def _format_unsigned_positive_value(value: Any, *, precision: int, suffix: str = "") -> str:
        if value is None:
            return "-"
        try:
            return f"{float(value):.{precision}f}{suffix}"
        except Exception:
            return "-"

    @staticmethod
    def _format_coordinate_value(value: Any) -> str:
        if value is None:
            return "-"
        try:
            return f"{float(value):.3f}"
        except Exception:
            return "-"

    @staticmethod
    def _format_xyz(values: tuple[float, float, float] | None) -> str:
        if values is None:
            return "X=-  Y=-  Z=-"
        x, y, z = values
        return f"X={x:.3f}  Y={y:.3f}  Z={z:.3f}"

    @staticmethod
    def _format_xyz_components(values: tuple[float, float, float] | None) -> tuple[str, str, str]:
        if values is None:
            return "X=-", "Y=-", "Z=-"
        x, y, z = values
        return f"X={x:.3f}", f"Y={y:.3f}", f"Z={z:.3f}"

    @staticmethod
    def _format_optional_float(value: Any, *, precision: int = 3, suffix: str = "") -> str:
        if value is None:
            return "-"
        try:
            return f"{float(value):.{precision}f}{suffix}"
        except Exception:
            return "-"

    def _format_config_text(self) -> str:
        if CONFIG is None:
            return "Config: nicht geladen"
        return (
            "Config:\n"
            f"  XYZ: {CONFIG.xyz.port} @ {CONFIG.xyz.baudrate}\n"
            f"  Tracker UDP: {CONFIG.tracker.udp_port}\n"
            f"  Gyro/KVH DSP: {getattr(getattr(CONFIG, 'gyro', None), 'port', 'COM3')} @ "
            f"{getattr(getattr(CONFIG, 'gyro', None), 'baudrate', 375000)}\n"
            f"  Workspace X/Y/Z:\n"
            f"    X {CONFIG.xyz.x_min:.0f}..{CONFIG.xyz.x_max:.0f}\n"
            f"    Y {CONFIG.xyz.y_min:.0f}..{CONFIG.xyz.y_max:.0f}\n"
            f"    Z {CONFIG.xyz.z_min:.0f}..{CONFIG.xyz.z_max:.0f}\n"
            f"  Marker:\n"
            f"    Shape={CONFIG.marker.shape}, Size={CONFIG.marker.size_mm:.3f} mm\n"
            f"    Z_MARK={getattr(CONFIG.marker, 'z_mark_mm', 166.0):.3f} mm\n"
            f"    Z_CLEAR={getattr(CONFIG.marker, 'z_clear_mm', getattr(CONFIG.marker, 'z_mark_mm', 166.0) + 5.0):.3f} mm\n"
            f"    Z_TRAVEL={getattr(CONFIG.marker, 'z_travel_mm', getattr(CONFIG.marker, 'z_mark_mm', 166.0) + 10.0):.3f} mm\n"
            f"  Offset:\n"
            f"    X={CONFIG.transformation.marker_to_reflector_robot[0]:.3f}\n"
            f"    Y={CONFIG.transformation.marker_to_reflector_robot[1]:.3f}\n"
            f"    Z={CONFIG.transformation.marker_to_reflector_robot[2]:.3f}"
        )

    def _config_float(self, section: str, name: str, fallback: float) -> float:
        if CONFIG is None:
            return fallback
        obj = getattr(CONFIG, section, None)
        if obj is None:
            return fallback
        return float(getattr(obj, name, fallback))

    def log(self, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {text}"

        # Das sichtbare Log wurde aus der rechten Statusspalte entfernt.
        # Falls eine aeltere UI-Variante noch self.logbox besitzt, bleibt die
        # Methode rueckwaertskompatibel.
        logbox = getattr(self, "logbox", None)
        if logbox is not None:
            try:
                logbox.insert("end", line + "\n")
                logbox.see("end")
            except Exception:
                pass

        try:
            with self.log_file_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def clear_log(self) -> None:
        # Kein sichtbares Log mehr vorhanden. Die Logdatei bleibt als
        # Protokoll erhalten und wird ueber Datei -> Log oeffnen eingesehen.
        self.set_current_action("Log wird nur als Datei gefuehrt.")

    def save_log_dialog(self) -> None:
        # Log speichern ist in der reduzierten Oberflaeche nicht mehr als
        # separater Bedienvorgang vorgesehen. Die aktuelle Logdatei wird
        # laufend geschrieben.
        self.open_log_file()


if __name__ == "__main__":
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")

    app = MowerOperatorApp()
    app.mainloop()

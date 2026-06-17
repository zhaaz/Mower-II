# App/mower_operator_app.py
# Version 13: Operator-Oberflaeche mit kompaktem Statusbereich ohne Status-Haupttitel

from __future__ import annotations

import json
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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

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
    from App.dialogs.xyz_connect_dialog_classic import show_xyz_connect_dialog_classic
except Exception:
    show_xyz_connect_dialog_classic = None

try:
    from App.dialogs.xyz_manual_move_dialog_classic import show_xyz_manual_move_dialog_classic
except Exception:
    show_xyz_manual_move_dialog_classic = None

try:
    from App.services.project_io import write_project_file
except Exception:
    write_project_file = None

try:
    from XYZ_Robot.xyz_robot_worker import XYZRobotWorker
except Exception:
    XYZRobotWorker = None

try:
    from Lasertracker.lasertracker_receiver import LasertrackerReceiver
except Exception:
    LasertrackerReceiver = None

try:
    from App.dialogs.trafo_dialog import show_trafo_dialog
except Exception:
    show_trafo_dialog = None

try:
    from Transformation.trafo_manager import TrafoManager
except Exception:
    TrafoManager = None

try:
    from Transformation.coordinate_mapper import CoordinateMapper, RobotWorkspace
except Exception:
    CoordinateMapper = None
    RobotWorkspace = None



class OperatorMapView(MapView):
    """Helle Kartenansicht fuer die klassische Operator-Oberflaeche."""

    COLOR_CANVAS = "#eeeeee"
    COLOR_GRID = "#d6d6d6"
    COLOR_AXIS = "#b8b8b8"
    COLOR_TEXT = "#222222"
    COLOR_BUTTON = "#f7f7f7"
    COLOR_BUTTON_BORDER = "#9e9e9e"
    COLOR_WORKSPACE_FILL = "#dceff5"
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
                stipple="gray25",
            )
            self.canvas.create_text(
                coords[0],
                coords[1] - 12,
                text="Wagen / Arbeitsbereich",
                fill=self.COLOR_WORKSPACE_OUTLINE,
                anchor="sw",
                font=("Segoe UI", 9),
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
        - Status + Log rechts
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

        if TrafoManager is not None:
            self.trafo_manager = TrafoManager()
        else:
            self.trafo_manager = None

        self.status_indicators: dict[str, ctk.CTkLabel] = {}

        self._build_ui()
        self.load_demo_points()
        self.set_current_action("Bereit.")
        self.update_status()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # --------------------------------------------------
    # UI
    # --------------------------------------------------

    def _build_ui(self) -> None:
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
        tracker_menu.add_command(label="Trackerposition aus Datei laden...", command=self.load_tracker_position_dialog)
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
        gyro_menu.add_command(label="Status anzeigen", command=self.show_gyro_status)
        menu_bar.add_cascade(label="Gyro", menu=gyro_menu)

        system_menu = Menu(menu_bar, tearoff=False)
        system_menu.add_command(label="Transformation starten", command=self.start_transformation)
        system_menu.add_command(label="Marker-/Reflektoroffset kalibrieren", command=self.offset_calibration)
        system_menu.add_separator()
        system_menu.add_command(label="ARN aktivieren", command=self.activate_arn)
        system_menu.add_command(label="ARN deaktivieren", command=self.deactivate_arn)
        system_menu.add_separator()
        system_menu.add_command(label="Aktive Config anzeigen", command=self.show_active_config)
        system_menu.add_command(label="Config neu laden", command=self.reload_config)
        menu_bar.add_cascade(label="System", menu=system_menu)

        view_menu = Menu(menu_bar, tearoff=False)
        view_menu.add_command(label="Karte aktualisieren", command=lambda: self.refresh_points(keep_map_view=True))
        view_menu.add_command(label="Log leeren", command=self.clear_log)
        view_menu.add_command(label="Log speichern...", command=self.save_log_dialog)
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
        panel.configure(width=280)

        ctk.CTkLabel(
            panel,
            text="Punktliste",
            text_color=self.COLOR_TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=16, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=12, pady=(12, 4), sticky="ew")

        self.lbl_point_count = ctk.CTkLabel(panel, text="0 Punkte", text_color=self.COLOR_MUTED, anchor="w")
        self.lbl_point_count.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")

        self.point_list_frame = ctk.CTkScrollableFrame(
            panel,
            width=250,
            fg_color=self.COLOR_PANEL_ALT,
            border_width=1,
            border_color=self.COLOR_BORDER,
            corner_radius=0,
        )
        self.point_list_frame.grid(row=2, column=0, padx=12, pady=8, sticky="nsew")
        self.point_list_frame.grid_columnconfigure(0, weight=1)

        self.lbl_selected_point_details = ctk.CTkLabel(
            panel,
            text="Auswahl: -",
            text_color=self.COLOR_TEXT,
            justify="left",
            anchor="w",
            wraplength=250,
        )
        self.lbl_selected_point_details.grid(row=3, column=0, padx=12, pady=(6, 12), sticky="ew")

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
        panel.grid_rowconfigure(5, weight=1)
        panel.configure(width=310)
        panel.grid_propagate(False)

        # Kein uebergeordneter Status-Titel: Komponenten/System/Lasertracker
        # sind in dieser Operator-Oberflaeche die sichtbaren Hauptueberschriften.
        status_frame = ctk.CTkFrame(panel, fg_color=self.COLOR_PANEL, corner_radius=0)
        status_frame.grid(row=0, column=0, padx=12, pady=(8, 6), sticky="ew")
        status_frame.grid_columnconfigure(0, weight=1)
        status_frame.grid_columnconfigure(1, weight=0, minsize=32)

        row = 0
        self._section_title(status_frame, "Komponenten", row)
        row += 1
        self._add_indicator_row(status_frame, row, "xyz", "XYZ")
        row += 1
        self._add_indicator_row(status_frame, row, "tracker", "Tracker")
        row += 1
        self._add_indicator_row(status_frame, row, "drehmotor", "Drehmotor")
        row += 1
        self._add_indicator_row(status_frame, row, "gyro", "Gyro")
        row += 1

        self._section_title(status_frame, "System", row)
        row += 1
        self._add_indicator_row(status_frame, row, "homing", "Homing")
        row += 1
        self._add_indicator_row(status_frame, row, "trafo", "Trafo")
        row += 1
        self._add_indicator_row(status_frame, row, "arn", "Reflektornachfuehrung")
        row += 1
        self._add_indicator_row(status_frame, row, "trackerdaten", "Trackerdaten")
        row += 1

        self._section_title(status_frame, "Lasertracker", row)
        row += 1

        tracker_values_frame = ctk.CTkFrame(
            status_frame,
            fg_color=self.COLOR_PANEL,
            corner_radius=0,
        )
        tracker_values_frame.grid(
            row=row,
            column=0,
            columnspan=2,
            padx=10,
            pady=(2, 8),
            sticky="ew",
        )
        tracker_values_frame.grid_columnconfigure(0, weight=1, uniform="tracker_values")
        tracker_values_frame.grid_columnconfigure(1, weight=1, uniform="tracker_values")

        ctk.CTkLabel(
            tracker_values_frame,
            text="Station",
            text_color=self.COLOR_TEXT,
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
        ).grid(row=0, column=0, padx=(0, 8), pady=(0, 3), sticky="ew")

        ctk.CTkLabel(
            tracker_values_frame,
            text="Messung",
            text_color=self.COLOR_TEXT,
            anchor="w",
            font=ctk.CTkFont(family=FONT_FAMILY, size=13, weight="bold"),
        ).grid(row=0, column=1, padx=(8, 0), pady=(0, 3), sticky="ew")

        self.lbl_tracker_station_x = ctk.CTkLabel(
            tracker_values_frame,
            text="X=-",
            text_color=self.COLOR_TEXT,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.lbl_tracker_station_x.grid(row=1, column=0, padx=(0, 8), pady=(0, 0), sticky="ew")

        self.lbl_tracker_measurement_x = ctk.CTkLabel(
            tracker_values_frame,
            text="X=-",
            text_color=self.COLOR_TEXT,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.lbl_tracker_measurement_x.grid(row=1, column=1, padx=(8, 0), pady=(0, 0), sticky="ew")

        self.lbl_tracker_station_y = ctk.CTkLabel(
            tracker_values_frame,
            text="Y=-",
            text_color=self.COLOR_TEXT,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.lbl_tracker_station_y.grid(row=2, column=0, padx=(0, 8), pady=(0, 0), sticky="ew")

        self.lbl_tracker_measurement_y = ctk.CTkLabel(
            tracker_values_frame,
            text="Y=-",
            text_color=self.COLOR_TEXT,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.lbl_tracker_measurement_y.grid(row=2, column=1, padx=(8, 0), pady=(0, 0), sticky="ew")

        self.lbl_tracker_station_z = ctk.CTkLabel(
            tracker_values_frame,
            text="Z=-",
            text_color=self.COLOR_TEXT,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.lbl_tracker_station_z.grid(row=3, column=0, padx=(0, 8), pady=(0, 0), sticky="ew")

        self.lbl_tracker_measurement_z = ctk.CTkLabel(
            tracker_values_frame,
            text="Z=-",
            text_color=self.COLOR_TEXT,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.lbl_tracker_measurement_z.grid(row=3, column=1, padx=(8, 0), pady=(0, 0), sticky="ew")

        ctk.CTkLabel(
            panel,
            text="Log",
            text_color=self.COLOR_TEXT,
            font=ctk.CTkFont(family=FONT_FAMILY, size=15, weight="bold"),
            anchor="w",
        ).grid(row=2, column=0, padx=12, pady=(6, 4), sticky="ew")

        self.logbox = ctk.CTkTextbox(
            panel,
            wrap="word",
            width=300,
            height=180,
            fg_color="#fbfbfb",
            text_color=self.COLOR_TEXT,
            border_width=1,
            border_color=self.COLOR_BORDER,
            corner_radius=0,
        )
        self.logbox.grid(row=5, column=0, padx=12, pady=(4, 8), sticky="nsew")

        log_button_frame = tk.Frame(
            panel,
            bg=self.COLOR_PANEL,
            highlightthickness=0,
            bd=0,
        )
        log_button_frame.grid(row=6, column=0, padx=12, pady=(4, 12), sticky="ew")
        log_button_frame.grid_columnconfigure(0, weight=1, uniform="log_buttons")
        log_button_frame.grid_columnconfigure(1, weight=1, uniform="log_buttons")

        ttk.Button(
            log_button_frame,
            text="Log leeren",
            command=self.clear_log,
            style="Operator.TButton",
        ).grid(row=0, column=0, padx=0, pady=0, sticky="ew")

        ttk.Button(
            log_button_frame,
            text="Log speichern...",
            command=self.save_log_dialog,
            style="Operator.TButton",
        ).grid(row=0, column=1, padx=0, pady=0, sticky="ew")

    def _add_indicator_row(self, parent: ctk.CTkFrame, row: int, key: str, label: str) -> None:
        ctk.CTkLabel(
            parent,
            text=label,
            text_color=self.COLOR_TEXT,
            anchor="w",
            height=18,
            font=ctk.CTkFont(family=FONT_FAMILY, size=13),
        ).grid(row=row, column=0, padx=(10, 12), pady=(0, 0), sticky="w")

        indicator = ctk.CTkLabel(
            parent,
            text="●",
            text_color=self.COLOR_RED,
            width=22,
            height=18,
            font=ctk.CTkFont(family=FONT_FAMILY, size=22, weight="bold"),
        )
        indicator.grid(row=row, column=1, padx=(0, 10), pady=(0, 0), sticky="e")

        self.status_indicators[key] = indicator

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

        if show_xyz_connect_dialog_classic is None:
            messagebox.showerror(
                "XYZ",
                "Klassischer XYZ-Connect-Dialog ist nicht verfügbar.",
                parent=self,
            )
            self.set_current_action("Fehler: XYZ-Connect-Dialog nicht verfügbar.")
            return

        selected_port = show_xyz_connect_dialog_classic(
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

        if show_xyz_manual_move_dialog_classic is None:
            messagebox.showerror(
                "XYZ",
                "Klassischer XYZ-Bewegungsdialog ist nicht verfügbar.",
                parent=self,
            )
            self.set_current_action("Fehler: XYZ-Bewegungsdialog nicht verfügbar.")
            return

        show_xyz_manual_move_dialog_classic(
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
                self.current_lt_measurement_xyz = (float(x), float(y), float(z))
            elif not data_valid:
                self.current_lt_measurement_xyz = None

            self.update_status()

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

    def load_tracker_position_dialog(self) -> None:
        self.set_current_action("Trackerstation wird geladen...")
        file_path = filedialog.askopenfilename(
            title="Trackerposition aus Datei laden",
            filetypes=[
                ("Textdateien", "*.txt *.csv"),
                ("Alle Dateien", "*.*"),
            ],
        )
        if not file_path:
            self.set_current_action("Bereit.")
            return

        try:
            x, y, z = self._read_tracker_xyz_from_file(Path(file_path))
        except Exception as exc:
            self.log(f"Trackerposition konnte nicht geladen werden: {exc}")
            messagebox.showerror("Trackerposition", str(exc), parent=self)
            self.set_current_action("Trackerstation konnte nicht geladen werden.")
            return

        self.tracker_station_xyz = (x, y, z)
        self.map_view.set_tracker_position((x, y))
        self.log(f"Trackerstation geladen: X={x:.3f}, Y={y:.3f}, Z={z:.3f} aus {file_path}")
        self.set_current_action("Trackerstation geladen.")
        self.update_status()

    @staticmethod
    def _read_tracker_xyz_from_file(path: Path) -> tuple[float, float, float]:
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            raw = line.strip()
            if not raw or raw.startswith("#"):
                continue
            parts = raw.replace(",", " ").replace(";", " ").replace("\t", " ").split()
            numeric_values: list[float] = []
            for part in parts:
                try:
                    numeric_values.append(float(part))
                except ValueError:
                    continue
            if len(numeric_values) >= 3:
                return numeric_values[0], numeric_values[1], numeric_values[2]
            if len(numeric_values) >= 2:
                return numeric_values[0], numeric_values[1], 0.0
            raise ValueError(f"Zeile {line_number}: keine X/Y/Z-Koordinaten gefunden.")
        raise ValueError("Datei enthaelt keine Trackerposition.")

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

    def connect_gyro(self) -> None:
        self.set_current_action("Gyro wird verbunden...")
        self.gyro_ready = True
        self.gyems_connected = True
        self.log("Gyro verbunden. Hinweis: In dieser Erstversion als Status gesetzt.")
        self.set_current_action("Gyro verbunden.")
        self.update_status()

    def disconnect_gyro(self) -> None:
        self.set_current_action("Gyro wird getrennt...")
        self.gyro_ready = False
        self.gyems_connected = False
        self.log("Gyro getrennt.")
        self.set_current_action("Gyro getrennt.")
        self.update_status()

    def show_gyro_status(self) -> None:
        self.log(f"Gyro Status: {'bereit' if self.gyro_ready else 'nicht bereit'}")

    # --------------------------------------------------
    # System
    # --------------------------------------------------

    def start_transformation(self) -> None:
        self.set_current_action("Transformation wird durchgefuehrt...")

        if show_trafo_dialog is not None and self.trafo_manager is not None:
            # Die echte Integration haengt von den im Hauptprogramm vorhandenen
            # Worker-/Receiver-Objekten ab. Falls diese noch nicht gesetzt sind,
            # bleibt diese Version im ersten Durchgang beim Status-Placeholder.
            try:
                if self.xyz_worker is not None and self.tracker_receiver is not None:
                    show_trafo_dialog(
                        parent=self,
                        xyz_worker=self.xyz_worker,
                        tracker_receiver=self.tracker_receiver,
                        trafo_manager=self.trafo_manager,
                        on_finished=self.on_trafo_finished,
                        log=self.log,
                    )
                    return
            except TypeError:
                # Falls die Dialogsignatur im Projekt leicht anders ist.
                pass
            except Exception as exc:
                self.log(f"Trafo-Dialog konnte nicht gestartet werden: {exc}")

        self.trafo_valid = True
        self.log("Transformation gestartet. Hinweis: In dieser Erstversion als Status auf gueltig gesetzt.")
        self.set_current_action("Transformation erfolgreich.")
        self.update_status()

    def on_trafo_finished(self) -> None:
        if self.trafo_manager is not None:
            self.trafo_valid = bool(getattr(self.trafo_manager, "valid", False))
        self.set_current_action("Transformation abgeschlossen.")
        self.update_status()

    def offset_calibration(self) -> None:
        self.set_current_action("Marker-/Reflektoroffset-Kalibrierung angefordert...")
        self.log("Marker-/Reflektoroffset kalibrieren: wird spaeter integriert.")

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
        self.map_view.set_points(self.points, keep_view=keep_map_view)
        self._update_selected_label()
        self.lbl_point_count.configure(text=f"{len(self.points)} Punkte")

    def _update_point_list(self) -> None:
        for child in self.point_list_frame.winfo_children():
            child.destroy()

        for row, point in enumerate(self.points):
            text = f"{point.name:<10}  {point.status_text}"
            if point.reachable and not point.marked:
                text += "  *"

            is_selected = point.name == self.selected_point_name
            button = ctk.CTkButton(
                self.point_list_frame,
                text=text,
                anchor="w",
                fg_color="#d9eaff" if is_selected else "#eeeeee",
                hover_color="#c7ddf6",
                text_color=self.COLOR_TEXT,
                border_width=1,
                border_color="#b8b8b8",
                corner_radius=0,
                command=lambda name=point.name: self.select_point_by_name(name),
            )
            button.grid(row=row, column=0, padx=4, pady=3, sticky="ew")

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
            self.lbl_selected_point_details.configure(text="Auswahl: -")
            return

        if self.lbl_selected_point is not None:
            self.lbl_selected_point.configure(text=f"Auswahl: {point.name} | {point.status_text}")
        self.lbl_selected_point_details.configure(
            text=(
                f"Auswahl:\n"
                f"{point.name}\n"
                f"{point.xyz_text()}\n"
                f"Status: {point.status_text}\n"
                f"Erreichbar: {'ja' if point.reachable else 'nein'}"
            )
        )

    # --------------------------------------------------
    # Demo scene / reachability placeholder
    # --------------------------------------------------

    def _apply_demo_scene(self) -> None:
        if not self.points:
            self.map_view.set_tracker_position(None)
            self.map_view.set_robot_workspace_polygon(None)
            return

        min_x = min(point.x for point in self.points)
        max_x = max(point.x for point in self.points)
        min_y = min(point.y for point in self.points)
        max_y = max(point.y for point in self.points)

        if self.tracker_station_xyz is None:
            tracker_xy = (min_x - 180.0, min_y - 120.0)
            self.map_view.set_tracker_position(tracker_xy)
        else:
            self.map_view.set_tracker_position((self.tracker_station_xyz[0], self.tracker_station_xyz[1]))

        center_x = (min_x + max_x) / 2.0
        center_y = (min_y + max_y) / 2.0
        half_w = self._config_float("xyz", "x_max", 500.0) / 2.0
        half_h = self._config_float("xyz", "y_max", 400.0) / 2.0

        workspace_polygon = [
            (center_x - half_w, center_y - half_h),
            (center_x + half_w, center_y - half_h),
            (center_x + half_w, center_y + half_h),
            (center_x - half_w, center_y + half_h),
        ]
        self.map_view.set_robot_workspace_polygon(workspace_polygon)

        for point in self.points:
            point.reachable = self._point_in_polygon((point.x, point.y), workspace_polygon)

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
        self._set_indicator("xyz", self.xyz_ready, "bereit", "nicht bereit")
        self._set_indicator("tracker", self.tracker_ready, "bereit", "nicht bereit")
        self._set_indicator("drehmotor", self.drehmotor_ready, "bereit", "nicht bereit")
        self._set_indicator("gyro", self.gyro_ready, "bereit", "nicht bereit")

        self._set_indicator("homing", self.homing_done, "referenziert", "nicht referenziert")
        self._set_indicator("trafo", self.trafo_valid, "gueltig", "ungueltig")
        self._set_indicator("arn", self.arn_active, "aktiv", "inaktiv")
        self._set_indicator("trackerdaten", self.tracker_data_current, "aktuell", "keine aktuellen Daten")

        station_x, station_y, station_z = self._format_xyz_components(self.tracker_station_xyz)
        measurement_x, measurement_y, measurement_z = self._format_xyz_components(self.current_lt_measurement_xyz)

        self.lbl_tracker_station_x.configure(text=station_x)
        self.lbl_tracker_station_y.configure(text=station_y)
        self.lbl_tracker_station_z.configure(text=station_z)

        self.lbl_tracker_measurement_x.configure(text=measurement_x)
        self.lbl_tracker_measurement_y.configure(text=measurement_y)
        self.lbl_tracker_measurement_z.configure(text=measurement_z)

    def _set_indicator(self, key: str, active: bool, active_text: str, inactive_text: str) -> None:
        indicator = self.status_indicators[key]
        indicator.configure(text_color=self.COLOR_GREEN if active else self.COLOR_RED)

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

    def _format_config_text(self) -> str:
        if CONFIG is None:
            return "Config: nicht geladen"
        return (
            "Config:\n"
            f"  XYZ: {CONFIG.xyz.port} @ {CONFIG.xyz.baudrate}\n"
            f"  Tracker UDP: {CONFIG.tracker.udp_port}\n"
            f"  Workspace X/Y/Z:\n"
            f"    X {CONFIG.xyz.x_min:.0f}..{CONFIG.xyz.x_max:.0f}\n"
            f"    Y {CONFIG.xyz.y_min:.0f}..{CONFIG.xyz.y_max:.0f}\n"
            f"    Z {CONFIG.xyz.z_min:.0f}..{CONFIG.xyz.z_max:.0f}\n"
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
        self.logbox.insert("end", line + "\n")
        self.logbox.see("end")
        try:
            with self.log_file_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def clear_log(self) -> None:
        self.logbox.delete("1.0", "end")
        self.set_current_action("Log geleert.")

    def save_log_dialog(self) -> None:
        content = self.logbox.get("1.0", "end-1c")
        if not content.strip():
            messagebox.showinfo("Log speichern", "Das Log ist leer.", parent=self)
            return

        default_name = f"mower_operator_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        file_path = filedialog.asksaveasfilename(
            title="Log speichern",
            defaultextension=".txt",
            initialfile=default_name,
            filetypes=[
                ("Textdateien", "*.txt"),
                ("Logdateien", "*.log"),
                ("Alle Dateien", "*.*"),
            ],
        )
        if not file_path:
            return

        try:
            Path(file_path).write_text(content + "\n", encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Log speichern", f"Log konnte nicht gespeichert werden:\n{exc}", parent=self)
            self.set_current_action("Fehler beim Speichern des Logs.")
            return

        self.log(f"Log gespeichert: {file_path}")
        self.set_current_action("Log gespeichert.")


if __name__ == "__main__":
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")

    app = MowerOperatorApp()
    app.mainloop()

# App/mower_main_app.py

from __future__ import annotations

import json
import os
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any
from tkinter import filedialog, messagebox, simpledialog

import numpy as np

import customtkinter as ctk

from Lasertracker.lasertracker_receiver import LasertrackerReceiver
from Lasertracker.lasertracker_state import LasertrackerState
from XYZ_Robot.xyz_robot_state import XYZRobotState
from XYZ_Robot.xyz_robot_worker import XYZRobotWorker

from App.dialogs.xyz_manual_move_dialog import show_xyz_manual_move_dialog
from App.dialogs.xyz_connect_dialog import show_xyz_connect_dialog

from App.widgets.menu_band import MenuBand

from App.services.project_io import write_project_file

from Transformation.trafo_manager import TrafoManager
from Transformation.coordinate_mapper import CoordinateMapper, RobotWorkspace
from App.dialogs.trafo_dialog import show_trafo_dialog

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

try:
    from config.mower_config import CONFIG
except Exception:
    CONFIG = None

from App.map_view import MapView
from App.stakeout_point import StakeoutPoint, create_demo_points, load_points_from_txt


class MowerMainApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Mower II - Hauptprogramm")
        self.geometry("1450x850")

        self.points: list[StakeoutPoint] = []
        self.selected_point_name: str | None = None

        self.project_path: Path | None = None

        logs_dir = PROJECT_ROOT / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file_path = logs_dir / f"mower_main_{timestamp}.log"

        # --------------------------------------------------
        # Hardware / Systemstatus
        # --------------------------------------------------

        self.xyz_state = XYZRobotState()
        self.tracker_state: LasertrackerState | None = None

        self.xyz_worker = XYZRobotWorker(
            on_event=self.on_xyz_event,
            on_state_changed=self.on_xyz_state_changed,
        )
        self.xyz_worker.start()

        self.tracker_receiver: LasertrackerReceiver | None = None

        self.trafo_valid = False

        # Noch Placeholder
        self.skr_connected = False
        self.gyems_connected = False
        self.arn_active = False

        self.tracker_station_xy: tuple[float, float] | None = None

        self._build_ui()
        self.load_demo_points()
        self.update_status()
        self.after(500, self.update_status_periodic)

        self.trafo_manager = TrafoManager()

        self.workspace = RobotWorkspace(
            x_min=CONFIG.xyz.x_min,
            x_max=CONFIG.xyz.x_max,
            y_min=CONFIG.xyz.y_min,
            y_max=CONFIG.xyz.y_max,
        )

        self.mapper = CoordinateMapper(
            trafo_manager=self.trafo_manager,
            workspace=self.workspace,
        )

    # --------------------------------------------------
    # UI
    # --------------------------------------------------

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)

        self._build_menu_band()
        self._build_main_area()
        self._build_status_bar()

    def _create_menu_definitions(self):
        return [
            (
                "Datei",
                [
                    ("command", "Punkte laden...", self.load_points_dialog),
                    ("separator", "", None),
                    ("command", "Projekt speichern", self.save_project),
                    ("command", "Projekt speichern unter...", self.save_project_as),
                    ("separator", "", None),
                    ("command", "Log oeffnen", self.open_log_file),
                    ("separator", "", None),
                    ("command", "Beenden", self.on_close),
                ],
            ),
            (
                "XYZ",
                [
                    ("command", "Verbinden", self.connect_xyz_placeholder),
                    ("command", "Trennen", self.disconnect_xyz_placeholder),
                    ("separator", "", None),
                    ("command", "Homing", self.homing_placeholder),
                    ("command", "Fahre zu Position...", self.move_xyz_to_position_dialog),
                    ("separator", "", None),
                    ("command", "Stop", self.stop_placeholder),
                ],
            ),
            (
                "Tracker",
                [
                    ("command", "UDP-Empfang starten", self.start_tracker_placeholder),
                    ("command", "UDP-Empfang stoppen", self.stop_tracker_placeholder),
                    ("separator", "", None),
                    ("command", "Trackerposition aus Datei laden...", self.load_tracker_position_dialog),
                    ("separator", "", None),
                    ("command", "Status anzeigen", self.show_tracker_status),
                ],
            ),
            (
                "SKR",
                [
                    ("command", "Verbinden", self.connect_skr_placeholder),
                    ("command", "Trennen", self.disconnect_skr_placeholder),
                    ("separator", "", None),
                    ("command", "Status anzeigen", self.show_skr_status),
                ],
            ),
            (
                "GYEMS",
                [
                    ("command", "Verbinden", self.connect_gyems_placeholder),
                    ("command", "Trennen", self.disconnect_gyems_placeholder),
                    ("separator", "", None),
                    ("command", "Nullstellung / Referenz setzen", self.gyems_set_reference_placeholder),
                    ("separator", "", None),
                    ("command", "Status anzeigen", self.show_gyems_status),
                ],
            ),
            (
                "Mower / System",
                [
                    ("command", "Transformation starten", self.trafo_placeholder),
                    ("command", "Marker-/Reflektoroffset kalibrieren", self.offset_calibration_placeholder),
                    ("separator", "", None),
                    ("command", "ARN aktivieren", self.activate_arn_placeholder),
                    ("command", "ARN deaktivieren", self.deactivate_arn_placeholder),
                    ("separator", "", None),
                    ("command", "Aktive Config anzeigen", self.show_active_config),
                    ("command", "Config neu laden", self.reload_config_placeholder),
                ],
            ),
        ]

    def _build_menu_band(self) -> None:
        self.menu_band = MenuBand(
            self,
            menu_definitions=self._create_menu_definitions(),
        )
        self.menu_band.grid(row=0, column=0, sticky="ew")


    def _build_main_area(self) -> None:
        main = ctk.CTkFrame(self)
        main.grid(row=1, column=0, padx=12, pady=(8, 8), sticky="nsew")

        main.grid_columnconfigure(0, weight=0)
        main.grid_columnconfigure(1, weight=1)
        main.grid_columnconfigure(2, weight=0)
        main.grid_rowconfigure(0, weight=1)

        self._build_point_list_panel(main)
        self._build_map_panel(main)
        self._build_status_log_panel(main)

    def _build_status_bar(self) -> None:
        self.lbl_status_bar = ctk.CTkLabel(
            self,
            text="",
            anchor="w",
            justify="left",
        )
        self.lbl_status_bar.grid(row=2, column=0, padx=12, pady=(0, 10), sticky="ew")

    def _build_point_list_panel(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, width=280)
        panel.grid(row=0, column=0, padx=(10, 6), pady=10, sticky="nsew")
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            panel,
            text="Punktliste",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=12, pady=(12, 4), sticky="w")

        self.lbl_point_count = ctk.CTkLabel(panel, text="0 Punkte")
        self.lbl_point_count.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="w")

        self.point_list_frame = ctk.CTkScrollableFrame(panel, width=250)
        self.point_list_frame.grid(row=2, column=0, padx=12, pady=8, sticky="nsew")
        self.point_list_frame.grid_columnconfigure(0, weight=1)

        self.lbl_selected_point_details = ctk.CTkLabel(
            panel,
            text="Auswahl: -",
            justify="left",
            anchor="w",
            wraplength=250,
        )
        self.lbl_selected_point_details.grid(row=3, column=0, padx=12, pady=(6, 12), sticky="ew")

    def _build_map_panel(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent)
        panel.grid(row=0, column=1, padx=6, pady=10, sticky="nsew")
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(panel)
        header.grid(row=0, column=0, padx=10, pady=(10, 4), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="2D-Draufsicht LT-System",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=8, pady=8, sticky="w")

        self.lbl_selected_point = ctk.CTkLabel(header, text="Auswahl: -")
        self.lbl_selected_point.grid(row=0, column=1, padx=8, pady=8, sticky="e")

        self.map_view = MapView(panel, on_point_selected=self.select_point_by_name)
        self.map_view.grid(row=1, column=0, padx=10, pady=(4, 10), sticky="nsew")

    def _build_status_log_panel(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, width=380)
        panel.grid(row=0, column=2, padx=(6, 10), pady=10, sticky="nsew")
        panel.grid_rowconfigure(1, weight=0)
        panel.grid_rowconfigure(3, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            panel,
            text="Status",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=12, pady=(12, 4), sticky="w")

        self.lbl_status = ctk.CTkLabel(
            panel,
            text=self._format_status_text(),
            justify="left",
            anchor="w",
        )
        self.lbl_status.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")

        ctk.CTkLabel(
            panel,
            text="Log",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=2, column=0, padx=12, pady=(8, 4), sticky="w")

        self.logbox = ctk.CTkTextbox(panel, wrap="word", width=350)
        self.logbox.grid(row=3, column=0, padx=12, pady=(4, 8), sticky="nsew")

        ctk.CTkButton(panel, text="Log loeschen", command=self.clear_log).grid(
            row=4, column=0, padx=12, pady=(4, 12), sticky="ew"
        )

    # --------------------------------------------------
    # Hardware callbacks
    # --------------------------------------------------

    def on_xyz_event(self, event) -> None:
        try:
            text = f"[{event.component}] [{event.level.name}] {event.message}"
        except Exception:
            text = str(event)

        self.after(0, lambda: self.log(text))

    def on_xyz_state_changed(self, state: XYZRobotState) -> None:
        self.xyz_state = state

    def on_tracker_state_changed(self, state: LasertrackerState) -> None:
        self.tracker_state = state

    def on_tracker_log(self, text: str) -> None:
        self.after(0, lambda: self.log(f"[Tracker] {text}"))

    def on_tracker_error(self, text: str) -> None:
        self.after(0, lambda: self.log(f"[Tracker ERROR] {text}"))

    def update_status_periodic(self) -> None:
        self.update_status()
        self.after(500, self.update_status_periodic)

    # --------------------------------------------------
    # Datei
    # --------------------------------------------------

    def _build_project_status(self) -> dict[str, Any]:
        tracker_started = (
                self.tracker_receiver is not None
                and self.tracker_receiver.running
        )

        return {
            "xyz_connected": self.xyz_state.connected,
            "xyz_homed": self.xyz_state.homed,
            "tracker_started": tracker_started,
            "trafo_valid": self.trafo_valid,
            "skr_connected": self.skr_connected,
            "gyems_connected": self.gyems_connected,
            "arn_active": self.arn_active,
        }

    def load_points_dialog(self) -> None:
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
            return

        try:
            self.points = load_points_from_txt(file_path)
        except Exception as exc:
            self.log(f"FEHLER beim Laden der Punktdatei: {exc}")
            messagebox.showerror("Punktdatei", str(exc))
            return

        self.selected_point_name = self.points[0].name if self.points else None
        self._apply_demo_scene()
        self.refresh_points()
        self.log(f"Punktdatei geladen: {file_path}")

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
        write_project_file(
            path=path,
            points=self.points,
            status=self._build_project_status(),
        )

        self.log(f"Projekt gespeichert: {path}")

    def open_log_file(self) -> None:
        self.log("Logdatei wird geoeffnet.")

        try:
            if hasattr(os, "startfile"):
                os.startfile(self.log_file_path)  # type: ignore[attr-defined]
            else:
                webbrowser.open(self.log_file_path.as_uri())
        except Exception as exc:
            self.log(f"Logdatei konnte nicht geoeffnet werden: {exc}")
            messagebox.showerror("Log oeffnen", str(exc))

    def on_close(self) -> None:
        if hasattr(self, "menu_band"):
            self.menu_band.close_dropdown()

        try:
            if self.tracker_receiver is not None:
                self.tracker_receiver.stop()

            if hasattr(self, "xyz_worker") and self.xyz_worker is not None:
                self.xyz_worker.stop()

        finally:
            self.destroy()

    # --------------------------------------------------
    # XYZ
    # --------------------------------------------------

    def center_toplevel(
            self,
            window: ctk.CTkToplevel,
            width: int,
            height: int,
    ) -> None:
        self.update_idletasks()

        parent_x = self.winfo_rootx()
        parent_y = self.winfo_rooty()
        parent_w = self.winfo_width()
        parent_h = self.winfo_height()

        x = parent_x + max(0, (parent_w - width) // 2)
        y = parent_y + max(0, (parent_h - height) // 2)

        window.geometry(f"{width}x{height}+{x}+{y}")


    def connect_xyz_with_port(self, port: str) -> None:
        if CONFIG is None:
            self.log("XYZ verbinden nicht möglich: Config nicht geladen.")
            return

        if self.xyz_state.connected:
            self.log("XYZ ist bereits verbunden.")
            return

        port = port.strip()

        if not port:
            self.log("XYZ verbinden nicht möglich: Kein Port gewählt.")
            return

        self.log(f"Verbinde XYZ: {port} @ {CONFIG.xyz.baudrate}")

        self.xyz_worker.send_command(
            "connect",
            port=port,
            baudrate=CONFIG.xyz.baudrate,
        )


    def connect_xyz_placeholder(self) -> None:
        if CONFIG is None:
            self.log("XYZ verbinden nicht möglich: Config nicht geladen.")
            return

        if self.xyz_state.connected:
            self.log("XYZ ist bereits verbunden.")
            return

        port = show_xyz_connect_dialog(
            parent=self,
            default_port=CONFIG.xyz.port,
            baudrate=CONFIG.xyz.baudrate,
            log=self.log,
        )

        if port:
            self.connect_xyz_with_port(port)

    def disconnect_xyz_placeholder(self) -> None:
        if not self.xyz_state.connected:
            self.log("XYZ ist bereits getrennt.")
            return

        self.log("Trenne XYZ...")
        self.xyz_worker.send_command("disconnect")

    def homing_placeholder(self) -> None:
        if not self.xyz_state.connected:
            self.log("Homing nicht möglich: XYZ ist nicht verbunden.")
            return

        self.log("Starte Homing...")
        self.xyz_worker.send_command("home_all")

    def move_xyz_to_position_dialog(self) -> None:
        show_xyz_manual_move_dialog(
            parent=self,
            config=CONFIG,
            xyz_worker=self.xyz_worker,
            xyz_state_getter=lambda: self.xyz_state,
            log=self.log,
        )

    def stop_placeholder(self) -> None:
        self.log("XYZ Stop: aktuell noch nicht als Worker-Befehl implementiert.")

    # --------------------------------------------------
    # Tracker
    # --------------------------------------------------

    def start_tracker_placeholder(self) -> None:
        if CONFIG is None:
            self.log("Tracker starten nicht möglich: Config nicht geladen.")
            return

        if self.tracker_receiver is not None and self.tracker_receiver.running:
            self.log("Tracker UDP-Empfang läuft bereits.")
            return

        self.log(f"Starte Tracker UDP-Empfang auf Port {CONFIG.tracker.udp_port}...")

        self.tracker_receiver = LasertrackerReceiver(
            port=CONFIG.tracker.udp_port,
            on_state_changed=self.on_tracker_state_changed,
            on_log=self.on_tracker_log,
            on_error=self.on_tracker_error,
        )

        self.tracker_receiver.start()

    def stop_tracker_placeholder(self) -> None:
        if self.tracker_receiver is None:
            self.log("Tracker UDP-Empfang ist nicht gestartet.")
            return

        self.log("Stoppe Tracker UDP-Empfang...")
        self.tracker_receiver.stop()
        self.tracker_receiver = None
        self.tracker_state = None
        self.update_status()

    def load_tracker_position_dialog(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Trackerposition aus Datei laden",
            filetypes=[
                ("Textdateien", "*.txt *.csv"),
                ("Alle Dateien", "*.*"),
            ],
        )

        if not file_path:
            return

        try:
            x, y = self._read_tracker_xy_from_file(Path(file_path))
        except Exception as exc:
            self.log(f"Trackerposition konnte nicht geladen werden: {exc}")
            messagebox.showerror("Trackerposition", str(exc))
            return

        self.tracker_station_xy = (x, y)
        self.map_view.set_tracker_position(self.tracker_station_xy)
        self.log(f"Trackerposition geladen: X={x:.3f}, Y={y:.3f} aus {file_path}")

    @staticmethod
    def _read_tracker_xy_from_file(path: Path) -> tuple[float, float]:
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

            if len(numeric_values) >= 2:
                return numeric_values[0], numeric_values[1]

            raise ValueError(f"Zeile {line_number}: keine X/Y-Koordinaten gefunden.")

        raise ValueError("Datei enthaelt keine Trackerposition.")

    def show_tracker_status(self) -> None:
        if self.tracker_receiver is None:
            self.log("Tracker Status: UDP-Empfang nicht gestartet.")
            return

        if self.tracker_state is None:
            self.log("Tracker Status: UDP-Empfang gestartet, aber noch keine Zustandsdaten.")
            return

        self.log(
            "Tracker Status: "
            f"receiving={self.tracker_state.receiving}, "
            f"stable={self.tracker_state.stable}, "
            f"stale={self.tracker_state.stale}"
        )

    # --------------------------------------------------
    # SKR / GYEMS / System
    # --------------------------------------------------

    def connect_skr_placeholder(self) -> None:
        self.skr_connected = True
        self.log("SKR verbinden: Placeholder aktiv. Status auf verbunden gesetzt.")
        self.update_status()

    def disconnect_skr_placeholder(self) -> None:
        self.skr_connected = False
        self.log("SKR trennen: Placeholder aktiv. Status auf nicht verbunden gesetzt.")
        self.update_status()

    def show_skr_status(self) -> None:
        self.log(f"SKR Status: {'verbunden' if self.skr_connected else 'nicht verbunden'}")

    def connect_gyems_placeholder(self) -> None:
        self.gyems_connected = True
        self.log("GYEMS verbinden: Placeholder aktiv. Status auf verbunden gesetzt.")
        self.update_status()

    def disconnect_gyems_placeholder(self) -> None:
        self.gyems_connected = False
        self.log("GYEMS trennen: Placeholder aktiv. Status auf nicht verbunden gesetzt.")
        self.update_status()

    def gyems_set_reference_placeholder(self) -> None:
        self.log("GYEMS Nullstellung / Referenz setzen: noch nicht implementiert.")

    def show_gyems_status(self) -> None:
        self.log(f"GYEMS Status: {'verbunden' if self.gyems_connected else 'nicht verbunden'}")

    def trafo_placeholder(self) -> None:
        if self.tracker_receiver is None or not self.tracker_receiver.running:
            self.log("Transformation nicht möglich: Tracker UDP-Empfang ist nicht gestartet.")
            messagebox.showwarning(
                "Transformation",
                "Tracker UDP-Empfang ist nicht gestartet.",
                parent=self,
            )
            return

        if not self.xyz_state.connected:
            self.log("Transformation nicht möglich: XYZ ist nicht verbunden.")
            messagebox.showwarning(
                "Transformation",
                "XYZ ist nicht verbunden.",
                parent=self,
            )
            return

        show_trafo_dialog(
            parent=self,
            xyz_worker=self.xyz_worker,
            tracker_receiver=self.tracker_receiver,
            xyz_state_getter=lambda: self.xyz_state,
            trafo_manager=self.trafo_manager,
            on_finished=self.on_trafo_finished,
            log=self.log,
        )

    def on_trafo_finished(self) -> None:
        self.trafo_valid = self.trafo_manager.valid

        if self.trafo_manager.valid:
            self.log("Aktive Transformation wurde übernommen.")
            self.update_workspace_from_trafo()
        else:
            self.log("Keine gültige Transformation aktiv.")

        self.update_status()

    def update_workspace_from_trafo(self) -> None:
        """
        Aktualisiert die Arbeitsraumdarstellung in der 2D-Karte.

        Dargestellt wird der Bewegungsbereich des oberen Reflektors im LT-System,
        wenn der Marker/Stift den Roboterarbeitsraum abfährt.

        Grundlage:
            marker_corner_robot
            reflector_corner_robot = marker_corner_robot + marker_to_reflector_robot
            reflector_corner_lt = trafo.robot_to_tracker(reflector_corner_robot)
        """

        if CONFIG is None:
            self.log("Arbeitsraum kann nicht aktualisiert werden: Config nicht geladen.")
            return

        if not self.trafo_manager.valid:
            self.log("Arbeitsraum kann nicht aktualisiert werden: Keine gültige Trafo.")
            return

        trafo = self.trafo_manager.active_trafo

        if trafo is None:
            self.log("Arbeitsraum kann nicht aktualisiert werden: Trafo ist None.")
            return

        marker_to_reflector_robot = np.asarray(
            CONFIG.transformation.marker_to_reflector_robot,
            dtype=float,
        )

        # Referenz-Z für die Arbeitsraumdarstellung.
        # Aktuell nehmen wir z_min als Marker-/Arbeits-Z.
        # Später besser: eigener Config-Wert, z. B. CONFIG.marker.z_mark.
        z_marker = float(CONFIG.xyz.z_min)

        marker_corners_robot = [
            np.array([CONFIG.xyz.x_min, CONFIG.xyz.y_min, z_marker], dtype=float),
            np.array([CONFIG.xyz.x_max, CONFIG.xyz.y_min, z_marker], dtype=float),
            np.array([CONFIG.xyz.x_max, CONFIG.xyz.y_max, z_marker], dtype=float),
            np.array([CONFIG.xyz.x_min, CONFIG.xyz.y_max, z_marker], dtype=float),
        ]

        workspace_polygon_lt: list[tuple[float, float]] = []

        for marker_corner_robot in marker_corners_robot:
            reflector_corner_robot = marker_corner_robot + marker_to_reflector_robot
            reflector_corner_lt = trafo.robot_to_tracker(reflector_corner_robot)

            workspace_polygon_lt.append(
                (
                    float(reflector_corner_lt[0]),
                    float(reflector_corner_lt[1]),
                )
            )

        self.map_view.set_robot_workspace_polygon(workspace_polygon_lt)

        self.log("Arbeitsraum aus aktiver Trafo aktualisiert:")
        for i, (x, y) in enumerate(workspace_polygon_lt, start=1):
            self.log(f"  Ecke {i}: LT X={x:.3f}, Y={y:.3f}")

        # Vorerst weiter einfache Polygon-Prüfung.
        # Später ersetzen wir das durch CoordinateMapper.tracker_xy_to_robot_target().
        for point in self.points:
            point.reachable = self._point_in_polygon(
                (point.x, point.y),
                workspace_polygon_lt,
            )

        self.refresh_points(keep_map_view=True)

    def offset_calibration_placeholder(self) -> None:
        self.log("Marker-/Reflektoroffset kalibrieren: wird spaeter integriert.")

    def activate_arn_placeholder(self) -> None:
        self.arn_active = True
        self.log("ARN aktivieren: Placeholder aktiv. ARN ist aktiv.")
        self.update_status()

    def deactivate_arn_placeholder(self) -> None:
        self.arn_active = False
        self.log("ARN deaktivieren: Placeholder aktiv. ARN ist inaktiv.")
        self.update_status()

    def show_active_config(self) -> None:
        if CONFIG is None:
            message = "Config konnte nicht geladen werden."
        else:
            message = self._format_config_text()

        self.log("Aktive Config angezeigt.")
        messagebox.showinfo("Aktive Config", message)

    def reload_config_placeholder(self) -> None:
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

            button = ctk.CTkButton(
                self.point_list_frame,
                text=text,
                anchor="w",
                command=lambda name=point.name: self.select_point_by_name(name),
            )
            button.grid(row=row, column=0, padx=4, pady=3, sticky="ew")

    def select_point_by_name(self, name: str) -> None:
        if not any(point.name == name for point in self.points):
            return

        self.selected_point_name = name
        self.refresh_points(keep_map_view=True)

    def selected_point(self) -> StakeoutPoint | None:
        for point in self.points:
            if point.name == self.selected_point_name:
                return point

        return None

    def _update_selected_label(self) -> None:
        point = self.selected_point()

        if point is None:
            self.lbl_selected_point.configure(text="Auswahl: -")
            self.lbl_selected_point_details.configure(text="Auswahl: -")
            return

        self.lbl_selected_point.configure(
            text=f"Auswahl: {point.name} | {point.status_text}"
        )
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

        if self.tracker_station_xy is None:
            tracker_position = (0, 0)
            self.map_view.set_tracker_position(tracker_position)
        else:
            self.map_view.set_tracker_position(self.tracker_station_xy)

        # Demo-Arbeitsbereich: spaeter wird dieses Polygon aus Trafo + Workspace berechnet.
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
    # Status / log
    # --------------------------------------------------


    def update_status(self) -> None:
        self.lbl_status.configure(text=self._format_status_text())
        self.lbl_status_bar.configure(text=self._format_status_bar_text())

    def _format_status_text(self) -> str:
        xyz_connected = self.xyz_state.connected
        xyz_homed = self.xyz_state.homed
        xyz_busy = self.xyz_state.busy

        if self.xyz_state.x is None or self.xyz_state.y is None:
            xyz_position = "X=-, Y=-, Z=-"
        else:
            z = self.xyz_state.z if self.xyz_state.z is not None else 0.0
            xyz_position = (
                f"X={self.xyz_state.x:.3f}, "
                f"Y={self.xyz_state.y:.3f}, "
                f"Z={z:.3f}"
            )

        if self.tracker_state is None:
            tracker_text = "UDP inaktiv / keine Daten"
        else:
            tracker_text = (
                f"receiving={self.tracker_state.receiving}, "
                f"stable={self.tracker_state.stable}, "
                f"stale={self.tracker_state.stale}"
            )

        return (
            "Systemstatus:\n"
            f"  XYZ:     {'verbunden' if xyz_connected else 'nicht verbunden'}\n"
            f"           homed={xyz_homed}, busy={xyz_busy}\n"
            f"           {xyz_position}\n"
            f"  Tracker: {tracker_text}\n"
            f"  Trafo:   {'gueltig' if self.trafo_valid else 'ungueltig'}\n"
            f"  SKR:     {'verbunden' if self.skr_connected else 'nicht verbunden'}\n"
            f"  GYEMS:   {'verbunden' if self.gyems_connected else 'nicht verbunden'}\n"
            f"  ARN:     {'aktiv' if self.arn_active else 'inaktiv'}\n\n"
            f"{self._format_config_text()}"
        )

    def _format_status_bar_text(self) -> str:
        if CONFIG is None:
            config = "Config: nicht geladen"
        else:
            config = (
                f"XYZ {CONFIG.xyz.port} | "
                f"Tracker UDP {CONFIG.tracker.udp_port} | "
                f"Offset X={CONFIG.transformation.marker_to_reflector_robot[0]:.3f}, "
                f"Y={CONFIG.transformation.marker_to_reflector_robot[1]:.3f}, "
                f"Z={CONFIG.transformation.marker_to_reflector_robot[2]:.3f}"
            )

        tracker_active = (
                self.tracker_receiver is not None
                and self.tracker_receiver.running
        )

        return (
            f"XYZ: {'verbunden' if self.xyz_state.connected else '-'}   |   "
            f"Homed: {'ja' if self.xyz_state.homed else '-'}   |   "
            f"Tracker: {'aktiv' if tracker_active else '-'}   |   "
            f"SKR: {'verbunden' if self.skr_connected else '-'}   |   "
            f"GYEMS: {'verbunden' if self.gyems_connected else '-'}   |   "
            f"ARN: {'aktiv' if self.arn_active else 'inaktiv'}   |   "
            f"Trafo: {'gueltig' if self.trafo_valid else '-'}   |   "
            f"{config}"
        )

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


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = MowerMainApp()
    app.mainloop()

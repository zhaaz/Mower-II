# App/xyz_robot_demo_app.py

from __future__ import annotations

import sys
import time
from pathlib import Path
from tkinter import messagebox

from App.services.hatch_logo_generator import generate_logo_hatch_segments


import customtkinter as ctk

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

try:
    from config.mower_config import CONFIG
except Exception:
    CONFIG = None

from XYZ_Robot.xyz_robot_state import XYZRobotState
from XYZ_Robot.xyz_robot_worker import XYZRobotWorker
from XYZ_Robot.marker_shapes import MARKER_SHAPES

from App.dialogs.xyz_connect_dialog import show_xyz_connect_dialog
from App.dialogs.xyz_manual_move_dialog import show_xyz_manual_move_dialog


class XYZWorkspaceView(ctk.CTkFrame):
    def __init__(self, master, xyz_state_getter, **kwargs):
        super().__init__(master, **kwargs)

        self.xyz_state_getter = xyz_state_getter

        self.canvas = ctk.CTkCanvas(
            self,
            bg="#202020",
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)

        self.canvas.bind("<Configure>", lambda event: self.redraw())

    def redraw(self) -> None:
        self.canvas.delete("all")

        if CONFIG is None:
            self._draw_text("Config nicht geladen")
            return

        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())

        margin = 50

        x_min = CONFIG.xyz.x_min
        x_max = CONFIG.xyz.x_max
        y_min = CONFIG.xyz.y_min
        y_max = CONFIG.xyz.y_max

        workspace_w = x_max - x_min
        workspace_h = y_max - y_min

        if workspace_w <= 0 or workspace_h <= 0:
            self._draw_text("Ungueltiger Arbeitsraum")
            return

        scale_x = (width - 2 * margin) / workspace_w
        scale_y = (height - 2 * margin) / workspace_h
        scale = min(scale_x, scale_y)

        draw_w = workspace_w * scale
        draw_h = workspace_h * scale

        offset_x = (width - draw_w) / 2
        offset_y = (height - draw_h) / 2

        def world_to_screen(x: float, y: float) -> tuple[float, float]:
            sx = offset_x + (x - x_min) * scale
            sy = offset_y + draw_h - (y - y_min) * scale
            return sx, sy

        # Arbeitsraum
        sx1, sy1 = world_to_screen(x_min, y_min)
        sx2, sy2 = world_to_screen(x_max, y_max)

        self.canvas.create_rectangle(
            sx1,
            sy2,
            sx2,
            sy1,
            outline="#4aa3ff",
            width=2,
        )

        self.canvas.create_text(
            sx1,
            sy2 - 24,
            anchor="w",
            fill="#d0d0d0",
            text=(
                f"Arbeitsraum XY: "
                f"X={x_min:.0f}..{x_max:.0f} mm, "
                f"Y={y_min:.0f}..{y_max:.0f} mm"
            ),
            font=("Consolas", 11),
        )

        # Achsen / Orientierung
        self.canvas.create_text(
            sx2,
            sy1 + 18,
            anchor="e",
            fill="#909090",
            text="XY-Roboterdraufsicht",
            font=("Consolas", 11),
        )

        # Aktuelle Position
        state = self.xyz_state_getter()

        if state.x is not None and state.y is not None:
            px, py = world_to_screen(state.x, state.y)

            inside = (
                x_min <= state.x <= x_max
                and y_min <= state.y <= y_max
            )

            color = "#00ff80" if inside else "#ff6060"

            r = 7
            self.canvas.create_oval(
                px - r,
                py - r,
                px + r,
                py + r,
                fill=color,
                outline="white",
                width=1,
            )

            self.canvas.create_line(px - 14, py, px + 14, py, fill=color, width=1)
            self.canvas.create_line(px, py - 14, px, py + 14, fill=color, width=1)

            z_text = "-" if state.z is None else f"{state.z:.3f}"

            self.canvas.create_text(
                px + 12,
                py - 12,
                anchor="w",
                fill="#ffffff",
                text=(
                    f"X={state.x:.3f}\n"
                    f"Y={state.y:.3f}\n"
                    f"Z={z_text}"
                ),
                font=("Consolas", 11),
            )
        else:
            self.canvas.create_text(
                width / 2,
                height / 2,
                fill="#b0b0b0",
                text="Keine XYZ-Position verfügbar",
                font=("Consolas", 14),
            )

        # Status unten
        z_val = "-" if state.z is None else f"{state.z:.3f}"
        x_val = "-" if state.x is None else f"{state.x:.3f}"
        y_val = "-" if state.y is None else f"{state.y:.3f}"

        status = (
            f"connected={state.connected} | "
            f"homed={state.homed} | "
            f"busy={state.busy} | "
            f"X={x_val}, Y={y_val}, Z={z_val}"
        )

        self.canvas.create_text(
            margin,
            height - 24,
            anchor="w",
            fill="#d0d0d0",
            text=status,
            font=("Consolas", 11),
        )

    def _draw_text(self, text: str) -> None:
        self.canvas.delete("all")
        self.canvas.create_text(
            self.canvas.winfo_width() / 2,
            self.canvas.winfo_height() / 2,
            fill="#ffffff",
            text=text,
            font=("Consolas", 14),
        )


class XYZRobotDemoApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Mower II - XYZ Robot Demo")
        self.geometry("1050x720")

        self.xyz_state = XYZRobotState()

        self.xyz_worker = XYZRobotWorker(
            on_event=self.on_xyz_event,
            on_state_changed=self.on_xyz_state_changed,
        )
        self.xyz_worker.start()

        self._build_ui()

        self.after(250, self.update_ui_periodic)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # --------------------------------------------------
    # UI
    # --------------------------------------------------

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(self)
        left.grid(row=0, column=0, padx=(16, 8), pady=16, sticky="nsew")
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            left,
            text="Arbeitsbereich / aktuelle XYZ-Position",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        title.grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")

        self.workspace_view = XYZWorkspaceView(
            left,
            xyz_state_getter=lambda: self.xyz_state,
        )
        self.workspace_view.grid(row=1, column=0, padx=16, pady=(8, 16), sticky="nsew")

        right = ctk.CTkFrame(self, width=280)
        right.grid(row=0, column=1, padx=(8, 16), pady=16, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(9, weight=1)

        ctk.CTkLabel(
            right,
            text="XYZ Demo",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, padx=16, pady=(20, 16), sticky="w")

        self.btn_connect = ctk.CTkButton(
            right,
            text="Connect",
            command=self.connect_xyz,
            height=38,
        )
        self.btn_connect.grid(row=1, column=0, padx=16, pady=8, sticky="ew")

        self.btn_homing = ctk.CTkButton(
            right,
            text="Homing",
            command=self.home_xyz,
            height=38,
        )
        self.btn_homing.grid(row=2, column=0, padx=16, pady=8, sticky="ew")

        self.btn_move = ctk.CTkButton(
            right,
            text="Move",
            command=self.open_move_dialog,
            height=38,
        )
        self.btn_move.grid(row=3, column=0, padx=16, pady=8, sticky="ew")

        self.btn_demo_mark = ctk.CTkButton(
            right,
            text="Demo Markierung",
            command=self.open_demo_mark_dialog,
            height=38,
        )
        self.btn_demo_mark.grid(row=4, column=0, padx=16, pady=8, sticky="ew")

        self.btn_placeholder = ctk.CTkButton(
            right,
            text="Muster",
            command=self.placeholder_action,
            height=38,
        )
        self.btn_placeholder.grid(row=5, column=0, padx=16, pady=8, sticky="ew")

        self.btn_hatch = ctk.CTkButton(
            right,
            text="Logo IfG",
            command=self.hatch_action,
            height=38,
        )
        self.btn_hatch.grid(row=6, column=0, padx=16, pady=8, sticky="ew")

        self.lbl_status = ctk.CTkLabel(
            right,
            text="Status: -",
            justify="left",
            anchor="w",
            wraplength=240,
        )
        self.lbl_status.grid(row=7, column=0, padx=16, pady=(16, 8), sticky="ew")

        ctk.CTkLabel(
            right,
            text="Log",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=8, column=0, padx=16, pady=(12, 4), sticky="sw")

        self.logbox = ctk.CTkTextbox(right, width=250, height=220, wrap="word")
        self.logbox.grid(row=9, column=0, padx=16, pady=(4, 16), sticky="nsew")

    # --------------------------------------------------
    # Worker callbacks
    # --------------------------------------------------

    def on_xyz_event(self, event) -> None:
        try:
            text = f"[{event.component}] [{event.level.name}] {event.message}"
        except Exception:
            text = str(event)

        self.after(0, lambda: self.log(text))

    def on_xyz_state_changed(self, state: XYZRobotState) -> None:
        self.xyz_state = state

    # --------------------------------------------------
    # Buttons
    # --------------------------------------------------

    def connect_xyz(self) -> None:
        if CONFIG is None:
            self.log("Connect nicht möglich: Config nicht geladen.")
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

        if not port:
            return

        self.log(f"Verbinde XYZ: {port} @ {CONFIG.xyz.baudrate}")

        self.xyz_worker.send_command(
            "connect",
            port=port,
            baudrate=CONFIG.xyz.baudrate,
        )

    def home_xyz(self) -> None:
        if not self.xyz_state.connected:
            self.log("Homing nicht möglich: XYZ ist nicht verbunden.")
            messagebox.showwarning(
                "Homing",
                "XYZ ist nicht verbunden.",
                parent=self,
            )
            return

        self.log("Starte Homing...")
        self.xyz_worker.send_command("home_all")

    def open_move_dialog(self) -> None:
        show_xyz_manual_move_dialog(
            parent=self,
            config=CONFIG,
            xyz_worker=self.xyz_worker,
            xyz_state_getter=lambda: self.xyz_state,
            log=self.log,
        )

    def open_demo_mark_dialog(self) -> None:
        if CONFIG is None:
            self.log("Demo Markierung nicht möglich: Config nicht geladen.")
            return

        if not self.xyz_state.connected:
            self.log("Demo Markierung nicht möglich: XYZ ist nicht verbunden.")
            messagebox.showwarning(
                "Demo Markierung",
                "XYZ ist nicht verbunden.",
                parent=self,
            )
            return

        if self.xyz_state.x is None or self.xyz_state.y is None:
            self.log("Demo Markierung nicht möglich: Keine aktuelle XY-Position.")
            messagebox.showwarning(
                "Demo Markierung",
                "Keine aktuelle XY-Position verfügbar.",
                parent=self,
            )
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Demo Markierung")
        self.center_toplevel(dialog, 520, 380)
        dialog.transient(self)
        dialog.grab_set()

        dialog.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            dialog,
            text="Demo Markierung auf aktueller Position",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=24, pady=(24, 8), sticky="w")

        pos_text = (
            f"Aktuelle Position:\n"
            f"X={self.xyz_state.x:.3f} mm\n"
            f"Y={self.xyz_state.y:.3f} mm\n"
            f"Z={'-' if self.xyz_state.z is None else f'{self.xyz_state.z:.3f} mm'}"
        )

        ctk.CTkLabel(
            dialog,
            text=pos_text,
            justify="left",
        ).grid(row=1, column=0, padx=24, pady=(0, 12), sticky="w")

        form = ctk.CTkFrame(dialog)
        form.grid(row=2, column=0, padx=24, pady=8, sticky="ew")
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="Markierung:").grid(
            row=0, column=0, padx=10, pady=10, sticky="e"
        )

        marker_shapes = list(MARKER_SHAPES.keys())

        marker_shape_var = ctk.StringVar(
            value=CONFIG.marker.shape if CONFIG.marker.shape in marker_shapes else marker_shapes[0]
        )

        marker_shape_menu = ctk.CTkOptionMenu(
            form,
            values=marker_shapes,
            variable=marker_shape_var,
        )
        marker_shape_menu.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(form, text="Größe [mm]:").grid(
            row=1, column=0, padx=10, pady=10, sticky="e"
        )

        entry_size = ctk.CTkEntry(form)
        entry_size.insert(0, str(CONFIG.marker.size_mm))
        entry_size.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(form, text="Text / Label:").grid(
            row=2, column=0, padx=10, pady=10, sticky="e"
        )

        entry_label = ctk.CTkEntry(form)
        entry_label.insert(0, "DEMO")
        entry_label.grid(row=2, column=1, padx=10, pady=10, sticky="ew")

        button_frame = ctk.CTkFrame(dialog)
        button_frame.grid(row=3, column=0, padx=24, pady=(18, 24), sticky="ew")
        button_frame.grid_columnconfigure((0, 1), weight=1)

        def mark() -> None:
            try:
                marker_size = float(entry_size.get().replace(",", "."))
            except ValueError:
                messagebox.showerror(
                    "Demo Markierung",
                    "Ungültige Markergröße.",
                    parent=dialog,
                )
                return

            if marker_size <= 0:
                messagebox.showerror(
                    "Demo Markierung",
                    "Markergröße muss > 0 sein.",
                    parent=dialog,
                )
                return

            label = entry_label.get().strip() or "DEMO"
            marker_shape = marker_shape_var.get()

            if marker_shape not in MARKER_SHAPES:
                messagebox.showerror(
                    "Demo Markierung",
                    f"Unbekannte Markerform: {marker_shape}",
                    parent=dialog,
                )
                return

            x = float(self.xyz_state.x)
            y = float(self.xyz_state.y)

            self.log(
                f"Demo Markierung: Label={label}, "
                f"Shape={marker_shape}, Size={marker_size:.3f}, "
                f"X={x:.3f}, Y={y:.3f}"
            )

            self.xyz_worker.send_command(
                "mark_point",
                x=x,
                y=y,
                label=label,
                marker_size=marker_size,
                marker_shape=marker_shape,
                angle_deg=CONFIG.marker.angle_deg,
            )

            dialog.destroy()

        ctk.CTkButton(
            button_frame,
            text="Markieren",
            command=mark,
        ).grid(row=0, column=0, padx=(0, 8), pady=10, sticky="ew")

        ctk.CTkButton(
            button_frame,
            text="Abbrechen",
            command=dialog.destroy,
        ).grid(row=0, column=1, padx=(8, 0), pady=10, sticky="ew")

    def hatch_action(self) -> None:
        """
        Öffnet einen Dialog für die Logo-Schraffur.

        Eingaben:
            Größe [mm]:
                Maximale Boxgröße. Das Logo wird proportional in diese Box eingepasst.

            Linienabstand [mm]:
                Abstand der Schraffurlinien.

        Automatisch:
            Mindestsegment = max(0.5 mm, 0.8 * Linienabstand)
        """

        if CONFIG is None:
            self.log("Logo-Schraffur nicht möglich: Config nicht geladen.")
            return

        if not self.xyz_state.connected:
            self.log("Logo-Schraffur nicht möglich: XYZ ist nicht verbunden.")
            messagebox.showwarning(
                "Logo-Schraffur",
                "XYZ ist nicht verbunden.",
                parent=self,
            )
            return

        if self.xyz_state.x is None or self.xyz_state.y is None:
            self.log("Logo-Schraffur nicht möglich: Keine aktuelle XY-Position.")
            messagebox.showwarning(
                "Logo-Schraffur",
                "Keine aktuelle XY-Position verfügbar.",
                parent=self,
            )
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Logo-Schraffur")
        self.center_toplevel(dialog, 520, 360)
        dialog.transient(self)
        dialog.grab_set()

        dialog.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            dialog,
            text="Logo-Schraffur",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=24, pady=(24, 8), sticky="w")

        ctk.CTkLabel(
            dialog,
            text=(
                "Die grauen Bereiche des Logos werden als horizontale und "
                "vertikale Schraffur an der aktuellen Roboterposition geplottet."
            ),
            justify="left",
            wraplength=460,
        ).grid(row=1, column=0, padx=24, pady=(0, 12), sticky="w")

        form = ctk.CTkFrame(dialog)
        form.grid(row=2, column=0, padx=24, pady=8, sticky="ew")
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(form, text="Größe [mm]:").grid(
            row=0, column=0, padx=10, pady=10, sticky="e"
        )

        entry_size = ctk.CTkEntry(form)
        entry_size.insert(0, "100.0")
        entry_size.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(form, text="Linienabstand [mm]:").grid(
            row=1, column=0, padx=10, pady=10, sticky="e"
        )

        entry_spacing = ctk.CTkEntry(form)
        entry_spacing.insert(0, "1.0")
        entry_spacing.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(form, text="Schraffur:").grid(
            row=2, column=0, padx=10, pady=10, sticky="e"
        )

        hatch_mode_var = ctk.StringVar(value="beides")

        hatch_mode_menu = ctk.CTkOptionMenu(
            form,
            values=["längs", "quer", "beides"],
            variable=hatch_mode_var,
        )
        hatch_mode_menu.grid(row=2, column=1, padx=10, pady=10, sticky="ew")

        info_label = ctk.CTkLabel(
            form,
            text="Mindestsegment wird automatisch aus dem Linienabstand berechnet.",
            justify="left",
            wraplength=420,
        )
        info_label.grid(row=3, column=0, columnspan=2, padx=10, pady=(0, 10), sticky="w")

        button_frame = ctk.CTkFrame(dialog)
        button_frame.grid(row=3, column=0, padx=24, pady=(18, 24), sticky="ew")
        button_frame.grid_columnconfigure((0, 1), weight=1)

        def parse_positive_float(entry: ctk.CTkEntry, name: str) -> float | None:
            try:
                value = float(entry.get().replace(",", "."))
            except ValueError:
                messagebox.showerror(
                    "Logo-Schraffur",
                    f"Ungültiger Wert für {name}.",
                    parent=dialog,
                )
                return None

            if value <= 0:
                messagebox.showerror(
                    "Logo-Schraffur",
                    f"{name} muss größer als 0 sein.",
                    parent=dialog,
                )
                return None

            return value

        def start_hatch() -> None:
            size_mm = parse_positive_float(entry_size, "Größe")
            spacing_mm = parse_positive_float(entry_spacing, "Linienabstand")

            if size_mm is None or spacing_mm is None:
                return

            min_segment_mm = max(0.5, spacing_mm * 0.8)

            hatch_mode = hatch_mode_var.get()

            if hatch_mode == "längs":
                add_vertical = True
                add_horizontal = False
            elif hatch_mode == "quer":
                add_vertical = False
                add_horizontal = True
            else:
                add_vertical = True
                add_horizontal = True

            dialog.destroy()

            self._run_logo_hatch(
                target_size_mm=size_mm,
                spacing_mm=spacing_mm,
                min_segment_length_mm=min_segment_mm,
                add_vertical=add_vertical,
                add_horizontal=add_horizontal,
                hatch_mode=hatch_mode,
            )

        ctk.CTkButton(
            button_frame,
            text="Schraffur starten",
            command=start_hatch,
        ).grid(row=0, column=0, padx=(0, 8), pady=10, sticky="ew")

        ctk.CTkButton(
            button_frame,
            text="Abbrechen",
            command=dialog.destroy,
        ).grid(row=0, column=1, padx=(8, 0), pady=10, sticky="ew")

    def _run_logo_hatch(
            self,
            *,
            target_size_mm: float,
            spacing_mm: float,
            min_segment_length_mm: float,
            add_vertical: bool,
            add_horizontal: bool,
            hatch_mode: str,
    ) -> None:
        center_x = float(self.xyz_state.x)
        center_y = float(self.xyz_state.y)

        image_path = PROJECT_ROOT / "App" / "assets" / "IFG_Unibw.png"

        if not image_path.exists():
            self.log(f"Logo-Datei nicht gefunden: {image_path}")
            messagebox.showerror(
                "Logo-Schraffur",
                f"Logo-Datei nicht gefunden:\n{image_path}",
                parent=self,
            )
            return

        try:
            segments = generate_logo_hatch_segments(
                image_path=image_path,
                center_x=center_x,
                center_y=center_y,
                target_box_width_mm=target_size_mm,
                target_box_height_mm=target_size_mm,
                spacing_mm=spacing_mm,
                min_segment_length_mm=min_segment_length_mm,
                mask_mode="gray",
                add_vertical=add_vertical,
                add_horizontal=add_horizontal,
            )
        except Exception as exc:
            self.log(f"Logo-Schraffur konnte nicht erzeugt werden: {exc}")
            messagebox.showerror(
                "Logo-Schraffur",
                str(exc),
                parent=self,
            )
            return

        self.log(
            f"Starte Logo-Schraffur: {len(segments)} Liniensegmente, "
            f"Mitte X={center_x:.3f}, Y={center_y:.3f}, "
            f"Größe={target_size_mm:.1f} mm, "
            f"Abstand={spacing_mm:.3f} mm, "
            f"MinSegment={min_segment_length_mm:.3f} mm, "
            f"Modus={hatch_mode}"
        )

        for i, (x1, y1, x2, y2) in enumerate(segments, start=1):
            self.log(
                f"Logo-Segment {i}: "
                f"X1={x1:.3f}, Y1={y1:.3f} -> "
                f"X2={x2:.3f}, Y2={y2:.3f}"
            )

            self.xyz_worker.send_command(
                "mark_line_absolute",
                start_x=x1,
                start_y=y1,
                end_x=x2,
                end_y=y2,
            )

        self.log("Logo-Schraffur an Worker übergeben.")

    def placeholder_action(self) -> None:
        """
        Demo-Kreuzschraffurmuster 100 x 100 mm an aktueller Position.

        Mittelpunkt:
            aktuelle Roboterposition

        Durchlauf 1:
            vertikale Linien
            Linienlaenge 100 mm
            Verteilung ueber 100 mm X-Breite

        Durchlauf 2:
            horizontale Linien
            Linienlaenge 100 mm
            Verteilung ueber 100 mm Y-Hoehe

        Abstand:
            1.00 mm, 1.05 mm, 1.10 mm, ...
        """

        if CONFIG is None:
            self.log("Schraffur-Demo nicht möglich: Config nicht geladen.")
            return

        if not self.xyz_state.connected:
            self.log("Schraffur-Demo nicht möglich: XYZ ist nicht verbunden.")
            messagebox.showwarning(
                "Schraffur-Demo",
                "XYZ ist nicht verbunden.",
                parent=self,
            )
            return

        if self.xyz_state.x is None or self.xyz_state.y is None:
            self.log("Schraffur-Demo nicht möglich: Keine aktuelle XY-Position.")
            messagebox.showwarning(
                "Schraffur-Demo",
                "Keine aktuelle XY-Position verfügbar.",
                parent=self,
            )
            return

        center_x = float(self.xyz_state.x)
        center_y = float(self.xyz_state.y)

        width_x = 100.0
        height_y = 100.0

        spacing_start = 1.0
        spacing_increment = 0.05

        self.log(
            "Starte Kreuzschraffur-Demo 100x100: "
            f"Mitte X={center_x:.3f}, Y={center_y:.3f}, "
            f"Breite={width_x:.1f} mm, Hoehe={height_y:.1f} mm"
        )


        def send_line(
                start_x: float,
                start_y: float,
                end_x: float,
                end_y: float,
                label: str,
        ) -> None:
            self.log(
                f"{label}: "
                f"X1={start_x:.3f}, Y1={start_y:.3f} -> "
                f"X2={end_x:.3f}, Y2={end_y:.3f}"
            )

            self.xyz_worker.send_command(
                "mark_line_absolute",
                start_x=start_x,
                start_y=start_y,
                end_x=end_x,
                end_y=end_y,
            )

        x_min = center_x - width_x / 2.0
        x_max = center_x + width_x / 2.0

        y_min = center_y - height_y / 2.0
        y_max = center_y + height_y / 2.0

        # --------------------------------------------------
        # 1. Durchlauf: vertikale Linien
        # --------------------------------------------------

        x = x_min
        spacing_x = spacing_start
        line_count_vertical = 0

        while x <= x_max:
            line_count_vertical += 1

            send_line(
                start_x=x,
                start_y=y_min,
                end_x=x,
                end_y=y_max,
                label=(
                    f"Vertikal {line_count_vertical} "
                    f"(Abstand vorher={spacing_x:.3f} mm)"
                ),
            )

            x += spacing_x
            spacing_x += spacing_increment

        # --------------------------------------------------
        # 2. Durchlauf: horizontale Linien
        # --------------------------------------------------

        y = y_min
        spacing_y = spacing_start
        line_count_horizontal = 0

        while y <= y_max:
            line_count_horizontal += 1

            send_line(
                start_x=x_min,
                start_y=y,
                end_x=x_max,
                end_y=y,
                label=(
                    f"Horizontal {line_count_horizontal} "
                    f"(Abstand vorher={spacing_y:.3f} mm)"
                ),
            )

            y += spacing_y
            spacing_y += spacing_increment

        self.log(
            "Kreuzschraffur-Demo 100x100 abgeschlossen: "
            f"{line_count_vertical} vertikale Linien, "
            f"{line_count_horizontal} horizontale Linien gesendet."
        )

    # --------------------------------------------------
    # UI update
    # --------------------------------------------------

    def update_ui_periodic(self) -> None:
        self.workspace_view.redraw()
        self.update_status_label()
        self.after(250, self.update_ui_periodic)

    def update_status_label(self) -> None:
        state = self.xyz_state

        x = "-" if state.x is None else f"{state.x:.3f}"
        y = "-" if state.y is None else f"{state.y:.3f}"
        z = "-" if state.z is None else f"{state.z:.3f}"

        self.lbl_status.configure(
            text=(
                "Status:\n"
                f"connected: {state.connected}\n"
                f"homed:     {state.homed}\n"
                f"busy:      {state.busy}\n"
                f"X:         {x}\n"
                f"Y:         {y}\n"
                f"Z:         {z}"
            )
        )

    # --------------------------------------------------
    # Helpers
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

    def log(self, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.logbox.insert("end", f"[{timestamp}] {text}\n")
        self.logbox.see("end")

    def on_close(self) -> None:
        try:
            self.xyz_worker.stop()
        finally:
            self.destroy()


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = XYZRobotDemoApp()
    app.mainloop()
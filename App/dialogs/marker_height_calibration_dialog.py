# App/dialogs/marker_height_calibration_dialog.py

from __future__ import annotations

import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable

from config.mower_config import CONFIG, update_marker_z_mark_mm


StateGetter = Callable[[], Any]
SendCommand = Callable[..., bool]
ReadPositionFunction = Callable[[], None]
LogFunction = Callable[[str], None]
ActionFunction = Callable[[str], None]
FinishedCallback = Callable[[], None]


FONT_NORMAL = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SECTION = ("Segoe UI", 11, "bold")
FONT_MONO = ("Consolas", 10)


Z_CLEAR_OFFSET_MM = 5.0
Z_TRAVEL_OFFSET_MM = 10.0


def show_marker_height_calibration_dialog(
        *,
        parent: tk.Misc,
        config: Any,
        xyz_state_getter: StateGetter,
        send_xyz_command: SendCommand,
        read_xyz_position: ReadPositionFunction,
        log: LogFunction | None = None,
        set_current_action: ActionFunction | None = None,
        on_finished: FinishedCallback | None = None,
) -> None:
    """Dialog zur Kalibrierung der Markierhoehe Z_MARK."""

    dialog = MarkerHeightCalibrationDialog(
        parent=parent,
        config=config,
        xyz_state_getter=xyz_state_getter,
        send_xyz_command=send_xyz_command,
        read_xyz_position=read_xyz_position,
        log=log,
        set_current_action=set_current_action,
        on_finished=on_finished,
    )
    dialog.show()


class MarkerHeightCalibrationDialog:
    def __init__(
            self,
            *,
            parent: tk.Misc,
            config: Any,
            xyz_state_getter: StateGetter,
            send_xyz_command: SendCommand,
            read_xyz_position: ReadPositionFunction,
            log: LogFunction | None = None,
            set_current_action: ActionFunction | None = None,
            on_finished: FinishedCallback | None = None,
    ) -> None:
        self.parent = parent
        self.config = config
        self.xyz_state_getter = xyz_state_getter
        self.send_xyz_command = send_xyz_command
        self.read_xyz_position = read_xyz_position
        self.external_log = log
        self.set_current_action = set_current_action
        self.on_finished = on_finished

        self.saved = False
        self.current_z_mark = float(getattr(config.marker, "z_mark_mm", 166.0))
        self.proposed_z_mark: float | None = None

        self.window = tk.Toplevel(parent)
        self.window.title("Markerhoehe kalibrieren")
        self.window.resizable(False, False)
        self.window.transient(parent)
        self.window.grab_set()

        _center_window(parent, self.window, 680, 560)

        self._configure_styles()
        self._build_ui()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())

    def show(self) -> None:
        self.log("Markerhoehen-Kalibrierung geoeffnet.")
        self.refresh_position()
        self.update_display()
        self.window.after(300, self.update_position_loop)
        self.parent.wait_window(self.window)

    # --------------------------------------------------
    # UI
    # --------------------------------------------------

    def _configure_styles(self) -> None:
        style = ttk.Style(self.window)
        style.configure("MarkerHeight.TLabel", font=FONT_NORMAL)
        style.configure("MarkerHeightBold.TLabel", font=FONT_BOLD)
        style.configure("MarkerHeight.TButton", font=FONT_NORMAL, padding=(8, 4))
        style.configure("MarkerHeight.TLabelframe.Label", font=FONT_SECTION)

    def _build_ui(self) -> None:
        root = ttk.Frame(self.window, padding=12)
        root.grid(row=0, column=0, sticky="nsew")
        root.grid_columnconfigure(0, weight=1)

        status_frame = ttk.LabelFrame(root, text="Status", padding=10, style="MarkerHeight.TLabelframe")
        status_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        status_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(status_frame, text="Aktuelle XYZ-Position:", style="MarkerHeight.TLabel").grid(
            row=0, column=0, padx=(0, 8), pady=3, sticky="w"
        )
        self.pos_var = tk.StringVar(value="X=---.---   Y=---.---   Z=---.---")
        ttk.Label(status_frame, textvariable=self.pos_var, font=FONT_MONO).grid(
            row=0, column=1, pady=3, sticky="ew"
        )

        ttk.Button(
            status_frame,
            text="Position lesen",
            command=self.refresh_position,
            style="MarkerHeight.TButton",
        ).grid(row=0, column=2, padx=(8, 0), pady=3, sticky="ew")

        value_frame = ttk.LabelFrame(root, text="Markerhoehen", padding=10, style="MarkerHeight.TLabelframe")
        value_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        value_frame.grid_columnconfigure(1, weight=1)

        self.current_mark_var = tk.StringVar()
        self.proposed_mark_var = tk.StringVar()
        self.clear_var = tk.StringVar()
        self.travel_var = tk.StringVar()

        ttk.Label(value_frame, text="Aktuell gespeichertes Z_MARK:", style="MarkerHeight.TLabel").grid(row=0, column=0, padx=(0, 8), pady=3, sticky="w")
        ttk.Label(value_frame, textvariable=self.current_mark_var, style="MarkerHeight.TLabel").grid(row=0, column=1, pady=3, sticky="ew")

        ttk.Label(value_frame, text="Neues Z_MARK:", style="MarkerHeight.TLabel").grid(row=1, column=0, padx=(0, 8), pady=3, sticky="w")
        ttk.Label(value_frame, textvariable=self.proposed_mark_var, style="MarkerHeightBold.TLabel").grid(row=1, column=1, pady=3, sticky="ew")

        ttk.Label(value_frame, text="Daraus Z_CLEAR:", style="MarkerHeight.TLabel").grid(row=2, column=0, padx=(0, 8), pady=3, sticky="w")
        ttk.Label(value_frame, textvariable=self.clear_var, style="MarkerHeight.TLabel").grid(row=2, column=1, pady=3, sticky="ew")

        ttk.Label(value_frame, text="Daraus Z_TRAVEL:", style="MarkerHeight.TLabel").grid(row=3, column=0, padx=(0, 8), pady=3, sticky="w")
        ttk.Label(value_frame, textvariable=self.travel_var, style="MarkerHeight.TLabel").grid(row=3, column=1, pady=3, sticky="ew")

        control_frame = ttk.LabelFrame(root, text="Z-Achse verfahren", padding=10, style="MarkerHeight.TLabelframe")
        control_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        for col in range(4):
            control_frame.grid_columnconfigure(col, weight=1)

        self.step_z_var = tk.StringVar(value="0.1")
        self.feed_z_var = tk.StringVar(value=f"{float(getattr(CONFIG.xyz, 'default_feedrate', 900.0)):.0f}")

        ttk.Label(control_frame, text="Schritt Z [mm]:", style="MarkerHeight.TLabel").grid(row=0, column=0, padx=(0, 8), pady=3, sticky="w")
        ttk.Entry(control_frame, textvariable=self.step_z_var, width=12).grid(row=0, column=1, padx=(0, 16), pady=3, sticky="ew")
        ttk.Label(control_frame, text="Feedrate [mm/min]:", style="MarkerHeight.TLabel").grid(row=0, column=2, padx=(0, 8), pady=3, sticky="w")
        ttk.Entry(control_frame, textvariable=self.feed_z_var, width=12).grid(row=0, column=3, pady=3, sticky="ew")

        ttk.Button(control_frame, text="Z+", command=lambda: self.jog_z(1.0), style="MarkerHeight.TButton").grid(row=1, column=0, padx=(0, 6), pady=(8, 0), sticky="ew")
        ttk.Button(control_frame, text="Z-", command=lambda: self.jog_z(-1.0), style="MarkerHeight.TButton").grid(row=1, column=1, padx=6, pady=(8, 0), sticky="ew")
        ttk.Button(control_frame, text="Aktuelle Z als Z_MARK", command=self.take_current_z_as_mark, style="MarkerHeight.TButton").grid(row=1, column=2, columnspan=2, padx=(6, 0), pady=(8, 0), sticky="ew")

        info_frame = ttk.LabelFrame(root, text="Hinweis", padding=10, style="MarkerHeight.TLabelframe")
        info_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(
            info_frame,
            text=(
                "Fahre die Z-Achse vorsichtig auf die gewuenschte Markierhoehe. "
                "Mit 'Aktuelle Z als Z_MARK' wird die aktuelle Z-Position als neue Markierhoehe vorgemerkt. "
                "Gespeichert wird nur Z_MARK; Z_CLEAR und Z_TRAVEL werden automatisch daraus abgeleitet."
            ),
            wraplength=620,
            justify="left",
            style="MarkerHeight.TLabel",
        ).grid(row=0, column=0, sticky="ew")

        button_frame = ttk.Frame(root)
        button_frame.grid(row=4, column=0, sticky="ew")
        for col in range(3):
            button_frame.grid_columnconfigure(col, weight=1)

        ttk.Button(button_frame, text="Abbrechen", command=self.close, style="MarkerHeight.TButton").grid(row=0, column=0, padx=(0, 6), sticky="ew")
        ttk.Button(button_frame, text="Z_MARK speichern", command=self.save_z_mark, style="MarkerHeight.TButton").grid(row=0, column=1, padx=6, sticky="ew")
        ttk.Button(button_frame, text="Schliessen", command=self.close, style="MarkerHeight.TButton").grid(row=0, column=2, padx=(6, 0), sticky="ew")

    # --------------------------------------------------
    # Actions
    # --------------------------------------------------

    def refresh_position(self) -> None:
        try:
            self.read_xyz_position()
        except Exception as exc:
            self.log(f"Position lesen konnte nicht angefordert werden: {exc}")

        self.update_display()

    def update_position_loop(self) -> None:
        if not self.window.winfo_exists():
            return
        self.update_display()
        self.window.after(300, self.update_position_loop)

    def jog_z(self, sign: float) -> None:
        step = self._parse_float(self.step_z_var.get(), "Schritt Z")
        feed = self._parse_float(self.feed_z_var.get(), "Feedrate")
        if step is None or feed is None:
            return

        dz = sign * step
        self.log(f"Markerhoehe: Jog Z dZ={dz:.3f} mm, Feedrate={feed:.0f}")
        if self.set_current_action:
            self.set_current_action("Markerhoehen-Kalibrierung: Z-Fahrt gesendet.")
        self.send_xyz_command("jog", dz=dz, feedrate=feed)

    def take_current_z_as_mark(self) -> None:
        z = self._current_z()
        if z is None:
            messagebox.showwarning("Markerhoehe", "Keine aktuelle Z-Position vorhanden.", parent=self.window)
            return

        self.proposed_z_mark = float(z)
        self.log(f"Neues Z_MARK vorgemerkt: {self.proposed_z_mark:.3f} mm")
        self.update_display()

    def save_z_mark(self) -> None:
        if self.proposed_z_mark is None:
            z = self._current_z()
            if z is None:
                messagebox.showwarning("Markerhoehe", "Keine neue Markierhoehe vorgemerkt.", parent=self.window)
                return
            self.proposed_z_mark = float(z)

        z_mark = float(self.proposed_z_mark)

        if not (float(CONFIG.xyz.z_min) <= z_mark <= float(CONFIG.xyz.z_max)):
            messagebox.showerror(
                "Markerhoehe",
                f"Z_MARK={z_mark:.3f} liegt ausserhalb des Arbeitsraums "
                f"[{CONFIG.xyz.z_min:.3f}, {CONFIG.xyz.z_max:.3f}].",
                parent=self.window,
            )
            return

        try:
            update_marker_z_mark_mm(z_mark)
            CONFIG.marker.z_mark_mm = z_mark
        except Exception as exc:
            self.log(f"FEHLER beim Speichern von Z_MARK: {exc}")
            messagebox.showerror("Markerhoehe", str(exc), parent=self.window)
            return

        self.current_z_mark = z_mark
        self.saved = True
        self.log(
            f"Z_MARK gespeichert: {z_mark:.3f} mm | "
            f"Z_CLEAR={z_mark + Z_CLEAR_OFFSET_MM:.3f} mm | "
            f"Z_TRAVEL={z_mark + Z_TRAVEL_OFFSET_MM:.3f} mm"
        )
        if self.set_current_action:
            self.set_current_action("Markerhoehe gespeichert.")
        if self.on_finished:
            self.on_finished()
        self.update_display()
        messagebox.showinfo("Markerhoehe", "Z_MARK wurde gespeichert.", parent=self.window)

    def close(self) -> None:
        try:
            self.window.grab_release()
        except Exception:
            pass
        self.window.destroy()

    # --------------------------------------------------
    # Display / helpers
    # --------------------------------------------------

    def update_display(self) -> None:
        x, y, z = self._current_xyz()
        if x is None or y is None or z is None:
            self.pos_var.set("X=---.---   Y=---.---   Z=---.---")
        else:
            self.pos_var.set(f"X={x:8.3f} mm   Y={y:8.3f} mm   Z={z:8.3f} mm")

        z_mark = self.proposed_z_mark if self.proposed_z_mark is not None else self.current_z_mark
        self.current_mark_var.set(f"{self.current_z_mark:.3f} mm")
        self.proposed_mark_var.set(f"{z_mark:.3f} mm")
        self.clear_var.set(f"{z_mark + Z_CLEAR_OFFSET_MM:.3f} mm")
        self.travel_var.set(f"{z_mark + Z_TRAVEL_OFFSET_MM:.3f} mm")

    def _current_xyz(self) -> tuple[float | None, float | None, float | None]:
        state = self.xyz_state_getter()
        if state is None:
            return None, None, None
        return (
            getattr(state, "x", None),
            getattr(state, "y", None),
            getattr(state, "z", None),
        )

    def _current_z(self) -> float | None:
        _, _, z = self._current_xyz()
        return None if z is None else float(z)

    def _parse_float(self, value: str, name: str) -> float | None:
        try:
            return float(value.replace(",", "."))
        except ValueError:
            messagebox.showerror("Markerhoehe", f"Ungueltiger Wert fuer {name}.", parent=self.window)
            return None

    def log(self, text: str) -> None:
        if self.external_log:
            self.external_log(f"[Markerhoehe] {text}")


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

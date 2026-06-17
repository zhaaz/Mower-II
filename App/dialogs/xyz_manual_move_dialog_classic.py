# App/dialogs/xyz_manual_move_dialog_classic.py

from __future__ import annotations

from typing import Any, Callable
import tkinter as tk
from tkinter import messagebox, ttk


StateGetter = Callable[[], Any]
SendCommand = Callable[..., bool]
LogFunction = Callable[[str], None]
ActionFunction = Callable[[str], None]
ReadPositionFunction = Callable[[], None]


def show_xyz_manual_move_dialog_classic(
        parent: tk.Misc,
        *,
        config: Any,
        xyz_state_getter: StateGetter,
        send_xyz_command: SendCommand,
        read_xyz_position: ReadPositionFunction,
        log: LogFunction,
        set_current_action: ActionFunction,
) -> None:
    """Klassischer Tk-Dialog für Jog, Positionslesen und absolute XYZ-Fahrt."""

    dialog = tk.Toplevel(parent)
    dialog.title("XYZ manuell bewegen")
    dialog.resizable(False, False)
    dialog.transient(parent)
    dialog.grab_set()

    _center_window(parent, dialog, 600, 550)

    root = ttk.Frame(dialog, padding=12)
    root.grid(row=0, column=0, sticky="nsew")
    root.grid_columnconfigure(0, weight=1)

    ttk.Label(root, text="XYZ manuell bewegen", font=("Segoe UI", 12, "bold")).grid(
        row=0, column=0, sticky="w", pady=(0, 10)
    )

    pos_frame = ttk.LabelFrame(root, text="Aktuelle Position", padding=10)
    pos_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
    pos_frame.grid_columnconfigure(0, weight=1)

    pos_var = tk.StringVar(value=_format_xyz_state(xyz_state_getter))
    ttk.Label(pos_frame, textvariable=pos_var, font=("Consolas", 11)).grid(
        row=0, column=0, sticky="w"
    )
    ttk.Button(pos_frame, text="Position aktualisieren", command=read_xyz_position).grid(
        row=0, column=1, padx=(12, 0), sticky="e"
    )

    parameter_frame = ttk.LabelFrame(root, text="Parameter", padding=10)
    parameter_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
    for col in (1, 3):
        parameter_frame.grid_columnconfigure(col, weight=1)

    default_feed_xy = _config_float(config, "xyz", "feedrate_xy", 6000.0)
    default_feed_z = _config_float(config, "xyz", "feedrate_z", 600.0)

    step_xy_var = tk.StringVar(value="10.0")
    step_z_var = tk.StringVar(value="1.0")
    feed_xy_var = tk.StringVar(value=f"{default_feed_xy:.0f}")
    feed_z_var = tk.StringVar(value=f"{default_feed_z:.0f}")

    ttk.Label(parameter_frame, text="Schritt XY [mm]:").grid(row=0, column=0, padx=(0, 8), pady=3, sticky="w")
    ttk.Entry(parameter_frame, textvariable=step_xy_var, width=14).grid(row=0, column=1, padx=(0, 20), pady=3, sticky="ew")
    ttk.Label(parameter_frame, text="Feedrate XY [mm/min]:").grid(row=0, column=2, padx=(0, 8), pady=3, sticky="w")
    ttk.Entry(parameter_frame, textvariable=feed_xy_var, width=14).grid(row=0, column=3, pady=3, sticky="ew")

    ttk.Label(parameter_frame, text="Schritt Z [mm]:").grid(row=1, column=0, padx=(0, 8), pady=3, sticky="w")
    ttk.Entry(parameter_frame, textvariable=step_z_var, width=14).grid(row=1, column=1, padx=(0, 20), pady=3, sticky="ew")
    ttk.Label(parameter_frame, text="Feedrate Z [mm/min]:").grid(row=1, column=2, padx=(0, 8), pady=3, sticky="w")
    ttk.Entry(parameter_frame, textvariable=feed_z_var, width=14).grid(row=1, column=3, pady=3, sticky="ew")

    move_frame = ttk.LabelFrame(root, text="Relative Bewegung", padding=10)
    move_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))
    for col in range(5):
        move_frame.grid_columnconfigure(col, weight=1)

    def parse_float(value: str, name: str) -> float | None:
        try:
            return float(value.replace(",", "."))
        except ValueError:
            messagebox.showerror("XYZ bewegen", f"Ungültiger Wert für {name}.", parent=dialog)
            return None

    def jog_xy(dx_sign: float, dy_sign: float) -> None:
        step = parse_float(step_xy_var.get(), "Schritt XY")
        feed = parse_float(feed_xy_var.get(), "Feedrate XY")
        if step is None or feed is None:
            return

        dx = dx_sign * step if dx_sign != 0.0 else 0.0
        dy = dy_sign * step if dy_sign != 0.0 else 0.0

        log(f"XYZ jog XY: dX={dx:.3f}, dY={dy:.3f}, Feedrate={feed:.0f}")
        send_xyz_command("jog", dx=dx, dy=dy, feedrate=feed)
        set_current_action("XYZ-Jog XY gesendet.")

    def jog_z(dz_sign: float) -> None:
        step = parse_float(step_z_var.get(), "Schritt Z")
        feed = parse_float(feed_z_var.get(), "Feedrate Z")
        if step is None or feed is None:
            return

        dz = dz_sign * step

        log(f"XYZ jog Z: dZ={dz:.3f}, Feedrate={feed:.0f}")
        send_xyz_command("jog", dz=dz, feedrate=feed)
        set_current_action("XYZ-Jog Z gesendet.")

    ttk.Button(move_frame, text="Y+", command=lambda: jog_xy(0.0, 1.0)).grid(row=0, column=1, padx=6, pady=4, sticky="ew")
    ttk.Button(move_frame, text="X-", command=lambda: jog_xy(-1.0, 0.0)).grid(row=1, column=0, padx=6, pady=4, sticky="ew")
    ttk.Button(move_frame, text="X+", command=lambda: jog_xy(1.0, 0.0)).grid(row=1, column=2, padx=6, pady=4, sticky="ew")
    ttk.Button(move_frame, text="Y-", command=lambda: jog_xy(0.0, -1.0)).grid(row=2, column=1, padx=6, pady=4, sticky="ew")

    ttk.Separator(move_frame, orient="vertical").grid(row=0, column=3, rowspan=3, padx=16, sticky="ns")
    ttk.Label(move_frame, text="Z-Achse").grid(row=0, column=4, padx=6, pady=4, sticky="w")
    ttk.Button(move_frame, text="Z+", command=lambda: jog_z(1.0)).grid(row=1, column=4, padx=6, pady=4, sticky="ew")
    ttk.Button(move_frame, text="Z-", command=lambda: jog_z(-1.0)).grid(row=2, column=4, padx=6, pady=4, sticky="ew")

    abs_frame = ttk.LabelFrame(root, text="Absolute Zielposition", padding=10)
    abs_frame.grid(row=4, column=0, sticky="ew", pady=(0, 10))
    for col in (1, 3, 5):
        abs_frame.grid_columnconfigure(col, weight=1)

    x_var = tk.StringVar(value="0.000")
    y_var = tk.StringVar(value="0.000")
    z_var = tk.StringVar(value="200.000")

    ttk.Label(abs_frame, text="X:").grid(row=0, column=0, padx=(0, 4), pady=3, sticky="w")
    ttk.Entry(abs_frame, textvariable=x_var, width=12).grid(row=0, column=1, padx=(0, 16), pady=3, sticky="ew")
    ttk.Label(abs_frame, text="Y:").grid(row=0, column=2, padx=(0, 4), pady=3, sticky="w")
    ttk.Entry(abs_frame, textvariable=y_var, width=12).grid(row=0, column=3, padx=(0, 16), pady=3, sticky="ew")
    ttk.Label(abs_frame, text="Z:").grid(row=0, column=4, padx=(0, 4), pady=3, sticky="w")
    ttk.Entry(abs_frame, textvariable=z_var, width=12).grid(row=0, column=5, pady=3, sticky="ew")

    button_frame = ttk.Frame(root)
    button_frame.grid(row=5, column=0, sticky="ew")
    for col in range(3):
        button_frame.grid_columnconfigure(col, weight=1)

    def take_current_position() -> None:
        x, y, z = _xyz_state_values(xyz_state_getter)
        if x is None or y is None or z is None:
            messagebox.showwarning("XYZ bewegen", "Keine aktuelle XYZ-Position vorhanden.", parent=dialog)
            return

        x_var.set(f"{x:.3f}")
        y_var.set(f"{y:.3f}")
        z_var.set(f"{z:.3f}")

    def move_absolute() -> None:
        x = parse_float(x_var.get(), "X")
        y = parse_float(y_var.get(), "Y")
        z = parse_float(z_var.get(), "Z")
        feed = parse_float(feed_xy_var.get(), "Feedrate XY")
        if x is None or y is None or z is None or feed is None:
            return

        log(f"XYZ fahre absolut: X={x:.3f}, Y={y:.3f}, Z={z:.3f}, Feedrate={feed:.0f}")
        send_xyz_command("move_absolute", x=x, y=y, z=z, feedrate=feed)
        set_current_action("XYZ-Fahrbefehl gesendet.")

    ttk.Button(button_frame, text="Aktuelle Position übernehmen", command=take_current_position).grid(
        row=0, column=0, padx=(0, 6), sticky="ew"
    )
    ttk.Button(button_frame, text="Absolute Position anfahren", command=move_absolute).grid(
        row=0, column=1, padx=6, sticky="ew"
    )
    ttk.Button(button_frame, text="Schließen", command=dialog.destroy).grid(
        row=0, column=2, padx=(6, 0), sticky="ew"
    )

    def update_position_label() -> None:
        if not dialog.winfo_exists():
            return
        pos_var.set(_format_xyz_state(xyz_state_getter))
        dialog.after(300, update_position_label)

    take_current_position()
    update_position_label()

    dialog.bind("<Escape>", lambda _event: dialog.destroy())
    dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
    parent.wait_window(dialog)


def _config_float(config: Any, section: str, name: str, default: float) -> float:
    try:
        section_obj = getattr(config, section)
        value = getattr(section_obj, name)
        return float(value)
    except Exception:
        return default


def _xyz_state_values(xyz_state_getter: StateGetter) -> tuple[float | None, float | None, float | None]:
    state = xyz_state_getter()
    if state is None:
        return None, None, None

    x = getattr(state, "x", None)
    y = getattr(state, "y", None)
    z = getattr(state, "z", None)

    return x, y, z


def _format_xyz_state(xyz_state_getter: StateGetter) -> str:
    x, y, z = _xyz_state_values(xyz_state_getter)
    if x is None or y is None or z is None:
        return "X=---.---   Y=---.---   Z=---.---"
    return f"X={x:8.3f} mm   Y={y:8.3f} mm   Z={z:8.3f} mm"


def _center_window(parent: tk.Misc, window: tk.Toplevel, width: int, height: int) -> None:
    parent.update_idletasks()

    try:
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
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

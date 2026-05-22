# App/dialogs/xyz_manual_move_dialog.py

from __future__ import annotations

from typing import Callable, Any
from tkinter import messagebox

import customtkinter as ctk


def show_xyz_manual_move_dialog(
    *,
    parent: ctk.CTk,
    config: Any,
    xyz_worker: Any,
    xyz_state_getter: Callable[[], Any],
    log: Callable[[str], None],
) -> None:
    if config is None:
        log("XYZ manuell bewegen nicht möglich: Config nicht geladen.")
        return

    xyz_state = xyz_state_getter()

    if not xyz_state.connected:
        log("XYZ manuell bewegen nicht möglich: XYZ ist nicht verbunden.")
        messagebox.showwarning(
            "XYZ manuell bewegen",
            "XYZ ist nicht verbunden.",
            parent=parent,
        )
        return

    dialog_width = 620
    dialog_height = 720

    dialog = ctk.CTkToplevel(parent)
    dialog.title("XYZ manuell bewegen")
    _center_toplevel(parent, dialog, dialog_width, dialog_height)
    dialog.transient(parent)
    dialog.grab_set()

    dialog.grid_columnconfigure(0, weight=1)
    dialog.grid_rowconfigure(4, weight=1)

    title = ctk.CTkLabel(
        dialog,
        text="XYZ manuell bewegen",
        font=ctk.CTkFont(size=20, weight="bold"),
    )
    title.grid(row=0, column=0, padx=20, pady=(20, 8), sticky="w")

    info = ctk.CTkLabel(
        dialog,
        text=(
            "Relative Bewegungen werden sofort an den Roboter gesendet.\n"
            "XY und Z verwenden getrennte Geschwindigkeiten."
        ),
        justify="left",
    )
    info.grid(row=1, column=0, padx=20, pady=(0, 12), sticky="w")

    # --------------------------------------------------
    # Position
    # --------------------------------------------------

    position_frame = ctk.CTkFrame(dialog)
    position_frame.grid(row=2, column=0, padx=20, pady=8, sticky="ew")
    position_frame.grid_columnconfigure(0, weight=1)

    position_var = ctk.StringVar(
        value=_format_xyz_position(xyz_state_getter())
    )

    lbl_position = ctk.CTkLabel(
        position_frame,
        textvariable=position_var,
        font=ctk.CTkFont(size=14, weight="bold"),
        justify="left",
    )
    lbl_position.grid(row=0, column=0, padx=12, pady=10, sticky="w")

    def refresh_position_label() -> None:
        position_var.set(_format_xyz_position(xyz_state_getter()))

    ctk.CTkButton(
        position_frame,
        text="Position aktualisieren",
        command=refresh_position_label,
        width=160,
    ).grid(row=0, column=1, padx=12, pady=10, sticky="e")

    # --------------------------------------------------
    # Einstellungen
    # --------------------------------------------------

    settings_frame = ctk.CTkFrame(dialog)
    settings_frame.grid(row=3, column=0, padx=20, pady=8, sticky="ew")
    settings_frame.grid_columnconfigure((1, 3), weight=1)

    ctk.CTkLabel(settings_frame, text="Schritt XY [mm]:").grid(
        row=0, column=0, padx=10, pady=8, sticky="e"
    )

    entry_step_xy = ctk.CTkEntry(settings_frame)
    entry_step_xy.insert(0, "10.0")
    entry_step_xy.grid(row=0, column=1, padx=10, pady=8, sticky="ew")

    ctk.CTkLabel(settings_frame, text="Feedrate XY [mm/min]:").grid(
        row=0, column=2, padx=10, pady=8, sticky="e"
    )

    entry_feed_xy = ctk.CTkEntry(settings_frame)
    entry_feed_xy.insert(0, "6000")
    entry_feed_xy.grid(row=0, column=3, padx=10, pady=8, sticky="ew")

    ctk.CTkLabel(settings_frame, text="Schritt Z [mm]:").grid(
        row=1, column=0, padx=10, pady=8, sticky="e"
    )

    entry_step_z = ctk.CTkEntry(settings_frame)
    entry_step_z.insert(0, "1.0")
    entry_step_z.grid(row=1, column=1, padx=10, pady=8, sticky="ew")

    ctk.CTkLabel(settings_frame, text="Feedrate Z [mm/min]:").grid(
        row=1, column=2, padx=10, pady=8, sticky="e"
    )

    entry_feed_z = ctk.CTkEntry(settings_frame)
    entry_feed_z.insert(0, "600")
    entry_feed_z.grid(row=1, column=3, padx=10, pady=8, sticky="ew")

    # --------------------------------------------------
    # Jog Buttons
    # --------------------------------------------------

    jog_frame = ctk.CTkFrame(dialog)
    jog_frame.grid(row=4, column=0, padx=20, pady=8, sticky="nsew")
    jog_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

    def parse_float(entry: ctk.CTkEntry, name: str) -> float | None:
        try:
            value = float(entry.get().replace(",", "."))
        except ValueError:
            log(f"Ungültiger Wert für {name}.")
            messagebox.showerror(
                "XYZ manuell bewegen",
                f"Ungültiger Wert für {name}.",
                parent=dialog,
            )
            return None

        return value

    def jog_xy(dx_sign: float, dy_sign: float) -> None:
        step_xy = parse_float(entry_step_xy, "Schritt XY")
        feed_xy = parse_float(entry_feed_xy, "Feedrate XY")

        if step_xy is None or feed_xy is None:
            return

        dx = dx_sign * step_xy
        dy = dy_sign * step_xy

        log(
            f"XYZ jog XY: dX={dx:.3f}, dY={dy:.3f}, "
            f"Feedrate={feed_xy:.1f}"
        )

        xyz_worker.send_command(
            "jog",
            dx=dx,
            dy=dy,
            dz=None,
            feedrate=feed_xy,
        )

        dialog.after(300, refresh_position_label)

    def jog_z(dz_sign: float) -> None:
        step_z = parse_float(entry_step_z, "Schritt Z")
        feed_z = parse_float(entry_feed_z, "Feedrate Z")

        if step_z is None or feed_z is None:
            return

        dz = dz_sign * step_z

        log(
            f"XYZ jog Z: dZ={dz:.3f}, "
            f"Feedrate={feed_z:.1f}"
        )

        xyz_worker.send_command(
            "jog",
            dx=None,
            dy=None,
            dz=dz,
            feedrate=feed_z,
        )

        dialog.after(300, refresh_position_label)

    ctk.CTkLabel(
        jog_frame,
        text="Relative Bewegung XY",
        font=ctk.CTkFont(size=15, weight="bold"),
    ).grid(row=0, column=0, columnspan=3, padx=10, pady=(12, 6), sticky="w")

    ctk.CTkButton(
        jog_frame,
        text="Y+",
        command=lambda: jog_xy(0.0, 1.0),
    ).grid(row=1, column=1, padx=8, pady=8, sticky="ew")

    ctk.CTkButton(
        jog_frame,
        text="X-",
        command=lambda: jog_xy(-1.0, 0.0),
    ).grid(row=2, column=0, padx=8, pady=8, sticky="ew")

    ctk.CTkButton(
        jog_frame,
        text="X+",
        command=lambda: jog_xy(1.0, 0.0),
    ).grid(row=2, column=2, padx=8, pady=8, sticky="ew")

    ctk.CTkButton(
        jog_frame,
        text="Y-",
        command=lambda: jog_xy(0.0, -1.0),
    ).grid(row=3, column=1, padx=8, pady=8, sticky="ew")

    ctk.CTkLabel(
        jog_frame,
        text="Relative Bewegung Z",
        font=ctk.CTkFont(size=15, weight="bold"),
    ).grid(row=0, column=3, columnspan=2, padx=10, pady=(12, 6), sticky="w")

    ctk.CTkButton(
        jog_frame,
        text="Z+",
        command=lambda: jog_z(1.0),
    ).grid(row=1, column=3, columnspan=2, padx=8, pady=8, sticky="ew")

    ctk.CTkButton(
        jog_frame,
        text="Z-",
        command=lambda: jog_z(-1.0),
    ).grid(row=2, column=3, columnspan=2, padx=8, pady=8, sticky="ew")

    # --------------------------------------------------
    # Absolute Position
    # --------------------------------------------------

    absolute_frame = ctk.CTkFrame(dialog)
    absolute_frame.grid(row=5, column=0, padx=20, pady=8, sticky="ew")
    absolute_frame.grid_columnconfigure((1, 3, 5), weight=1)

    ctk.CTkLabel(
        absolute_frame,
        text="Absolute Zielposition",
        font=ctk.CTkFont(size=15, weight="bold"),
    ).grid(row=0, column=0, columnspan=6, padx=10, pady=(10, 4), sticky="w")

    ctk.CTkLabel(absolute_frame, text="X:").grid(
        row=1, column=0, padx=8, pady=8, sticky="e"
    )
    entry_abs_x = ctk.CTkEntry(absolute_frame)
    entry_abs_x.grid(row=1, column=1, padx=8, pady=8, sticky="ew")

    ctk.CTkLabel(absolute_frame, text="Y:").grid(
        row=1, column=2, padx=8, pady=8, sticky="e"
    )
    entry_abs_y = ctk.CTkEntry(absolute_frame)
    entry_abs_y.grid(row=1, column=3, padx=8, pady=8, sticky="ew")

    ctk.CTkLabel(absolute_frame, text="Z:").grid(
        row=1, column=4, padx=8, pady=8, sticky="e"
    )
    entry_abs_z = ctk.CTkEntry(absolute_frame)
    entry_abs_z.grid(row=1, column=5, padx=8, pady=8, sticky="ew")

    def fill_current_position() -> None:
        state = xyz_state_getter()

        if state.x is not None:
            entry_abs_x.delete(0, "end")
            entry_abs_x.insert(0, f"{state.x:.3f}")

        if state.y is not None:
            entry_abs_y.delete(0, "end")
            entry_abs_y.insert(0, f"{state.y:.3f}")

        if state.z is not None:
            entry_abs_z.delete(0, "end")
            entry_abs_z.insert(0, f"{state.z:.3f}")

    def move_absolute() -> None:
        x = parse_float(entry_abs_x, "Absolut X")
        y = parse_float(entry_abs_y, "Absolut Y")

        if x is None or y is None:
            return

        z_text = entry_abs_z.get().strip()

        if z_text:
            z = parse_float(entry_abs_z, "Absolut Z")
            if z is None:
                return
        else:
            z = None

        feed_xy = parse_float(entry_feed_xy, "Feedrate XY")

        if feed_xy is None:
            return

        log(
            f"XYZ fahre absolut: X={x:.3f}, Y={y:.3f}"
            + (f", Z={z:.3f}" if z is not None else "")
            + f", Feedrate={feed_xy:.1f}"
        )

        xyz_worker.send_command(
            "move_absolute_verified",
            x=x,
            y=y,
            z=z,
            feedrate=feed_xy,
            tolerance_mm=config.xyz.tolerance_mm,
        )

        dialog.after(500, refresh_position_label)

    abs_button_frame = ctk.CTkFrame(dialog)
    abs_button_frame.grid(row=6, column=0, padx=20, pady=(8, 20), sticky="ew")
    abs_button_frame.grid_columnconfigure((0, 1, 2), weight=1)

    ctk.CTkButton(
        abs_button_frame,
        text="Aktuelle Position übernehmen",
        command=fill_current_position,
    ).grid(row=0, column=0, padx=(0, 8), pady=10, sticky="ew")

    ctk.CTkButton(
        abs_button_frame,
        text="Absolute Position anfahren",
        command=move_absolute,
    ).grid(row=0, column=1, padx=8, pady=10, sticky="ew")

    ctk.CTkButton(
        abs_button_frame,
        text="Schließen",
        command=dialog.destroy,
    ).grid(row=0, column=2, padx=(8, 0), pady=10, sticky="ew")

    fill_current_position()


def _format_xyz_position(state: Any) -> str:
    if state.x is None or state.y is None:
        return (
            "Aktuelle Position:\n"
            "X = -\n"
            "Y = -\n"
            "Z = -"
        )

    z = state.z if state.z is not None else 0.0

    return (
        "Aktuelle Position:\n"
        f"X = {state.x:.3f} mm\n"
        f"Y = {state.y:.3f} mm\n"
        f"Z = {z:.3f} mm"
    )


def _center_toplevel(
    parent: ctk.CTk,
    window: ctk.CTkToplevel,
    width: int,
    height: int,
) -> None:
    parent.update_idletasks()

    parent_x = parent.winfo_rootx()
    parent_y = parent.winfo_rooty()
    parent_w = parent.winfo_width()
    parent_h = parent.winfo_height()

    x = parent_x + max(0, (parent_w - width) // 2)
    y = parent_y + max(0, (parent_h - height) // 2)

    window.geometry(f"{width}x{height}+{x}+{y}")
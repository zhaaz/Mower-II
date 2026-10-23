from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk


@dataclass(frozen=True)
class SerialConnectionSettings:
    port: str
    baudrate: int
    motor_id: int | None = None


def show_serial_connect_dialog(
        parent: tk.Misc,
        *,
        title: str,
        heading: str,
        device_name: str,
        default_port: str,
        baudrate: int,
        motor_id: int | None = None,
) -> SerialConnectionSettings | None:
    """Einheitlicher Verbindungsdialog fuer serielle Mower-II-Komponenten."""

    result: dict[str, SerialConnectionSettings | None] = {"settings": None}

    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.resizable(False, False)
    dialog.transient(parent)
    dialog.grab_set()

    has_motor_id = motor_id is not None
    _center_window(parent, dialog, 420, 260 if has_motor_id else 220)

    frame = ttk.Frame(dialog, padding=12)
    frame.grid(row=0, column=0, sticky="nsew")
    frame.grid_columnconfigure(1, weight=1)

    ttk.Label(frame, text=heading, font=("Segoe UI", 12, "bold")).grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 12)
    )

    ports = _list_serial_ports(default_port)

    ttk.Label(frame, text="Port:").grid(row=1, column=0, padx=(0, 8), pady=4, sticky="w")
    port_var = tk.StringVar(value=default_port)
    port_combo = ttk.Combobox(
        frame,
        textvariable=port_var,
        values=ports,
        state="normal",
        width=28,
    )
    port_combo.grid(row=1, column=1, padx=(0, 8), pady=4, sticky="ew")

    def refresh_ports() -> None:
        new_ports = _list_serial_ports(default_port)
        port_combo.configure(values=new_ports)
        if port_var.get().strip() == "" and new_ports:
            port_var.set(new_ports[0])

    ttk.Button(frame, text="Aktualisieren", command=refresh_ports).grid(
        row=1, column=2, pady=4, sticky="ew"
    )

    ttk.Label(frame, text="Baudrate:").grid(row=2, column=0, padx=(0, 8), pady=4, sticky="w")
    ttk.Label(frame, text=str(baudrate)).grid(
        row=2, column=1, columnspan=2, pady=4, sticky="w"
    )

    motor_id_var = tk.StringVar(value=str(motor_id if motor_id is not None else ""))
    info_row = 3
    if has_motor_id:
        ttk.Label(frame, text="Motor-ID:").grid(
            row=3, column=0, padx=(0, 8), pady=4, sticky="w"
        )
        motor_id_spinbox = ttk.Spinbox(
            frame,
            from_=0,
            to=255,
            textvariable=motor_id_var,
            width=10,
        )
        motor_id_spinbox.grid(row=3, column=1, columnspan=2, pady=4, sticky="w")
        info_row = 4

    info = (
        f"Waehle den COM-Port des {device_name}. "
        "Die Baudrate kommt aus der aktiven Config."
    )
    ttk.Label(frame, text=info, wraplength=380).grid(
        row=info_row,
        column=0,
        columnspan=3,
        pady=(8, 12),
        sticky="w",
    )

    buttons = ttk.Frame(frame)
    buttons.grid(row=info_row + 1, column=0, columnspan=3, sticky="ew")
    buttons.grid_columnconfigure(0, weight=1)
    buttons.grid_columnconfigure(1, weight=1)

    def accept() -> None:
        selected_port = port_var.get().strip()
        if not selected_port:
            messagebox.showerror(title, "Bitte einen Port angeben.", parent=dialog)
            return

        selected_motor_id: int | None = None
        if has_motor_id:
            try:
                selected_motor_id = int(motor_id_var.get().strip())
            except ValueError:
                messagebox.showerror(title, "Bitte eine gueltige Motor-ID angeben.", parent=dialog)
                return
            if not 0 <= selected_motor_id <= 255:
                messagebox.showerror(
                    title,
                    "Die Motor-ID muss zwischen 0 und 255 liegen.",
                    parent=dialog,
                )
                return

        result["settings"] = SerialConnectionSettings(
            port=selected_port,
            baudrate=int(baudrate),
            motor_id=selected_motor_id,
        )
        dialog.destroy()

    def cancel() -> None:
        result["settings"] = None
        dialog.destroy()

    ttk.Button(buttons, text="Verbinden", command=accept).grid(
        row=0, column=0, padx=(0, 6), sticky="ew"
    )
    ttk.Button(buttons, text="Abbrechen", command=cancel).grid(
        row=0, column=1, padx=(6, 0), sticky="ew"
    )

    dialog.bind("<Return>", lambda _event: accept())
    dialog.bind("<Escape>", lambda _event: cancel())
    dialog.protocol("WM_DELETE_WINDOW", cancel)

    port_combo.focus_set()
    parent.wait_window(dialog)

    return result["settings"]


def _list_serial_ports(default_port: str) -> list[str]:
    ports: list[str] = []

    try:
        from serial.tools import list_ports

        ports = [port.device for port in list_ports.comports()]
    except Exception:
        ports = []

    if default_port and default_port not in ports:
        ports.insert(0, default_port)

    return ports


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

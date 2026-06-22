# App/dialogs/xyz_connect_dialog.py

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk


def show_xyz_connect_dialog(
        parent: tk.Misc,
        *,
        default_port: str,
        baudrate: int,
) -> str | None:
    """Tk-Dialog zum Verbinden des XYZ-Roboters.

    Gibt den ausgewählten Port zurück oder None bei Abbruch.
    """

    result: dict[str, str | None] = {"port": None}

    dialog = tk.Toplevel(parent)
    dialog.title("XYZ verbinden")
    dialog.resizable(False, False)
    dialog.transient(parent)
    dialog.grab_set()

    _center_window(parent, dialog, 420, 220)

    frame = ttk.Frame(dialog, padding=12)
    frame.grid(row=0, column=0, sticky="nsew")
    frame.grid_columnconfigure(1, weight=1)

    ttk.Label(frame, text="XYZ verbinden", font=("Segoe UI", 12, "bold")).grid(
        row=0, column=0, columnspan=3, sticky="w", pady=(0, 12)
    )

    ports = _list_serial_ports(default_port)

    ttk.Label(frame, text="Port:").grid(row=1, column=0, padx=(0, 8), pady=4, sticky="w")
    port_var = tk.StringVar(value=default_port)
    port_combo = ttk.Combobox(frame, textvariable=port_var, values=ports, state="normal", width=28)
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
    ttk.Label(frame, text=str(baudrate)).grid(row=2, column=1, columnspan=2, pady=4, sticky="w")

    info = (
        "Wähle den COM-Port des XYZ-Roboters. "
        "Die Baudrate kommt aus der aktiven Config."
    )
    ttk.Label(frame, text=info, wraplength=380).grid(
        row=3, column=0, columnspan=3, pady=(8, 12), sticky="w"
    )

    buttons = ttk.Frame(frame)
    buttons.grid(row=4, column=0, columnspan=3, sticky="ew")
    buttons.grid_columnconfigure(0, weight=1)
    buttons.grid_columnconfigure(1, weight=1)

    def accept() -> None:
        port = port_var.get().strip()
        if not port:
            messagebox.showerror("XYZ verbinden", "Bitte einen Port angeben.", parent=dialog)
            return
        result["port"] = port
        dialog.destroy()

    def cancel() -> None:
        result["port"] = None
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

    return result["port"]


def _list_serial_ports(default_port: str) -> list[str]:
    ports: list[str] = []

    try:
        from serial.tools import list_ports

        ports = [p.device for p in list_ports.comports()]
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

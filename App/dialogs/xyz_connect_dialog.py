# App/dialogs/xyz_connect_dialog.py

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

try:
    from serial.tools import list_ports
except Exception:
    list_ports = None


def show_xyz_connect_dialog(
    *,
    parent: ctk.CTk,
    default_port: str,
    baudrate: int,
    log: Callable[[str], None],
) -> str | None:
    """
    Zeigt einen Dialog zur manuellen XYZ-Portauswahl.

    Returns:
        Gewaehlter Port, z. B. "COM5", oder None bei Abbruch.
    """

    selected_result: dict[str, str | None] = {"port": None}

    dialog_width = 520
    dialog_height = 300

    dialog = ctk.CTkToplevel(parent)
    dialog.title("XYZ verbinden")
    _center_toplevel(parent, dialog, dialog_width, dialog_height)
    dialog.transient(parent)
    dialog.grab_set()

    ctk.CTkLabel(
        dialog,
        text="XYZ-Roboter verbinden",
        font=ctk.CTkFont(size=18, weight="bold"),
    ).pack(padx=24, pady=(24, 8), anchor="w")

    ctk.CTkLabel(
        dialog,
        text=(
            "Wähle den seriellen Port für den XYZ-Roboter.\n"
            "Die Baudrate ist fest in der Config hinterlegt."
        ),
        justify="left",
        wraplength=460,
    ).pack(padx=24, pady=(0, 16), anchor="w")

    form_frame = ctk.CTkFrame(dialog)
    form_frame.pack(padx=24, pady=8, fill="x")
    form_frame.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(form_frame, text="Port:").grid(
        row=0,
        column=0,
        padx=10,
        pady=10,
        sticky="e",
    )

    port_items = _get_serial_port_items(default_port)
    display_to_port = {display: device for device, display in port_items}
    display_values = list(display_to_port.keys())

    default_display = display_values[0]

    for device, display in port_items:
        if device == default_port:
            default_display = display
            break

    selected_port_display = ctk.StringVar(value=default_display)

    port_menu = ctk.CTkOptionMenu(
        form_frame,
        values=display_values,
        variable=selected_port_display,
    )
    port_menu.grid(
        row=0,
        column=1,
        padx=10,
        pady=10,
        sticky="ew",
    )

    ctk.CTkLabel(form_frame, text="Baudrate:").grid(
        row=1,
        column=0,
        padx=10,
        pady=10,
        sticky="e",
    )

    ctk.CTkLabel(
        form_frame,
        text=str(baudrate),
        anchor="w",
    ).grid(
        row=1,
        column=1,
        padx=10,
        pady=10,
        sticky="w",
    )

    button_frame = ctk.CTkFrame(dialog)
    button_frame.pack(padx=24, pady=(18, 24), fill="x")
    button_frame.grid_columnconfigure((0, 1, 2), weight=1)

    def refresh_ports() -> None:
        nonlocal display_to_port

        refreshed_items = _get_serial_port_items(default_port)
        display_to_port = {display: device for device, display in refreshed_items}
        refreshed_values = list(display_to_port.keys())

        port_menu.configure(values=refreshed_values)

        if refreshed_values:
            selected_port_display.set(refreshed_values[0])

        log("Serielle Portliste aktualisiert.")

    def connect() -> None:
        display = selected_port_display.get()
        port = display_to_port.get(display)

        if not port:
            log("Kein gueltiger Port gewaehlt.")
            return

        selected_result["port"] = port
        dialog.destroy()

    def cancel() -> None:
        selected_result["port"] = None
        dialog.destroy()

    ctk.CTkButton(
        button_frame,
        text="Aktualisieren",
        command=refresh_ports,
    ).grid(row=0, column=0, padx=(0, 8), pady=10, sticky="ew")

    ctk.CTkButton(
        button_frame,
        text="Verbinden",
        command=connect,
    ).grid(row=0, column=1, padx=8, pady=10, sticky="ew")

    ctk.CTkButton(
        button_frame,
        text="Abbrechen",
        command=cancel,
    ).grid(row=0, column=2, padx=(8, 0), pady=10, sticky="ew")

    dialog.protocol("WM_DELETE_WINDOW", cancel)

    parent.wait_window(dialog)

    return selected_result["port"]


def _get_serial_port_items(default_port: str) -> list[tuple[str, str]]:
    """
    Returns:
        Liste aus (device, display_text)

        Beispiel:
            ("COM5", "COM5 - USB-SERIAL CH340")
    """

    if list_ports is None:
        return [(default_port, f"{default_port} (aus Config)")]

    ports: list[tuple[str, str]] = []

    for port in list_ports.comports():
        device = port.device
        description = port.description or ""

        if description and description != "n/a":
            display = f"{device} - {description}"
        else:
            display = device

        ports.append((device, display))

    devices = [device for device, _ in ports]

    if default_port and default_port not in devices:
        ports.insert(0, (default_port, f"{default_port} (aus Config)"))

    if not ports:
        ports.append((default_port, f"{default_port} (aus Config)"))

    return ports


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
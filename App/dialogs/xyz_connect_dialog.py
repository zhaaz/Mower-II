from __future__ import annotations

import tkinter as tk

from App.dialogs.serial_connect_dialog import show_serial_connect_dialog


def show_xyz_connect_dialog(
        parent: tk.Misc,
        *,
        default_port: str,
        baudrate: int,
) -> str | None:
    """Einheitlicher Dialog zum Verbinden des XYZ-Roboters."""

    settings = show_serial_connect_dialog(
        parent,
        title="XYZ verbinden",
        heading="XYZ verbinden",
        device_name="XYZ-Roboters",
        default_port=default_port,
        baudrate=baudrate,
    )
    return settings.port if settings is not None else None

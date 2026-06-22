# App/ui/classic_style.py

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

FONT_FAMILY = "Segoe UI"
FONT_SIZE_NORMAL = 10
FONT_SIZE_TITLE = 12
FONT_SIZE_SECTION = 11
FONT_SIZE_MONO = 10

FONT_NORMAL = (FONT_FAMILY, FONT_SIZE_NORMAL)
FONT_BOLD = (FONT_FAMILY, FONT_SIZE_NORMAL, "bold")
FONT_SECTION = (FONT_FAMILY, FONT_SIZE_SECTION, "bold")
FONT_TITLE = (FONT_FAMILY, FONT_SIZE_TITLE, "bold")
FONT_MONO = ("Consolas", FONT_SIZE_MONO)


def apply_classic_style(root: tk.Misc) -> None:
    """Apply one consistent classic ttk style for the operator UI."""
    try:
        root.option_add("*Font", FONT_NORMAL)
    except Exception:
        pass

    style = ttk.Style(root)

    # Use the Windows/native theme where available. This keeps controls close to
    # the operating system look and matches the classic operator UI.
    try:
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "xpnative" in style.theme_names():
            style.theme_use("xpnative")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
    except Exception:
        pass

    style.configure("TButton", font=FONT_NORMAL, padding=(8, 4))
    style.configure("TLabel", font=FONT_NORMAL)
    style.configure("TEntry", font=FONT_NORMAL)
    style.configure("TCombobox", font=FONT_NORMAL)
    style.configure("TLabelframe.Label", font=FONT_SECTION)
    style.configure("TCheckbutton", font=FONT_NORMAL)
    style.configure("TRadiobutton", font=FONT_NORMAL)

    style.configure("Operator.TButton", font=FONT_NORMAL, padding=(8, 4))
    style.configure("OperatorTitle.TLabel", font=FONT_TITLE)
    style.configure("OperatorSection.TLabel", font=FONT_SECTION)
    style.configure("OperatorMono.TLabel", font=FONT_MONO)

# App/widgets/menu_band.py

from __future__ import annotations

from typing import Any, Callable

import customtkinter as ctk


MenuEntry = tuple[str, str, Callable[[], None] | None]
MenuDefinition = tuple[str, list[MenuEntry]]


class MenuBand(ctk.CTkFrame):
    """
    Eigenes CustomTkinter-Menueband.

    Erwartetes Format:

        menu_definitions = [
            (
                "Datei",
                [
                    ("command", "Punkte laden...", callback),
                    ("separator", "", None),
                    ("command", "Beenden", callback),
                ],
            ),
        ]
    """

    def __init__(
        self,
        master: Any,
        menu_definitions: list[MenuDefinition],
        **kwargs: Any,
    ) -> None:
        super().__init__(
            master,
            corner_radius=0,
            fg_color=("#e7e7e7", "#1f1f1f"),
            **kwargs,
        )

        self.menu_definitions = menu_definitions

        self.active_menu_popup: ctk.CTkFrame | None = None
        self.active_menu_label: str | None = None

        self.grid_columnconfigure(99, weight=1)

        self._build()

    def _build(self) -> None:
        for column, (label, entries) in enumerate(self.menu_definitions):
            self._add_menu_button(column, label, entries)

    def _add_menu_button(
        self,
        column: int,
        label: str,
        entries: list[MenuEntry],
    ) -> None:
        button = ctk.CTkButton(
            self,
            text=label,
            width=92 if label != "Mower / System" else 150,
            height=34,
            corner_radius=0,
            fg_color="transparent",
            hover_color=("#d8e9f8", "#24384a"),
            text_color=("#111111", "#f2f2f2"),
        )

        button.configure(
            command=lambda b=button, b_label=label, b_entries=entries: self._toggle_menu_dropdown(
                b,
                b_label,
                b_entries,
            )
        )

        button.grid(
            row=0,
            column=column,
            padx=(4 if column == 0 else 0, 0),
            pady=3,
            sticky="w",
        )

    def _toggle_menu_dropdown(
        self,
        anchor_button: ctk.CTkButton,
        label: str,
        entries: list[MenuEntry],
    ) -> None:
        if self.active_menu_popup is not None and self.active_menu_label == label:
            self.close_dropdown()
            return

        self._open_menu_dropdown(anchor_button, label, entries)

    def _open_menu_dropdown(
        self,
        anchor_button: ctk.CTkButton,
        label: str,
        entries: list[MenuEntry],
    ) -> None:
        self.close_dropdown()

        width = 260 if label != "Mower / System" else 300

        popup = ctk.CTkFrame(
            self.master,
            width=width,
            fg_color=("#f4f4f4", "#202020"),
            corner_radius=8,
            border_width=1,
            border_color=("#c8c8c8", "#404040"),
        )

        ctk.CTkLabel(
            popup,
            text=label,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
            text_color=("#111111", "#f2f2f2"),
        ).pack(fill="x", padx=10, pady=(8, 4))

        for kind, item_label, callback in entries:
            if kind == "separator":
                ctk.CTkFrame(
                    popup,
                    height=1,
                    fg_color=("#d0d0d0", "#4a4a4a"),
                ).pack(fill="x", padx=8, pady=4)
                continue

            def run_action(cb=callback) -> None:
                self.close_dropdown()
                if cb is not None:
                    cb()

            ctk.CTkButton(
                popup,
                text=item_label,
                anchor="w",
                height=30,
                corner_radius=4,
                fg_color="transparent",
                hover_color=("#d8e9f8", "#1f6aa5"),
                text_color=("#111111", "#f2f2f2"),
                command=run_action,
            ).pack(fill="x", padx=6, pady=1)

        popup.update_idletasks()

        parent = self.master

        x = anchor_button.winfo_rootx() - parent.winfo_rootx()
        y = (
            anchor_button.winfo_rooty()
            - parent.winfo_rooty()
            + anchor_button.winfo_height()
            + 2
        )

        popup.place(x=x, y=y)
        popup.grid_columnconfigure(0, weight=1)
        popup.lift()

        self.active_menu_popup = popup
        self.active_menu_label = label

    def close_dropdown(self) -> None:
        if self.active_menu_popup is not None:
            try:
                self.active_menu_popup.destroy()
            except Exception:
                pass
            finally:
                self.active_menu_popup = None
                self.active_menu_label = None
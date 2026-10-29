from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from App.services.flexible_point_import import (
    FlexibleImportSettings,
    load_points_flexible,
    preview_rows,
    read_source_text,
)
from App.stakeout_point import StakeoutPoint


SEPARATOR_LABELS: dict[str, str] = {
    "Leerraum": "whitespace",
    "Semikolon (;)": ";",
    "Komma (, )": ",",
    "Tabulator": "\t",
    "Eigenes Zeichen": "custom",
}
AUTO_ID = "Laufende Nummer"
FIXED_REMARK = "Fester Kommentar"
MARKER_LABELS = {
    1: "1 – Plus (+)",
    2: "2 – Kreuz (x)",
    3: "3 – Kreis mit Mittelpunkt",
    4: "4 – Plus mit Kreis",
}


class FreePointImportDialog(tk.Toplevel):
    """Freier Import mit Rohdaten- und Ergebnisvorschau."""

    def __init__(self, parent: tk.Misc, path: str | Path) -> None:
        super().__init__(parent)
        self.path = Path(path)
        self.result: list[StakeoutPoint] | None = None
        self._refresh_job: str | None = None

        self.title(f"Freier Import – {self.path.name}")
        self.geometry("1220x820")
        self.minsize(1000, 680)
        self.transient(parent)
        self.grab_set()

        self.separator_var = tk.StringVar(value="Leerraum")
        self.custom_separator_var = tk.StringVar(value="|")
        self.skip_rows_var = tk.StringVar(value="0")
        self.decimal_var = tk.StringVar(value=".")

        self.id_source_var = tk.StringVar(value=AUTO_ID)
        self.id_prefix_var = tk.StringVar(value="P")
        self.id_start_var = tk.StringVar(value="1")
        self.x_source_var = tk.StringVar(value="Spalte 1")
        self.y_source_var = tk.StringVar(value="Spalte 2")
        self.z_source_var = tk.StringVar(value="Spalte 3")
        self.marker_source_var = tk.StringVar(value=MARKER_LABELS[1])
        self.remark_source_var = tk.StringVar(value=FIXED_REMARK)
        self.fixed_remark_var = tk.StringVar(value="")
        self.preview_status_var = tk.StringVar(value="")

        self._column_boxes: list[ttk.Combobox] = []
        self._build_ui()
        self._load_source_preview()
        self._bind_updates()
        self._refresh_preview()

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.after_idle(self._center_on_parent)
        self.wait_window(self)

    def _build_ui(self) -> None:
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        file_frame = ttk.LabelFrame(self, text="Dateiaufbau", padding=8)
        file_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        for column in range(8):
            file_frame.columnconfigure(column, weight=1 if column in {0, 1, 4} else 0)

        ttk.Label(file_frame, text="Datei").grid(row=0, column=0, sticky="w")
        ttk.Label(file_frame, text=str(self.path)).grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=(0, 12)
        )
        ttk.Label(file_frame, text="Trennzeichen").grid(row=0, column=2, sticky="w")
        separator_box = ttk.Combobox(
            file_frame,
            textvariable=self.separator_var,
            values=tuple(SEPARATOR_LABELS),
            state="readonly",
            width=17,
        )
        separator_box.grid(row=1, column=2, sticky="w", padx=(0, 8))

        ttk.Label(file_frame, text="Eigenes Zeichen").grid(row=0, column=3, sticky="w")
        ttk.Entry(file_frame, textvariable=self.custom_separator_var, width=8).grid(
            row=1, column=3, sticky="w", padx=(0, 8)
        )
        ttk.Label(file_frame, text="Kopfzeilen überspringen").grid(row=0, column=4, sticky="w")
        ttk.Spinbox(
            file_frame,
            from_=0,
            to=100000,
            textvariable=self.skip_rows_var,
            width=10,
        ).grid(row=1, column=4, sticky="w", padx=(0, 8))
        ttk.Label(file_frame, text="Dezimalzeichen").grid(row=0, column=5, sticky="w")
        ttk.Combobox(
            file_frame,
            textvariable=self.decimal_var,
            values=(".", ","),
            state="readonly",
            width=6,
        ).grid(row=1, column=5, sticky="w")

        mapping = ttk.LabelFrame(self, text="Zuordnung und Vorgaben", padding=8)
        mapping.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        for column in range(9):
            mapping.columnconfigure(column, weight=1)

        labels = (
            "Punkt-ID", "Präfix", "Start", "X *", "Y *", "Z *", "Markierung", "Kommentarquelle"
        )
        for column, label in enumerate(labels):
            ttk.Label(mapping, text=label).grid(row=0, column=column, sticky="w", padx=(0, 6))

        self.id_box = ttk.Combobox(
            mapping, textvariable=self.id_source_var, state="readonly", width=18
        )
        self.id_box.grid(row=1, column=0, sticky="ew", padx=(0, 6))
        self.id_prefix_entry = ttk.Entry(mapping, textvariable=self.id_prefix_var, width=8)
        self.id_prefix_entry.grid(row=1, column=1, sticky="ew", padx=(0, 6))
        self.id_start_spinbox = ttk.Spinbox(
            mapping, from_=0, to=999999999, textvariable=self.id_start_var, width=9
        )
        self.id_start_spinbox.grid(row=1, column=2, sticky="ew", padx=(0, 6))

        self.x_box = self._mapping_box(mapping, self.x_source_var, 3)
        self.y_box = self._mapping_box(mapping, self.y_source_var, 4)
        self.z_box = self._mapping_box(mapping, self.z_source_var, 5)
        self.marker_box = ttk.Combobox(
            mapping, textvariable=self.marker_source_var, state="readonly", width=23
        )
        self.marker_box.grid(row=1, column=6, sticky="ew", padx=(0, 6))
        self.remark_box = ttk.Combobox(
            mapping, textvariable=self.remark_source_var, state="readonly", width=20
        )
        self.remark_box.grid(row=1, column=7, sticky="ew", padx=(0, 6))
        self._column_boxes.extend([self.id_box, self.marker_box, self.remark_box])

        ttk.Label(mapping, text="Kommentartext").grid(row=0, column=8, sticky="w")
        self.remark_entry = ttk.Entry(mapping, textvariable=self.fixed_remark_var, width=22)
        self.remark_entry.grid(row=1, column=8, sticky="ew")
        ttk.Label(mapping, text="* Pflichtfeld").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        ttk.Label(
            mapping,
            text="Ohne ID-Spalte werden IDs aus Präfix und laufender Nummer gebildet (z. B. P1, P2, …).",
        ).grid(row=2, column=2, columnspan=7, sticky="w", pady=(6, 0))

        previews = ttk.Panedwindow(self, orient="vertical")
        previews.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)

        source_frame = ttk.LabelFrame(previews, text="Vorschau der geladenen Datei", padding=6)
        source_frame.grid_rowconfigure(0, weight=1)
        source_frame.grid_columnconfigure(0, weight=1)
        self.source_text = tk.Text(
            source_frame,
            wrap="none",
            height=10,
            font=("Consolas", 9),
            background="#ffffff",
            foreground="#202020",
        )
        source_y = ttk.Scrollbar(source_frame, orient="vertical", command=self.source_text.yview)
        source_x = ttk.Scrollbar(source_frame, orient="horizontal", command=self.source_text.xview)
        self.source_text.configure(yscrollcommand=source_y.set, xscrollcommand=source_x.set)
        self.source_text.grid(row=0, column=0, sticky="nsew")
        source_y.grid(row=0, column=1, sticky="ns")
        source_x.grid(row=1, column=0, sticky="ew")

        result_frame = ttk.LabelFrame(previews, text="Vorschau der Importdaten", padding=6)
        result_frame.grid_rowconfigure(0, weight=1)
        result_frame.grid_columnconfigure(0, weight=1)
        columns = ("id", "x", "y", "z", "marker", "remark")
        self.result_tree = ttk.Treeview(result_frame, columns=columns, show="headings", height=10)
        headings = {
            "id": "ID", "x": "X", "y": "Y", "z": "Z", "marker": "Markierung", "remark": "Kommentar"
        }
        widths = {"id": 120, "x": 145, "y": 145, "z": 145, "marker": 115, "remark": 300}
        for column in columns:
            self.result_tree.heading(column, text=headings[column])
            self.result_tree.column(column, width=widths[column], minwidth=70, stretch=True)
        result_y = ttk.Scrollbar(result_frame, orient="vertical", command=self.result_tree.yview)
        result_x = ttk.Scrollbar(result_frame, orient="horizontal", command=self.result_tree.xview)
        self.result_tree.configure(yscrollcommand=result_y.set, xscrollcommand=result_x.set)
        self.result_tree.grid(row=0, column=0, sticky="nsew")
        result_y.grid(row=0, column=1, sticky="ns")
        result_x.grid(row=1, column=0, sticky="ew")
        self.preview_status_label = ttk.Label(result_frame, textvariable=self.preview_status_var)
        self.preview_status_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(5, 0))

        previews.add(source_frame, weight=1)
        previews.add(result_frame, weight=1)

        footer = ttk.Frame(self, padding=(10, 5, 10, 10))
        footer.grid(row=3, column=0, sticky="ew")
        ttk.Button(footer, text="Abbrechen", command=self._cancel).pack(side="right")
        ttk.Button(footer, text="Punkte importieren", command=self._import).pack(
            side="right", padx=(0, 8)
        )

    def _mapping_box(
            self,
            parent: tk.Misc,
            variable: tk.StringVar,
            column: int,
    ) -> ttk.Combobox:
        box = ttk.Combobox(parent, textvariable=variable, state="readonly", width=13)
        box.grid(row=1, column=column, sticky="ew", padx=(0, 6))
        self._column_boxes.append(box)
        return box

    def _load_source_preview(self) -> None:
        text = read_source_text(self.path)
        lines = text.splitlines()
        shown = lines[:2000]
        display = "\n".join(f"{index:>6}  {line}" for index, line in enumerate(shown, 1))
        if len(lines) > len(shown):
            display += f"\n\n… Vorschau nach {len(shown)} von {len(lines)} Zeilen gekürzt …"
        self.source_text.insert("1.0", display)
        self.source_text.configure(state="disabled")

    def _bind_updates(self) -> None:
        variables = (
            self.separator_var,
            self.custom_separator_var,
            self.skip_rows_var,
            self.decimal_var,
            self.id_source_var,
            self.id_prefix_var,
            self.id_start_var,
            self.x_source_var,
            self.y_source_var,
            self.z_source_var,
            self.marker_source_var,
            self.remark_source_var,
            self.fixed_remark_var,
        )
        for variable in variables:
            variable.trace_add("write", self._schedule_refresh)

    def _schedule_refresh(self, *_args: object) -> None:
        if self._refresh_job is not None:
            self.after_cancel(self._refresh_job)
        self._refresh_job = self.after(120, self._refresh_preview)

    def _delimiter(self) -> str:
        selected = SEPARATOR_LABELS.get(self.separator_var.get(), "whitespace")
        return self.custom_separator_var.get() if selected == "custom" else selected

    def _refresh_preview(self) -> None:
        self._refresh_job = None
        try:
            skip_rows = int(self.skip_rows_var.get())
            rows = preview_rows(self.path, self._delimiter(), max(skip_rows, 0))
            column_count = max((len(row.columns) for row in rows), default=3)
            self._update_column_options(column_count)
            settings = self._settings()
            points = load_points_flexible(self.path, settings)
        except Exception as exc:
            self._clear_result_tree()
            self.preview_status_var.set(f"Vorschau nicht möglich: {exc}")
            self.preview_status_label.configure(foreground="#b00020")
            self._update_entry_states()
            return

        self._clear_result_tree()
        shown = points[:200]
        for point in shown:
            self.result_tree.insert(
                "",
                "end",
                values=(
                    point.name,
                    _format_coordinate(point.x),
                    _format_coordinate(point.y),
                    _format_coordinate(point.z),
                    MARKER_LABELS[point.marker_code],
                    point.remark,
                ),
            )
        suffix = f"; Vorschau zeigt die ersten {len(shown)}" if len(points) > len(shown) else ""
        self.preview_status_var.set(f"{len(points)} Punkt(e) importierbar{suffix}.")
        self.preview_status_label.configure(foreground="#1f6b2a")
        self._update_entry_states()

    def _update_column_options(self, column_count: int) -> None:
        columns = [f"Spalte {index}" for index in range(1, column_count + 1)]
        self.id_box.configure(values=(AUTO_ID, *columns))
        self.x_box.configure(values=columns)
        self.y_box.configure(values=columns)
        self.z_box.configure(values=columns)
        self.marker_box.configure(values=(*MARKER_LABELS.values(), *columns))
        self.remark_box.configure(values=(FIXED_REMARK, *columns))

        defaults = (
            (self.id_source_var, AUTO_ID),
            (self.x_source_var, columns[0]),
            (self.y_source_var, columns[min(1, len(columns) - 1)]),
            (self.z_source_var, columns[min(2, len(columns) - 1)]),
            (self.marker_source_var, MARKER_LABELS[1]),
            (self.remark_source_var, FIXED_REMARK),
        )
        allowed = {
            id(self.id_source_var): {AUTO_ID, *columns},
            id(self.x_source_var): set(columns),
            id(self.y_source_var): set(columns),
            id(self.z_source_var): set(columns),
            id(self.marker_source_var): {*MARKER_LABELS.values(), *columns},
            id(self.remark_source_var): {FIXED_REMARK, *columns},
        }
        for variable, fallback in defaults:
            if variable.get() not in allowed[id(variable)]:
                variable.set(fallback)

    def _settings(self) -> FlexibleImportSettings:
        marker_value = self.marker_source_var.get()
        marker_column = self._column_index(marker_value) if marker_value.startswith("Spalte ") else None
        fixed_marker = 1
        if marker_column is None:
            fixed_marker = next(
                (code for code, label in MARKER_LABELS.items() if label == marker_value),
                1,
            )
        remark_value = self.remark_source_var.get()
        remark_column = self._column_index(remark_value) if remark_value.startswith("Spalte ") else None
        id_value = self.id_source_var.get()
        id_column = self._column_index(id_value) if id_value.startswith("Spalte ") else None
        return FlexibleImportSettings(
            delimiter=self._delimiter(),
            skip_rows=int(self.skip_rows_var.get()),
            decimal_separator=self.decimal_var.get(),
            id_column=id_column,
            id_prefix=self.id_prefix_var.get(),
            id_start=int(self.id_start_var.get()),
            x_column=self._required_column(self.x_source_var.get(), "X"),
            y_column=self._required_column(self.y_source_var.get(), "Y"),
            z_column=self._required_column(self.z_source_var.get(), "Z"),
            marker_column=marker_column,
            fixed_marker_code=fixed_marker,
            remark_column=remark_column,
            fixed_remark=self.fixed_remark_var.get(),
        )

    @staticmethod
    def _column_index(value: str) -> int:
        if not value.startswith("Spalte "):
            raise ValueError(f"Ungültige Spaltenauswahl: {value}")
        return int(value.removeprefix("Spalte ")) - 1

    def _required_column(self, value: str, field: str) -> int:
        if not value.startswith("Spalte "):
            raise ValueError(f"{field} muss einer Spalte zugeordnet sein.")
        return self._column_index(value)

    def _update_entry_states(self) -> None:
        automatic_id = self.id_source_var.get() == AUTO_ID
        id_state = "normal" if automatic_id else "disabled"
        self.id_prefix_entry.configure(state=id_state)
        self.id_start_spinbox.configure(state=id_state)
        self.remark_entry.configure(
            state="normal" if self.remark_source_var.get() == FIXED_REMARK else "disabled"
        )

    def _clear_result_tree(self) -> None:
        self.result_tree.delete(*self.result_tree.get_children())

    def _import(self) -> None:
        try:
            points = load_points_flexible(self.path, self._settings())
        except Exception as exc:
            messagebox.showerror("Freier Import", str(exc), parent=self)
            return
        self.result = points
        self.grab_release()
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def _center_on_parent(self) -> None:
        self.update_idletasks()
        parent = self.master
        if parent is None:
            return
        x = parent.winfo_rootx() + max((parent.winfo_width() - self.winfo_width()) // 2, 0)
        y = parent.winfo_rooty() + max((parent.winfo_height() - self.winfo_height()) // 2, 0)
        self.geometry(f"+{x}+{y}")


def _format_coordinate(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6f}".rstrip("0").rstrip(".")


def show_free_point_import_dialog(
        parent: tk.Misc,
        path: str | Path,
) -> list[StakeoutPoint] | None:
    return FreePointImportDialog(parent, path).result

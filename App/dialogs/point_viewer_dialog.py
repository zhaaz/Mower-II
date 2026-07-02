# App/dialogs/point_viewer_dialog.py

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable


RefreshCallback = Callable[[], None]

FONT_NORMAL = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SECTION = ("Segoe UI", 11, "bold")
FONT_MONO = ("Consolas", 10)


POINT_VIEW_FIELDS: list[tuple[str, str]] = [
    ("name", "Punkt"),
    ("x", "X Soll"),
    ("y", "Y Soll"),
    ("z", "Z Soll"),
    ("marked", "Markiert"),
    ("reachable", "Erreichbar"),
    ("last_robot_x", "Robot X"),
    ("last_robot_y", "Robot Y"),
    ("residual_mm", "Residual"),
    ("measured_after_marking", "Gemessen"),
    ("measured_marker_lt_x", "Mess X"),
    ("measured_marker_lt_y", "Mess Y"),
    ("measured_marker_lt_z", "Mess Z"),
    ("measurement_dx", "dX"),
    ("measurement_dy", "dY"),
    ("measurement_dz", "dZ"),
    ("measurement_d2d", "d2D"),
    ("measurement_d3d", "d3D"),
    ("measurement_robot_z_mm", "Mess-Z"),
    ("measurement_z_correction_mm", "Z-Korr."),
    ("measurement_attempts", "Messversuche"),
    ("measurement_retry_threshold_mm", "Grenze d2D"),
    ("measurement_valid", "Messung OK"),
    ("measurement_warning", "Messwarnung"),
    ("measurement_method", "Messmethode"),
    ("measured_at", "Gemessen am"),
    ("marker_shape", "Form"),
    ("marker_code", "Code"),
    ("remark", "Bemerkung"),
]


def show_point_viewer_dialog(
        *,
        parent: tk.Misc,
        points: list[Any],
        on_refresh: RefreshCallback | None = None,
) -> None:
    dialog = PointViewerDialog(parent=parent, points=points, on_refresh=on_refresh)
    dialog.show()


class PointViewerDialog:
    def __init__(
            self,
            *,
            parent: tk.Misc,
            points: list[Any],
            on_refresh: RefreshCallback | None = None,
    ) -> None:
        self.parent = parent
        self.points = points
        self.on_refresh = on_refresh
        self.point_by_iid: dict[str, Any] = {}

        self.window = tk.Toplevel(parent)
        self.window.title("Punktviewer")
        self.window.minsize(980, 620)
        self.window.transient(parent)

        _center_window(parent, self.window, 1180, 720)
        self._configure_styles()
        self._build_ui()
        self.refresh_table()

        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())

    def show(self) -> None:
        self.window.lift()
        self.window.focus_set()

    def _configure_styles(self) -> None:
        style = ttk.Style(self.window)
        style.configure("PointViewer.TLabel", font=FONT_NORMAL)
        style.configure("PointViewerBold.TLabel", font=FONT_BOLD)
        style.configure("PointViewer.TButton", font=FONT_NORMAL, padding=(8, 4))
        style.configure("PointViewer.TLabelframe.Label", font=FONT_SECTION)
        style.configure("PointViewer.Treeview", font=FONT_NORMAL, rowheight=24)
        style.configure("PointViewer.Treeview.Heading", font=FONT_BOLD)

    def _build_ui(self) -> None:
        root = ttk.Frame(self.window, padding=12)
        root.grid(row=0, column=0, sticky="nsew")
        self.window.grid_rowconfigure(0, weight=1)
        self.window.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)
        root.grid_columnconfigure(0, weight=1)

        header = ttk.Frame(root)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.grid_columnconfigure(0, weight=1)

        self.summary_var = tk.StringVar(value="")
        ttk.Label(header, textvariable=self.summary_var, style="PointViewerBold.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(header, text="Aktualisieren", command=self.refresh_table, style="PointViewer.TButton").grid(
            row=0, column=1, padx=(8, 0), sticky="e"
        )
        ttk.Button(header, text="Schliessen", command=self.close, style="PointViewer.TButton").grid(
            row=0, column=2, padx=(8, 0), sticky="e"
        )

        body = ttk.Panedwindow(root, orient="vertical")
        body.grid(row=1, column=0, sticky="nsew")

        table_frame = ttk.LabelFrame(body, text="Punkte", padding=8, style="PointViewer.TLabelframe")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        body.add(table_frame, weight=3)

        columns = [key for key, _label in POINT_VIEW_FIELDS]
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="PointViewer.Treeview",
        )
        for key, label in POINT_VIEW_FIELDS:
            self.tree.heading(key, text=label)
            width = 100
            anchor = "e"
            if key in {"name", "measurement_method", "measured_at", "marker_shape", "marker_code", "remark", "measurement_warning"}:
                width = 150
                anchor = "w"
            if key in {"marked", "reachable", "measured_after_marking"}:
                width = 85
                anchor = "center"
            self.tree.column(key, width=width, minwidth=70, stretch=False, anchor=anchor)

        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self.on_selection_changed)

        y_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        detail_frame = ttk.LabelFrame(body, text="Details", padding=8, style="PointViewer.TLabelframe")
        detail_frame.grid_rowconfigure(0, weight=1)
        detail_frame.grid_columnconfigure(0, weight=1)
        body.add(detail_frame, weight=1)

        self.detail_text = ScrolledText(
            detail_frame,
            wrap="none",
            height=10,
            font=FONT_MONO,
            background="#ffffff",
            foreground="#111111",
        )
        self.detail_text.grid(row=0, column=0, sticky="nsew")

    def refresh_table(self) -> None:
        if self.on_refresh:
            try:
                self.on_refresh()
            except Exception:
                pass

        for item in self.tree.get_children():
            self.tree.delete(item)
        self.point_by_iid.clear()

        marked_count = 0
        measured_count = 0
        for index, point in enumerate(self.points):
            iid = str(index)
            self.point_by_iid[iid] = point
            if bool(getattr(point, "marked", False)):
                marked_count += 1
            if bool(getattr(point, "measured_after_marking", False)):
                measured_count += 1
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=[self._format_value(getattr(point, key, "")) for key, _label in POINT_VIEW_FIELDS],
            )

        self.summary_var.set(
            f"{len(self.points)} Punkt(e) | {marked_count} markiert | {measured_count} automatisch gemessen"
        )
        first = self.tree.get_children()
        if first:
            self.tree.selection_set(first[0])
            self.tree.focus(first[0])
            self.show_point_details(self.point_by_iid[first[0]])
        else:
            self.show_text("Keine Punkte geladen.")

    def on_selection_changed(self, _event: tk.Event) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        point = self.point_by_iid.get(selection[0])
        if point is not None:
            self.show_point_details(point)

    def show_point_details(self, point: Any) -> None:
        lines: list[str] = []
        lines.append("Punktdetails")
        lines.append("=" * 80)
        for key, label in POINT_VIEW_FIELDS:
            lines.append(f"{label:<24}: {self._format_value(getattr(point, key, ''))}")

        extra_keys = sorted(
            key for key in vars(point).keys()
            if key not in {field for field, _label in POINT_VIEW_FIELDS}
        ) if hasattr(point, "__dict__") else []
        if extra_keys:
            lines.append("")
            lines.append("Weitere Attribute")
            lines.append("-" * 80)
            for key in extra_keys:
                lines.append(f"{key:<24}: {self._format_value(getattr(point, key, ''))}")
        self.show_text("\n".join(lines))

    def show_text(self, text: str) -> None:
        try:
            self.detail_text.configure(state="normal")
            self.detail_text.delete("1.0", "end")
            self.detail_text.insert("end", text)
            self.detail_text.configure(state="disabled")
        except Exception:
            pass

    @staticmethod
    def _format_value(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "ja" if value else "nein"
        if isinstance(value, float):
            return f"{value:.6f}"
        return str(value).replace("\n", " ")

    def close(self) -> None:
        self.window.destroy()


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

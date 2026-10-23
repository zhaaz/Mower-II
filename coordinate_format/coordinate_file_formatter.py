from __future__ import annotations

import csv
import math
import re
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


OUTPUT_HEADER = (
    "// Mower II Punktimport",
    "// Format: punktnummer x y z bemerkung // Kommentar",
    "// XYZ in mm",
    "// Point. X. Y. Z. Bemerkung",
)

MARKER_LABELS: dict[int, str] = {
    1: "Plus (+)",
    2: "Kreuz (x)",
    3: "Kreis mit Mittelpunkt",
    4: "Plus mit Kreis",
}


@dataclass
class CoordinateRow:
    name: str
    x: str
    y: str
    z: str
    marker_code: int = 1
    text: str = ""


@dataclass(frozen=True)
class CoordinateTransform:
    """Starre 3D-Transformation mit Massstab 1.

    Die Rotationen werden in dieser Reihenfolge auf den Punkt angewendet:
    RX, danach RY, danach RZ. In Matrixschreibweise gilt damit:

        P_neu = RZ * RY * RX * P_alt + [X, Y, Z]
    """

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    rx_deg: float = 0.0
    ry_deg: float = 0.0
    rz_deg: float = 0.0

    def apply(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        rx = math.radians(self.rx_deg)
        ry = math.radians(self.ry_deg)
        rz = math.radians(self.rz_deg)

        # 1. Rotation um X
        x1 = x
        y1 = math.cos(rx) * y - math.sin(rx) * z
        z1 = math.sin(rx) * y + math.cos(rx) * z

        # 2. Rotation um Y
        x2 = math.cos(ry) * x1 + math.sin(ry) * z1
        y2 = y1
        z2 = -math.sin(ry) * x1 + math.cos(ry) * z1

        # 3. Rotation um Z
        x3 = math.cos(rz) * x2 - math.sin(rz) * y2
        y3 = math.sin(rz) * x2 + math.cos(rz) * y2
        z3 = z2

        return x3 + self.x, y3 + self.y, z3 + self.z

    def is_identity(self, tolerance: float = 1e-15) -> bool:
        return all(
            abs(value) <= tolerance
            for value in (self.x, self.y, self.z, self.rx_deg, self.ry_deg, self.rz_deg)
        )


def parse_raw_coordinate_file(path: str | Path) -> list[CoordinateRow]:
    """Liest eine rohe Koordinatendatei mit Name, X, Y und Z."""

    source = Path(path)
    content = _read_text(source)
    rows: list[CoordinateRow] = []

    for line_number, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("#"):
            continue

        parts = _split_raw_line(stripped)
        if len(parts) != 4:
            raise ValueError(
                f"Zeile {line_number}: Erwartet werden genau vier Werte "
                f"(Punktname, X, Y, Z), gefunden wurden {len(parts)}."
            )

        name, x, y, z = (part.strip() for part in parts)
        if not name:
            raise ValueError(f"Zeile {line_number}: Der Punktname fehlt.")
        if any(char.isspace() for char in name):
            raise ValueError(
                f"Zeile {line_number}: Der Punktname darf keine Leerzeichen enthalten: {name!r}"
            )

        for axis, value in (("X", x), ("Y", y), ("Z", z)):
            try:
                float(value.replace(",", "."))
            except ValueError as exc:
                raise ValueError(
                    f"Zeile {line_number}: {axis} ist keine gueltige Zahl: {value!r}"
                ) from exc

        rows.append(
            CoordinateRow(
                name=name,
                x=_normalize_number_text(x),
                y=_normalize_number_text(y),
                z=_normalize_number_text(z),
            )
        )

    if not rows:
        raise ValueError("Die Datei enthaelt keine Koordinatenzeilen.")

    return rows


def format_coordinate_rows(
        rows: list[CoordinateRow],
        transform: CoordinateTransform | None = None,
) -> str:
    """Erzeugt das vom Mower-II-Punktimport erwartete Textformat."""

    lines = [*OUTPUT_HEADER, ""]

    for index, row in enumerate(rows, start=1):
        if row.marker_code not in MARKER_LABELS:
            raise ValueError(
                f"Zeile {index}: Unbekannte Markierungskennziffer {row.marker_code}. "
                "Erlaubt sind 1 bis 4."
            )

        text = validate_output_text(row.text, row_name=row.name)
        x, y, z = transformed_coordinate_text(row, transform)
        lines.append(
            f'{row.name}  {x}  {y}  {z} {row.marker_code} "{text}"'
        )

    return "\n".join(lines) + "\n"


def save_formatted_coordinate_file(
        path: str | Path,
        rows: list[CoordinateRow],
        transform: CoordinateTransform | None = None,
) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = format_coordinate_rows(rows, transform=transform)

    # CRLF entspricht den vorhandenen Mower-II-Beispieldateien und laesst sich
    # unter Windows in allen gaengigen Editoren sauber oeffnen.
    with target.open("w", encoding="utf-8", newline="") as file:
        file.write(content.replace("\n", "\r\n"))


def validate_output_text(text: str, *, row_name: str = "") -> str:
    value = str(text)
    if '"' in value:
        suffix = f" bei Punkt {row_name}" if row_name else ""
        raise ValueError(
            f'Der Text{suffix} darf kein doppeltes Anfuehrungszeichen (") enthalten.'
        )
    if "\r" in value or "\n" in value:
        suffix = f" bei Punkt {row_name}" if row_name else ""
        raise ValueError(f"Der Text{suffix} darf keinen Zeilenumbruch enthalten.")
    return value


def transformed_coordinates(
        row: CoordinateRow,
        transform: CoordinateTransform | None,
) -> tuple[float, float, float]:
    x = float(row.x)
    y = float(row.y)
    z = float(row.z)

    if transform is None:
        return x, y, z
    return transform.apply(x, y, z)


def transformed_coordinate_text(
        row: CoordinateRow,
        transform: CoordinateTransform | None,
) -> tuple[str, str, str]:
    # Ohne Transformation bleiben Schreibweise und Nachkommastellen der
    # Raw-Datei unveraendert.
    if transform is None or transform.is_identity():
        return row.x, row.y, row.z

    return tuple(_format_transformed_number(value) for value in transformed_coordinates(row, transform))


def suggested_output_name(input_path: str | Path) -> str:
    source = Path(input_path)
    stem = source.stem
    if stem.lower().endswith("_raw"):
        stem = stem[:-4]
    return f"{stem}.txt"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="cp1252")


def _split_raw_line(line: str) -> list[str]:
    if line.count(",") >= 3:
        return next(csv.reader([line], skipinitialspace=True))

    # Alternativ werden Semikolon, Tabulatoren oder Leerzeichen akzeptiert.
    return [part for part in re.split(r"[;\t ]+", line) if part]


def _normalize_number_text(value: str) -> str:
    return value.strip().replace(",", ".")


def _format_transformed_number(value: float) -> str:
    # Negative Nullwerte vermeiden, die durch Rundungsfehler bei Rotationen
    # entstehen koennen.
    if abs(value) < 0.0000005:
        value = 0.0
    return f"{value:.6f}"


class CoordinateFormatterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Mower II - Koordinatendatei formatieren")
        self.root.minsize(820, 520)

        self.rows: list[CoordinateRow] = []
        self.input_path: Path | None = None

        self.input_path_var = tk.StringVar(value="Keine Datei geladen")
        self.marker_var = tk.StringVar(value=self._marker_display(1))
        self.text_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Bitte eine Raw-Datei oeffnen.")
        self.transform_status_var = tk.StringVar(value="Keine Transformation: alle Werte sind 0.")
        self.transform_vars: dict[str, tk.StringVar] = {
            "x": tk.StringVar(value="0.0"),
            "y": tk.StringVar(value="0.0"),
            "z": tk.StringVar(value="0.0"),
            "rx": tk.StringVar(value="0.0"),
            "ry": tk.StringVar(value="0.0"),
            "rz": tk.StringVar(value="0.0"),
        }
        self.active_transform = CoordinateTransform()

        self._configure_style()
        self._build_ui()
        self._bind_transform_updates()
        self._center_window(1180, 720)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            if "vista" in style.theme_names():
                style.theme_use("vista")
            elif "clam" in style.theme_names():
                style.theme_use("clam")
        except Exception:
            pass

        style.configure("TButton", padding=(8, 5))
        style.configure("Treeview", rowheight=25)

    def _build_ui(self) -> None:
        root_frame = ttk.Frame(self.root, padding=12)
        root_frame.grid(row=0, column=0, sticky="nsew")

        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        root_frame.grid_columnconfigure(0, weight=1)
        root_frame.grid_rowconfigure(2, weight=1)

        file_frame = ttk.LabelFrame(root_frame, text="Raw-Datei", padding=10)
        file_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        file_frame.grid_columnconfigure(0, weight=1)

        ttk.Label(file_frame, textvariable=self.input_path_var).grid(
            row=0, column=0, padx=(0, 10), sticky="w"
        )
        ttk.Button(file_frame, text="Datei oeffnen...", command=self.open_raw_file).grid(
            row=0, column=1, sticky="e"
        )

        transform_frame = ttk.LabelFrame(
            root_frame,
            text="Koordinatentransformation",
            padding=10,
        )
        transform_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        transform_fields = (
            ("X [mm]", "x"),
            ("Y [mm]", "y"),
            ("Z [mm]", "z"),
            ("RX [Grad]", "rx"),
            ("RY [Grad]", "ry"),
            ("RZ [Grad]", "rz"),
        )
        for index, (label, key) in enumerate(transform_fields):
            label_column = index * 2
            ttk.Label(transform_frame, text=f"{label}:").grid(
                row=0, column=label_column, padx=(0 if index == 0 else 10, 4), sticky="w"
            )
            ttk.Entry(
                transform_frame,
                textvariable=self.transform_vars[key],
                width=12,
            ).grid(row=0, column=label_column + 1, sticky="ew")

        ttk.Button(
            transform_frame,
            text="Zuruecksetzen",
            command=self.reset_transform,
        ).grid(row=0, column=12, padx=(12, 0), sticky="e")

        ttk.Label(
            transform_frame,
            text="Reihenfolge: RX -> RY -> RZ | P_neu = RZ * RY * RX * P_raw + [X, Y, Z] | Massstab = 1",
        ).grid(row=1, column=0, columnspan=13, pady=(8, 2), sticky="w")
        ttk.Label(
            transform_frame,
            textvariable=self.transform_status_var,
        ).grid(row=2, column=0, columnspan=13, sticky="w")

        table_frame = ttk.LabelFrame(root_frame, text="Koordinaten", padding=8)
        table_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        columns = (
            "name",
            "x_raw",
            "y_raw",
            "z_raw",
            "x_new",
            "y_new",
            "z_new",
            "marker",
            "text",
        )
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
        )
        self.tree.heading("name", text="Punkt")
        self.tree.heading("x_raw", text="X roh")
        self.tree.heading("y_raw", text="Y roh")
        self.tree.heading("z_raw", text="Z roh")
        self.tree.heading("x_new", text="X neu")
        self.tree.heading("y_new", text="Y neu")
        self.tree.heading("z_new", text="Z neu")
        self.tree.heading("marker", text="Markierung")
        self.tree.heading("text", text="Text")
        self.tree.column("name", width=100, anchor="w")
        for column in ("x_raw", "y_raw", "z_raw", "x_new", "y_new", "z_new"):
            self.tree.column(column, width=115, anchor="e")
        self.tree.column("marker", width=95, anchor="center")
        self.tree.column("text", width=145, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self.on_selection_changed)
        self.tree.bind("<Control-a>", self.select_all_rows)
        self.tree.bind("<Control-A>", self.select_all_rows)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        horizontal_scrollbar = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        horizontal_scrollbar.grid(row=1, column=0, sticky="ew")
        self.tree.configure(
            yscrollcommand=scrollbar.set,
            xscrollcommand=horizontal_scrollbar.set,
        )

        edit_frame = ttk.LabelFrame(root_frame, text="Ausgewaehlte Punkte bearbeiten", padding=10)
        edit_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        edit_frame.grid_columnconfigure(3, weight=1)

        ttk.Label(edit_frame, text="Markierung:").grid(row=0, column=0, padx=(0, 6), sticky="w")
        self.marker_combo = ttk.Combobox(
            edit_frame,
            textvariable=self.marker_var,
            values=tuple(self._marker_display(code) for code in MARKER_LABELS),
            state="readonly",
            width=29,
        )
        self.marker_combo.grid(row=0, column=1, padx=(0, 14), sticky="w")

        ttk.Label(edit_frame, text='Text in "":').grid(row=0, column=2, padx=(0, 6), sticky="w")
        self.text_entry = ttk.Entry(edit_frame, textvariable=self.text_var)
        self.text_entry.grid(row=0, column=3, padx=(0, 10), sticky="ew")

        ttk.Button(
            edit_frame,
            text="Auf Auswahl anwenden",
            command=self.apply_to_selection,
        ).grid(row=0, column=4, padx=(0, 6), sticky="e")

        ttk.Button(
            edit_frame,
            text="Auf alle anwenden",
            command=self.apply_to_all,
        ).grid(row=0, column=5, sticky="e")

        bottom = ttk.Frame(root_frame)
        bottom.grid(row=4, column=0, sticky="ew")
        bottom.grid_columnconfigure(0, weight=1)

        ttk.Label(bottom, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        ttk.Button(bottom, text="Schliessen", command=self.root.destroy).grid(
            row=0, column=1, padx=(10, 6), sticky="e"
        )
        self.save_button = ttk.Button(
            bottom,
            text="Formatierte Datei speichern...",
            command=self.save_formatted_file,
            state="disabled",
        )
        self.save_button.grid(row=0, column=2, sticky="e")

    def _bind_transform_updates(self) -> None:
        for variable in self.transform_vars.values():
            variable.trace_add("write", self.on_transform_changed)

    def on_transform_changed(self, *_args: object) -> None:
        try:
            transform = self.read_transform_inputs()
        except ValueError:
            self.transform_status_var.set(
                "Transformationseingabe ist noch unvollstaendig oder ungueltig."
            )
            return

        self.active_transform = transform
        self.refresh_transformed_coordinates()
        if transform.is_identity():
            self.transform_status_var.set("Keine Transformation: alle Werte sind 0.")
        else:
            self.transform_status_var.set(
                "Transformation aktiv. Die Spalten X/Y/Z neu werden exportiert."
            )

    def read_transform_inputs(self) -> CoordinateTransform:
        values: dict[str, float] = {}
        labels = {
            "x": "X",
            "y": "Y",
            "z": "Z",
            "rx": "RX",
            "ry": "RY",
            "rz": "RZ",
        }
        for key, variable in self.transform_vars.items():
            raw = variable.get().strip().replace(",", ".")
            try:
                values[key] = float(raw)
            except ValueError as exc:
                raise ValueError(f"{labels[key]} muss eine gueltige Zahl sein.") from exc

        return CoordinateTransform(
            x=values["x"],
            y=values["y"],
            z=values["z"],
            rx_deg=values["rx"],
            ry_deg=values["ry"],
            rz_deg=values["rz"],
        )

    def reset_transform(self) -> None:
        for variable in self.transform_vars.values():
            variable.set("0.0")
        self.active_transform = CoordinateTransform()
        self.refresh_transformed_coordinates()
        self.transform_status_var.set("Keine Transformation: alle Werte sind 0.")

    def open_raw_file(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="Raw-Koordinatendatei oeffnen",
            filetypes=(("Textdateien", "*.txt *.csv"), ("Alle Dateien", "*.*")),
        )
        if not selected:
            return

        try:
            rows = parse_raw_coordinate_file(selected)
        except Exception as exc:
            messagebox.showerror("Datei konnte nicht gelesen werden", str(exc), parent=self.root)
            return

        self.input_path = Path(selected)
        self.rows = rows
        self.input_path_var.set(str(self.input_path))
        self.populate_table()
        self.save_button.configure(state="normal")
        self.status_var.set(f"{len(self.rows)} Koordinaten geladen. Markierung und Text koennen bearbeitet werden.")

    def populate_table(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        for index, row in enumerate(self.rows):
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=self._tree_values(row),
            )

    def refresh_transformed_coordinates(self) -> None:
        for index in range(len(self.rows)):
            self._refresh_tree_row(index)

    def on_selection_changed(self, _event: tk.Event | None = None) -> None:
        selection = self.tree.selection()
        if not selection:
            return

        selected_rows = [self.rows[int(iid)] for iid in selection]
        marker_codes = {row.marker_code for row in selected_rows}
        texts = {row.text for row in selected_rows}

        if len(marker_codes) == 1:
            self.marker_var.set(self._marker_display(selected_rows[0].marker_code))
        if len(texts) == 1:
            self.text_var.set(selected_rows[0].text)
        else:
            self.text_var.set("")

    def apply_to_selection(self, *, show_message: bool = True) -> bool:
        selection = self.tree.selection()
        if not selection:
            if show_message:
                messagebox.showinfo(
                    "Keine Auswahl",
                    "Bitte mindestens einen Punkt in der Tabelle auswaehlen.",
                    parent=self.root,
                )
            return False

        try:
            marker_code = self._selected_marker_code()
            text = validate_output_text(self.text_var.get())
        except ValueError as exc:
            messagebox.showerror("Ungueltige Eingabe", str(exc), parent=self.root)
            return False

        for iid in selection:
            row = self.rows[int(iid)]
            row.marker_code = marker_code
            row.text = text
            self._refresh_tree_row(int(iid))

        self.status_var.set(f"Einstellungen auf {len(selection)} Punkt(e) angewendet.")
        return True

    def apply_to_all(self) -> None:
        if not self.rows:
            return

        try:
            marker_code = self._selected_marker_code()
            text = validate_output_text(self.text_var.get())
        except ValueError as exc:
            messagebox.showerror("Ungueltige Eingabe", str(exc), parent=self.root)
            return

        for index, row in enumerate(self.rows):
            row.marker_code = marker_code
            row.text = text
            self._refresh_tree_row(index)

        self.status_var.set(f"Einstellungen auf alle {len(self.rows)} Punkte angewendet.")

    def save_formatted_file(self) -> None:
        if not self.rows or self.input_path is None:
            messagebox.showinfo("Keine Daten", "Bitte zuerst eine Raw-Datei oeffnen.", parent=self.root)
            return

        # Noch nicht mit dem Button uebernommene Eingaben fuer die aktuelle
        # Auswahl werden beim Speichern automatisch beruecksichtigt.
        if self.tree.selection() and not self.apply_to_selection(show_message=False):
            return

        try:
            self.active_transform = self.read_transform_inputs()
        except ValueError as exc:
            messagebox.showerror("Ungueltige Transformation", str(exc), parent=self.root)
            return

        selected = filedialog.asksaveasfilename(
            parent=self.root,
            title="Formatierte Koordinatendatei speichern",
            initialdir=str(self.input_path.parent),
            initialfile=suggested_output_name(self.input_path),
            defaultextension=".txt",
            filetypes=(("Textdateien", "*.txt"), ("Alle Dateien", "*.*")),
        )
        if not selected:
            return

        try:
            save_formatted_coordinate_file(
                selected,
                self.rows,
                transform=self.active_transform,
            )
        except Exception as exc:
            messagebox.showerror("Datei konnte nicht gespeichert werden", str(exc), parent=self.root)
            return

        self.status_var.set(f"Gespeichert: {selected}")
        messagebox.showinfo(
            "Datei gespeichert",
            f"Die formatierte Datei wurde gespeichert:\n\n{selected}",
            parent=self.root,
        )

    def select_all_rows(self, _event: tk.Event | None = None) -> str:
        items = self.tree.get_children()
        if items:
            self.tree.selection_set(items)
        return "break"

    def _refresh_tree_row(self, index: int) -> None:
        row = self.rows[index]
        self.tree.item(
            str(index),
            values=self._tree_values(row),
        )

    def _tree_values(self, row: CoordinateRow) -> tuple[object, ...]:
        x_new, y_new, z_new = transformed_coordinate_text(row, self.active_transform)
        return (
            row.name,
            row.x,
            row.y,
            row.z,
            x_new,
            y_new,
            z_new,
            row.marker_code,
            row.text,
        )

    def _selected_marker_code(self) -> int:
        display = self.marker_var.get()
        try:
            marker_code = int(display.split(" ", 1)[0])
        except (TypeError, ValueError) as exc:
            raise ValueError("Bitte eine Markierung zwischen 1 und 4 auswaehlen.") from exc

        if marker_code not in MARKER_LABELS:
            raise ValueError("Bitte eine Markierung zwischen 1 und 4 auswaehlen.")
        return marker_code

    @staticmethod
    def _marker_display(marker_code: int) -> str:
        return f"{marker_code} - {MARKER_LABELS[marker_code]}"

    def _center_window(self, width: int, height: int) -> None:
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = max((screen_width - width) // 2, 0)
        y = max((screen_height - height) // 2, 0)
        self.root.geometry(f"{width}x{height}+{x}+{y}")


def main() -> None:
    root = tk.Tk()
    CoordinateFormatterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

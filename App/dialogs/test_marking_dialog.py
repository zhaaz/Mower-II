# App/dialogs/test_marking_dialog.py

from __future__ import annotations

import math
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable

from config.mower_config import CONFIG
from XYZ_Robot.marker_shapes import MARKER_SHAPES
from XYZ_Robot.stroke_font import STROKE_FONT


StateGetter = Callable[[], Any]
LogFunction = Callable[[str], None]
FinishedCallback = Callable[[], None]

FONT_NORMAL = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SECTION = ("Segoe UI", 11, "bold")

SHAPE_LABELS: dict[str, str] = {
    "plus": "Plus (+)",
    "cross": "Kreuz (x)",
    "circle_point": "Kreis mit Mittelpunkt",
    "plus_circle": "Plus mit Kreis",
}
SHAPE_BY_LABEL = {label: shape for shape, label in SHAPE_LABELS.items()}

DEFAULT_TEXT_HEIGHT_MM = 8.0
MIN_TEXT_HEIGHT_MM = 1.0
MAX_TEXT_HEIGHT_MM = 50.0


def show_test_marking_dialog(
        *,
        parent: tk.Misc,
        xyz_worker: Any,
        xyz_state_getter: StateGetter,
        on_finished: FinishedCallback | None = None,
        log: LogFunction | None = None,
) -> None:
    """Oeffnet den Dialog fuer eine Testmarkierung an der aktuellen XYZ-Position."""

    dialog = TestMarkingDialog(
        parent=parent,
        xyz_worker=xyz_worker,
        xyz_state_getter=xyz_state_getter,
        on_finished=on_finished,
        external_log=log,
    )
    dialog.show()


class TestMarkingDialog:
    def __init__(
            self,
            *,
            parent: tk.Misc,
            xyz_worker: Any,
            xyz_state_getter: StateGetter,
            on_finished: FinishedCallback | None = None,
            external_log: LogFunction | None = None,
    ) -> None:
        self.parent = parent
        self.xyz_worker = xyz_worker
        self.xyz_state_getter = xyz_state_getter
        self.on_finished = on_finished
        self.external_log = external_log

        self.gui_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.workflow_thread: threading.Thread | None = None
        self.workflow_running = False
        self.closed = False

        default_shape = str(getattr(CONFIG.marker, "shape", "plus"))
        if default_shape not in SHAPE_LABELS:
            default_shape = "plus"

        self.shape_var = tk.StringVar(value=SHAPE_LABELS[default_shape])
        self.text_var = tk.StringVar(value="")
        self.text_height_var = tk.StringVar(value=f"{DEFAULT_TEXT_HEIGHT_MM:.1f}")
        self.position_var = tk.StringVar(value="X=-   Y=-   Z=-")
        self.status_var = tk.StringVar(value="Bereit.")

        self.window = tk.Toplevel(parent)
        self.window.title("Testmarkierung")
        self.window.minsize(560, 520)
        self.window.transient(parent)
        self.window.grab_set()

        _center_window(parent, self.window, 620, 600)

        self._configure_styles()
        self._build_ui()
        self._bind_preview_updates()
        self.update_position_display()
        self.update_preview()

        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())

    def show(self) -> None:
        self.window.after(100, self.process_gui_queue)
        self.window.after(250, self.refresh_live_position)

    # --------------------------------------------------
    # UI
    # --------------------------------------------------

    def _configure_styles(self) -> None:
        style = ttk.Style(self.window)
        style.configure("TestMark.TLabel", font=FONT_NORMAL)
        style.configure("TestMarkBold.TLabel", font=FONT_BOLD)
        style.configure("TestMark.TButton", font=FONT_NORMAL, padding=(8, 4))
        style.configure("TestMark.TLabelframe.Label", font=FONT_SECTION)

    def _build_ui(self) -> None:
        root = ttk.Frame(self.window, padding=12)
        root.grid(row=0, column=0, sticky="nsew")

        self.window.grid_rowconfigure(0, weight=1)
        self.window.grid_columnconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(2, weight=1)

        ttk.Label(
            root,
            text=(
                "Die Markierung wird mit der aktuell gelesenen XYZ-Position als Mittelpunkt ausgefuehrt. "
                "Eine Transformation oder Punktdatei ist dafuer nicht erforderlich."
            ),
            wraplength=570,
            justify="left",
            style="TestMark.TLabel",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 10))

        settings = ttk.LabelFrame(
            root,
            text="Einstellungen",
            padding=10,
            style="TestMark.TLabelframe",
        )
        settings.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        settings.grid_columnconfigure(1, weight=1)

        ttk.Label(settings, text="Markierung:", style="TestMark.TLabel").grid(
            row=0, column=0, padx=(0, 10), pady=4, sticky="w"
        )
        self.shape_combo = ttk.Combobox(
            settings,
            textvariable=self.shape_var,
            values=tuple(SHAPE_LABELS.values()),
            state="readonly",
            width=28,
            font=FONT_NORMAL,
        )
        self.shape_combo.grid(row=0, column=1, pady=4, sticky="ew")

        ttk.Label(settings, text="Optionaler Text:", style="TestMark.TLabel").grid(
            row=1, column=0, padx=(0, 10), pady=4, sticky="w"
        )
        self.text_entry = ttk.Entry(settings, textvariable=self.text_var, font=FONT_NORMAL)
        self.text_entry.grid(row=1, column=1, pady=4, sticky="ew")

        ttk.Label(settings, text="Textgroesse [mm]:", style="TestMark.TLabel").grid(
            row=2, column=0, padx=(0, 10), pady=4, sticky="w"
        )
        self.text_height_entry = ttk.Entry(
            settings,
            textvariable=self.text_height_var,
            width=12,
            font=FONT_NORMAL,
        )
        self.text_height_entry.grid(row=2, column=1, pady=4, sticky="w")

        marker_size = float(getattr(CONFIG.marker, "size_mm", 10.0))
        ttk.Label(
            settings,
            text=f"Markierungsgroesse aus Config: {marker_size:.1f} mm",
            style="TestMark.TLabel",
        ).grid(row=3, column=0, columnspan=2, pady=(8, 2), sticky="w")

        ttk.Label(settings, text="Aktuelle XYZ-Position:", style="TestMarkBold.TLabel").grid(
            row=4, column=0, padx=(0, 10), pady=(8, 2), sticky="w"
        )
        ttk.Label(settings, textvariable=self.position_var, style="TestMark.TLabel").grid(
            row=4, column=1, pady=(8, 2), sticky="w"
        )

        preview_frame = ttk.LabelFrame(
            root,
            text="Vorschau",
            padding=8,
            style="TestMark.TLabelframe",
        )
        preview_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        preview_frame.grid_rowconfigure(0, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)

        self.preview = tk.Canvas(
            preview_frame,
            width=540,
            height=250,
            background="#ffffff",
            highlightthickness=1,
            highlightbackground="#b0b0b0",
        )
        self.preview.grid(row=0, column=0, sticky="nsew")
        self.preview.bind("<Configure>", lambda _event: self.update_preview())

        ttk.Label(
            root,
            textvariable=self.status_var,
            style="TestMarkBold.TLabel",
        ).grid(row=3, column=0, sticky="w", pady=(0, 10))

        buttons = ttk.Frame(root)
        buttons.grid(row=4, column=0, sticky="ew")
        buttons.grid_columnconfigure(0, weight=1)
        buttons.grid_columnconfigure(1, weight=1)

        self.btn_close = ttk.Button(
            buttons,
            text="Schliessen",
            command=self.close,
            style="TestMark.TButton",
        )
        self.btn_close.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.btn_execute = ttk.Button(
            buttons,
            text="Testmarkierung durchfuehren",
            command=self.start_test_marking,
            style="TestMark.TButton",
        )
        self.btn_execute.grid(row=0, column=1, padx=(6, 0), sticky="ew")

    def _bind_preview_updates(self) -> None:
        self.shape_var.trace_add("write", lambda *_args: self.update_preview())
        self.text_var.trace_add("write", lambda *_args: self.update_preview())
        self.text_height_var.trace_add("write", lambda *_args: self.update_preview())

    # --------------------------------------------------
    # Preview
    # --------------------------------------------------

    def update_preview(self) -> None:
        if self.closed:
            return

        try:
            self.preview.delete("all")
            width = max(self.preview.winfo_width(), 100)
            height = max(self.preview.winfo_height(), 100)

            shape = self.selected_shape()
            text = self.text_var.get().strip().upper()
            marker_size = float(getattr(CONFIG.marker, "size_mm", 10.0))
            angle_deg = float(getattr(CONFIG.marker, "angle_deg", 0.0))
            text_height = self.parse_text_height(require_value=False)

            strokes = build_preview_strokes(
                shape=shape,
                text=text,
                marker_size=marker_size,
                text_height=text_height,
                angle_deg=angle_deg,
            )
            points = [point for stroke in strokes for point in stroke]
            if not points:
                return

            min_x = min(point[0] for point in points)
            max_x = max(point[0] for point in points)
            min_y = min(point[1] for point in points)
            max_y = max(point[1] for point in points)
            span_x = max(max_x - min_x, 1.0)
            span_y = max(max_y - min_y, 1.0)
            scale = min((width - 50.0) / span_x, (height - 50.0) / span_y)
            center_x = (min_x + max_x) / 2.0
            center_y = (min_y + max_y) / 2.0

            self.preview.create_line(width / 2, 12, width / 2, height - 12, fill="#eeeeee")
            self.preview.create_line(12, height / 2, width - 12, height / 2, fill="#eeeeee")

            for stroke in strokes:
                if len(stroke) < 2:
                    continue
                coords: list[float] = []
                for x, y in stroke:
                    coords.extend((
                        width / 2 + (x - center_x) * scale,
                        height / 2 - (y - center_y) * scale,
                    ))
                self.preview.create_line(*coords, fill="#111111", width=2)

        except Exception as exc:
            try:
                self.preview.create_text(
                    12,
                    12,
                    anchor="nw",
                    text=f"Vorschau nicht moeglich: {exc}",
                    fill="#a00000",
                    font=FONT_NORMAL,
                )
            except Exception:
                pass

    # --------------------------------------------------
    # Workflow
    # --------------------------------------------------

    def start_test_marking(self) -> None:
        if self.workflow_running:
            return

        try:
            shape = self.selected_shape()
            text = self.text_var.get().strip()
            text_height = self.parse_text_height(require_value=bool(text))
            self.validate_text(text)
            self.validate_runtime_state(require_position=True)
            self.validated_marker_z_heights()
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror("Testmarkierung", str(exc), parent=self.window)
            return

        state = self.xyz_state_getter()
        x = float(getattr(state, "x"))
        y = float(getattr(state, "y"))
        marker_label = SHAPE_LABELS[shape]
        text_info = text if text else "ohne Text"
        confirmed = messagebox.askyesno(
            "Testmarkierung durchfuehren",
            f"Testmarkierung an der aktuellen Position durchfuehren?\n\n"
            f"Mittelpunkt: X={x:.3f} mm, Y={y:.3f} mm\n"
            f"Markierung: {marker_label}\n"
            f"Beschriftung: {text_info}\n\n"
            "Der Stift wird dabei auf Z_MARK abgesenkt.",
            parent=self.window,
        )
        if not confirmed:
            return

        self.workflow_running = True
        self.set_controls_enabled(False)
        self.status_var.set("Aktuelle Position wird gelesen...")
        self.log(
            f"Testmarkierung angefordert: {shape}, "
            f"Text={text_info}, Textgroesse={text_height:.1f} mm."
        )

        self.workflow_thread = threading.Thread(
            target=self._workflow_main,
            args=(shape, text, text_height),
            daemon=True,
        )
        self.workflow_thread.start()

    def _workflow_main(self, shape: str, text: str, text_height: float) -> None:
        try:
            self.send_robot_command("read_position", timeout_s=30.0)
            self.validate_runtime_state(require_position=True)

            state = self.xyz_state_getter()
            x = float(getattr(state, "x"))
            y = float(getattr(state, "y"))
            z_mark, z_clear, z_travel = self.validated_marker_z_heights()

            self.gui_queue.put(("status", f"Markierung bei X={x:.3f}, Y={y:.3f} wird ausgefuehrt..."))
            self.log(f"Aktuelle XYZ-Position: X={x:.3f}, Y={y:.3f}.")

            self.send_robot_command(
                "mark_point",
                timeout_s=240.0,
                x=x,
                y=y,
                label=text,
                marker_size=float(getattr(CONFIG.marker, "size_mm", 10.0)),
                marker_shape=shape,
                text_height=text_height,
                angle_deg=float(getattr(CONFIG.marker, "angle_deg", 0.0)),
                z_mark_mm=z_mark,
                z_clear_mm=z_clear,
                z_travel_mm=z_travel,
            )

            self.log("Testmarkierung abgeschlossen.")
            self.gui_queue.put(("finished", (x, y)))

        except Exception as exc:
            self.log(f"FEHLER bei der Testmarkierung: {exc}")
            self.gui_queue.put(("error", str(exc)))

    def send_robot_command(self, command: str, timeout_s: float, **kwargs: Any) -> None:
        self.xyz_worker.send_command(command, **kwargs)
        self.wait_robot_done(timeout_s=timeout_s)

    def wait_robot_done(self, timeout_s: float) -> None:
        start = time.time()
        while time.time() - start < timeout_s:
            state = self.xyz_state_getter()
            queue_empty = True
            try:
                queue_empty = self.xyz_worker.command_queue.empty()
            except Exception:
                pass

            busy = bool(getattr(state, "busy", False)) if state is not None else False
            error_text = getattr(state, "error_text", "") if state is not None else ""

            if queue_empty and not busy:
                if error_text:
                    raise RuntimeError(str(error_text))
                return

            time.sleep(0.05)

        raise TimeoutError("Timeout beim Warten auf XYZRobotWorker.")

    # --------------------------------------------------
    # Validation / state
    # --------------------------------------------------

    def selected_shape(self) -> str:
        label = self.shape_var.get()
        shape = SHAPE_BY_LABEL.get(label)
        if shape is None or shape not in MARKER_SHAPES:
            raise ValueError(f"Unbekannte Markierung: {label}")
        return shape

    def parse_text_height(self, *, require_value: bool) -> float:
        raw = self.text_height_var.get().strip().replace(",", ".")
        if not raw and not require_value:
            return DEFAULT_TEXT_HEIGHT_MM
        try:
            value = float(raw)
        except ValueError as exc:
            raise ValueError("Die Textgroesse muss eine Zahl sein.") from exc
        if not (MIN_TEXT_HEIGHT_MM <= value <= MAX_TEXT_HEIGHT_MM):
            raise ValueError(
                f"Die Textgroesse muss zwischen {MIN_TEXT_HEIGHT_MM:.1f} und "
                f"{MAX_TEXT_HEIGHT_MM:.1f} mm liegen."
            )
        return value

    @staticmethod
    def validate_text(text: str) -> None:
        unsupported = sorted({char for char in text.upper() if char != " " and char not in STROKE_FONT})
        if unsupported:
            raise ValueError(
                "Diese Zeichen werden vom Markierfont nicht unterstuetzt: "
                + " ".join(unsupported)
            )

    def validate_runtime_state(self, *, require_position: bool) -> None:
        if self.xyz_worker is None:
            raise RuntimeError("XYZ-Worker ist nicht verfuegbar.")

        state = self.xyz_state_getter()
        if state is None:
            raise RuntimeError("Kein XYZ-Zustand verfuegbar.")
        if not bool(getattr(state, "connected", False)):
            raise RuntimeError("XYZ ist nicht verbunden.")
        if not bool(getattr(state, "homed", False)):
            raise RuntimeError("XYZ-Homing wurde noch nicht durchgefuehrt.")
        if require_position and (
                getattr(state, "x", None) is None
                or getattr(state, "y", None) is None
        ):
            raise RuntimeError("Die aktuelle XYZ-Position ist nicht verfuegbar.")

    @staticmethod
    def validated_marker_z_heights() -> tuple[float, float, float]:
        z_min = float(getattr(CONFIG.xyz, "z_min", 150.0))
        z_max = float(getattr(CONFIG.xyz, "z_max", 200.0))
        z_mark = float(getattr(CONFIG.marker, "z_mark_mm", 166.0))
        z_clear = float(getattr(CONFIG.marker, "z_clear_mm", z_mark + 5.0))
        z_travel = float(getattr(CONFIG.marker, "z_travel_mm", z_mark + 10.0))

        if not (z_min <= z_mark <= z_clear <= z_travel <= z_max):
            raise ValueError(
                "Ungueltige Marker-Z-Hoehen. Erwartet: "
                f"{z_min:.3f} <= Z_MARK <= Z_CLEAR <= Z_TRAVEL <= {z_max:.3f} mm."
            )
        return z_mark, z_clear, z_travel

    def refresh_live_position(self) -> None:
        if self.closed:
            return
        self.update_position_display()
        self.window.after(250, self.refresh_live_position)

    def update_position_display(self) -> None:
        state = self.xyz_state_getter()
        x = getattr(state, "x", None) if state is not None else None
        y = getattr(state, "y", None) if state is not None else None
        z = getattr(state, "z", None) if state is not None else None
        if x is None or y is None or z is None:
            self.position_var.set("X=-   Y=-   Z=-")
            return
        self.position_var.set(f"X={float(x):.3f}   Y={float(y):.3f}   Z={float(z):.3f} mm")

    def set_controls_enabled(self, enabled: bool) -> None:
        self.btn_execute.configure(state="normal" if enabled else "disabled")
        self.btn_close.configure(state="normal" if enabled else "disabled")
        self.shape_combo.configure(state="readonly" if enabled else "disabled")
        self.text_entry.configure(state="normal" if enabled else "disabled")
        self.text_height_entry.configure(state="normal" if enabled else "disabled")

    # --------------------------------------------------
    # Queue / close
    # --------------------------------------------------

    def process_gui_queue(self) -> None:
        if self.closed:
            return

        try:
            while True:
                kind, payload = self.gui_queue.get_nowait()
                if kind == "status":
                    self.status_var.set(str(payload))
                elif kind == "finished":
                    self.workflow_running = False
                    self.set_controls_enabled(True)
                    x, y = payload
                    self.status_var.set("Testmarkierung erfolgreich abgeschlossen.")
                    self.update_position_display()
                    if self.on_finished:
                        self.on_finished()
                    messagebox.showinfo(
                        "Testmarkierung",
                        f"Testmarkierung bei X={x:.3f} mm, Y={y:.3f} mm abgeschlossen.",
                        parent=self.window,
                    )
                elif kind == "error":
                    self.workflow_running = False
                    self.set_controls_enabled(True)
                    self.status_var.set("Testmarkierung fehlgeschlagen.")
                    messagebox.showerror("Testmarkierung", str(payload), parent=self.window)
        except queue.Empty:
            pass

        if not self.closed:
            self.window.after(100, self.process_gui_queue)

    def log(self, text: str) -> None:
        if self.external_log:
            self.external_log(f"[Testmarkierung] {text}")

    def close(self) -> None:
        if self.workflow_running:
            messagebox.showwarning(
                "Testmarkierung",
                "Die Testmarkierung laeuft noch und kann nicht geschlossen werden.",
                parent=self.window,
            )
            return
        if self.closed:
            return
        self.closed = True
        try:
            self.window.grab_release()
        except Exception:
            pass
        self.window.destroy()


def build_preview_strokes(
        *,
        shape: str,
        text: str,
        marker_size: float,
        text_height: float,
        angle_deg: float,
) -> list[list[tuple[float, float]]]:
    """Erzeugt Vorschaugeometrie entsprechend der XYZRobot-Markierlogik."""

    strokes: list[list[tuple[float, float]]] = []

    for stroke in MARKER_SHAPES.get(shape, []):
        strokes.append([
            _transform_point(x * marker_size, y * marker_size, 0.0, 0.0, angle_deg)
            for x, y in stroke
        ])

    if shape == "circle_point":
        strokes.append(_circle_points(marker_size / 2.0, angle_deg))
    elif shape == "plus_circle":
        strokes.append(_circle_points(marker_size * 0.7 / 2.0, angle_deg))

    if text:
        text = text.upper()
        char_width = text_height * 0.6
        step = char_width * 1.25
        angle_rad = math.radians(angle_deg)
        origin_x = (marker_size / 2.0 + 6.0) * math.cos(angle_rad)
        origin_y = (marker_size / 2.0 + 6.0) * math.sin(angle_rad)

        for char in text:
            if char != " " and char in STROKE_FONT:
                for stroke in STROKE_FONT[char]:
                    points: list[tuple[float, float]] = []
                    for x, y in stroke:
                        points.append(_transform_point(
                            x * char_width,
                            y * text_height,
                            origin_x,
                            origin_y,
                            angle_deg,
                        ))
                    strokes.append(points)
            origin_x += step * math.cos(angle_rad)
            origin_y += step * math.sin(angle_rad)

    return strokes


def _transform_point(
        x: float,
        y: float,
        origin_x: float,
        origin_y: float,
        angle_deg: float,
) -> tuple[float, float]:
    angle_rad = math.radians(angle_deg)
    return (
        origin_x + x * math.cos(angle_rad) - y * math.sin(angle_rad),
        origin_y + x * math.sin(angle_rad) + y * math.cos(angle_rad),
    )


def _circle_points(radius: float, angle_deg: float) -> list[tuple[float, float]]:
    # Die Kreisrotation ist geometrisch ohne Wirkung, wird aber fuer eine
    # einheitliche Vorschau-Transformation beibehalten.
    return [
        _transform_point(
            radius * math.cos(2.0 * math.pi * index / 48.0),
            radius * math.sin(2.0 * math.pi * index / 48.0),
            0.0,
            0.0,
            angle_deg,
        )
        for index in range(49)
    ]


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

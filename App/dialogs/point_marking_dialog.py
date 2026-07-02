# App/dialogs/point_marking_dialog.py

from __future__ import annotations

import math
from datetime import datetime
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable

from config.mower_config import (
    CONFIG,
    update_marker_align_to_tracker_axes,
    update_marker_measure_after_marking,
)
from App.services.point_reachability import (
    PointReachability,
    apply_reachability_to_points,
    evaluate_points_reachability,
    reachable_points_only,
)


StateGetter = Callable[[], Any]
LogFunction = Callable[[str], None]
FinishedCallback = Callable[[], None]
PointsChangedCallback = Callable[[], None]

FONT_NORMAL = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SECTION = ("Segoe UI", 11, "bold")
FONT_MONO = ("Consolas", 10)


SelectionFlag = str
SELECTED: SelectionFlag = "[x]"
NOT_SELECTED: SelectionFlag = "[ ]"

LABEL_NONE = "Keine"
LABEL_POINT_NAME = "Punktnummer"
LABEL_REMARK = "Bemerkung"
LABEL_OPTIONS = (LABEL_NONE, LABEL_POINT_NAME, LABEL_REMARK)

AUTO_MEASURE_RETRY_D2D_THRESHOLD_MM = 2.0
AUTO_MEASURE_MAX_ATTEMPTS = 2


def show_point_marking_dialog(
        *,
        parent: tk.Misc,
        points: list[Any],
        xyz_worker: Any,
        xyz_state_getter: StateGetter,
        trafo_manager: Any,
        tracker_receiver: Any | None = None,
        on_points_changed: PointsChangedCallback | None = None,
        on_finished: FinishedCallback | None = None,
        log: LogFunction | None = None,
) -> None:
    """Dialog zum Markieren aktuell erreichbarer Punkte."""

    dialog = PointMarkingDialog(
        parent=parent,
        points=points,
        xyz_worker=xyz_worker,
        xyz_state_getter=xyz_state_getter,
        trafo_manager=trafo_manager,
        tracker_receiver=tracker_receiver,
        on_points_changed=on_points_changed,
        on_finished=on_finished,
        external_log=log,
    )
    dialog.show()


class PointMarkingDialog:
    def __init__(
            self,
            *,
            parent: tk.Misc,
            points: list[Any],
            xyz_worker: Any,
            xyz_state_getter: StateGetter,
            trafo_manager: Any,
            tracker_receiver: Any | None = None,
            on_points_changed: PointsChangedCallback | None = None,
            on_finished: FinishedCallback | None = None,
            external_log: LogFunction | None = None,
    ) -> None:
        self.parent = parent
        self.points = points
        self.xyz_worker = xyz_worker
        self.xyz_state_getter = xyz_state_getter
        self.trafo_manager = trafo_manager
        self.tracker_receiver = tracker_receiver
        self.on_points_changed = on_points_changed
        self.on_finished = on_finished
        self.external_log = external_log

        # Queue und Laufzeit-Flags muessen vor der ersten Logausgabe existieren.
        # Die Reachability-Auswertung kann ueber self.log bereits Debugausgaben schreiben.
        self.gui_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.abort_event = threading.Event()
        self.workflow_thread: threading.Thread | None = None
        self.workflow_running = False
        self.closed = False

        all_results = evaluate_points_reachability(
            points=self.points,
            trafo_manager=self.trafo_manager,
            config=CONFIG,
            log=self.log,
            debug=True,
        )
        apply_reachability_to_points(all_results)
        self.reachable_results = reachable_points_only(all_results)

        if self.on_points_changed:
            self.on_points_changed()

        self.result_by_iid: dict[str, PointReachability] = {}
        self.selected_iids: set[str] = set()
        self.label_mode_var = tk.StringVar(value=LABEL_POINT_NAME)
        self.align_to_tracker_axes_var = tk.BooleanVar(
            value=bool(getattr(CONFIG.marker, "align_to_tracker_axes", False))
        )
        self.measure_after_marking_var = tk.BooleanVar(
            value=bool(getattr(CONFIG.marker, "measure_after_marking", False))
        )
        self.allow_remark_marked_var = tk.BooleanVar(value=False)

        self.window = tk.Toplevel(parent)
        self.window.title("Punkte markieren")
        self.window.minsize(720, 540)
        self.window.transient(parent)
        self.window.grab_set()

        _center_window(parent, self.window, 900, 640)

        self._configure_styles()
        self._build_ui()
        self._populate_table()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())

    def show(self) -> None:
        self.window.after(100, self.process_gui_queue)

    # --------------------------------------------------
    # UI
    # --------------------------------------------------

    def _configure_styles(self) -> None:
        style = ttk.Style(self.window)
        style.configure("PointMarking.TLabel", font=FONT_NORMAL)
        style.configure("PointMarkingBold.TLabel", font=FONT_BOLD)
        style.configure("PointMarking.TButton", font=FONT_NORMAL, padding=(8, 4))
        style.configure("PointMarking.TLabelframe.Label", font=FONT_SECTION)
        style.configure("PointMarking.Treeview", font=FONT_NORMAL, rowheight=25)
        style.configure("PointMarking.Treeview.Heading", font=FONT_BOLD)

    def _build_ui(self) -> None:
        root = ttk.Frame(self.window, padding=12)
        root.grid(row=0, column=0, sticky="nsew")

        self.window.grid_rowconfigure(0, weight=1)
        self.window.grid_columnconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(2, weight=1)

        summary_frame = ttk.LabelFrame(root, text="Zusammenfassung", padding=10, style="PointMarking.TLabelframe")
        summary_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        summary_frame.grid_columnconfigure(0, weight=1)

        reachable_count = len(self.reachable_results)
        marked_count = sum(1 for result in self.reachable_results if result.marked)
        unmarked_count = reachable_count - marked_count

        self.summary_var = tk.StringVar(
            value=(
                f"Erreichbare Punkte: {reachable_count}    "
                f"Bereits markiert: {marked_count}    "
                f"Noch nicht markiert: {unmarked_count}"
            )
        )
        ttk.Label(summary_frame, textvariable=self.summary_var, style="PointMarking.TLabel").grid(
            row=0,
            column=0,
            sticky="w",
        )

        label_frame = ttk.LabelFrame(root, text="Beschriftung", padding=10, style="PointMarking.TLabelframe")
        label_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        label_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(label_frame, text="Beschriftung:", style="PointMarking.TLabel").grid(
            row=0, column=0, padx=(0, 8), sticky="w"
        )
        self.label_mode_combo = ttk.Combobox(
            label_frame,
            textvariable=self.label_mode_var,
            values=LABEL_OPTIONS,
            state="readonly",
            width=24,
            font=FONT_NORMAL,
        )
        self.label_mode_combo.grid(row=0, column=1, sticky="w")
        ttk.Label(
            label_frame,
            text="Bemerkung wird nur verwendet, wenn sie in der Punktdatei vorhanden ist.",
            style="PointMarking.TLabel",
        ).grid(row=1, column=0, columnspan=2, pady=(6, 0), sticky="w")

        ttk.Checkbutton(
            label_frame,
            text="Markierungen an LT-X-Achse ausrichten",
            variable=self.align_to_tracker_axes_var,
            command=self.on_align_to_tracker_axes_changed,
        ).grid(row=2, column=0, columnspan=2, pady=(8, 0), sticky="w")

        self.measure_after_marking_check = ttk.Checkbutton(
            label_frame,
            text="Nach dem Markieren automatisch messen",
            variable=self.measure_after_marking_var,
            command=self.on_measure_after_marking_changed,
        )
        self.measure_after_marking_check.grid(row=3, column=0, columnspan=2, pady=(4, 0), sticky="w")

        self.allow_remark_marked_check = ttk.Checkbutton(
            label_frame,
            text="Bereits markierte Punkte erneut markieren",
            variable=self.allow_remark_marked_var,
            command=self.on_allow_remark_marked_changed,
        )
        self.allow_remark_marked_check.grid(row=4, column=0, columnspan=2, pady=(4, 0), sticky="w")

        table_frame = ttk.LabelFrame(root, text="Markierbare Punkte", padding=8, style="PointMarking.TLabelframe")
        table_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        columns = ("selected", "name", "status", "marker", "remark")
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="PointMarking.Treeview",
        )
        self.tree.heading("selected", text="Auswahl")
        self.tree.heading("name", text="Punktname")
        self.tree.heading("status", text="Status")
        self.tree.heading("marker", text="Markierung")
        self.tree.heading("remark", text="Bemerkung")
        self.tree.column("selected", width=90, stretch=False, anchor="center")
        self.tree.column("name", width=210, stretch=True, anchor="w")
        self.tree.column("status", width=120, stretch=False, anchor="w")
        self.tree.column("marker", width=130, stretch=False, anchor="w")
        self.tree.column("remark", width=220, stretch=True, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<ButtonRelease-1>", self.on_table_click)
        self.tree.bind("<space>", self.on_space_toggle)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        log_frame = ttk.LabelFrame(root, text="Log", padding=8, style="PointMarking.TLabelframe")
        log_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 10))
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(0, weight=1)

        self.textbox = ScrolledText(
            log_frame,
            wrap="word",
            height=9,
            font=FONT_MONO,
            background="#ffffff",
            foreground="#111111",
        )
        self.textbox.grid(row=0, column=0, sticky="nsew")

        button_frame = ttk.Frame(root)
        button_frame.grid(row=4, column=0, sticky="ew")
        for col in range(3):
            button_frame.grid_columnconfigure(col, weight=1)

        self.btn_close = ttk.Button(
            button_frame,
            text="Schliessen",
            command=self.close,
            style="PointMarking.TButton",
        )
        self.btn_close.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.btn_selected = ttk.Button(
            button_frame,
            text="Ausgewaehlte markieren",
            command=self.mark_selected_points,
            style="PointMarking.TButton",
        )
        self.btn_selected.grid(row=0, column=1, padx=6, sticky="ew")

        self.btn_all = ttk.Button(
            button_frame,
            text="Alle markierbaren markieren",
            command=self.mark_all_markable_points,
            style="PointMarking.TButton",
        )
        self.btn_all.grid(row=0, column=2, padx=(6, 0), sticky="ew")

    def _populate_table(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.result_by_iid.clear()
        self.selected_iids.clear()

        for index, result in enumerate(self.reachable_results):
            iid = str(index)
            is_selected = self._result_can_be_marked(result)
            self.result_by_iid[iid] = result

            if is_selected:
                self.selected_iids.add(iid)

            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    SELECTED if is_selected else NOT_SELECTED,
                    result.name,
                    result.status_text,
                    self.marker_text_for_point(result.point),
                    self.remark_for_point(result.point),
                ),
            )

        self.update_buttons()
        self.log("Punktmarkierdialog geoeffnet.")

    def update_buttons(self) -> None:
        has_selected_markable = any(
            iid in self.selected_iids and self._result_can_be_marked(self.result_by_iid[iid])
            for iid in self.result_by_iid
        )
        has_markable = any(self._result_can_be_marked(result) for result in self.reachable_results)

        state_selected = "normal" if has_selected_markable and not self.workflow_running else "disabled"
        state_all = "normal" if has_markable and not self.workflow_running else "disabled"
        state_close = "normal"
        close_text = "Abbrechen" if self.workflow_running else "Schliessen"

        self.btn_selected.configure(state=state_selected)
        self.btn_all.configure(state=state_all)
        self.btn_close.configure(state=state_close, text=close_text)
        try:
            self.label_mode_combo.configure(state="disabled" if self.workflow_running else "readonly")
            self.measure_after_marking_check.configure(state="disabled" if self.workflow_running else "normal")
            self.allow_remark_marked_check.configure(state="disabled" if self.workflow_running else "normal")
        except Exception:
            pass

    def _result_can_be_marked(self, result: PointReachability) -> bool:
        if not bool(getattr(result, "marked", False)):
            return True
        return bool(self.allow_remark_marked_var.get())

    def on_allow_remark_marked_changed(self) -> None:
        enabled = bool(self.allow_remark_marked_var.get())
        self.log(
            "Erneutes Markieren bereits markierter Punkte: "
            + ("aktiv" if enabled else "inaktiv")
        )
        self.refresh_after_point_change()

    def on_table_click(self, event: tk.Event) -> None:
        if self.workflow_running:
            return

        iid = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)

        if iid and column == "#1":
            self.toggle_iid(iid)

    def on_space_toggle(self, _event: tk.Event) -> str:
        if self.workflow_running:
            return "break"

        selection = self.tree.selection()
        if selection:
            self.toggle_iid(selection[0])
        return "break"

    def toggle_iid(self, iid: str) -> None:
        if iid not in self.result_by_iid:
            return

        if iid in self.selected_iids:
            self.selected_iids.remove(iid)
            flag = NOT_SELECTED
        else:
            self.selected_iids.add(iid)
            flag = SELECTED

        result = self.result_by_iid[iid]
        self.tree.item(
            iid,
            values=(
                flag,
                result.name,
                result.status_text,
                self.marker_text_for_point(result.point),
                self.remark_for_point(result.point),
            ),
        )
        self.update_buttons()

    # --------------------------------------------------
    # Marking workflow
    # --------------------------------------------------

    def mark_selected_points(self) -> None:
        selected_results = [
            self.result_by_iid[iid]
            for iid in self.result_by_iid
            if iid in self.selected_iids and self._result_can_be_marked(self.result_by_iid[iid])
        ]
        self.start_marking(selected_results)

    def mark_all_markable_points(self) -> None:
        selected_results = [
            result for result in self.reachable_results
            if self._result_can_be_marked(result)
        ]
        self.start_marking(selected_results)

    def start_marking(self, selected_results: list[PointReachability]) -> None:
        if self.workflow_running:
            return

        if not selected_results:
            messagebox.showinfo("Punkte markieren", "Keine markierbaren Punkte ausgewaehlt.", parent=self.window)
            return

        if not self._confirm_remarking_if_needed(selected_results):
            self.log("Markierung abgebrochen: erneutes Markieren nicht bestaetigt.")
            return

        try:
            z_mark_mm, z_clear_mm, z_travel_mm = self._validated_marker_z_heights()
            if self.measure_after_marking_var.get():
                self._validate_tracker_measurement_ready()
        except (ValueError, RuntimeError) as exc:
            messagebox.showerror("Punkte markieren", str(exc), parent=self.window)
            self.log(f"Markierung nicht gestartet: {exc}")
            return

        self.workflow_running = True
        self.abort_event.clear()
        self.update_buttons()
        self.log(f"Markierung gestartet: {len(selected_results)} Punkt(e).")
        self.log(f"Beschriftung: {self.label_mode_var.get()}")
        if self.align_to_tracker_axes_var.get():
            self.log("Markierausrichtung: LT-X-Achse + Marker-Winkeloffset.")
        else:
            self.log("Markierausrichtung: Roboter-XY / fester Marker-Winkel.")
        self.log(
            f"Markierhoehen geprueft: Z_MARK={z_mark_mm:.3f} mm, "
            f"Z_CLEAR={z_clear_mm:.3f} mm, Z_TRAVEL={z_travel_mm:.3f} mm"
        )
        if self.measure_after_marking_var.get():
            self.log("Automatische Kontrollmessung: aktiv, Messung ueber oberen Reflektor.")
        else:
            self.log("Automatische Kontrollmessung: inaktiv.")

        self.workflow_thread = threading.Thread(
            target=self._marking_thread_main,
            args=(selected_results,),
            daemon=True,
        )
        self.workflow_thread.start()

    def _confirm_remarking_if_needed(self, selected_results: list[PointReachability]) -> bool:
        marked_results = [result for result in selected_results if bool(getattr(result, "marked", False))]
        if not marked_results:
            return True

        names = ", ".join(result.name for result in marked_results[:10])
        if len(marked_results) > 10:
            names += f", ... ({len(marked_results)} Punkte)"

        return bool(messagebox.askyesno(
            "Punkte erneut markieren",
            "Es sind bereits markierte Punkte ausgewaehlt.\n\n"
            f"Diese Punkte werden erneut markiert:\n{names}\n\n"
            "Vorhandene automatische Kontrollmesswerte werden ersetzt. "
            "Wenn die automatische Kontrollmessung deaktiviert ist, werden alte Kontrollmesswerte am Punkt geloescht.\n\n"
            "Fortfahren?",
            parent=self.window,
        ))

    def _marking_thread_main(self, selected_results: list[PointReachability]) -> None:
        try:
            total = len(selected_results)
            for index, result in enumerate(selected_results, start=1):
                self.check_abort()
                self._validate_runtime_state()

                refreshed = evaluate_points_reachability(
                    points=[result.point],
                    trafo_manager=self.trafo_manager,
                    config=CONFIG,
                    log=self.log,
                    debug=True,
                )[0]

                if not refreshed.reachable:
                    self.log(f"{result.name}: wird uebersprungen, nicht mehr erreichbar ({refreshed.reason}).")
                    continue

                was_marked = bool(getattr(result.point, "marked", False))
                label_text = self.get_label_for_point(result.point)
                label_info = label_text if label_text else "ohne Beschriftung"
                marker_angle_deg = self._marker_angle_deg()
                self.log(f"{index}/{total}: markiere {result.name} ({label_info}).")
                self.log(f"Markierwinkel: {marker_angle_deg:.3f} deg")
                z_mark_mm, z_clear_mm, z_travel_mm = self._validated_marker_z_heights()
                self.log(
                    f"Markierhoehen: Z_MARK={z_mark_mm:.3f} mm, "
                    f"Z_CLEAR={z_clear_mm:.3f} mm, Z_TRAVEL={z_travel_mm:.3f} mm"
                )
                self.send_robot_command(
                    "mark_point",
                    timeout_s=240.0,
                    x=float(refreshed.robot_x),
                    y=float(refreshed.robot_y),
                    label=label_text,
                    marker_size=CONFIG.marker.size_mm,
                    marker_shape=self.marker_shape_for_point(result.point),
                    angle_deg=marker_angle_deg,
                    z_mark_mm=z_mark_mm,
                    z_clear_mm=z_clear_mm,
                    z_travel_mm=z_travel_mm,
                )

                try:
                    result.point.marked = True
                except Exception:
                    pass

                self._increment_marking_count(result.point)
                if was_marked:
                    self.log(f"{result.name}: bereits markierter Punkt wurde erneut markiert.")

                if self.measure_after_marking_var.get():
                    measure_z_mm = self.move_to_measurement_position(
                        x=float(refreshed.robot_x),
                        y=float(refreshed.robot_y),
                        name=result.name,
                    )
                    try:
                        self.measure_marked_point(result.point, result.name, measure_z_mm=measure_z_mm)
                    finally:
                        self.move_to_z_travel_after_measurement(result.name)
                elif was_marked:
                    self._clear_mark_measurement(result.point)
                    self.log(f"{result.name}: alte Kontrollmesswerte geloescht, da automatische Messung inaktiv ist.")

                self.log(f"{result.name}: markiert.")
                self.gui_queue.put(("points_changed", None))

            self.log("Markierung abgeschlossen.")

        except InterruptedError:
            self.log("Markierung abgebrochen.")
        except Exception as exc:
            self.log(f"FEHLER: {exc}")
            self.gui_queue.put(("error", str(exc)))
        finally:
            self.gui_queue.put(("workflow_finished", None))

    def on_align_to_tracker_axes_changed(self) -> None:
        enabled = bool(self.align_to_tracker_axes_var.get())
        CONFIG.marker.align_to_tracker_axes = enabled
        try:
            update_marker_align_to_tracker_axes(enabled)
            self.log(
                "Markierausrichtung gespeichert: "
                + ("LT-X-Achse" if enabled else "Roboter-XY / fester Winkel")
            )
        except Exception as exc:
            self.log(f"FEHLER beim Speichern der Markierausrichtung: {exc}")
            messagebox.showerror("Punkte markieren", str(exc), parent=self.window)


    def on_measure_after_marking_changed(self) -> None:
        enabled = bool(self.measure_after_marking_var.get())
        CONFIG.marker.measure_after_marking = enabled
        try:
            update_marker_measure_after_marking(enabled)
            self.log(
                "Automatische Kontrollmessung gespeichert: "
                + ("aktiv" if enabled else "inaktiv")
            )
        except Exception as exc:
            self.log(f"FEHLER beim Speichern der Kontrollmessung: {exc}")
            messagebox.showerror("Punkte markieren", str(exc), parent=self.window)

    def _validate_tracker_measurement_ready(self) -> None:
        if self.tracker_receiver is None:
            raise RuntimeError("Automatische Messung ist aktiv, aber kein LasertrackerReceiver ist verfuegbar.")
        if not bool(getattr(self.tracker_receiver, "running", False)):
            raise RuntimeError("Automatische Messung ist aktiv, aber der Lasertracker-Empfang laeuft nicht.")
        if not hasattr(self.tracker_receiver, "capture_stable_point"):
            raise RuntimeError("Automatische Messung ist aktiv, aber capture_stable_point ist nicht verfuegbar.")
        self._marker_to_reflector_lt_vector()

    def move_to_measurement_position(self, *, x: float, y: float, name: str) -> float:
        """Faehrt vor der automatischen Messung auf Punktmitte, ohne den Stift erneut abzusenken.

        Z_CLEAR dient hier nur als sichere Stift-Abhebehoehe. Die Reflektor-Messrechnung
        verwendet ausschliesslich den kalibrierten marker_to_reflector-Vektor;
        Z_MARK/Z_CLEAR/Z_TRAVEL duerfen die Reflektorhoehe rechnerisch nicht beeinflussen.
        """

        z_mark_mm, z_clear_mm, _z_travel_mm = self._validated_marker_z_heights()
        z_measure_mm = z_clear_mm
        feedrate = float(getattr(CONFIG.xyz, "default_feedrate", 6000.0))
        tolerance_mm = float(getattr(CONFIG.xyz, "tolerance_mm", 0.05))

        self.log(
            f"{name}: fahre fuer Kontrollmessung auf Punktmitte "
            f"X={x:.3f}, Y={y:.3f}, Z_CLEAR={z_measure_mm:.3f} mm "
            f"(ohne erneutes Absenken auf Z_MARK={z_mark_mm:.3f} mm)."
        )
        self.send_robot_command(
            "move_absolute_verified",
            timeout_s=180.0,
            x=x,
            y=y,
            z=z_measure_mm,
            feedrate=feedrate,
            tolerance_mm=tolerance_mm,
        )
        return z_measure_mm

    def move_to_z_travel_after_measurement(self, name: str) -> None:
        try:
            z_travel = float(getattr(CONFIG.marker, "z_travel_mm", 176.0))
            feedrate = float(getattr(CONFIG.xyz, "default_feedrate", 6000.0))
            self.send_robot_command(
                "move_absolute",
                timeout_s=120.0,
                z=z_travel,
                feedrate=feedrate,
            )
            self.log(f"{name}: Kontrollmessung abgeschlossen, fahre Z_TRAVEL={z_travel:.3f} mm an.")
        except Exception as exc:
            self.log(f"{name}: Z_TRAVEL nach Kontrollmessung konnte nicht angefahren werden: {exc}")

    def measure_marked_point(self, point: Any, name: str, *, measure_z_mm: float) -> None:
        self._validate_tracker_measurement_ready()

        best_result: dict[str, Any] | None = None
        threshold_mm = AUTO_MEASURE_RETRY_D2D_THRESHOLD_MM
        max_attempts = AUTO_MEASURE_MAX_ATTEMPTS

        for attempt in range(1, max_attempts + 1):
            self.check_abort()
            self.log(
                f"{name}: automatische Kontrollmessung des oberen Reflektors "
                f"(Versuch {attempt}/{max_attempts})..."
            )

            result = self._capture_mark_measurement(point)
            result["attempt"] = attempt
            best_result = result

            d2d = float(result["d2d"])
            if d2d <= threshold_mm:
                if attempt > 1:
                    self.log(
                        f"{name}: Wiederholungsmessung plausibel: "
                        f"d2D={d2d:.3f} mm <= {threshold_mm:.3f} mm."
                    )
                break

            if attempt < max_attempts:
                self.log(
                    f"{name}: WARNUNG Kontrollmessung d2D={d2d:.3f} mm > "
                    f"{threshold_mm:.3f} mm. Messung wird einmal wiederholt."
                )
                time.sleep(0.25)
            else:
                warning_text = (
                    f"{name}: WARNUNG automatische Kontrollmessung weiterhin auffaellig: "
                    f"d2D={d2d:.3f} mm > {threshold_mm:.3f} mm nach {max_attempts} Versuchen. "
                    "Messwert wurde gespeichert, sollte aber geprueft werden."
                )
                self.log(warning_text)
                self.gui_queue.put(("warning", warning_text))

        if best_result is None:
            raise RuntimeError(f"{name}: automatische Kontrollmessung lieferte kein Ergebnis.")

        final_d2d = float(best_result["d2d"])
        measurement_valid = final_d2d <= threshold_mm
        warning_text = "" if measurement_valid else (
            f"d2D={final_d2d:.3f} mm > {threshold_mm:.3f} mm nach {max_attempts} Versuchen"
        )

        self._store_mark_measurement(
            point=point,
            reflector_lt=best_result["reflector_lt"],
            marker_lt=best_result["marker_lt"],
            delta=best_result["delta"],
            d2d=best_result["d2d"],
            d3d=best_result["d3d"],
            measure_z_mm=measure_z_mm,
            z_delta_mm=0.0,
            attempts=int(best_result["attempt"]),
            threshold_mm=threshold_mm,
            valid=measurement_valid,
            warning=warning_text,
        )

        marker_lt = best_result["marker_lt"]
        delta = best_result["delta"]
        d2d = float(best_result["d2d"])
        d3d = float(best_result["d3d"])
        self.log(
            f"{name}: Kontrollmessung Marker_LT "
            f"X={marker_lt[0]:.3f}, Y={marker_lt[1]:.3f}, Z={marker_lt[2]:.3f} mm | "
            f"Messhoehe Stift-Z={measure_z_mm:.3f} mm, Z-Korrektur=0.000 mm | "
            f"dX={delta[0]:.3f}, dY={delta[1]:.3f}, dZ={delta[2]:.3f}, "
            f"d2D={d2d:.3f}, d3D={d3d:.3f} mm | "
            f"Versuche={int(best_result['attempt'])}, "
            f"Status={'OK' if measurement_valid else 'WARNUNG'}"
        )

    def _capture_mark_measurement(self, point: Any) -> dict[str, Any]:
        measurement = self.tracker_receiver.capture_stable_point(
            timeout_s=float(getattr(CONFIG.tracker, "capture_timeout_s", 30.0)),
            min_age_after_start_s=0.1,
        )
        reflector_lt = (float(measurement.x), float(measurement.y), float(measurement.z))
        marker_to_reflector_lt = self._marker_to_reflector_lt_vector()
        marker_lt = tuple(
            reflector_lt[i] - marker_to_reflector_lt[i]
            for i in range(3)
        )

        target_lt = (
            float(getattr(point, "x", 0.0)),
            float(getattr(point, "y", 0.0)),
            float(getattr(point, "z", 0.0)),
        )
        delta = tuple(marker_lt[i] - target_lt[i] for i in range(3))
        d2d = math.hypot(delta[0], delta[1])
        d3d = math.sqrt(delta[0] * delta[0] + delta[1] * delta[1] + delta[2] * delta[2])

        return {
            "reflector_lt": reflector_lt,
            "marker_lt": marker_lt,
            "delta": delta,
            "d2d": d2d,
            "d3d": d3d,
        }

    def _increment_marking_count(self, point: Any) -> None:
        try:
            current = int(getattr(point, "marking_count", 0) or 0)
        except Exception:
            current = 0
        try:
            setattr(point, "marking_count", current + 1)
        except Exception:
            pass

    def _clear_mark_measurement(self, point: Any) -> None:
        measurement_fields = (
            "measured_after_marking",
            "measurement_method",
            "measured_at",
            "measured_reflector_lt_x",
            "measured_reflector_lt_y",
            "measured_reflector_lt_z",
            "measured_marker_lt_x",
            "measured_marker_lt_y",
            "measured_marker_lt_z",
            "measurement_dx",
            "measurement_dy",
            "measurement_dz",
            "measurement_d2d",
            "measurement_d3d",
            "measurement_robot_z_mm",
            "measurement_z_correction_mm",
            "measurement_attempts",
            "measurement_retry_threshold_mm",
            "measurement_valid",
            "measurement_warning",
        )
        for field in measurement_fields:
            try:
                if field == "measured_after_marking":
                    setattr(point, field, False)
                else:
                    setattr(point, field, None)
            except Exception:
                pass

    def _store_mark_measurement(
            self,
            *,
            point: Any,
            reflector_lt: tuple[float, float, float],
            marker_lt: tuple[float, float, float],
            delta: tuple[float, float, float],
            d2d: float,
            d3d: float,
            measure_z_mm: float,
            z_delta_mm: float,
            attempts: int,
            threshold_mm: float,
            valid: bool,
            warning: str,
    ) -> None:
        values = {
            "measured_after_marking": True,
            "measurement_method": "upper_reflector_offset",
            "measured_at": datetime.now().isoformat(timespec="seconds"),
            "measured_reflector_lt_x": reflector_lt[0],
            "measured_reflector_lt_y": reflector_lt[1],
            "measured_reflector_lt_z": reflector_lt[2],
            "measured_marker_lt_x": marker_lt[0],
            "measured_marker_lt_y": marker_lt[1],
            "measured_marker_lt_z": marker_lt[2],
            "measurement_dx": delta[0],
            "measurement_dy": delta[1],
            "measurement_dz": delta[2],
            "measurement_d2d": d2d,
            "measurement_d3d": d3d,
            "measurement_robot_z_mm": measure_z_mm,
            "measurement_z_correction_mm": z_delta_mm,
            "measurement_attempts": attempts,
            "measurement_retry_threshold_mm": threshold_mm,
            "measurement_valid": valid,
            "measurement_warning": warning,
        }
        for key, value in values.items():
            try:
                setattr(point, key, value)
            except Exception:
                pass

    def _marker_to_reflector_lt_vector(self) -> tuple[float, float, float]:
        vector = getattr(self.trafo_manager, "marker_to_reflector_lt", None)
        if vector is not None:
            try:
                return (float(vector[0]), float(vector[1]), float(vector[2]))
            except Exception:
                pass

        offset_robot = tuple(float(v) for v in CONFIG.transformation.marker_to_reflector_robot)
        trafo = getattr(self.trafo_manager, "active_trafo", None)
        rotation = getattr(trafo, "rotation", None)
        if rotation is None:
            raise RuntimeError(
                "Automatische Messung ist aktiv, aber marker_to_reflector_lt/Rotation ist nicht verfuegbar."
            )

        return self._apply_rotation_to_vector(rotation, offset_robot)

    @staticmethod
    def _apply_rotation_to_vector(rotation: Any, vector: tuple[float, float, float]) -> tuple[float, float, float]:
        values: list[float] = []
        for row in range(3):
            total = 0.0
            row_available = False
            for col in range(3):
                try:
                    coeff = float(rotation[row, col])
                except Exception:
                    try:
                        coeff = float(rotation[row][col])
                    except Exception:
                        if row == 2 and col == 2:
                            coeff = 1.0
                        elif row == 2 or col == 2:
                            coeff = 0.0
                        else:
                            raise RuntimeError("Rotationsmatrix fuer automatische Messung ist unvollstaendig.")
                row_available = True
                total += coeff * vector[col]
            if not row_available:
                raise RuntimeError("Rotationsmatrix fuer automatische Messung ist unvollstaendig.")
            values.append(total)
        return values[0], values[1], values[2]

    def _marker_angle_deg(self) -> float:
        base_angle = float(getattr(CONFIG.marker, "angle_deg", 0.0))

        if not bool(self.align_to_tracker_axes_var.get()):
            return self._normalize_angle_360(base_angle)

        tracker_x_angle_robot_deg = self._tracker_x_axis_angle_robot_deg()
        if tracker_x_angle_robot_deg is None:
            raise RuntimeError(
                "Markierausrichtung an LT-X-Achse ist aktiv, "
                "aber aus der Transformation konnte kein Rotationswinkel bestimmt werden."
            )

        return self._normalize_angle_360(tracker_x_angle_robot_deg + base_angle)

    def _tracker_x_axis_angle_robot_deg(self) -> float | None:
        if self.trafo_manager is None or not bool(getattr(self.trafo_manager, "valid", False)):
            return None

        trafo = getattr(self.trafo_manager, "active_trafo", None)
        rotation = getattr(trafo, "rotation", None)
        if rotation is None:
            return None

        try:
            # Annahme analog zur Haupt-App:
            # rotation bildet Roboterachsen ins Lasertracker-System ab.
            # Die LT-X-Achse im Robotersystem ergibt sich aus R^T * [1, 0].
            vx_robot = float(rotation[0, 0])
            vy_robot = float(rotation[0, 1])
        except Exception:
            try:
                vx_robot = float(rotation[0][0])
                vy_robot = float(rotation[0][1])
            except Exception:
                return None

        if abs(vx_robot) < 1e-12 and abs(vy_robot) < 1e-12:
            return None

        return math.degrees(math.atan2(vy_robot, vx_robot))

    @staticmethod
    def _normalize_angle_360(angle_deg: float) -> float:
        return float(angle_deg) % 360.0

    def get_label_for_point(self, point: Any) -> str:
        mode = self.label_mode_var.get()

        if mode == LABEL_NONE:
            return ""

        if mode == LABEL_REMARK:
            return str(getattr(point, "remark", "")).strip()

        return str(getattr(point, "name", "")).strip()

    @staticmethod
    def marker_shape_for_point(point: Any) -> str:
        shape = str(getattr(point, "marker_shape", "")).strip()
        return shape if shape else str(getattr(CONFIG.marker, "shape", "plus"))

    @staticmethod
    def marker_text_for_point(point: Any) -> str:
        code = getattr(point, "marker_code", None)
        shape = str(getattr(point, "marker_shape", "")).strip()

        if code is None and not shape:
            return str(getattr(CONFIG.marker, "shape", "plus"))

        if code is None:
            return shape

        return f"{code} / {shape}" if shape else str(code)

    @staticmethod
    def remark_for_point(point: Any) -> str:
        return str(getattr(point, "remark", "")).strip()

    def _validated_marker_z_heights(self) -> tuple[float, float, float]:
        z_min = float(getattr(CONFIG.xyz, "z_min", 150.0))
        z_max = float(getattr(CONFIG.xyz, "z_max", 200.0))

        z_mark = float(getattr(CONFIG.marker, "z_mark_mm", 166.0))
        z_clear = float(getattr(CONFIG.marker, "z_clear_mm", z_mark + 5.0))
        z_travel = float(getattr(CONFIG.marker, "z_travel_mm", z_mark + 10.0))

        if not (z_min <= z_mark <= z_clear <= z_travel <= z_max):
            raise ValueError(
                "Ungueltige Marker-Z-Hoehen. Erwartet: "
                f"{z_min:.3f} <= Z_MARK <= Z_CLEAR <= Z_TRAVEL <= {z_max:.3f} mm. "
                f"Aktuell: Z_MARK={z_mark:.3f}, "
                f"Z_CLEAR={z_clear:.3f}, Z_TRAVEL={z_travel:.3f}."
            )

        return z_mark, z_clear, z_travel

    def _validate_runtime_state(self) -> None:
        if self.xyz_worker is None:
            raise RuntimeError("XYZ-Worker ist nicht verfuegbar.")

        state = self.xyz_state_getter()
        if state is None:
            raise RuntimeError("Kein XYZ-Zustand verfuegbar.")
        if not bool(getattr(state, "connected", False)):
            raise RuntimeError("XYZ ist nicht verbunden.")
        if not bool(getattr(state, "homed", False)):
            raise RuntimeError("XYZ-Homing wurde noch nicht durchgefuehrt.")

        if self.trafo_manager is None or not bool(getattr(self.trafo_manager, "valid", False)):
            raise RuntimeError("Keine gueltige Transformation vorhanden.")

    def send_robot_command(self, command: str, timeout_s: float, **kwargs: Any) -> None:
        self.xyz_worker.send_command(command, **kwargs)
        self.wait_robot_done(timeout_s=timeout_s)

    def wait_robot_done(self, timeout_s: float) -> None:
        start = time.time()
        while time.time() - start < timeout_s:
            self.check_abort()
            state = self.xyz_state_getter()
            queue_empty = True
            try:
                queue_empty = self.xyz_worker.command_queue.empty()
            except Exception:
                queue_empty = True

            busy = bool(getattr(state, "busy", False)) if state is not None else False
            error_text = getattr(state, "error_text", "") if state is not None else ""

            if queue_empty and not busy:
                if error_text:
                    raise RuntimeError(str(error_text))
                return

            time.sleep(0.05)

        raise TimeoutError("Timeout beim Warten auf XYZRobotWorker.")

    # --------------------------------------------------
    # Queue / state
    # --------------------------------------------------

    def process_gui_queue(self) -> None:
        if self.closed:
            return

        try:
            while True:
                kind, payload = self.gui_queue.get_nowait()

                if kind == "log":
                    self._write_log(str(payload))
                elif kind == "points_changed":
                    self.refresh_after_point_change()
                elif kind == "workflow_finished":
                    self.workflow_running = False
                    self.refresh_after_point_change()
                    self.update_buttons()
                    if self.on_finished:
                        self.on_finished()
                elif kind == "warning":
                    messagebox.showwarning("Punkte markieren", str(payload), parent=self.window)
                elif kind == "error":
                    messagebox.showerror("Punkte markieren", str(payload), parent=self.window)
        except queue.Empty:
            pass

        if not self.closed:
            self.window.after(100, self.process_gui_queue)

    def refresh_after_point_change(self) -> None:
        all_results = evaluate_points_reachability(
            points=self.points,
            trafo_manager=self.trafo_manager,
            config=CONFIG,
            log=self.log,
            debug=True,
        )
        apply_reachability_to_points(all_results)
        self.reachable_results = reachable_points_only(all_results)

        # Bestehende Auswahl moeglichst erhalten.
        previously_selected_names = {
            self.result_by_iid[iid].name
            for iid in self.selected_iids
            if iid in self.result_by_iid
        }

        self.result_by_iid.clear()
        self.selected_iids.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)

        for index, result in enumerate(self.reachable_results):
            iid = str(index)
            self.result_by_iid[iid] = result
            is_selected = result.name in previously_selected_names and self._result_can_be_marked(result)
            if is_selected:
                self.selected_iids.add(iid)
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    SELECTED if is_selected else NOT_SELECTED,
                    result.name,
                    result.status_text,
                    self.marker_text_for_point(result.point),
                    self.remark_for_point(result.point),
                ),
            )

        reachable_count = len(self.reachable_results)
        marked_count = sum(1 for result in self.reachable_results if result.marked)
        unmarked_count = reachable_count - marked_count
        self.summary_var.set(
            f"Erreichbare Punkte: {reachable_count}    "
            f"Bereits markiert: {marked_count}    "
            f"Noch nicht markiert: {unmarked_count}"
        )

        if self.on_points_changed:
            self.on_points_changed()

    def log(self, text: str) -> None:
        self.gui_queue.put(("log", text))
        if self.external_log:
            self.external_log(f"[Punkte markieren] {text}")

    def _write_log(self, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        try:
            self.textbox.insert("end", f"[{timestamp}] {text}\n")
            self.textbox.see("end")
        except Exception:
            pass

    def check_abort(self) -> None:
        if self.abort_event.is_set():
            raise InterruptedError()

    def close(self) -> None:
        if self.workflow_running:
            self.abort_event.set()
            self.log("Abbruch angefordert...")
            return

        if self.closed:
            return

        self.move_robot_to_z_travel_on_close()

        self.closed = True
        try:
            self.window.grab_release()
        except Exception:
            pass
        self.window.destroy()

    def move_robot_to_z_travel_on_close(self) -> None:
        """Faehrt beim Schliessen des Markierdialogs defensiv auf Z_TRAVEL.

        Der Befehl wird asynchron in die XYZ-Worker-Queue gelegt. Dadurch bleibt
        das Schliessen des Dialogs reaktionsschnell und der Roboter faehrt nach
        Abschluss eventuell bereits gepufferter Befehle auf sichere Fahrhoehe.
        """

        try:
            state = self.xyz_state_getter()
            if self.xyz_worker is None or state is None:
                return
            if not bool(getattr(state, "connected", False)):
                return
            if not bool(getattr(state, "homed", False)):
                return

            z_travel = float(getattr(CONFIG.marker, "z_travel_mm", 176.0))
            self.xyz_worker.send_command(
                "move_absolute",
                z=z_travel,
                feedrate=900.0,
            )
            self.log(f"Dialog geschlossen: fahre Z_TRAVEL={z_travel:.3f} mm an.")
        except Exception as exc:
            self.log(f"Z_TRAVEL beim Schliessen konnte nicht angefordert werden: {exc}")


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

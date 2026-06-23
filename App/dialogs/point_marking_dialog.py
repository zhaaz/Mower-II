# App/dialogs/point_marking_dialog.py

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable

from config.mower_config import CONFIG
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


def show_point_marking_dialog(
        *,
        parent: tk.Misc,
        points: list[Any],
        xyz_worker: Any,
        xyz_state_getter: StateGetter,
        trafo_manager: Any,
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
            on_points_changed: PointsChangedCallback | None = None,
            on_finished: FinishedCallback | None = None,
            external_log: LogFunction | None = None,
    ) -> None:
        self.parent = parent
        self.points = points
        self.xyz_worker = xyz_worker
        self.xyz_state_getter = xyz_state_getter
        self.trafo_manager = trafo_manager
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

        self.window = tk.Toplevel(parent)
        self.window.title("Punkte markieren")
        self.window.minsize(620, 520)
        self.window.transient(parent)
        self.window.grab_set()

        _center_window(parent, self.window, 760, 620)

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
        root.grid_rowconfigure(1, weight=1)

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

        table_frame = ttk.LabelFrame(root, text="Markierbare Punkte", padding=8, style="PointMarking.TLabelframe")
        table_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        columns = ("selected", "name", "status")
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
        self.tree.column("selected", width=90, stretch=False, anchor="center")
        self.tree.column("name", width=260, stretch=True, anchor="w")
        self.tree.column("status", width=140, stretch=False, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<ButtonRelease-1>", self.on_table_click)
        self.tree.bind("<space>", self.on_space_toggle)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        log_frame = ttk.LabelFrame(root, text="Log", padding=8, style="PointMarking.TLabelframe")
        log_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
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
        button_frame.grid(row=3, column=0, sticky="ew")
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
            is_selected = not result.marked
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
                ),
            )

        self.update_buttons()
        self.log("Punktmarkierdialog geoeffnet.")

    def update_buttons(self) -> None:
        has_selected_unmarked = any(
            iid in self.selected_iids and not self.result_by_iid[iid].marked
            for iid in self.result_by_iid
        )
        has_unmarked = any(not result.marked for result in self.reachable_results)

        state_selected = "normal" if has_selected_unmarked and not self.workflow_running else "disabled"
        state_all = "normal" if has_unmarked and not self.workflow_running else "disabled"
        state_close = "normal"
        close_text = "Abbrechen" if self.workflow_running else "Schliessen"

        self.btn_selected.configure(state=state_selected)
        self.btn_all.configure(state=state_all)
        self.btn_close.configure(state=state_close, text=close_text)

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
        self.tree.item(iid, values=(flag, result.name, result.status_text))
        self.update_buttons()

    # --------------------------------------------------
    # Marking workflow
    # --------------------------------------------------

    def mark_selected_points(self) -> None:
        selected_results = [
            self.result_by_iid[iid]
            for iid in self.result_by_iid
            if iid in self.selected_iids and not self.result_by_iid[iid].marked
        ]
        self.start_marking(selected_results)

    def mark_all_markable_points(self) -> None:
        selected_results = [
            result for result in self.reachable_results
            if not result.marked
        ]
        self.start_marking(selected_results)

    def start_marking(self, selected_results: list[PointReachability]) -> None:
        if self.workflow_running:
            return

        if not selected_results:
            messagebox.showinfo("Punkte markieren", "Keine nicht markierten Punkte ausgewaehlt.", parent=self.window)
            return

        self.workflow_running = True
        self.abort_event.clear()
        self.update_buttons()
        self.log(f"Markierung gestartet: {len(selected_results)} Punkt(e).")

        self.workflow_thread = threading.Thread(
            target=self._marking_thread_main,
            args=(selected_results,),
            daemon=True,
        )
        self.workflow_thread.start()

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

                self.log(f"{index}/{total}: markiere {result.name}.")
                self.send_robot_command(
                    "mark_point",
                    timeout_s=240.0,
                    x=float(refreshed.robot_x),
                    y=float(refreshed.robot_y),
                    label=result.name,
                    marker_size=CONFIG.marker.size_mm,
                    marker_shape=CONFIG.marker.shape,
                    angle_deg=CONFIG.marker.angle_deg,
                )

                try:
                    result.point.marked = True
                except Exception:
                    pass

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
            is_selected = result.name in previously_selected_names and not result.marked
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

        self.closed = True
        try:
            self.window.grab_release()
        except Exception:
            pass
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

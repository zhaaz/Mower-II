# App/dialogs/trafo_dialog.py

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable

from Transformation.trafo_manager import TrafoManager
from Transformation.trafo_workflow import TrafoWorkflow, TrafoWorkflowConfig


StateGetter = Callable[[], Any]
LogFunction = Callable[[str], None]
FinishedCallback = Callable[[], None]


FONT_NORMAL = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SECTION = ("Segoe UI", 11, "bold")
FONT_MONO = ("Consolas", 10)


def show_trafo_dialog(
        *,
        parent: tk.Misc,
        xyz_worker: Any,
        tracker_receiver: Any,
        xyz_state_getter: StateGetter,
        trafo_manager: TrafoManager,
        on_finished: FinishedCallback | None = None,
        log: LogFunction | None = None,
) -> None:
    """Tk-Dialog fuer die Transformationsmessung.

    Der Workflow startet direkt nach dem Oeffnen des Dialogs. Die eigentliche
    Berechnung laeuft in einem Hintergrundthread; GUI-Updates erfolgen ueber
    eine Queue im Tk-Hauptthread.
    """

    dialog = TrafoDialog(
        parent=parent,
        xyz_worker=xyz_worker,
        tracker_receiver=tracker_receiver,
        xyz_state_getter=xyz_state_getter,
        trafo_manager=trafo_manager,
        on_finished=on_finished,
        external_log=log,
    )
    dialog.show()


class TrafoDialog:
    def __init__(
            self,
            *,
            parent: tk.Misc,
            xyz_worker: Any,
            tracker_receiver: Any,
            xyz_state_getter: StateGetter,
            trafo_manager: TrafoManager,
            on_finished: FinishedCallback | None = None,
            external_log: LogFunction | None = None,
    ) -> None:
        self.parent = parent
        self.xyz_worker = xyz_worker
        self.tracker_receiver = tracker_receiver
        self.xyz_state_getter = xyz_state_getter
        self.trafo_manager = trafo_manager
        self.on_finished = on_finished
        self.external_log = external_log

        self.workflow: TrafoWorkflow | None = None
        self.workflow_thread: threading.Thread | None = None
        self.result: Any | None = None
        self.closed = False
        self.workflow_running = False

        self.gui_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

        self.window = tk.Toplevel(parent)
        self.window.title("Transformation")
        self.window.minsize(760, 520)
        self.window.transient(parent)
        self.window.grab_set()

        _center_window(parent, self.window, 900, 660)

        self._configure_styles()
        self._build_ui()
        self.window.protocol("WM_DELETE_WINDOW", self.discard_and_close)
        self.window.bind("<Escape>", lambda _event: self.discard_and_close())

    def show(self) -> None:
        self.window.after(100, self.process_gui_queue)
        self.window.after(150, self.start_workflow)

    # --------------------------------------------------
    # UI
    # --------------------------------------------------

    def _configure_styles(self) -> None:
        style = ttk.Style(self.window)
        style.configure("Trafo.TLabel", font=FONT_NORMAL)
        style.configure("TrafoBold.TLabel", font=FONT_BOLD)
        style.configure("Trafo.TButton", font=FONT_NORMAL, padding=(8, 4))
        style.configure("Trafo.TLabelframe.Label", font=FONT_SECTION)

    def _build_ui(self) -> None:
        root = ttk.Frame(self.window, padding=12)
        root.grid(row=0, column=0, sticky="nsew")

        self.window.grid_rowconfigure(0, weight=1)
        self.window.grid_columnconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(2, weight=1)

        status_frame = ttk.LabelFrame(root, text="Status", padding=10, style="Trafo.TLabelframe")
        status_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        status_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(status_frame, text="Aktueller Schritt:", style="Trafo.TLabel").grid(
            row=0, column=0, padx=(0, 8), pady=3, sticky="w"
        )
        self.status_var = tk.StringVar(value="Vorbereitung...")
        ttk.Label(status_frame, textvariable=self.status_var, style="Trafo.TLabel").grid(
            row=0, column=1, pady=3, sticky="ew"
        )

        ttk.Label(status_frame, text="Fortschritt:", style="Trafo.TLabel").grid(
            row=1, column=0, padx=(0, 8), pady=3, sticky="w"
        )
        progress_row = ttk.Frame(status_frame)
        progress_row.grid(row=1, column=1, pady=3, sticky="ew")
        progress_row.grid_columnconfigure(0, weight=1)

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress = ttk.Progressbar(
            progress_row,
            orient="horizontal",
            mode="determinate",
            variable=self.progress_var,
            maximum=100.0,
        )
        self.progress.grid(row=0, column=0, sticky="ew")

        self.progress_text_var = tk.StringVar(value="0/0")
        ttk.Label(progress_row, textvariable=self.progress_text_var, width=10, style="Trafo.TLabel").grid(
            row=0, column=1, padx=(8, 0), sticky="e"
        )

        result_frame = ttk.LabelFrame(root, text="Ergebnis", padding=10, style="Trafo.TLabelframe")
        result_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        for col in (1, 3, 5):
            result_frame.grid_columnconfigure(col, weight=1)

        self.result_status_var = tk.StringVar(value="-")
        self.result_rms_var = tk.StringVar(value="-")
        self.result_max_var = tk.StringVar(value="-")
        self.result_scale_var = tk.StringVar(value="-")
        self.result_quality_var = tk.StringVar(value="-")

        ttk.Label(result_frame, text="Status:", style="Trafo.TLabel").grid(row=0, column=0, padx=(0, 6), pady=2, sticky="w")
        ttk.Label(result_frame, textvariable=self.result_status_var, style="Trafo.TLabel").grid(row=0, column=1, padx=(0, 16), pady=2, sticky="ew")
        ttk.Label(result_frame, text="RMS:", style="Trafo.TLabel").grid(row=0, column=2, padx=(0, 6), pady=2, sticky="w")
        ttk.Label(result_frame, textvariable=self.result_rms_var, style="Trafo.TLabel").grid(row=0, column=3, padx=(0, 16), pady=2, sticky="ew")
        ttk.Label(result_frame, text="Max:", style="Trafo.TLabel").grid(row=0, column=4, padx=(0, 6), pady=2, sticky="w")
        ttk.Label(result_frame, textvariable=self.result_max_var, style="Trafo.TLabel").grid(row=0, column=5, pady=2, sticky="ew")

        ttk.Label(result_frame, text="Massstab:", style="Trafo.TLabel").grid(row=1, column=0, padx=(0, 6), pady=2, sticky="w")
        ttk.Label(result_frame, textvariable=self.result_scale_var, style="Trafo.TLabel").grid(row=1, column=1, padx=(0, 16), pady=2, sticky="ew")
        ttk.Label(result_frame, text="Bewertung:", style="Trafo.TLabel").grid(row=1, column=2, padx=(0, 6), pady=2, sticky="w")
        ttk.Label(result_frame, textvariable=self.result_quality_var, style="Trafo.TLabel").grid(row=1, column=3, columnspan=3, pady=2, sticky="ew")

        log_frame = ttk.LabelFrame(root, text="Log", padding=8, style="Trafo.TLabelframe")
        log_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        self.textbox = ScrolledText(
            log_frame,
            wrap="none",
            height=18,
            font=FONT_MONO,
            background="#ffffff",
            foreground="#111111",
        )
        self.textbox.grid(row=0, column=0, sticky="nsew")

        button_frame = ttk.Frame(root)
        button_frame.grid(row=3, column=0, sticky="ew")
        for col in range(4):
            button_frame.grid_columnconfigure(col, weight=1)

        self.btn_cancel = ttk.Button(
            button_frame,
            text="Abbrechen",
            command=self.cancel_workflow,
            style="Trafo.TButton",
        )
        self.btn_cancel.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.btn_repeat = ttk.Button(
            button_frame,
            text="Trafo Wiederholen",
            command=self.repeat_workflow,
            state="disabled",
            style="Trafo.TButton",
        )
        self.btn_repeat.grid(row=0, column=1, padx=6, sticky="ew")

        self.btn_discard = ttk.Button(
            button_frame,
            text="Trafo Verwerfen",
            command=self.discard_and_close,
            style="Trafo.TButton",
        )
        self.btn_discard.grid(row=0, column=2, padx=6, sticky="ew")

        self.btn_accept = ttk.Button(
            button_frame,
            text="Trafo Uebernehmen",
            command=self.accept_trafo,
            state="disabled",
            style="Trafo.TButton",
        )
        self.btn_accept.grid(row=0, column=3, padx=(6, 0), sticky="ew")

    # --------------------------------------------------
    # Workflow
    # --------------------------------------------------

    def start_workflow(self) -> None:
        if self.workflow_running:
            return

        self._reset_result_display()
        self.workflow_running = True
        self.btn_cancel.configure(state="normal")
        self.btn_repeat.configure(state="disabled")
        self.btn_accept.configure(state="disabled")
        self.btn_discard.configure(state="normal")

        config = TrafoWorkflowConfig(
            tracker_capture_timeout_s=10.0,
            max_allowed_rms_mm=0.10,
            max_allowed_max_residual_mm=0.15,
            minimum_required_measurements=4,
            allow_scale=True,
            min_geometry_rank=2,
        )

        self.workflow = TrafoWorkflow(
            xyz_worker=self.xyz_worker,
            tracker_receiver=self.tracker_receiver,
            xyz_state_getter=self.xyz_state_getter,
            config=config,
            on_status=lambda text: self.gui_queue.put(("status", text)),
            on_progress=lambda current, total, label: self.gui_queue.put(
                ("progress", (current, total, label))
            ),
            on_log=lambda text: self.gui_queue.put(("log", text)),
        )

        self.workflow_thread = threading.Thread(
            target=self._workflow_thread_main,
            daemon=True,
        )
        self.workflow_thread.start()
        self.log("Transformationsworkflow gestartet.")

    def _workflow_thread_main(self) -> None:
        if self.workflow is None:
            self.gui_queue.put(("log", "FEHLER: Kein TrafoWorkflow vorhanden."))
            return

        result = self.workflow.run()
        self.gui_queue.put(("result", result))

    def cancel_workflow(self) -> None:
        if self.workflow is not None and self.workflow_running:
            self.workflow.cancel()
            self.log("Abbruch angefordert...")
            self.status_var.set("Abbruch angefordert...")

    def repeat_workflow(self) -> None:
        if self.workflow_running:
            return

        try:
            self.trafo_manager.clear_pending()
        except Exception:
            pass

        self.log("")
        self.log("------------------------------------------------------------")
        self.log("TRANSFORMATION WIRD WIEDERHOLT")
        self.log("------------------------------------------------------------")
        self.start_workflow()

    def accept_trafo(self) -> None:
        if self.result is None:
            return

        try:
            self.trafo_manager.set_pending(self.result)
            self.trafo_manager.accept_pending()
        except Exception as exc:
            self.log(f"FEHLER beim Uebernehmen der Trafo: {exc}")
            messagebox.showerror("Transformation", str(exc), parent=self.window)
            return

        self.log("Trafo wurde uebernommen und ist jetzt gueltig.")

        if self.on_finished:
            self.on_finished()

        self.close()

    def discard_and_close(self) -> None:
        if self.workflow is not None and self.workflow_running:
            self.workflow.cancel()

        try:
            self.trafo_manager.clear_pending()
        except Exception:
            pass

        if self.on_finished:
            self.on_finished()

        self.close()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.window.grab_release()
        except Exception:
            pass
        self.window.destroy()

    # --------------------------------------------------
    # Queue / GUI update
    # --------------------------------------------------

    def process_gui_queue(self) -> None:
        if self.closed:
            return

        try:
            while True:
                kind, payload = self.gui_queue.get_nowait()

                if kind == "status":
                    self.status_var.set(str(payload))
                    self.log(str(payload))

                elif kind == "progress":
                    current, total, label = payload
                    value = 100.0 * current / total if total else 0.0
                    self.progress_var.set(value)
                    self.progress_text_var.set(f"{current}/{total}")
                    self.log(f"Fortschritt {current}/{total}: {label}")

                elif kind == "log":
                    self.log(str(payload))

                elif kind == "result":
                    self.handle_result(payload)

        except queue.Empty:
            pass

        if not self.closed:
            self.window.after(100, self.process_gui_queue)

    # --------------------------------------------------
    # Ergebnis
    # --------------------------------------------------

    def handle_result(self, result: Any) -> None:
        self.result = result
        self.workflow_running = False

        self.btn_cancel.configure(state="disabled")
        self.btn_repeat.configure(state="normal")

        self.log("")
        self.log("------------------------------------------------------------")
        self.log("ERGEBNIS TRANSFORMATION")
        self.log("------------------------------------------------------------")
        self.log(f"Status: {result.status}")
        self.log(f"Meldung: {result.message}")
        self.log(f"Dauer: {result.duration_s:.2f} s")

        self.result_status_var.set(str(result.status))

        if result.error:
            self.log("")
            self.log(f"Fehler: {result.error}")

        if result.failed_measurements:
            self.log("")
            self.log("Nicht messbare Punkte:")

            for failed in result.failed_measurements:
                self.log(
                    f"  {failed['name']}: "
                    f"X={failed['robot_target_x']:.3f}, "
                    f"Y={failed['robot_target_y']:.3f} | "
                    f"{failed['reason']}"
                )

        if result.excluded_measurement is not None:
            excluded = result.excluded_measurement
            self.log("")
            self.log(f"Ausgeschlossener Punkt: {excluded.get('name', '-')}")

        if result.trafo is not None:
            trafo = result.trafo

            self.log("")
            self.log("Restklaffungen:")

            for measurement, residual_norm in zip(
                    result.used_measurements,
                    trafo.residual_norms,
            ):
                self.log(
                    f"  {measurement['name']}: "
                    f"{float(residual_norm):.3f} mm"
                )

            quality_text = self._evaluate_trafo_quality(
                rms=trafo.rms,
                max_residual=trafo.max_residual,
            )

            self.result_rms_var.set(f"{trafo.rms:.3f} mm")
            self.result_max_var.set(f"{trafo.max_residual:.3f} mm")
            self.result_scale_var.set(f"{trafo.scale:.9f}")
            self.result_quality_var.set(quality_text)

            self.log("")
            self.log("Qualitaet:")
            self.log(f"  Punktanzahl: {trafo.point_count}")
            self.log(f"  RMS:         {trafo.rms:.3f} mm")
            self.log(f"  Max:         {trafo.max_residual:.3f} mm")
            self.log(f"  Massstab:    {trafo.scale:.9f}")
            self.log(f"  Bewertung:   {quality_text}")

        self.log("")
        self.log("Ergebnis:")

        if result.success:
            self.log("  Transformation erfolgreich.")
            self.status_var.set("Transformation erfolgreich.")
            self.btn_accept.configure(state="normal")
            self.btn_discard.configure(state="normal")
        else:
            self.log("  Transformation nicht erfolgreich.")
            self.status_var.set(f"Transformation nicht erfolgreich: {result.status}")
            self.btn_accept.configure(state="disabled")

    def _reset_result_display(self) -> None:
        self.result = None
        self.status_var.set("Vorbereitung...")
        self.progress_var.set(0.0)
        self.progress_text_var.set("0/0")
        self.result_status_var.set("-")
        self.result_rms_var.set("-")
        self.result_max_var.set("-")
        self.result_scale_var.set("-")
        self.result_quality_var.set("-")

    @staticmethod
    def _evaluate_trafo_quality(*, rms: float, max_residual: float) -> str:
        if rms <= 0.05 and max_residual <= 0.10:
            return "SEHR GUT"

        if rms <= 0.10 and max_residual <= 0.20:
            return "GUT"

        if rms <= 0.25 and max_residual <= 0.50:
            return "OK"

        return "PRUEFEN"

    # --------------------------------------------------
    # Logging
    # --------------------------------------------------

    def log(self, text: str) -> None:
        try:
            self.textbox.insert("end", text + "\n")
            self.textbox.see("end")
        except Exception:
            pass

        if self.external_log:
            self.external_log(f"[Trafo] {text}")


def _center_window(parent: tk.Misc, window: tk.Toplevel, width: int, height: int) -> None:
    parent.update_idletasks()

    try:
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
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

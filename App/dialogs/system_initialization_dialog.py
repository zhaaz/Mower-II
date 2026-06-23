# App/dialogs/system_initialization_dialog.py

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Callable, Literal


StateGetter = Callable[[], Any]
LogFunction = Callable[[str], None]
FinishedCallback = Callable[[], None]
SendXYZCommand = Callable[..., bool]
StartTrackerFunction = Callable[[], None]
ShowTrafoDialogFunction = Callable[..., None]

DialogRequestKind = Literal["trafo"]

FONT_NORMAL = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SECTION = ("Segoe UI", 11, "bold")
FONT_MONO = ("Consolas", 10)


@dataclass
class StepState:
    key: str
    label: str
    status: str = "offen"


@dataclass
class DialogRequest:
    kind: DialogRequestKind
    event: threading.Event
    success: bool = False
    error_text: str = ""


def show_system_initialization_dialog(
        *,
        parent: tk.Misc,
        config: Any,
        xyz_worker_getter: Callable[[], Any],
        ensure_xyz_worker: Callable[[], bool],
        xyz_state_getter: StateGetter,
        send_xyz_command: SendXYZCommand,
        tracker_receiver_getter: Callable[[], Any],
        tracker_data_current_getter: Callable[[], bool],
        start_tracker: StartTrackerFunction,
        trafo_manager: Any,
        show_trafo_dialog: ShowTrafoDialogFunction | None,
        on_trafo_finished: FinishedCallback | None = None,
        on_finished: FinishedCallback | None = None,
        log: LogFunction | None = None,
) -> None:
    dialog = SystemInitializationDialog(
        parent=parent,
        config=config,
        xyz_worker_getter=xyz_worker_getter,
        ensure_xyz_worker=ensure_xyz_worker,
        xyz_state_getter=xyz_state_getter,
        send_xyz_command=send_xyz_command,
        tracker_receiver_getter=tracker_receiver_getter,
        tracker_data_current_getter=tracker_data_current_getter,
        start_tracker=start_tracker,
        trafo_manager=trafo_manager,
        show_trafo_dialog=show_trafo_dialog,
        on_trafo_finished=on_trafo_finished,
        on_finished=on_finished,
        external_log=log,
    )
    dialog.show()


class SystemInitializationDialog:
    """Initialisiert das System schrittweise.

    Ablauf:
        1. XYZ auf Config-Default-Port verbinden
        2. XYZ Homing durchfuehren
        3. Lasertracker UDP starten
        4. Transformationsdialog starten
    """

    def __init__(
            self,
            *,
            parent: tk.Misc,
            config: Any,
            xyz_worker_getter: Callable[[], Any],
            ensure_xyz_worker: Callable[[], bool],
            xyz_state_getter: StateGetter,
            send_xyz_command: SendXYZCommand,
            tracker_receiver_getter: Callable[[], Any],
            tracker_data_current_getter: Callable[[], bool],
            start_tracker: StartTrackerFunction,
            trafo_manager: Any,
            show_trafo_dialog: ShowTrafoDialogFunction | None,
            on_trafo_finished: FinishedCallback | None = None,
            on_finished: FinishedCallback | None = None,
            external_log: LogFunction | None = None,
    ) -> None:
        self.parent = parent
        self.config = config
        self.xyz_worker_getter = xyz_worker_getter
        self.ensure_xyz_worker = ensure_xyz_worker
        self.xyz_state_getter = xyz_state_getter
        self.send_xyz_command = send_xyz_command
        self.tracker_receiver_getter = tracker_receiver_getter
        self.tracker_data_current_getter = tracker_data_current_getter
        self.start_tracker = start_tracker
        self.trafo_manager = trafo_manager
        self.show_trafo_dialog = show_trafo_dialog
        self.on_trafo_finished = on_trafo_finished
        self.on_finished = on_finished
        self.external_log = external_log

        self.gui_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.abort_event = threading.Event()
        self.workflow_thread: threading.Thread | None = None
        self.workflow_running = False
        self.closed = False
        self.trafo_finished_event = threading.Event()

        self.steps: list[StepState] = [
            StepState("xyz_connect", "XYZ verbinden"),
            StepState("homing", "XYZ Homing"),
            StepState("tracker", "Tracker UDP starten"),
            StepState("trafo", "Transformation durchführen"),
        ]
        self.step_vars: dict[str, tk.StringVar] = {}

        self.window = tk.Toplevel(parent)
        self.window.title("System initialisieren")
        self.window.minsize(760, 520)
        self.window.transient(parent)
        self.window.grab_set()

        _center_window(parent, self.window, 820, 620)

        self._configure_styles()
        self._build_ui()
        self.window.protocol("WM_DELETE_WINDOW", self.close_or_cancel)
        self.window.bind("<Escape>", lambda _event: self.close_or_cancel())

    def show(self) -> None:
        self.window.after(100, self.process_gui_queue)
        self.window.after(150, self.start_workflow)

    # --------------------------------------------------
    # UI
    # --------------------------------------------------

    def _configure_styles(self) -> None:
        style = ttk.Style(self.window)
        style.configure("Init.TLabel", font=FONT_NORMAL)
        style.configure("InitBold.TLabel", font=FONT_BOLD)
        style.configure("Init.TButton", font=FONT_NORMAL, padding=(8, 4))
        style.configure("Init.TLabelframe.Label", font=FONT_SECTION)

    def _build_ui(self) -> None:
        root = ttk.Frame(self.window, padding=12)
        root.grid(row=0, column=0, sticky="nsew")

        self.window.grid_rowconfigure(0, weight=1)
        self.window.grid_columnconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(2, weight=1)

        status_frame = ttk.LabelFrame(root, text="Status", padding=10, style="Init.TLabelframe")
        status_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        status_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(status_frame, text="Aktueller Schritt:", style="Init.TLabel").grid(
            row=0, column=0, padx=(0, 8), pady=3, sticky="w"
        )
        self.status_var = tk.StringVar(value="Vorbereitung...")
        ttk.Label(status_frame, textvariable=self.status_var, style="Init.TLabel").grid(
            row=0, column=1, pady=3, sticky="ew"
        )

        ttk.Label(status_frame, text="Fortschritt:", style="Init.TLabel").grid(
            row=1, column=0, padx=(0, 8), pady=3, sticky="w"
        )
        progress_row = ttk.Frame(status_frame)
        progress_row.grid(row=1, column=1, pady=3, sticky="ew")
        progress_row.grid_columnconfigure(0, weight=1)

        self.progress_var = tk.DoubleVar(value=0.0)
        ttk.Progressbar(
            progress_row,
            orient="horizontal",
            mode="determinate",
            variable=self.progress_var,
            maximum=100.0,
        ).grid(row=0, column=0, sticky="ew")

        self.progress_text_var = tk.StringVar(value="0/4")
        ttk.Label(progress_row, textvariable=self.progress_text_var, width=10, style="Init.TLabel").grid(
            row=0, column=1, padx=(8, 0), sticky="e"
        )

        steps_frame = ttk.LabelFrame(root, text="Initialisierung", padding=10, style="Init.TLabelframe")
        steps_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        steps_frame.grid_columnconfigure(1, weight=1)

        for row, step in enumerate(self.steps):
            ttk.Label(steps_frame, text=step.label, style="Init.TLabel").grid(
                row=row, column=0, padx=(0, 12), pady=3, sticky="w"
            )
            var = tk.StringVar(value="offen")
            self.step_vars[step.key] = var
            ttk.Label(steps_frame, textvariable=var, style="Init.TLabel").grid(
                row=row, column=1, pady=3, sticky="ew"
            )

        log_frame = ttk.LabelFrame(root, text="Log", padding=8, style="Init.TLabelframe")
        log_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        self.textbox = ScrolledText(
            log_frame,
            wrap="word",
            height=16,
            font=FONT_MONO,
            background="#ffffff",
            foreground="#111111",
        )
        self.textbox.grid(row=0, column=0, sticky="nsew")

        button_frame = ttk.Frame(root)
        button_frame.grid(row=3, column=0, sticky="ew")
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)

        self.btn_cancel = ttk.Button(
            button_frame,
            text="Abbrechen",
            command=self.cancel_workflow,
            style="Init.TButton",
        )
        self.btn_cancel.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.btn_close = ttk.Button(
            button_frame,
            text="Schließen",
            command=self.close,
            state="disabled",
            style="Init.TButton",
        )
        self.btn_close.grid(row=0, column=1, padx=(6, 0), sticky="ew")

    # --------------------------------------------------
    # Workflow
    # --------------------------------------------------

    def start_workflow(self) -> None:
        if self.workflow_running:
            return

        self.workflow_running = True
        self.abort_event.clear()
        self.trafo_finished_event.clear()
        self.btn_cancel.configure(state="normal")
        self.btn_close.configure(state="disabled")

        self.workflow_thread = threading.Thread(target=self._workflow_thread_main, daemon=True)
        self.workflow_thread.start()
        self.log("Systeminitialisierung gestartet.")

    def _workflow_thread_main(self) -> None:
        success = False
        try:
            self._run_workflow()
            success = True
            self.set_status("Initialisierung abgeschlossen.")
            self.log("")
            self.log("Systeminitialisierung abgeschlossen.")
        except InterruptedError:
            self.set_status("Initialisierung abgebrochen.")
            self.log("")
            self.log("Initialisierung abgebrochen.")
        except Exception as exc:
            self.set_status(f"Fehler: {exc}")
            self.log("")
            self.log(f"FEHLER: {exc}")
        finally:
            self.gui_queue.put(("workflow_finished", success))

    def _run_workflow(self) -> None:
        if self.config is None:
            raise RuntimeError("CONFIG ist nicht geladen.")

        self.set_progress(0, len(self.steps))

        self.connect_xyz_default()
        self.set_progress(1, len(self.steps))

        self.home_xyz()
        self.set_progress(2, len(self.steps))

        self.start_tracker_udp()
        self.set_progress(3, len(self.steps))

        self.run_transformation()
        self.set_progress(4, len(self.steps))

    def connect_xyz_default(self) -> None:
        self.check_abort()
        self.set_step("xyz_connect", "läuft")
        self.set_status("XYZ wird auf Default-Port verbunden.")

        port = str(getattr(self.config.xyz, "port", "COM5"))
        baudrate = int(getattr(self.config.xyz, "baudrate", 115200))
        self.log(f"XYZ verbinden: Port={port}, Baudrate={baudrate}")

        state = self.xyz_state_getter()
        if state is not None and bool(getattr(state, "connected", False)):
            current_port = getattr(state, "port", "")
            self.log(f"XYZ ist bereits verbunden. Port={current_port or '-'}")
            self.set_step("xyz_connect", "bereits verbunden")
            return

        ok = self.ensure_xyz_worker()
        if not ok:
            raise RuntimeError("XYZ-Worker konnte nicht initialisiert werden.")

        ok = self.send_xyz_command("connect", port=port, baudrate=baudrate)
        if not ok:
            raise RuntimeError("XYZ-Verbindungsbefehl konnte nicht gesendet werden.")

        self.wait_for_xyz_state(
            predicate=lambda state: bool(getattr(state, "connected", False)),
            timeout_s=20.0,
            error_text="Timeout beim Verbinden mit XYZ.",
        )

        self.log("XYZ verbunden.")
        self.set_step("xyz_connect", "OK")

    def home_xyz(self) -> None:
        self.check_abort()
        self.set_step("homing", "läuft")
        self.set_status("XYZ-Homing wird durchgeführt.")

        state = self.xyz_state_getter()
        if state is not None and bool(getattr(state, "homed", False)):
            self.log("XYZ ist bereits referenziert.")
            self.set_step("homing", "bereits OK")
            return

        self.log("XYZ Homing starten.")
        ok = self.send_xyz_command("home_all")
        if not ok:
            raise RuntimeError("XYZ-Homing-Befehl konnte nicht gesendet werden.")

        self.wait_for_xyz_state(
            predicate=lambda state: bool(getattr(state, "homed", False)) and not bool(getattr(state, "busy", False)),
            timeout_s=180.0,
            error_text="Timeout beim XYZ-Homing.",
        )

        self.log("XYZ-Homing abgeschlossen.")
        self.set_step("homing", "OK")

    def start_tracker_udp(self) -> None:
        self.check_abort()
        self.set_step("tracker", "läuft")
        self.set_status("Tracker UDP-Empfang wird gestartet.")

        receiver = self.tracker_receiver_getter()
        if receiver is not None and bool(getattr(receiver, "running", False)):
            self.log("Tracker UDP-Empfang läuft bereits.")
        else:
            self.log("Tracker UDP-Empfang starten.")
            self.gui_queue.put(("start_tracker", None))

        self.wait_for_tracker_running(timeout_s=10.0)
        self.log("Tracker UDP-Empfang läuft.")

        # Fuer die anschliessende Transformation werden aktuelle Trackerdaten benoetigt.
        # Wenn noch keine Daten anliegen, warten wir kurz und melden dann klar den Zustand.
        self.set_status("Warte auf aktuelle Trackerdaten.")
        self.wait_for_tracker_data(timeout_s=30.0)
        self.log("Aktuelle Trackerdaten vorhanden.")
        self.set_step("tracker", "OK")

    def run_transformation(self) -> None:
        self.check_abort()
        self.set_step("trafo", "läuft")
        self.set_status("Transformation wird gestartet.")

        if self.show_trafo_dialog is None:
            raise RuntimeError("Trafo-Dialog ist nicht verfügbar.")
        if self.trafo_manager is None:
            raise RuntimeError("TrafoManager ist nicht verfügbar.")

        self.trafo_finished_event.clear()
        request = DialogRequest(kind="trafo", event=threading.Event())
        self.gui_queue.put(("dialog", request))

        while not request.event.wait(timeout=0.1):
            self.check_abort()

        if not request.success:
            raise RuntimeError(request.error_text or "Transformation konnte nicht gestartet werden.")

        self.set_status("Transformation läuft im Transformationsdialog.")
        self.log("Transformationsdialog geöffnet. Warte auf Abschluss.")

        while not self.trafo_finished_event.wait(timeout=0.1):
            self.check_abort()

        if not bool(getattr(self.trafo_manager, "valid", False)):
            reason = str(getattr(self.trafo_manager, "invalid_reason", ""))
            raise RuntimeError(reason or "Transformation wurde nicht gültig abgeschlossen.")

        self.log("Transformation gültig abgeschlossen.")
        self.set_step("trafo", "OK")

    # --------------------------------------------------
    # Wait helpers
    # --------------------------------------------------

    def wait_for_xyz_state(self, *, predicate: Callable[[Any], bool], timeout_s: float, error_text: str) -> None:
        start = time.time()
        while time.time() - start < timeout_s:
            self.check_abort()
            state = self.xyz_state_getter()
            if state is not None:
                error = getattr(state, "error_text", None)
                if error:
                    raise RuntimeError(str(error))
                if predicate(state):
                    return
            time.sleep(0.05)
        raise TimeoutError(error_text)

    def wait_for_tracker_running(self, *, timeout_s: float) -> None:
        start = time.time()
        while time.time() - start < timeout_s:
            self.check_abort()
            receiver = self.tracker_receiver_getter()
            if receiver is not None and bool(getattr(receiver, "running", False)):
                return
            time.sleep(0.05)
        raise TimeoutError("Timeout beim Starten des Tracker UDP-Empfangs.")

    def wait_for_tracker_data(self, *, timeout_s: float) -> None:
        start = time.time()
        while time.time() - start < timeout_s:
            self.check_abort()
            if bool(self.tracker_data_current_getter()):
                return
            time.sleep(0.1)
        raise TimeoutError("Keine aktuellen Trackerdaten empfangen.")

    # --------------------------------------------------
    # GUI queue
    # --------------------------------------------------

    def process_gui_queue(self) -> None:
        if self.closed:
            return

        try:
            while True:
                kind, payload = self.gui_queue.get_nowait()

                if kind == "log":
                    self._write_log(str(payload))
                elif kind == "status":
                    self.status_var.set(str(payload))
                elif kind == "progress":
                    current, total = payload
                    value = 100.0 * current / total if total else 0.0
                    self.progress_var.set(value)
                    self.progress_text_var.set(f"{current}/{total}")
                elif kind == "step":
                    key, status = payload
                    var = self.step_vars.get(str(key))
                    if var is not None:
                        var.set(str(status))
                elif kind == "start_tracker":
                    self.start_tracker()
                elif kind == "dialog":
                    request: DialogRequest = payload
                    if request.kind == "trafo":
                        self.create_trafo_dialog(request)
                elif kind == "workflow_finished":
                    success = bool(payload)
                    self.workflow_running = False
                    self.btn_cancel.configure(state="disabled")
                    self.btn_close.configure(state="normal")
                    if success:
                        self.btn_close.focus_set()
                    if self.on_finished:
                        self.on_finished()
        except queue.Empty:
            pass

        if not self.closed:
            self.window.after(100, self.process_gui_queue)

    def create_trafo_dialog(self, request: DialogRequest) -> None:
        try:
            xyz_worker = self.xyz_worker_getter()
            tracker_receiver = self.tracker_receiver_getter()
            if xyz_worker is None:
                raise RuntimeError("XYZ-Worker ist nicht verfügbar.")
            if tracker_receiver is None:
                raise RuntimeError("TrackerReceiver ist nicht verfügbar.")

            def trafo_finished_wrapper() -> None:
                if self.on_trafo_finished:
                    self.on_trafo_finished()
                self.trafo_finished_event.set()

            self.show_trafo_dialog(
                parent=self.window,
                xyz_worker=xyz_worker,
                tracker_receiver=tracker_receiver,
                xyz_state_getter=self.xyz_state_getter,
                trafo_manager=self.trafo_manager,
                on_finished=trafo_finished_wrapper,
                log=self.log,
            )
            request.success = True
            request.event.set()
        except Exception as exc:
            request.success = False
            request.error_text = str(exc)
            request.event.set()

    def set_status(self, text: str) -> None:
        self.gui_queue.put(("status", text))

    def set_progress(self, current: int, total: int) -> None:
        self.gui_queue.put(("progress", (current, total)))

    def set_step(self, key: str, status: str) -> None:
        self.gui_queue.put(("step", (key, status)))

    def log(self, text: str) -> None:
        self.gui_queue.put(("log", text))
        if self.external_log:
            self.external_log(f"[Init] {text}")

    def _write_log(self, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        try:
            self.textbox.insert("end", f"[{timestamp}] {text}\n")
            self.textbox.see("end")
        except Exception:
            pass

    # --------------------------------------------------
    # Buttons / close
    # --------------------------------------------------

    def cancel_workflow(self) -> None:
        if self.workflow_running:
            self.abort_event.set()
            self.trafo_finished_event.set()
            self.set_status("Abbruch angefordert...")
            self.log("Abbruch angefordert...")
        else:
            self.close()

    def close_or_cancel(self) -> None:
        if self.workflow_running:
            self.cancel_workflow()
        else:
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

    def check_abort(self) -> None:
        if self.abort_event.is_set():
            raise InterruptedError()


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

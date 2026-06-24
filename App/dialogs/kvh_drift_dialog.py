# App/dialogs/kvh_drift_dialog.py

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable


StateGetter = Callable[[], Any]
CommandSender = Callable[[str], None]
LogFunction = Callable[[str], None]
ActionSetter = Callable[[str], None]
FinishedCallback = Callable[[], None]

FONT_NORMAL = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SECTION = ("Segoe UI", 11, "bold")


def show_kvh_drift_dialog(
        *,
        parent: tk.Misc,
        state_getter: StateGetter,
        send_gyro_command: Callable[..., None],
        default_seconds: float = 30.0,
        on_finished: FinishedCallback | None = None,
        log: LogFunction | None = None,
        set_current_action: ActionSetter | None = None,
) -> None:
    dialog = KVHDriftDialog(
        parent=parent,
        state_getter=state_getter,
        send_gyro_command=send_gyro_command,
        default_seconds=default_seconds,
        on_finished=on_finished,
        log=log,
        set_current_action=set_current_action,
    )
    dialog.show()


class KVHDriftDialog:
    def __init__(
            self,
            *,
            parent: tk.Misc,
            state_getter: StateGetter,
            send_gyro_command: Callable[..., None],
            default_seconds: float,
            on_finished: FinishedCallback | None,
            log: LogFunction | None,
            set_current_action: ActionSetter | None,
    ) -> None:
        self.parent = parent
        self.state_getter = state_getter
        self.send_gyro_command = send_gyro_command
        self.default_seconds = float(default_seconds)
        self.on_finished = on_finished
        self.external_log = log
        self.set_current_action = set_current_action

        self.closed = False
        self.last_drift_active = False
        self.completion_reported = False

        self.window = tk.Toplevel(parent)
        self.window.title("KVH DSP Driftmessung")
        self.window.minsize(520, 400)
        self.window.transient(parent)
        self.window.grab_set()

        _center_window(parent, self.window, 560, 360)
        self._configure_styles()
        self._build_ui()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())

    def show(self) -> None:
        self._poll_state()

    def _configure_styles(self) -> None:
        style = ttk.Style(self.window)
        style.configure("KVH.TLabel", font=FONT_NORMAL)
        style.configure("KVHBold.TLabel", font=FONT_BOLD)
        style.configure("KVH.TButton", font=FONT_NORMAL, padding=(8, 4))
        style.configure("KVH.TLabelframe.Label", font=FONT_SECTION)

    def _build_ui(self) -> None:
        root = ttk.Frame(self.window, padding=12)
        root.grid(row=0, column=0, sticky="nsew")
        self.window.grid_rowconfigure(0, weight=1)
        self.window.grid_columnconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)

        info = ttk.LabelFrame(root, text="Driftmessung", padding=10, style="KVH.TLabelframe")
        info.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        info.grid_columnconfigure(1, weight=1)

        ttk.Label(info, text="Dauer [s]:", style="KVH.TLabel").grid(row=0, column=0, padx=(0, 8), pady=3, sticky="w")
        self.duration_var = tk.StringVar(value=f"{self.default_seconds:.0f}")
        self.entry_duration = ttk.Entry(info, textvariable=self.duration_var, width=10)
        self.entry_duration.grid(row=0, column=1, pady=3, sticky="w")

        self.status_var = tk.StringVar(value="Bereit. Sensor fuer Driftmessung ruhig stehen lassen.")
        ttk.Label(info, textvariable=self.status_var, style="KVH.TLabel").grid(row=1, column=0, columnspan=2, pady=(8, 3), sticky="w")

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress = ttk.Progressbar(info, orient="horizontal", mode="determinate", maximum=100.0, variable=self.progress_var)
        self.progress.grid(row=2, column=0, columnspan=2, pady=(5, 3), sticky="ew")

        self.progress_text_var = tk.StringVar(value="0.0 / 0.0 s")
        ttk.Label(info, textvariable=self.progress_text_var, style="KVH.TLabel").grid(row=3, column=0, columnspan=2, pady=(2, 3), sticky="w")

        values = ttk.LabelFrame(root, text="Messwerte", padding=10, style="KVH.TLabelframe")
        values.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        values.grid_columnconfigure(1, weight=1)

        self.value_vars: dict[str, tk.StringVar] = {
            "angle": tk.StringVar(value="-"),
            "rate": tk.StringVar(value="-"),
            "current_drift": tk.StringVar(value="-"),
            "pending_drift": tk.StringVar(value="-"),
            "packets": tk.StringVar(value="-"),
        }
        rows = [
            ("Winkel:", "angle"),
            ("Rate:", "rate"),
            ("Aktive Drift:", "current_drift"),
            ("Gemessene Drift:", "pending_drift"),
            ("Pakete:", "packets"),
        ]
        for row, (label, key) in enumerate(rows):
            ttk.Label(values, text=label, style="KVH.TLabel").grid(row=row, column=0, padx=(0, 8), pady=2, sticky="w")
            ttk.Label(values, textvariable=self.value_vars[key], style="KVH.TLabel").grid(row=row, column=1, pady=2, sticky="w")

        buttons = ttk.Frame(root)
        buttons.grid(row=2, column=0, sticky="ew")
        for col in range(5):
            buttons.grid_columnconfigure(col, weight=1)

        self.btn_start = ttk.Button(buttons, text="Start", command=self.start_drift, style="KVH.TButton")
        self.btn_start.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.btn_stop = ttk.Button(buttons, text="Stop Driftmessung", command=self.stop_drift, style="KVH.TButton")
        self.btn_stop.grid(row=0, column=1, padx=5, sticky="ew")

        self.btn_set = ttk.Button(buttons, text="Drift setzen", command=self.set_drift, style="KVH.TButton")
        self.btn_set.grid(row=0, column=2, padx=5, sticky="ew")

        self.btn_cancel = ttk.Button(buttons, text="Abbrechen", command=self.close, style="KVH.TButton")
        self.btn_cancel.grid(row=0, column=3, padx=5, sticky="ew")

        self.btn_close = ttk.Button(buttons, text="Schliessen", command=self.close, style="KVH.TButton")
        self.btn_close.grid(row=0, column=4, padx=(5, 0), sticky="ew")

        self._update_button_states(None)

    def start_drift(self) -> None:
        try:
            seconds = float(self.duration_var.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("KVH Driftmessung", "Bitte eine gueltige Dauer in Sekunden eingeben.", parent=self.window)
            return

        if seconds <= 0.0:
            messagebox.showerror("KVH Driftmessung", "Die Dauer muss groesser 0 sein.", parent=self.window)
            return

        try:
            self.send_gyro_command("determine_drift", seconds=seconds)
        except Exception as exc:
            messagebox.showerror("KVH Driftmessung", str(exc), parent=self.window)
            return

        self.completion_reported = False
        self.log(f"KVH DSP Driftmessung gestartet: {seconds:.1f} s.")
        self.action("KVH DSP Driftmessung laeuft...")

    def stop_drift(self) -> None:
        try:
            self.send_gyro_command("cancel_drift")
            self.log("KVH DSP Driftmessung gestoppt.")
            self.action("KVH DSP Driftmessung gestoppt.")
        except Exception as exc:
            messagebox.showerror("KVH Driftmessung", str(exc), parent=self.window)

    def set_drift(self) -> None:
        try:
            self.send_gyro_command("set_drift")
            self.log("KVH DSP Driftwert setzen angefordert.")
            self.action("KVH DSP Driftwert gesetzt.")
            if self.on_finished is not None:
                self.on_finished()
        except Exception as exc:
            messagebox.showerror("KVH Driftmessung", str(exc), parent=self.window)

    def _poll_state(self) -> None:
        if self.closed:
            return

        state = self.state_getter()
        self._update_values(state)
        self._update_progress(state)
        self._update_button_states(state)

        if not self.closed:
            self.window.after(100, self._poll_state)

    def _update_values(self, state: Any | None) -> None:
        if state is None:
            return

        self.value_vars["angle"].set(f"{float(getattr(state, 'angle_deg', 0.0)):+.6f} deg")
        self.value_vars["rate"].set(f"{float(getattr(state, 'rate_dps', 0.0)):+.6f} deg/s")
        self.value_vars["current_drift"].set(f"{float(getattr(state, 'drift_dps', 0.0)):+.10f} deg/s")
        pending = getattr(state, "pending_drift_dps", None)
        if pending is None:
            self.value_vars["pending_drift"].set("-")
        else:
            self.value_vars["pending_drift"].set(f"{float(pending):+.10f} deg/s")
        self.value_vars["packets"].set(str(int(getattr(state, "drift_packet_count", 0))))

    def _update_progress(self, state: Any | None) -> None:
        if state is None:
            self.progress_var.set(0.0)
            self.progress_text_var.set("0.0 / 0.0 s")
            return

        active = bool(getattr(state, "drift_active", False))
        elapsed = float(getattr(state, "drift_elapsed_s", 0.0))
        duration = float(getattr(state, "drift_duration_s", 0.0))
        progress = float(getattr(state, "drift_progress", 0.0))
        pending = getattr(state, "pending_drift_dps", None)

        self.progress_var.set(max(0.0, min(progress * 100.0, 100.0)))
        self.progress_text_var.set(f"{elapsed:.1f} / {duration:.1f} s")

        if active:
            self.status_var.set("Driftmessung laeuft. Sensor ruhig stehen lassen.")
        elif pending is not None:
            self.status_var.set("Driftmessung abgeschlossen. Driftwert kann gesetzt werden.")
            if self.last_drift_active and not self.completion_reported:
                self.completion_reported = True
                self.log(f"KVH DSP Driftmessung abgeschlossen: {float(pending):+.10f} deg/s.")
                self.action("KVH DSP Driftmessung abgeschlossen.")
        else:
            self.status_var.set("Bereit. Sensor fuer Driftmessung ruhig stehen lassen.")

        self.last_drift_active = active

    def _update_button_states(self, state: Any | None) -> None:
        active = bool(getattr(state, "drift_active", False)) if state is not None else False
        pending = getattr(state, "pending_drift_dps", None) if state is not None else None

        self.btn_start.configure(state="disabled" if active else "normal")
        self.btn_stop.configure(state="normal" if active else "disabled")
        self.btn_set.configure(state="normal" if (not active and pending is not None) else "disabled")
        self.entry_duration.configure(state="disabled" if active else "normal")

    def log(self, text: str) -> None:
        if self.external_log is not None:
            self.external_log(text)

    def action(self, text: str) -> None:
        if self.set_current_action is not None:
            self.set_current_action(text)

    def close(self) -> None:
        state = self.state_getter()
        if state is not None and bool(getattr(state, "drift_active", False)):
            confirmed = messagebox.askyesno(
                "KVH Driftmessung",
                "Driftmessung laeuft noch. Wirklich abbrechen?",
                parent=self.window,
            )
            if not confirmed:
                return
            try:
                self.send_gyro_command("cancel_drift")
            except Exception:
                pass

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

# App/dialogs/gyems_diagnostic_dialog.py

from __future__ import annotations

import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable

try:
    from GYEMS.gyems_rs485 import GyemsRmdRs485
except Exception:
    GyemsRmdRs485 = None


StateGetter = Callable[[], Any]
EnsureWorker = Callable[[], bool]
SendCommand = Callable[..., Any]
LogFunction = Callable[[str], None]
ActionFunction = Callable[[str], None]

FONT_NORMAL = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SECTION = ("Segoe UI", 11, "bold")
FONT_MONO = ("Consolas", 10)

DEFAULT_BAUDRATE = 115200
DEFAULT_MOTOR_ID = 1


def show_gyems_diagnostic_dialog(
        *,
        parent: tk.Misc,
        config: Any,
        ensure_worker: EnsureWorker,
        state_getter: StateGetter,
        send_command: SendCommand,
        log: LogFunction | None = None,
        set_current_action: ActionFunction | None = None,
) -> None:
    """Oeffnet einen GYEMS-Diagnosedialog ohne eigenen Worker.

    Der Dialog verwendet ausschliesslich den vom Hauptprogramm bereitgestellten
    GYEMS-Worker. Dadurch kann es keinen zweiten Zugriff auf denselben COM-Port
    geben und die ARN bleibt kontrollierbar.
    """

    dialog = GyemsDiagnosticDialog(
        parent=parent,
        config=config,
        ensure_worker=ensure_worker,
        state_getter=state_getter,
        send_command=send_command,
        log=log,
        set_current_action=set_current_action,
    )
    dialog.show()


class GyemsDiagnosticDialog:
    def __init__(
            self,
            *,
            parent: tk.Misc,
            config: Any,
            ensure_worker: EnsureWorker,
            state_getter: StateGetter,
            send_command: SendCommand,
            log: LogFunction | None = None,
            set_current_action: ActionFunction | None = None,
    ) -> None:
        self.parent = parent
        self.config = config
        self.ensure_worker = ensure_worker
        self.state_getter = state_getter
        self.send_command = send_command
        self.external_log = log
        self.set_current_action = set_current_action
        self.closed = False

        self.window = tk.Toplevel(parent)
        self.window.title("GYEMS Diagnose")
        self.window.minsize(760, 620)
        self.window.transient(parent)
        self.window.grab_set()

        _center_window(parent, self.window, 820, 680)

        self._configure_styles()
        self._build_ui()
        self._refresh_ports()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _event: self.close())

    def show(self) -> None:
        self.log("GYEMS Diagnose geoeffnet.")
        self.window.after(100, self.update_loop)

    # --------------------------------------------------
    # UI
    # --------------------------------------------------

    def _configure_styles(self) -> None:
        style = ttk.Style(self.window)
        style.configure("GyemsDiag.TLabel", font=FONT_NORMAL)
        style.configure("GyemsDiagBold.TLabel", font=FONT_BOLD)
        style.configure("GyemsDiag.TButton", font=FONT_NORMAL, padding=(8, 4))
        style.configure("GyemsDiag.TLabelframe.Label", font=FONT_SECTION)

    def _build_ui(self) -> None:
        root = ttk.Frame(self.window, padding=12)
        root.grid(row=0, column=0, sticky="nsew")
        self.window.grid_rowconfigure(0, weight=1)
        self.window.grid_columnconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(3, weight=1)

        self._build_connection(root)
        self._build_status(root)
        self._build_commands(root)
        self._build_log(root)

    def _build_connection(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Verbindung", padding=8, style="GyemsDiag.TLabelframe")
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        frame.grid_columnconfigure(1, weight=1)

        gyems_cfg = getattr(self.config, "gyems", None)
        default_port = str(getattr(gyems_cfg, "port", "COM4"))
        default_baudrate = int(getattr(gyems_cfg, "baudrate", DEFAULT_BAUDRATE))
        default_motor_id = int(getattr(gyems_cfg, "motor_id", DEFAULT_MOTOR_ID))

        ttk.Label(frame, text="COM-Port:", style="GyemsDiag.TLabel").grid(row=0, column=0, sticky="w")
        self.port_var = tk.StringVar(value=default_port)
        self.port_combo = ttk.Combobox(frame, textvariable=self.port_var, width=18, state="normal")
        self.port_combo.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(frame, text="Refresh", command=self._refresh_ports, style="GyemsDiag.TButton").grid(row=0, column=2, padx=(0, 8))

        ttk.Label(frame, text="Motor-ID:", style="GyemsDiag.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.motor_id_var = tk.StringVar(value=str(default_motor_id))
        ttk.Entry(frame, textvariable=self.motor_id_var, width=8).grid(row=1, column=1, sticky="w", padx=(8, 8), pady=(6, 0))

        ttk.Label(frame, text="Baudrate:", style="GyemsDiag.TLabel").grid(row=1, column=2, sticky="e", pady=(6, 0))
        self.baudrate_var = tk.StringVar(value=str(default_baudrate))
        ttk.Entry(frame, textvariable=self.baudrate_var, width=10).grid(row=1, column=3, sticky="w", padx=(8, 0), pady=(6, 0))

        self.btn_connect = ttk.Button(frame, text="Verbinden", command=self.connect, style="GyemsDiag.TButton")
        self.btn_connect.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.btn_disconnect = ttk.Button(frame, text="Trennen", command=self.disconnect, state="disabled", style="GyemsDiag.TButton")
        self.btn_disconnect.grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(8, 0))

    def _build_status(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Status", padding=8, style="GyemsDiag.TLabelframe")
        frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        for col in range(4):
            frame.grid_columnconfigure(col, weight=1)

        self.status_vars: dict[str, tk.StringVar] = {}
        fields = [
            ("connected", "Verbunden"),
            ("status", "Status"),
            ("angle", "Winkel abs."),
            ("rel_angle", "Winkel rel."),
            ("temp", "Temperatur"),
            ("iq", "Iq"),
            ("speed", "Speed raw"),
            ("enc", "Encoder"),
            ("cmd", "Speed-Cmd"),
            ("ok", "OK-Lesungen"),
            ("errors", "Fehlerzaehler"),
            ("model", "Modell"),
        ]
        for index, (key, label) in enumerate(fields):
            row = index // 2
            col = (index % 2) * 2
            ttk.Label(frame, text=f"{label}:", style="GyemsDiag.TLabel").grid(row=row, column=col, sticky="w", padx=(0, 8), pady=2)
            var = tk.StringVar(value="-")
            self.status_vars[key] = var
            ttk.Label(frame, textvariable=var, style="GyemsDiag.TLabel").grid(row=row, column=col + 1, sticky="w", pady=2)

        self.error_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.error_var, foreground="#b00020", style="GyemsDiag.TLabel").grid(
            row=6, column=0, columnspan=4, sticky="ew", pady=(6, 0)
        )

    def _build_commands(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Befehle", padding=8, style="GyemsDiag.TLabelframe")
        frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        for col in range(6):
            frame.grid_columnconfigure(col, weight=1)

        ttk.Button(frame, text="Model Info", command=lambda: self._send("read_model_info"), style="GyemsDiag.TButton").grid(row=0, column=0, sticky="ew", padx=3, pady=3)
        ttk.Button(frame, text="Read Errors", command=lambda: self._send("read_errors"), style="GyemsDiag.TButton").grid(row=0, column=1, sticky="ew", padx=3, pady=3)
        ttk.Button(frame, text="Clear Errors", command=lambda: self._send("clear_errors"), style="GyemsDiag.TButton").grid(row=0, column=2, sticky="ew", padx=3, pady=3)
        ttk.Button(frame, text="Read Once", command=lambda: self._send("read_once"), style="GyemsDiag.TButton").grid(row=0, column=3, sticky="ew", padx=3, pady=3)
        ttk.Button(frame, text="Referenz hier", command=lambda: self._send("set_reference_here"), style="GyemsDiag.TButton").grid(row=0, column=4, sticky="ew", padx=3, pady=3)
        ttk.Button(frame, text="STOP", command=lambda: self._send("stop_motor"), style="GyemsDiag.TButton").grid(row=0, column=5, sticky="ew", padx=3, pady=3)

        ttk.Label(frame, text="Speed [deg/s]:", style="GyemsDiag.TLabel").grid(row=1, column=0, sticky="w", padx=3, pady=(8, 3))
        self.speed_var = tk.StringVar(value="0")
        ttk.Entry(frame, textvariable=self.speed_var, width=10).grid(row=1, column=1, sticky="ew", padx=3, pady=(8, 3))
        ttk.Button(frame, text="Set Speed", command=self.set_speed, style="GyemsDiag.TButton").grid(row=1, column=2, sticky="ew", padx=3, pady=(8, 3))
        ttk.Button(frame, text="Speed 0", command=lambda: self._send("set_speed", speed_dps=0.0), style="GyemsDiag.TButton").grid(row=1, column=3, sticky="ew", padx=3, pady=(8, 3))

        ttk.Label(frame, text="Abs [deg]:", style="GyemsDiag.TLabel").grid(row=2, column=0, sticky="w", padx=3, pady=3)
        self.abs_var = tk.StringVar(value="0")
        ttk.Entry(frame, textvariable=self.abs_var, width=10).grid(row=2, column=1, sticky="ew", padx=3, pady=3)
        ttk.Button(frame, text="Move Abs", command=self.move_abs, style="GyemsDiag.TButton").grid(row=2, column=2, sticky="ew", padx=3, pady=3)

        for i, delta in enumerate((-5.0, -1.0, 1.0, 5.0)):
            ttk.Button(
                frame,
                text=f"{delta:+.0f} deg",
                command=lambda d=delta: self._send("move_relative", delta_deg=d),
                style="GyemsDiag.TButton",
            ).grid(row=3, column=i, sticky="ew", padx=3, pady=(8, 3))

    def _build_log(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text="Log", padding=8, style="GyemsDiag.TLabelframe")
        frame.grid(row=3, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        self.logbox = tk.Text(frame, height=10, font=FONT_MONO, wrap="word")
        self.logbox.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.logbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.logbox.configure(yscrollcommand=scrollbar.set)

    # --------------------------------------------------
    # Actions
    # --------------------------------------------------

    def _refresh_ports(self) -> None:
        if GyemsRmdRs485 is None:
            return
        try:
            ports = GyemsRmdRs485.list_ports()
            self.port_combo["values"] = ports
            if ports and not self.port_var.get():
                self.port_var.set(ports[0])
        except Exception as exc:
            self.log(f"COM-Port-Liste konnte nicht gelesen werden: {exc}")

    def connect(self) -> None:
        port = self.port_var.get().strip()
        if not port:
            messagebox.showerror("GYEMS Diagnose", "Bitte COM-Port angeben.", parent=self.window)
            return
        try:
            motor_id = int(self.motor_id_var.get().strip(), 0)
            baudrate = int(self.baudrate_var.get().strip())
        except ValueError:
            messagebox.showerror("GYEMS Diagnose", "Motor-ID oder Baudrate ist ungueltig.", parent=self.window)
            return
        if not self._ensure_worker():
            return
        self._send("connect", port=port, baudrate=baudrate, motor_id=motor_id)

    def disconnect(self) -> None:
        self._send("disconnect")

    def set_speed(self) -> None:
        try:
            speed = float(self.speed_var.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("GYEMS Diagnose", "Speed muss eine Zahl sein.", parent=self.window)
            return
        self._send("set_speed", speed_dps=speed)

    def move_abs(self) -> None:
        try:
            angle = float(self.abs_var.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("GYEMS Diagnose", "Winkel muss eine Zahl sein.", parent=self.window)
            return
        self._send("move_abs", angle_deg=angle)

    def _send(self, command: str, **kwargs: Any) -> None:
        if not self._ensure_worker():
            return
        try:
            self.send_command(command, **kwargs)
            args = ", ".join(f"{key}={value}" for key, value in kwargs.items())
            self.log(f"Befehl gesendet: {command}" + (f" ({args})" if args else ""))
            if self.set_current_action:
                self.set_current_action(f"GYEMS Diagnose: {command}")
        except Exception as exc:
            self.log(f"FEHLER beim Senden von {command}: {exc}")
            messagebox.showerror("GYEMS Diagnose", str(exc), parent=self.window)

    def _ensure_worker(self) -> bool:
        try:
            ok = bool(self.ensure_worker())
        except Exception as exc:
            self.log(f"GYEMS-Worker konnte nicht initialisiert werden: {exc}")
            messagebox.showerror("GYEMS Diagnose", str(exc), parent=self.window)
            return False
        if not ok:
            self.log("GYEMS-Worker ist nicht verfuegbar.")
            messagebox.showerror("GYEMS Diagnose", "GYEMS-Worker ist nicht verfuegbar.", parent=self.window)
            return False
        return True

    # --------------------------------------------------
    # Status update
    # --------------------------------------------------

    def update_loop(self) -> None:
        if self.closed:
            return
        self.apply_state(self.state_getter())
        self.window.after(200, self.update_loop)

    def apply_state(self, state: Any | None) -> None:
        connected = bool(getattr(state, "connected", False)) if state is not None else False
        self.status_vars["connected"].set("ja" if connected else "nein")
        self.status_vars["status"].set(str(getattr(state, "status_text", "-")) if state is not None else "-")
        self.status_vars["angle"].set(_fmt(getattr(state, "angle_deg", None) if state is not None else None, 3, "deg"))
        self.status_vars["rel_angle"].set(_fmt(getattr(state, "relative_angle_deg", None) if state is not None else None, 3, "deg"))
        temp = getattr(state, "temperature_C", None) if state is not None else None
        self.status_vars["temp"].set("-" if temp is None else f"{temp} C")
        self.status_vars["iq"].set("-" if state is None or getattr(state, "torque_current", None) is None else str(getattr(state, "torque_current")))
        self.status_vars["speed"].set("-" if state is None or getattr(state, "speed_raw", None) is None else str(getattr(state, "speed_raw")))
        self.status_vars["enc"].set("-" if state is None or getattr(state, "encoder_pos", None) is None else str(getattr(state, "encoder_pos")))
        self.status_vars["cmd"].set(_fmt(getattr(state, "last_speed_cmd_dps", None) if state is not None else None, 1, "deg/s"))
        self.status_vars["ok"].set(str(int(getattr(state, "ok_count", 0))) if state is not None else "0")
        self.status_vars["errors"].set(str(int(getattr(state, "error_count", 0))) if state is not None else "0")
        model = "-"
        if state is not None:
            driver = str(getattr(state, "model_driver", "") or "")
            motor = str(getattr(state, "model_motor", "") or "")
            if driver or motor:
                model = f"{driver} / {motor}"
        self.status_vars["model"].set(model)
        self.error_var.set(str(getattr(state, "error_text", "") or "") if state is not None else "")

        self.btn_connect.configure(state="disabled" if connected else "normal")
        self.btn_disconnect.configure(state="normal" if connected else "disabled")

    def log(self, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {text}"
        try:
            self.logbox.insert("end", line + "\n")
            self.logbox.see("end")
        except Exception:
            pass
        if self.external_log:
            self.external_log(f"[GYEMS Diagnose] {text}")

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            # Safety: diagnostic movement should never leave a non-zero speed command running.
            if self.state_getter() is not None:
                self.send_command("set_speed", speed_dps=0.0)
        except Exception:
            pass
        try:
            self.window.grab_release()
        except Exception:
            pass
        self.window.destroy()


def _fmt(value: Any, precision: int, suffix: str = "") -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.{precision}f} {suffix}".strip()
    except Exception:
        return "-"


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

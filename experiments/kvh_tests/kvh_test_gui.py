# experiments/kvh_tests/kvh_test_gui.py

from __future__ import annotations

import queue
import time
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

try:
    from .kvh_dsp_worker import KVHDSPWorker
    from .dsp3100 import DEFAULT_BAUDRATE
except ImportError:
    from kvh_dsp_worker import KVHDSPWorker
    from dsp3100 import DEFAULT_BAUDRATE


DEFAULT_PORT = "COM6"

FONT_NORMAL = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 12, "bold")
FONT_MONO = ("Consolas", 10)


class KVHTestGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()

        self.title("KVH DSP-3100 Test")
        self.geometry("720x520")
        self.minsize(640, 460)

        self.gui_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker = KVHDSPWorker(
            on_log=self.on_worker_log,
            on_state_changed=self.on_worker_state,
            update_interval_s=0.05,
        )
        self.worker.start()

        self.connected_var = tk.StringVar(value="nicht verbunden")
        self.angle_var = tk.StringVar(value="+0.000000 deg")
        self.rate_var = tk.StringVar(value="+0.000000 deg/s")
        self.drift_var = tk.StringVar(value="+0.0000000000 deg/s")
        self.packet_var = tk.StringVar(value="0")
        self.skipped_var = tk.StringVar(value="0")
        self.status_var = tk.StringVar(value="Bereit.")

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.process_gui_queue)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.grid(row=0, column=0, sticky="nsew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(2, weight=1)

        ttk.Label(root, text="KVH DSP-3100 Test", font=FONT_TITLE).grid(row=0, column=0, sticky="w", pady=(0, 10))

        conn = ttk.LabelFrame(root, text="Verbindung", padding=10)
        conn.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        for col in range(8):
            conn.grid_columnconfigure(col, weight=0)
        conn.grid_columnconfigure(7, weight=1)

        ttk.Label(conn, text="Port:", font=FONT_NORMAL).grid(row=0, column=0, padx=(0, 4), sticky="w")
        self.port_var = tk.StringVar(value=DEFAULT_PORT)
        ttk.Entry(conn, textvariable=self.port_var, width=10, font=FONT_NORMAL).grid(row=0, column=1, padx=(0, 10), sticky="w")

        ttk.Label(conn, text="Baud:", font=FONT_NORMAL).grid(row=0, column=2, padx=(0, 4), sticky="w")
        self.baud_var = tk.IntVar(value=DEFAULT_BAUDRATE)
        ttk.Entry(conn, textvariable=self.baud_var, width=10, font=FONT_NORMAL).grid(row=0, column=3, padx=(0, 10), sticky="w")

        ttk.Button(conn, text="Connect", command=self.connect).grid(row=0, column=4, padx=4)
        ttk.Button(conn, text="Disconnect", command=self.disconnect).grid(row=0, column=5, padx=4)
        ttk.Button(conn, text="Winkel 0", command=self.reset_angle).grid(row=0, column=6, padx=4)

        drift_frame = ttk.Frame(conn)
        drift_frame.grid(row=1, column=0, columnspan=8, pady=(10, 0), sticky="ew")
        ttk.Label(drift_frame, text="Driftdauer [s]:", font=FONT_NORMAL).grid(row=0, column=0, padx=(0, 4), sticky="w")
        self.drift_seconds_var = tk.DoubleVar(value=20.0)
        ttk.Entry(drift_frame, textvariable=self.drift_seconds_var, width=8, font=FONT_NORMAL).grid(row=0, column=1, padx=(0, 8), sticky="w")
        ttk.Button(drift_frame, text="Drift bestimmen", command=self.determine_drift).grid(row=0, column=2, padx=4, sticky="w")
        ttk.Label(drift_frame, text="Sensor dabei ruhig halten.", font=FONT_NORMAL).grid(row=0, column=3, padx=(10, 0), sticky="w")

        values = ttk.LabelFrame(root, text="Messwerte", padding=10)
        values.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        values.grid_columnconfigure(1, weight=1)

        self._value_row(values, 0, "Status:", self.connected_var)
        self._value_row(values, 1, "Winkel:", self.angle_var, big=True)
        self._value_row(values, 2, "Rate:", self.rate_var)
        self._value_row(values, 3, "Drift:", self.drift_var)
        self._value_row(values, 4, "Gültige Pakete:", self.packet_var)
        self._value_row(values, 5, "Übersprungene Bytes:", self.skipped_var)

        log_frame = ttk.LabelFrame(root, text="Log", padding=8)
        log_frame.grid(row=3, column=0, sticky="nsew")
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)
        self.logbox = ScrolledText(log_frame, height=8, font=FONT_MONO, background="#ffffff")
        self.logbox.grid(row=0, column=0, sticky="nsew")

        ttk.Label(root, textvariable=self.status_var, font=FONT_NORMAL).grid(row=4, column=0, sticky="ew", pady=(8, 0))

    def _value_row(self, parent: ttk.Frame, row: int, label: str, var: tk.StringVar, *, big: bool = False) -> None:
        ttk.Label(parent, text=label, font=FONT_BOLD).grid(row=row, column=0, padx=(0, 10), pady=3, sticky="w")
        font = ("Consolas", 20, "bold") if big else FONT_MONO
        ttk.Label(parent, textvariable=var, font=font).grid(row=row, column=1, pady=3, sticky="w")

    def connect(self) -> None:
        try:
            port = self.port_var.get().strip()
            baudrate = int(self.baud_var.get())
            self.worker.send_command("connect", port=port, baudrate=baudrate)
            self.status_var.set("Verbindung wird aufgebaut...")
        except Exception as exc:
            messagebox.showerror("Connect", str(exc), parent=self)

    def disconnect(self) -> None:
        self.worker.send_command("disconnect")
        self.status_var.set("Trennen angefordert...")

    def reset_angle(self) -> None:
        self.worker.send_command("reset_angle")

    def determine_drift(self) -> None:
        try:
            seconds = float(self.drift_seconds_var.get())
            self.worker.send_command("determine_drift", seconds=seconds)
        except Exception as exc:
            messagebox.showerror("Drift", str(exc), parent=self)

    def on_worker_log(self, text: str) -> None:
        self.gui_queue.put(("log", text))

    def on_worker_state(self, state) -> None:
        self.gui_queue.put(("state", state))

    def process_gui_queue(self) -> None:
        try:
            while True:
                kind, payload = self.gui_queue.get_nowait()
                if kind == "log":
                    self.write_log(str(payload))
                elif kind == "state":
                    self.apply_state(payload)
        except queue.Empty:
            pass
        self.after(100, self.process_gui_queue)

    def apply_state(self, state) -> None:
        self.connected_var.set("verbunden" if state.connected else "nicht verbunden")
        self.angle_var.set(f"{state.angle_deg:+.6f} deg")
        self.rate_var.set(f"{state.rate_dps:+.6f} deg/s")
        self.drift_var.set(f"{state.drift_dps:+.10f} deg/s")
        self.packet_var.set(str(state.valid_packets))
        self.skipped_var.set(str(state.skipped_bytes))
        if state.error_text:
            self.status_var.set(f"Fehler: {state.error_text}")
        elif state.drift_active:
            self.status_var.set("Driftmessung läuft...")
        else:
            self.status_var.set(state.status_text)

    def write_log(self, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.logbox.insert("end", f"[{timestamp}] {text}\n")
        self.logbox.see("end")

    def on_close(self) -> None:
        try:
            self.worker.stop()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    app = KVHTestGui()
    app.mainloop()

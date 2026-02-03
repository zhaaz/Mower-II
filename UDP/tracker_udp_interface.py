import socket
import threading
import time
import math
import tkinter as tk
from tkinter import ttk
from typing import Optional, Dict, Any


class TrackerUdpReceiver:
    """
    UDP-Receiver für Spatial Analyzer Watch Window Text.
    - Läuft in einem Hintergrundthread
    - Parst X/Y/Z + Einheit
    - Hält stets den neuesten Messwert als "snapshot"
    - Liefert link_alive (keine Daten seit timeout_s) und stale_s

    Wichtiger Hinweis:
    - start() kann mehrfach aufgerufen werden; läuft dann einfach weiter.
    - stop() beendet den Thread und schließt den Socket.
    """

    def __init__(
        self,
        port: int = 10000,
        bind_ip: str = "0.0.0.0",
        buffer_size: int = 8192,
        timeout_s: float = 5.0,
        socket_poll_s: float = 0.5,
    ):
        self.port = port
        self.bind_ip = bind_ip
        self.buffer_size = buffer_size
        self.timeout_s = float(timeout_s)
        self.socket_poll_s = float(socket_poll_s)

        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._lock = threading.Lock()
        self._latest: Optional[Dict[str, Any]] = None
        self._last_rx_time: Optional[float] = None
        self._last_valid_time: Optional[float] = None

    def start(self) -> None:
        if self.is_running():
            return

        self._stop_event.clear()

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.bind_ip, self.port))
        sock.settimeout(self.socket_poll_s)

        self._sock = sock
        self._thread = threading.Thread(target=self._run, name="TrackerUdpReceiver", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        if self._thread:
            self._thread.join(timeout=2.0)
        self._sock = None
        self._thread = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def get_latest(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self._latest is None:
                return None
            m = dict(self._latest)  # shallow copy
            last_rx = self._last_rx_time
            last_valid = self._last_valid_time

        now = time.time()
        link_alive = (last_rx is not None) and ((now - last_rx) < self.timeout_s)
        stale_s = None if last_valid is None else (now - last_valid)

        m["link_alive"] = link_alive
        m["stale_s"] = stale_s
        return m

    def _run(self) -> None:
        assert self._sock is not None
        sock = self._sock

        while not self._stop_event.is_set():
            try:
                data, addr = sock.recvfrom(self.buffer_size)
            except TimeoutError:
                continue
            except OSError:
                break  # socket closed

            rx_ts = time.time()
            with self._lock:
                self._last_rx_time = rx_ts

            line = self._decode(data)
            parsed = self._parse_sa_watch_line(line)

            measurement = {
                "timestamp": rx_ts,
                "src_ip": addr[0],
                "src_port": addr[1],
                "x": parsed.get("x"),
                "y": parsed.get("y"),
                "z": parsed.get("z"),
                "unit": parsed.get("unit", "unknown"),
                "measurement_valid": parsed.get("measurement_valid", False),
                "raw": line,
            }

            if measurement["measurement_valid"]:
                with self._lock:
                    self._last_valid_time = rx_ts

            with self._lock:
                self._latest = measurement

    @staticmethod
    def _decode(data: bytes) -> str:
        try:
            return data.decode("utf-8").strip()
        except UnicodeDecodeError:
            return data.decode("latin-1").strip()

    @staticmethod
    def _parse_sa_watch_line(line: str) -> Dict[str, Any]:
        parts = [p.strip() for p in line.split("|")]

        x = y = z = None
        unit = None

        for p in parts:
            if not p:
                continue

            if "Units:" in p:
                tail = p.split("Units:", 1)[1].strip().strip(",").strip()
                if tail.startswith("(") and tail.endswith(")"):
                    tail = tail[1:-1].strip()
                unit = tail if tail else "unknown"
                continue

            if p.startswith("X"):
                x = TrackerUdpReceiver._parse_axis_value(p)
                continue
            if p.startswith("Y"):
                y = TrackerUdpReceiver._parse_axis_value(p)
                continue
            if p.startswith("Z"):
                z = TrackerUdpReceiver._parse_axis_value(p)
                continue

        valid = (
            x is not None and y is not None and z is not None
            and math.isfinite(x) and math.isfinite(y) and math.isfinite(z)
        )

        return {"x": x, "y": y, "z": z, "unit": unit or "unknown", "measurement_valid": valid}

    @staticmethod
    def _parse_axis_value(token: str) -> Optional[float]:
        parts = [t.strip() for t in token.split(",")]
        if len(parts) < 2 or not parts[1]:
            return None
        try:
            return float(parts[1])
        except ValueError:
            return None


class TrackerGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tracker UDP Monitor (Spatial Analyzer)")
        self.geometry("860x420")

        self.rx = TrackerUdpReceiver(port=10000, timeout_s=5.0)

        # --- UI Variables ---
        self.var_running = tk.StringVar(value="Stopped")
        self.var_link = tk.StringVar(value="Offline")
        self.var_valid = tk.StringVar(value="-")
        self.var_xyz = tk.StringVar(value="-")
        self.var_unit = tk.StringVar(value="-")
        self.var_ts = tk.StringVar(value="-")
        self.var_src = tk.StringVar(value="-")
        self.var_stale = tk.StringVar(value="-")

        # --- Layout ---
        self._build_ui()

        # Update loop
        self.after(100, self._update_view)

        # Proper shutdown
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        top = ttk.Frame(self)
        top.pack(fill="x", **pad)

        ttk.Button(top, text="Start", command=self._on_start).pack(side="left")
        ttk.Button(top, text="Stop", command=self._on_stop).pack(side="left", padx=(10, 0))

        ttk.Label(top, text="Receiver:").pack(side="left", padx=(20, 5))
        ttk.Label(top, textvariable=self.var_running).pack(side="left")

        sep = ttk.Separator(self, orient="horizontal")
        sep.pack(fill="x", padx=10, pady=10)

        main = ttk.Frame(self)
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # Status block
        status = ttk.LabelFrame(main, text="Status")
        status.pack(fill="x", pady=(0, 10))

        self._row(status, 0, "UDP Link:", self.var_link)
        self._row(status, 1, "Measurement valid:", self.var_valid)
        self._row(status, 2, "Stale (s):", self.var_stale)
        self._row(status, 3, "Timestamp:", self.var_ts)
        self._row(status, 4, "Source:", self.var_src)

        # Data block
        data = ttk.LabelFrame(main, text="Latest measurement (snapshot)")
        data.pack(fill="both", expand=True)

        self._row(data, 0, "X, Y, Z:", self.var_xyz)
        self._row(data, 1, "Unit:", self.var_unit)

        # Raw / dict view
        raw = ttk.LabelFrame(main, text="Data structure (dict) / raw")
        raw.pack(fill="both", expand=True, pady=(10, 0))

        self.txt = tk.Text(raw, height=8, wrap="none")
        self.txt.pack(fill="both", expand=True, padx=8, pady=8)
        self.txt.configure(state="disabled")

    def _row(self, parent, r, label, var):
        ttk.Label(parent, text=label, width=18).grid(row=r, column=0, sticky="w", padx=8, pady=4)
        ttk.Label(parent, textvariable=var).grid(row=r, column=1, sticky="w", padx=8, pady=4)

    def _on_start(self):
        self.rx.start()
        self.var_running.set("Running")

    def _on_stop(self):
        self.rx.stop()
        self.var_running.set("Stopped")
        # Optional: UI status zurücksetzen
        self.var_link.set("Offline")

    def _update_view(self):
        # Receiver running indicator (falls Thread unerwartet stoppt)
        self.var_running.set("Running" if self.rx.is_running() else "Stopped")

        m = self.rx.get_latest()

        if m is None:
            self.var_link.set("Offline")
            self.var_valid.set("-")
            self.var_xyz.set("-")
            self.var_unit.set("-")
            self.var_ts.set("-")
            self.var_src.set("-")
            self.var_stale.set("-")
            self._set_text("")
        else:
            # Link status
            self.var_link.set("Online" if m.get("link_alive") else "Offline")

            # Valid
            self.var_valid.set("True" if m.get("measurement_valid") else "False")

            # XYZ
            x, y, z = m.get("x"), m.get("y"), m.get("z")
            if x is not None and y is not None and z is not None:
                self.var_xyz.set(f"{x:.2f}, {y:.2f}, {z:.2f}")
            else:
                self.var_xyz.set(f"{x}, {y}, {z}")

            # Unit
            self.var_unit.set(str(m.get("unit", "-")))

            # Timestamp
            ts = m.get("timestamp")
            self.var_ts.set(f"{ts:.3f}" if isinstance(ts, (int, float)) else str(ts))

            # Source
            self.var_src.set(f'{m.get("src_ip")}:{m.get("src_port")}')

            # Stale
            stale_s = m.get("stale_s")
            self.var_stale.set(f"{stale_s:.2f}" if isinstance(stale_s, (int, float)) else "-")

            # Data structure / raw
            # Wir zeigen das dict ohne riesige raw-Zeile doppelt an, aber raw ist oft hilfreich.
            view = dict(m)
            self._set_text(self._pretty(view))

        # GUI refresh rate (10 Hz)
        self.after(100, self._update_view)

    def _set_text(self, s: str):
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", s)
        self.txt.configure(state="disabled")

    @staticmethod
    def _pretty(d: Dict[str, Any]) -> str:
        # einfache, stabile Pretty-Ausgabe ohne pprint-Import
        lines = []
        for k in sorted(d.keys()):
            v = d[k]
            if isinstance(v, float):
                lines.append(f"{k}: {v:.6f}")
            else:
                lines.append(f"{k}: {v}")
        return "\n".join(lines)

    def _on_close(self):
        try:
            self.rx.stop()
        finally:
            self.destroy()


if __name__ == "__main__":
    # ttk Standard-Theme aktivieren
    root = TrackerGui()
    try:
        ttk.Style().theme_use("clam")
    except Exception:
        pass
    root.mainloop()

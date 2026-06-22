import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

import serial


class SerialGCodeGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SKR G-Code Sender (minimal)")

        self.ser = None
        self.rx_thread = None
        self.rx_stop = threading.Event()

        # Defaults
        self.port_var = tk.StringVar(value="COM5")
        self.baud_var = tk.StringVar(value="115200")
        self.gcode_var = tk.StringVar(value="G0 X10 Y10 F3000")
        self.wait_ok_var = tk.BooleanVar(value=True)

        self._build_ui()

    def _build_ui(self):
        frm = ttk.Frame(self.root, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # Connection row
        row0 = ttk.Frame(frm)
        row0.grid(row=0, column=0, sticky="ew")
        row0.columnconfigure(6, weight=1)

        ttk.Label(row0, text="Port:").grid(row=0, column=0, padx=(0, 6))
        ttk.Entry(row0, textvariable=self.port_var, width=10).grid(row=0, column=1, padx=(0, 12))

        ttk.Label(row0, text="Baud:").grid(row=0, column=2, padx=(0, 6))
        ttk.Entry(row0, textvariable=self.baud_var, width=10).grid(row=0, column=3, padx=(0, 12))

        ttk.Checkbutton(row0, text="wait for 'ok'", variable=self.wait_ok_var).grid(row=0, column=4, padx=(0, 12))

        self.btn_connect = ttk.Button(row0, text="Connect", command=self.connect)
        self.btn_connect.grid(row=0, column=5, padx=(0, 6))

        self.btn_disconnect = ttk.Button(row0, text="Disconnect", command=self.disconnect, state="disabled")
        self.btn_disconnect.grid(row=0, column=6, sticky="w")

        # G-code send row
        row1 = ttk.Frame(frm)
        row1.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        row1.columnconfigure(0, weight=1)

        self.entry_gcode = ttk.Entry(row1, textvariable=self.gcode_var)
        self.entry_gcode.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.entry_gcode.bind("<Return>", lambda e: self.send_gcode())

        self.btn_send = ttk.Button(row1, text="Send", command=self.send_gcode, state="disabled")
        self.btn_send.grid(row=0, column=1)

        # Log box
        self.log = tk.Text(frm, height=18, wrap="word")
        self.log.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        frm.rowconfigure(2, weight=1)

        # Status bar
        self.status_var = tk.StringVar(value="Disconnected")
        ttk.Label(frm, textvariable=self.status_var).grid(row=3, column=0, sticky="w", pady=(8, 0))

    def _log(self, msg: str):
        self.log.insert("end", msg + "\n")
        self.log.see("end")

    def connect(self):
        if self.ser and self.ser.is_open:
            return

        port = self.port_var.get().strip()
        try:
            baud = int(self.baud_var.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Baudrate must be an integer.")
            return

        try:
            self.ser = serial.Serial(port=port, baudrate=baud, timeout=0.2)
        except Exception as e:
            messagebox.showerror("Connect failed", str(e))
            self.ser = None
            return

        # Many boards reset on connect → give it a moment, then flush input
        time.sleep(1.5)
        try:
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
        except Exception:
            pass

        self.rx_stop.clear()
        self.rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self.rx_thread.start()

        self._log(f"[INFO] Connected to {port} @ {baud}")
        self.status_var.set(f"Connected: {port} @ {baud}")

        self.btn_connect.config(state="disabled")
        self.btn_disconnect.config(state="normal")
        self.btn_send.config(state="normal")

    def disconnect(self):
        self.rx_stop.set()
        if self.rx_thread and self.rx_thread.is_alive():
            self.rx_thread.join(timeout=1.0)

        if self.ser:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

        self._log("[INFO] Disconnected")
        self.status_var.set("Disconnected")

        self.btn_connect.config(state="normal")
        self.btn_disconnect.config(state="disabled")
        self.btn_send.config(state="disabled")

    def _rx_loop(self):
        # Read lines continuously without blocking GUI
        while not self.rx_stop.is_set() and self.ser and self.ser.is_open:
            try:
                line = self.ser.readline()
                if line:
                    text = line.decode(errors="replace").strip()
                    # marshal UI update onto main thread
                    self.root.after(0, self._log, f"[RX] {text}")
            except Exception as e:
                self.root.after(0, self._log, f"[RX-ERR] {e}")
                break

    def send_gcode(self):
        if not (self.ser and self.ser.is_open):
            messagebox.showwarning("Not connected", "Please connect first.")
            return

        cmd = self.gcode_var.get().strip()
        if not cmd:
            return

        # Ensure single line, proper newline
        line = (cmd + "\n").encode()

        try:
            self.ser.write(line)
            self.ser.flush()
            self._log(f"[TX] {cmd}")
        except Exception as e:
            self._log(f"[TX-ERR] {e}")
            return

        if self.wait_ok_var.get():
            # wait for "ok" in a short worker thread so GUI stays responsive
            threading.Thread(target=self._wait_for_ok, daemon=True).start()

    def _wait_for_ok(self):
        deadline = time.time() + 3.0  # seconds
        buf = ""
        while time.time() < deadline and self.ser and self.ser.is_open:
            try:
                chunk = self.ser.read(256)
                if chunk:
                    text = chunk.decode(errors="replace")
                    buf += text
                    # log any complete lines we got
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()
                        if line:
                            self.root.after(0, self._log, f"[RX] {line}")
                        if line.lower().startswith("ok") or line.lower() == "ok":
                            return
                else:
                    time.sleep(0.05)
            except Exception as e:
                self.root.after(0, self._log, f"[OK-WAIT-ERR] {e}")
                return

        self.root.after(0, self._log, "[WARN] No 'ok' received (timeout)")


if __name__ == "__main__":
    root = tk.Tk()
    app = SerialGCodeGUI(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.disconnect(), root.destroy()))
    root.mainloop()
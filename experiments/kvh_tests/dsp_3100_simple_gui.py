import tkinter as tk
from tkinter import ttk
import threading
import time
import math
from dsp3100 import DSP3100  # Importiere deine bestehende Klasse!
import serial.tools.list_ports


class DSPApp:
    def __init__(self, root):
        self.root = root
        self.root.title("DSP3100 Test GUI")
        self.dsp = DSP3100()
        self.running = False

        self.angle_var = tk.StringVar(value="0.000°")
        self.drift_var = tk.StringVar(value="0.000000 °/s")
        self.selected_port = tk.StringVar()

        # 🔸 Layout: linke Seite für Anzeige, rechte Seite für Buttons
        main_frame = ttk.Frame(root)
        main_frame.pack(padx=10, pady=10)

        display_frame = ttk.Frame(main_frame)
        display_frame.grid(row=0, column=0, padx=10)

        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=0, column=1, padx=10, sticky="n")

        # --- Anzeige: Winkel, Drift, Richtungspfeil ---
        ttk.Label(display_frame, text="Winkel:").grid(row=0, column=0, sticky="e")
        self.angle_label = ttk.Label(display_frame, textvariable=self.angle_var, font=("Courier", 14))
        self.angle_label.grid(row=0, column=1, sticky="w")

        ttk.Label(display_frame, text="Drift:").grid(row=1, column=0, sticky="e")
        self.drift_label = ttk.Label(display_frame, textvariable=self.drift_var, font=("Courier", 12))
        self.drift_label.grid(row=1, column=1, sticky="w")

        self.canvas = tk.Canvas(display_frame, width=100, height=100, bg="white")
        self.canvas.grid(row=2, column=0, columnspan=2, pady=10)
        self.arrow = self.canvas.create_line(50, 50, 50, 10, arrow=tk.LAST, width=3)

        # --- Portauswahl oben rechts ---
        ttk.Label(control_frame, text="Port:").pack(anchor="w")
        self.port_menu = ttk.Combobox(control_frame, textvariable=self.selected_port, values=self.get_serial_ports(), state="readonly", width=15)
        self.port_menu.pack(pady=(0, 10))
        if self.port_menu['values']:
            self.selected_port.set(self.port_menu['values'][0])

        # --- Buttons untereinander ---
        self.connect_button = ttk.Button(control_frame, text="Connect", command=self.connect)
        self.connect_button.pack(fill='x', pady=2)

        self.drift_button = ttk.Button(control_frame, text="Drift bestimmen", command=self.start_drift_thread)
        self.drift_button.pack(fill='x', pady=2)

        self.zero_button = ttk.Button(control_frame, text="Set Zero", command=self.set_zero)
        self.zero_button.pack(fill='x', pady=2)

        self.disconnect_button = ttk.Button(control_frame, text="Disconnect", command=self.disconnect)
        self.disconnect_button.pack(fill='x', pady=2)

    def connect(self):
        self.dsp.connect("COM4")  # Passe ggf. Port an
        self.running = True
        self.update_loop()

    def disconnect(self):
        self.running = False
        self.dsp.disconnect()

    def update_loop(self):
        if not self.running:
            return
        angle = self.dsp.get_angle()
        self.angle_var.set(f"{angle:+.3f}°")
        self.draw_arrow(angle)
        self.root.after(100, self.update_loop)  # 10 Hz

    def draw_arrow(self, angle_deg):
        length = 40
        center = (50, 50)
        angle_rad = math.radians(angle_deg)

        x_end = center[0] + length * math.sin(angle_rad)
        y_end = center[1] - length * math.cos(angle_rad)

        self.canvas.coords(self.arrow, center[0], center[1], x_end, y_end)

    def start_drift_thread(self):
        # Starte die Driftmessung in einem eigenen Thread
        t = threading.Thread(target=self.measure_drift, daemon=True)

        t.start()

    def measure_drift(self):
        self.dsp.determine_drift(5)  # 10 Sekunden Driftbestimmung
        time.sleep(6)
        drift = self.dsp.get_drift()
        self.drift_var.set(f"{drift:+.3f}°")

    def set_zero(self):
        self.dsp.reset_angle()

    def get_serial_ports(self):
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]

    def connect(self):
        port = self.selected_port.get()
        if not port:
            print("⚠️ Kein Port ausgewählt.")
            return
        self.dsp.connect(port)
        self.running = True
        self.update_loop()


if __name__ == "__main__":
    root = tk.Tk()
    app = DSPApp(root)
    root.mainloop()

# ARN/arn_gui_test.py
import math
import tkinter as tk
from tkinter import ttk

from GYEMS.gyems_rs485 import GyemsRmdRs485
from ARN.arn_controller import ArnController, ArnParams


class ArnGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ARN Test GUI (Kompass: DSP + GYEMS)")
        self.geometry("980x560")

        self.ctrl = ArnController(ArnParams())

        self._build_ui()
        self._schedule_update()

    def _build_ui(self):
        # ---- Top Controls ----
        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X, padx=10, pady=8)

        ports = GyemsRmdRs485.list_ports()
        if not ports:
            ports = ["COM3", "COM4", "COM5"]

        self.var_dsp_port = tk.StringVar(value="COM3")
        self.var_gy_port = tk.StringVar(value="COM4")

        ttk.Label(top, text="DSP Port:").pack(side=tk.LEFT)
        ttk.Combobox(top, textvariable=self.var_dsp_port, values=ports, width=8).pack(side=tk.LEFT, padx=6)

        ttk.Label(top, text="GYEMS Port:").pack(side=tk.LEFT, padx=(12, 0))
        ttk.Combobox(top, textvariable=self.var_gy_port, values=ports, width=8).pack(side=tk.LEFT, padx=6)

        ttk.Button(top, text="Connect", command=self.on_connect).pack(side=tk.LEFT, padx=(12, 6))
        ttk.Button(top, text="Disconnect", command=self.on_disconnect).pack(side=tk.LEFT, padx=6)

        ttk.Button(top, text="Start", command=self.on_start).pack(side=tk.LEFT, padx=(12, 6))
        ttk.Button(top, text="Stop", command=self.on_stop).pack(side=tk.LEFT, padx=6)

        ttk.Button(top, text="Zero (Nord)", command=self.on_zero).pack(side=tk.LEFT, padx=(12, 6))

        # ---- Params row ----
        params = ttk.Frame(self)
        params.pack(side=tk.TOP, fill=tk.X, padx=10)

        self.var_kp = tk.DoubleVar(value=1.0)
        self.var_deadband = tk.DoubleVar(value=0.05)
        self.var_maxdps = tk.DoubleVar(value=180.0)
        self.var_invert = tk.BooleanVar(value=True)  # True => gyro_sign = -1

        ttk.Label(params, text="Kp:").pack(side=tk.LEFT)
        ttk.Entry(params, textvariable=self.var_kp, width=8).pack(side=tk.LEFT, padx=6)

        ttk.Label(params, text="Deadband (°/s):").pack(side=tk.LEFT, padx=(12, 0))
        ttk.Entry(params, textvariable=self.var_deadband, width=8).pack(side=tk.LEFT, padx=6)

        ttk.Label(params, text="Max (°/s):").pack(side=tk.LEFT, padx=(12, 0))
        ttk.Entry(params, textvariable=self.var_maxdps, width=8).pack(side=tk.LEFT, padx=6)

        ttk.Checkbutton(params, text="Invert Gyro", variable=self.var_invert, command=self.apply_params).pack(
            side=tk.LEFT, padx=(12, 0)
        )
        ttk.Button(params, text="Apply", command=self.apply_params).pack(side=tk.LEFT, padx=8)

        # ---- Main split ----
        main = ttk.Frame(self)
        main.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left: Canvas compass
        left = ttk.Frame(main)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(left, width=600, height=420, bg="white")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Right: Telemetry
        right = ttk.Frame(main)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))

        self.lbl_conn = ttk.Label(right, text="Connected: False")
        self.lbl_conn.pack(anchor="w", pady=(0, 6))

        self.lbl_run = ttk.Label(right, text="Running: False")
        self.lbl_run.pack(anchor="w", pady=(0, 6))

        self.lbl_t = ttk.Label(right, text="t: 0.0 s")
        self.lbl_t.pack(anchor="w", pady=(0, 10))

        ttk.Separator(right).pack(fill=tk.X, pady=8)

        self.lbl_dsp_rate = ttk.Label(right, text="DSP rate: 0.000 °/s")
        self.lbl_dsp_rate.pack(anchor="w")

        self.lbl_dsp_dir = ttk.Label(right, text="DSP Richtung: 0.0 °")
        self.lbl_dsp_dir.pack(anchor="w", pady=(0, 10))

        self.lbl_cmd = ttk.Label(right, text="GYEMS cmd: 0.00 °/s")
        self.lbl_cmd.pack(anchor="w")

        self.lbl_gy_dir = ttk.Label(right, text="GYEMS Richtung: 0.0 °")
        self.lbl_gy_dir.pack(anchor="w")

        self.lbl_gy_raw = ttk.Label(right, text="GYEMS Angle raw: 0.0 °")
        self.lbl_gy_raw.pack(anchor="w", pady=(0, 10))

        ttk.Separator(right).pack(fill=tk.X, pady=8)

        self.lbl_temp = ttk.Label(right, text="Temp: -")
        self.lbl_temp.pack(anchor="w")
        self.lbl_iq = ttk.Label(right, text="Iq: -")
        self.lbl_iq.pack(anchor="w")
        self.lbl_spd = ttk.Label(right, text="Speed raw: -")
        self.lbl_spd.pack(anchor="w")
        self.lbl_enc = ttk.Label(right, text="Encoder: -")
        self.lbl_enc.pack(anchor="w", pady=(0, 10))

        self.lbl_status = ttk.Label(right, text="Status ok/to/row: 0 / 0 / 0")
        self.lbl_status.pack(anchor="w", pady=(0, 10))

        ttk.Separator(right).pack(fill=tk.X, pady=8)
        self.lbl_err = ttk.Label(right, text="Last error: -", foreground="red", wraplength=320)
        self.lbl_err.pack(anchor="w")

    def apply_params(self):
        gyro_sign = -1.0 if self.var_invert.get() else 1.0
        self.ctrl.set_params(
            kp=self.var_kp.get(),
            deadband_dps=self.var_deadband.get(),
            gyro_sign=gyro_sign,
            max_dps=self.var_maxdps.get(),
        )

    # ---- button handlers ----
    def on_connect(self):
        try:
            self.ctrl.connect(dsp_port=self.var_dsp_port.get(), gyems_port=self.var_gy_port.get())
            self.apply_params()
        except Exception as e:
            # (kleiner Hack: Fehlertext in Snapshot)
            try:
                self.ctrl._set_error(f"Connect failed: {type(e).__name__}: {e}")
            except Exception:
                pass

    def on_disconnect(self):
        try:
            self.ctrl.disconnect()
        except Exception:
            pass

    def on_start(self):
        try:
            self.apply_params()
            self.ctrl.start()
        except Exception as e:
            try:
                self.ctrl._set_error(f"Start failed: {type(e).__name__}: {e}")
            except Exception:
                pass

    def on_stop(self):
        try:
            self.ctrl.stop()
        except Exception:
            pass

    def on_zero(self):
        try:
            self.ctrl.zero_orientation()
        except Exception as e:
            try:
                self.ctrl._set_error(f"Zero failed: {type(e).__name__}: {e}")
            except Exception:
                pass

    # ---- drawing ----
    def _draw_compass(self, dsp_heading_deg: float, gy_heading_deg: float):
        self.canvas.delete("all")

        w = int(self.canvas.winfo_width())
        h = int(self.canvas.winfo_height())
        cx, cy = w // 2, h // 2

        R = min(w, h) // 2 - 50
        L = R - 25  # fixe Pfeillänge

        # Kreis
        self.canvas.create_oval(cx - R, cy - R, cx + R, cy + R, outline="#888", width=2)

        # Kardinalpunkte
        self.canvas.create_text(cx, cy - R - 12, text="N (0°)", fill="#333")
        self.canvas.create_text(cx + R + 18, cy, text="E (90°)", fill="#333")
        self.canvas.create_text(cx, cy + R + 12, text="S (180°)", fill="#333")
        self.canvas.create_text(cx - R - 18, cy, text="W (270°)", fill="#333")

        # kleine Ticks alle 30°
        for deg in range(0, 360, 30):
            theta = math.radians(90.0 - deg)
            x1 = cx + (R - 8) * math.cos(theta)
            y1 = cy - (R - 8) * math.sin(theta)
            x2 = cx + R * math.cos(theta)
            y2 = cy - R * math.sin(theta)
            self.canvas.create_line(x1, y1, x2, y2, fill="#bbb", width=2)

        def end_point(heading_deg: float):
            # heading: 0° = North (up), clockwise positive
            theta = math.radians(90.0 - heading_deg)
            x = cx + L * math.cos(theta)
            y = cy - L * math.sin(theta)
            return x, y

        # DSP Pfeil (schwarz)
        x1, y1 = end_point(dsp_heading_deg)
        self.canvas.create_line(cx, cy, x1, y1, arrow=tk.LAST, width=4, fill="black")
        self.canvas.create_text(cx, cy - R + 20, text=f"DSP: {dsp_heading_deg:5.1f}°", fill="black")

        # GYEMS Pfeil (blau)
        x2, y2 = end_point(gy_heading_deg)
        self.canvas.create_line(cx, cy, x2, y2, arrow=tk.LAST, width=4, fill="blue")
        self.canvas.create_text(cx, cy - R + 40, text=f"GYEMS: {gy_heading_deg:5.1f}°", fill="blue")

        # Center dot
        self.canvas.create_oval(cx - 4, cy - 4, cx + 4, cy + 4, fill="#444", outline="")

    def _schedule_update(self):
        snap = self.ctrl.get_snapshot()

        self.lbl_conn.config(text=f"Connected: {snap.connected}")
        self.lbl_run.config(text=f"Running: {snap.running}")
        self.lbl_t.config(text=f"t: {snap.t_s:.1f} s")

        self.lbl_dsp_rate.config(text=f"DSP rate: {snap.dsp_rate_dps:+.6f} °/s")
        self.lbl_dsp_dir.config(text=f"DSP Richtung: {snap.dsp_heading_deg:6.1f} °")

        self.lbl_cmd.config(text=f"GYEMS cmd: {snap.cmd_dps:+.2f} °/s")
        self.lbl_gy_dir.config(text=f"GYEMS Richtung: {snap.gyems_heading_deg:6.1f} °")
        self.lbl_gy_raw.config(text=f"GYEMS Angle raw: {snap.gyems_angle_deg:6.2f} °")

        st = snap.gyems_status
        if st is None:
            self.lbl_temp.config(text="Temp: -")
            self.lbl_iq.config(text="Iq: -")
            self.lbl_spd.config(text="Speed raw: -")
            self.lbl_enc.config(text="Encoder: -")
        else:
            self.lbl_temp.config(text=f"Temp: {st.temperature_C} °C")
            self.lbl_iq.config(text=f"Iq: {st.torque_current}")
            self.lbl_spd.config(text=f"Speed raw: {st.speed_raw}")
            self.lbl_enc.config(text=f"Encoder: {st.encoder_pos}")

        self.lbl_status.config(text=f"Status ok/to/row: {snap.status_ok} / {snap.status_timeouts} / {snap.status_fail_row}")
        self.lbl_err.config(text=f"Last error: {snap.last_error or '-'}")

        self._draw_compass(snap.dsp_heading_deg, snap.gyems_heading_deg)

        self.after(100, self._schedule_update)


if __name__ == "__main__":
    app = ArnGui()
    app.mainloop()
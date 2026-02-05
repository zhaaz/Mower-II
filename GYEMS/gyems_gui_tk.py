# gyems_gui_tk.py
import tkinter as tk
from tkinter import ttk, messagebox

from gyems_rs485 import GyemsRmdRs485, GyemsStatus


BAUD_FIXED = 115200


class GyemsGui(ttk.Frame):
    def __init__(self, master: tk.Tk):
        super().__init__(master)
        self.master = master
        self.master.title("GYEMS RS-485 Test GUI (minimal)")
        self.grid(padx=12, pady=12)

        self.motor: GyemsRmdRs485 | None = None
        self.connected = False

        # --- top: connection ---
        conn = ttk.LabelFrame(self, text="Connection")
        conn.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        conn.columnconfigure(1, weight=1)

        ttk.Label(conn, text="COM Port:").grid(row=0, column=0, sticky="w")
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(conn, textvariable=self.port_var, width=18, state="readonly")
        self.port_combo.grid(row=0, column=1, sticky="ew", padx=6)

        self.refresh_btn = ttk.Button(conn, text="Refresh", command=self.refresh_ports)
        self.refresh_btn.grid(row=0, column=2, padx=6)

        ttk.Label(conn, text=f"Baudrate: {BAUD_FIXED}").grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.connect_btn = ttk.Button(conn, text="Connect", command=self.connect)
        self.connect_btn.grid(row=1, column=1, sticky="w", pady=(6, 0))

        self.disconnect_btn = ttk.Button(conn, text="Disconnect", command=self.disconnect, state="disabled")
        self.disconnect_btn.grid(row=1, column=2, sticky="w", pady=(6, 0))

        # --- status ---
        stat = ttk.LabelFrame(self, text="Live Status (0x9C / 0x94)")
        stat.grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        stat.columnconfigure(1, weight=1)

        self.angle_var = tk.StringVar(value="---")
        self.temp_var = tk.StringVar(value="---")
        self.iq_var = tk.StringVar(value="---")
        self.spd_var = tk.StringVar(value="---")
        self.enc_var = tk.StringVar(value="---")
        self.err_var = tk.StringVar(value="")

        row = 0
        ttk.Label(stat, text="Angle (deg):").grid(row=row, column=0, sticky="w")
        ttk.Label(stat, textvariable=self.angle_var).grid(row=row, column=1, sticky="w")
        row += 1

        ttk.Label(stat, text="Temp (°C):").grid(row=row, column=0, sticky="w")
        ttk.Label(stat, textvariable=self.temp_var).grid(row=row, column=1, sticky="w")
        row += 1

        ttk.Label(stat, text="Torque current (Iq):").grid(row=row, column=0, sticky="w")
        ttk.Label(stat, textvariable=self.iq_var).grid(row=row, column=1, sticky="w")
        row += 1

        ttk.Label(stat, text="Speed raw:").grid(row=row, column=0, sticky="w")
        ttk.Label(stat, textvariable=self.spd_var).grid(row=row, column=1, sticky="w")
        row += 1

        ttk.Label(stat, text="Encoder:").grid(row=row, column=0, sticky="w")
        ttk.Label(stat, textvariable=self.enc_var).grid(row=row, column=1, sticky="w")
        row += 1

        ttk.Label(stat, textvariable=self.err_var, foreground="red").grid(row=row, column=0, columnspan=2, sticky="w", pady=(6, 0))

        # --- controls ---
        ctrl = ttk.LabelFrame(self, text="Commands")
        ctrl.grid(row=2, column=0, sticky="ew", padx=4, pady=4)
        ctrl.columnconfigure(1, weight=1)

        # Model info
        ttk.Button(ctrl, text="Read Model Info (0x12)", command=self.read_model_info).grid(row=0, column=0, sticky="w", padx=4, pady=4)

        # Errors
        ttk.Button(ctrl, text="Read Errors (0x9A)", command=self.read_errors).grid(row=0, column=1, sticky="w", padx=4, pady=4)
        ttk.Button(ctrl, text="Clear Errors (0x9B)", command=self.clear_errors).grid(row=0, column=2, sticky="w", padx=4, pady=4)

        # Stop
        ttk.Button(ctrl, text="STOP / Shutdown (0x80)", command=self.stop).grid(row=1, column=0, sticky="w", padx=4, pady=4)

        # Set speed
        ttk.Label(ctrl, text="Speed (deg/s):").grid(row=2, column=0, sticky="w", padx=4)
        self.speed_entry = ttk.Entry(ctrl, width=10)
        self.speed_entry.insert(0, "0")
        self.speed_entry.grid(row=2, column=1, sticky="w", padx=4)
        ttk.Button(ctrl, text="Set Speed (0xA2)", command=self.set_speed).grid(row=2, column=2, sticky="w", padx=4)

        # Move abs
        ttk.Label(ctrl, text="Abs angle (deg):").grid(row=3, column=0, sticky="w", padx=4)
        self.abs_entry = ttk.Entry(ctrl, width=10)
        self.abs_entry.insert(0, "0")
        self.abs_entry.grid(row=3, column=1, sticky="w", padx=4)
        ttk.Button(ctrl, text="Move Abs (0xA3)", command=self.move_abs).grid(row=3, column=2, sticky="w", padx=4)

        # --- init ---
        self.refresh_ports()
        self.master.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(200, self.update_live)

    def refresh_ports(self):
        ports = GyemsRmdRs485.list_ports()
        self.port_combo["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def connect(self):
        port = self.port_var.get().strip()
        if not port:
            messagebox.showerror("Error", "Please select a COM port.")
            return
        try:
            self.motor = GyemsRmdRs485(port=port, motor_id=0x01, baudrate=BAUD_FIXED, timeout=0.2)
            self.motor.connect()
            self.connected = True
            self.connect_btn.config(state="disabled")
            self.disconnect_btn.config(state="normal")
            self.err_var.set("")
        except Exception as e:
            self.connected = False
            self.motor = None
            messagebox.showerror("Connect failed", str(e))

    def disconnect(self):
        try:
            if self.motor:
                self.motor.close()
        finally:
            self.motor = None
            self.connected = False
            self.connect_btn.config(state="normal")
            self.disconnect_btn.config(state="disabled")

    def read_model_info(self):
        if not self.motor:
            return
        try:
            info = self.motor.read_model_info()
            msg = f"Driver: {info.driver}\nMotor: {info.motor}\nHW: {info.hw_version}\nFW: {info.fw_version}"
            messagebox.showinfo("Model Info", msg)
        except Exception as e:
            messagebox.showerror("Model Info failed", str(e))

    def read_errors(self):
        if not self.motor:
            return
        try:
            err = self.motor.read_error_flags()
            messagebox.showinfo("Errors (raw)", f"{err}")
        except Exception as e:
            messagebox.showerror("Read Errors failed", str(e))

    def clear_errors(self):
        if not self.motor:
            return
        try:
            self.motor.clear_error_flags()
            self.err_var.set("Errors cleared.")
        except Exception as e:
            messagebox.showerror("Clear Errors failed", str(e))

    def stop(self):
        if not self.motor:
            return
        try:
            self.motor.shutdown()
        except Exception as e:
            messagebox.showerror("Stop failed", str(e))

    def set_speed(self):
        if not self.motor:
            return
        try:
            val = float(self.speed_entry.get().replace(",", "."))
            self.motor.set_speed_deg_s(val)
        except ValueError:
            messagebox.showerror("Input error", "Speed must be a number.")
        except Exception as e:
            messagebox.showerror("Set Speed failed", str(e))

    def move_abs(self):
        if not self.motor:
            return
        try:
            val = float(self.abs_entry.get().replace(",", "."))
            self.motor.move_to_abs_angle_deg(val)
        except ValueError:
            messagebox.showerror("Input error", "Angle must be a number.")
        except Exception as e:
            messagebox.showerror("Move Abs failed", str(e))

    def update_live(self):
        if self.motor and self.connected:
            try:
                ang = self.motor.read_singleturn_angle_deg()
                st: GyemsStatus = self.motor.read_status()
                self.angle_var.set(f"{ang:.2f}")
                self.temp_var.set(str(st.temperature_C))
                self.iq_var.set(str(st.torque_current))
                self.spd_var.set(str(st.speed_raw))
                self.enc_var.set(str(st.encoder_pos))
                self.err_var.set("")
            except Exception as e:
                # keep GUI alive; show last error
                self.err_var.set(f"COMM: {e}")
        self.after(200, self.update_live)

    def on_close(self):
        try:
            if self.motor:
                try:
                    # best-effort stop
                    self.motor.set_speed_deg_s(0.0)
                except Exception:
                    pass
                self.motor.close()
        finally:
            self.master.destroy()


def main():
    root = tk.Tk()
    app = GyemsGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()

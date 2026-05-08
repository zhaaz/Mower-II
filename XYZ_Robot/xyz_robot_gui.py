# xyz_robot_gui.py
import serial.tools.list_ports
import customtkinter as ctk
from tkinter import messagebox

from xyz_robot import XYZRobot



class XYZRobotGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("XYZ-Roboter")
        self.geometry("1000x700")
        self.minsize(1000, 700)

        self.robot: XYZRobot | None = None

        self.port_var = ctk.StringVar(value="COM3")
        self.baudrate_var = ctk.StringVar(value="115200")

        self.connection_indicator_var = ctk.StringVar(value="● Not Connected")
        self.homed_var = ctk.StringVar(value="Nein")

        self.pos_x_var = ctk.StringVar(value="-")
        self.pos_y_var = ctk.StringVar(value="-")
        self.pos_z_var = ctk.StringVar(value="-")

        self.step_var = ctk.StringVar(value="10.0")
        self.feedrate_xy_var = ctk.StringVar(value="6000")
        self.feedrate_z_var = ctk.StringVar(value="600")

        self.mark_x_var = ctk.StringVar(value="100.0")
        self.mark_y_var = ctk.StringVar(value="100.0")
        self.label_var = ctk.StringVar(value="P101")
        self.marker_size_var = ctk.StringVar(value="10.0")

        self.marker_shape_var = ctk.StringVar(value="plus_circle")
        self.hardware_buttons: list[ctk.CTkButton] = []

        self._build_gui()
        self._bind_hotkeys()

    # --------------------------------------------------
    # GUI Aufbau
    # --------------------------------------------------

    def _bind_hotkeys(self):
        self.bind("<Left>", lambda event: self.hotkey_jog(dy=self._get_step()))
        self.bind("<Right>", lambda event: self.hotkey_jog(dy=-self._get_step()))
        self.bind("<Down>", lambda event: self.hotkey_jog(dx=-self._get_step()))
        self.bind("<Up>", lambda event: self.hotkey_jog(dx=self._get_step()))

        self.bind("<Prior>", lambda event: self.hotkey_jog(dz=self._get_step()))
        self.bind("<Next>", lambda event: self.hotkey_jog(dz=-self._get_step()))

    def _build_gui(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")

        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="nsew")

        self.main_frame.grid_columnconfigure(0, weight=1)

        self._build_connection_frame()
        self._build_status_frame()
        self._build_homing_frame()
        self._build_manual_frame()
        self._build_marking_frame()
        self._build_log_frame()

    def _build_connection_frame(self):
        frame = ctk.CTkFrame(self.main_frame)
        frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        frame.grid_columnconfigure(1, weight=1)

        ports = self._get_available_ports()
        if ports:
            self.port_var.set(ports[0])
        else:
            ports = [""]

        ctk.CTkLabel(frame, text="Port").grid(row=0, column=0, padx=8, pady=8)

        self.port_menu = ctk.CTkOptionMenu(
            frame,
            variable=self.port_var,
            values=ports
        )
        self.port_menu.grid(row=0, column=1, padx=8, pady=8, sticky="ew")

        ctk.CTkButton(
            frame,
            text="Refresh",
            command=self.refresh_ports
        ).grid(row=0, column=2, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Baudrate").grid(row=1, column=0, padx=8, pady=8)
        ctk.CTkEntry(
            frame,
            textvariable=self.baudrate_var
        ).grid(row=1, column=1, padx=8, pady=8, sticky="ew")

        ctk.CTkButton(
            frame,
            text="Connect",
            command=self.connect_robot
        ).grid(row=2, column=0, padx=8, pady=8)

        ctk.CTkButton(
            frame,
            text="Disconnect",
            command=self.disconnect_robot
        ).grid(row=2, column=1, padx=8, pady=8)

    def _build_status_frame(self):
        frame = ctk.CTkFrame(self.main_frame)
        frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        frame.grid_columnconfigure((1, 3, 5), weight=1)

        self.connection_label = ctk.CTkLabel(
            frame,
            textvariable=self.connection_indicator_var,
            text_color="red"
        )
        self.connection_label.grid(row=0, column=0, padx=8, pady=8, sticky="w")

        ctk.CTkLabel(frame, text="Homed:").grid(row=0, column=1, padx=8, pady=8)
        ctk.CTkLabel(frame, textvariable=self.homed_var).grid(row=0, column=2, padx=8, pady=8)

        ctk.CTkButton(frame, text="Position lesen", command=self.read_position).grid(row=0, column=3, padx=8, pady=8)

        ctk.CTkLabel(frame, text="X").grid(row=1, column=0, padx=8, pady=8)
        ctk.CTkLabel(frame, textvariable=self.pos_x_var).grid(row=1, column=1, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Y").grid(row=1, column=2, padx=8, pady=8)
        ctk.CTkLabel(frame, textvariable=self.pos_y_var).grid(row=1, column=3, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Z").grid(row=1, column=4, padx=8, pady=8)
        ctk.CTkLabel(frame, textvariable=self.pos_z_var).grid(row=1, column=5, padx=8, pady=8)

    def _build_homing_frame(self):
        frame = ctk.CTkFrame(self.main_frame)
        frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

        ctk.CTkButton(
            frame,
            text="Homing alle Achsen",
            command=self.home_all
        ).grid(row=0, column=0, padx=8, pady=8)

    def _build_manual_frame(self):
        frame = ctk.CTkFrame(self.main_frame)
        frame.grid(row=3, column=0, padx=10, pady=5, sticky="ew")

        ctk.CTkLabel(frame, text="Schrittweite [mm]").grid(row=0, column=0, padx=8, pady=8)
        ctk.CTkEntry(frame, textvariable=self.step_var, width=100).grid(row=0, column=1, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Feedrate XY").grid(row=1, column=0, padx=8, pady=8)
        ctk.CTkEntry(frame, textvariable=self.feedrate_xy_var, width=100).grid(row=1, column=1, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Feedrate Z").grid(row=2, column=0, padx=8, pady=8)
        ctk.CTkEntry(frame, textvariable=self.feedrate_z_var, width=100).grid(row=2, column=1, padx=8, pady=8)

        ctk.CTkButton(frame, text="X-", command=lambda: self.jog(dx=-self._get_step())).grid(row=0, column=3, padx=8,
                                                                                             pady=8)
        ctk.CTkButton(frame, text="X+", command=lambda: self.jog(dx=self._get_step())).grid(row=0, column=4, padx=8,
                                                                                            pady=8)

        ctk.CTkButton(frame, text="Y-", command=lambda: self.jog(dy=-self._get_step())).grid(row=1, column=3, padx=8,
                                                                                             pady=8)
        ctk.CTkButton(frame, text="Y+", command=lambda: self.jog(dy=self._get_step())).grid(row=1, column=4, padx=8,
                                                                                            pady=8)

        ctk.CTkButton(frame, text="Z-", command=lambda: self.jog(dz=-self._get_step())).grid(row=2, column=3, padx=8,
                                                                                             pady=8)
        ctk.CTkButton(frame, text="Z+", command=lambda: self.jog(dz=self._get_step())).grid(row=2, column=4, padx=8,
                                                                                            pady=8)

    def _build_marking_frame(self):
        frame = ctk.CTkFrame(self.main_frame)
        frame.grid(row=4, column=0, padx=10, pady=5, sticky="ew")

        ctk.CTkLabel(frame, text="X").grid(row=0, column=0, padx=8, pady=8)
        ctk.CTkEntry(frame, textvariable=self.mark_x_var, width=100).grid(row=0, column=1, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Y").grid(row=0, column=2, padx=8, pady=8)
        ctk.CTkEntry(frame, textvariable=self.mark_y_var, width=100).grid(row=0, column=3, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Punktnr.").grid(row=1, column=0, padx=8, pady=8)
        ctk.CTkEntry(frame, textvariable=self.label_var, width=100).grid(row=1, column=1, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Größe").grid(row=1, column=2, padx=8, pady=8)
        ctk.CTkEntry(frame, textvariable=self.marker_size_var, width=100).grid(row=1, column=3, padx=8, pady=8)

        ctk.CTkButton(
            frame,
            text="Punkt markieren",
            command=self.mark_point
        ).grid(row=3, column=0, columnspan=4, padx=8, pady=12, sticky="ew")

        ctk.CTkLabel(frame, text="Markierung").grid(row=2, column=0, padx=8, pady=8)

        ctk.CTkOptionMenu(
            frame,
            variable=self.marker_shape_var,
            values=[
                "plus",
                "cross",
                "circle_point",
                "plus_circle"
            ]
        ).grid(row=2, column=1, padx=8, pady=8, sticky="ew")

    def _build_log_frame(self):
        self.log_frame.grid_rowconfigure(1, weight=1)
        self.log_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.log_frame,
            text="Log"
        ).grid(row=0, column=0, padx=8, pady=(8, 0), sticky="w")

        self.log_text = ctk.CTkTextbox(self.log_frame, width=260)
        self.log_text.grid(row=1, column=0, padx=8, pady=8, sticky="nsew")

    # --------------------------------------------------
    # Hilfsfunktionen
    # --------------------------------------------------

    def hotkey_jog(self, dx=None, dy=None, dz=None):
        if self.robot is None or not self.robot.is_connected:
            return

        self.jog(dx=dx, dy=dy, dz=dz)

    def log(self, text: str):
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")

    def _require_robot(self) -> XYZRobot:
        if self.robot is None or not self.robot.is_connected:
            raise RuntimeError("XYZ-Roboter ist nicht verbunden.")
        return self.robot

    def _get_step(self) -> float:
        return float(self.step_var.get().replace(",", "."))

    def _get_feedrate_xy(self) -> float:
        return float(self.feedrate_xy_var.get().replace(",", "."))

    def _get_feedrate_z(self) -> float:
        return float(self.feedrate_z_var.get().replace(",", "."))

    def _set_connected_ui(self):
        self.connection_indicator_var.set("● Connected")
        self.connection_label.configure(text_color="green")

    def _set_disconnected_ui(self):
        self.connection_indicator_var.set("● Not Connected")
        self.connection_label.configure(text_color="red")
        self.homed_var.set("Nein")
        self.pos_x_var.set("-")
        self.pos_y_var.set("-")
        self.pos_z_var.set("-")

    def _get_available_ports(self) -> list[str]:
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]

    def refresh_ports(self):
        ports = self._get_available_ports()

        if not ports:
            ports = [""]

        self.port_menu.configure(values=ports)

        if self.port_var.get() not in ports:
            self.port_var.set(ports[0])

        self.log("COM-Ports aktualisiert")

    # --------------------------------------------------
    # Aktionen
    # --------------------------------------------------

    def connect_robot(self):
        try:
            port = self.port_var.get().strip()
            baudrate = int(self.baudrate_var.get())

            self.robot = XYZRobot(port=port, baudrate=baudrate)
            self.robot.connect()

            self._set_connected_ui()
            self.log(f"Verbunden mit {port} @ {baudrate}")

            # Test, ob die Steuerung wirklich antwortet
            self.read_position()

        except Exception as e:
            if self.robot is not None:
                self.robot.disconnect()

            messagebox.showerror("Verbindungsfehler", str(e))
            self.log(f"Fehler beim Verbinden oder Positionslesen: {e}")
            self._set_disconnected_ui()

    def disconnect_robot(self):
        try:
            if self.robot is not None:
                self.robot.disconnect()

            self._set_disconnected_ui()
            self.log("Verbindung getrennt")

        except Exception as e:
            messagebox.showerror("Fehler", str(e))
            self.log(f"Fehler beim Trennen: {e}")

    def home_all(self):
        try:
            robot = self._require_robot()

            self.log("Homing gestartet...")
            robot.homing()

            self.homed_var.set("Ja")
            self.log("Homing abgeschlossen")

            self.read_position()

        except Exception as e:
            messagebox.showerror("Homing-Fehler", str(e))
            self.log(f"Homing-Fehler: {e}")

    def read_position(self):
        try:
            robot = self._require_robot()
            pos = robot.get_current_position()

            self.pos_x_var.set(f"{pos['X']:.3f}")
            self.pos_y_var.set(f"{pos['Y']:.3f}")
            self.pos_z_var.set(f"{pos['Z']:.3f}")

            self.log(
                f"Position: X={pos['X']:.3f}, "
                f"Y={pos['Y']:.3f}, "
                f"Z={pos['Z']:.3f}"
            )

        except Exception as e:
            messagebox.showerror("Positionsfehler", str(e))
            self.log(f"Positionsfehler: {e}")

    def jog(self, dx=None, dy=None, dz=None):
        try:
            robot = self._require_robot()

            if dz is not None:
                feedrate = self._get_feedrate_z()
            else:
                feedrate = self._get_feedrate_xy()

            robot.move_relative(
                dx=dx,
                dy=dy,
                dz=dz,
                feedrate=feedrate
            )

            self.read_position()

        except Exception as e:
            messagebox.showerror("Fahrfehler", str(e))
            self.log(f"Fahrfehler: {e}")

    def mark_point(self):
        try:
            robot = self._require_robot()

            x = float(self.mark_x_var.get().replace(",", "."))
            y = float(self.mark_y_var.get().replace(",", "."))
            label = self.label_var.get().strip()
            size = float(self.marker_size_var.get().replace(",", "."))
            marker_shape = self.marker_shape_var.get()

            self.log(f"Markiere Punkt {label}: X={x:.3f}, Y={y:.3f}")

            robot.mark_point_with_label(
                x=x,
                y=y,
                label=label,
                marker_size=size,
                marker_shape=marker_shape
            )

            self.log(f"Punkt {label} markiert")
            self.read_position()

        except Exception as e:
            messagebox.showerror("Markierfehler", str(e))
            self.log(f"Markierfehler: {e}")


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = XYZRobotGUI()
    app.mainloop()
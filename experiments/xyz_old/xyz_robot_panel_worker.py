# xyz_robot_panel_worker.py

import serial.tools.list_ports
import customtkinter as ctk
from tkinter import messagebox

from xyz_robot_worker import XYZRobotWorker
from xyz_robot_state import XYZRobotState
from component_event import ComponentEvent, EventLevel


class XYZRobotPanelWorker(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)

        self.port_var = ctk.StringVar(value="")
        self.baudrate_var = ctk.StringVar(value="115200")

        self.connection_indicator_var = ctk.StringVar(value="● Not Connected")
        self.homed_var = ctk.StringVar(value="Nein")
        self.busy_var = ctk.StringVar(value="Nein")

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

        self.worker = XYZRobotWorker(
            on_event=self._on_worker_event,
            on_state_changed=self._on_worker_state_changed,
        )
        self.worker.start()

        self._build_gui()
        self._set_disconnected_ui()

    # --------------------------------------------------
    # GUI Aufbau
    # --------------------------------------------------

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

        self.connection_label = ctk.CTkLabel(
            frame,
            textvariable=self.connection_indicator_var,
            text_color="red"
        )
        self.connection_label.grid(row=0, column=0, padx=8, pady=8, sticky="w")

        ctk.CTkLabel(frame, text="Homed:").grid(row=0, column=1, padx=8, pady=8)
        ctk.CTkLabel(frame, textvariable=self.homed_var).grid(row=0, column=2, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Busy:").grid(row=0, column=3, padx=8, pady=8)
        ctk.CTkLabel(frame, textvariable=self.busy_var).grid(row=0, column=4, padx=8, pady=8)

        button = ctk.CTkButton(
            frame,
            text="Position lesen",
            command=self.read_position
        )
        button.grid(row=0, column=5, padx=8, pady=8)
        self._add_hardware_button(button)

        ctk.CTkLabel(frame, text="X").grid(row=1, column=0, padx=8, pady=8)
        ctk.CTkLabel(frame, textvariable=self.pos_x_var).grid(row=1, column=1, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Y").grid(row=1, column=2, padx=8, pady=8)
        ctk.CTkLabel(frame, textvariable=self.pos_y_var).grid(row=1, column=3, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Z").grid(row=1, column=4, padx=8, pady=8)
        ctk.CTkLabel(frame, textvariable=self.pos_z_var).grid(row=1, column=5, padx=8, pady=8)

    def _build_homing_frame(self):
        frame = ctk.CTkFrame(self.main_frame)
        frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

        button = ctk.CTkButton(
            frame,
            text="Homing alle Achsen",
            command=self.home_all
        )
        button.grid(row=0, column=0, padx=8, pady=8)
        self._add_hardware_button(button)

    def _build_manual_frame(self):
        frame = ctk.CTkFrame(self.main_frame)
        frame.grid(row=3, column=0, padx=10, pady=5, sticky="ew")

        ctk.CTkLabel(frame, text="Schrittweite [mm]").grid(row=0, column=0, padx=8, pady=8)
        ctk.CTkEntry(frame, textvariable=self.step_var, width=100).grid(row=0, column=1, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Feedrate XY").grid(row=1, column=0, padx=8, pady=8)
        ctk.CTkEntry(frame, textvariable=self.feedrate_xy_var, width=100).grid(row=1, column=1, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Feedrate Z").grid(row=2, column=0, padx=8, pady=8)
        ctk.CTkEntry(frame, textvariable=self.feedrate_z_var, width=100).grid(row=2, column=1, padx=8, pady=8)

        self._make_hardware_button(frame, "X-", lambda: self.jog(dx=-self._get_step()), 0, 3)
        self._make_hardware_button(frame, "X+", lambda: self.jog(dx=self._get_step()), 0, 4)

        self._make_hardware_button(frame, "Y-", lambda: self.jog(dy=-self._get_step()), 1, 3)
        self._make_hardware_button(frame, "Y+", lambda: self.jog(dy=self._get_step()), 1, 4)

        self._make_hardware_button(frame, "Z-", lambda: self.jog(dz=-self._get_step()), 2, 3)
        self._make_hardware_button(frame, "Z+", lambda: self.jog(dz=self._get_step()), 2, 4)

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

        ctk.CTkLabel(frame, text="Markierung").grid(row=2, column=0, padx=8, pady=8)

        ctk.CTkOptionMenu(
            frame,
            variable=self.marker_shape_var,
            values=["none", "plus", "cross", "circle_point", "plus_circle"]
        ).grid(row=2, column=1, padx=8, pady=8, sticky="ew")

        button = ctk.CTkButton(
            frame,
            text="Punkt markieren",
            command=self.mark_point
        )
        button.grid(row=3, column=0, columnspan=4, padx=8, pady=12, sticky="ew")
        self._add_hardware_button(button)

    def _build_log_frame(self):
        self.log_frame.grid_rowconfigure(1, weight=1)
        self.log_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.log_frame, text="Log").grid(
            row=0, column=0, padx=8, pady=(8, 0), sticky="w"
        )

        self.log_text = ctk.CTkTextbox(self.log_frame, width=280)
        self.log_text.grid(row=1, column=0, padx=8, pady=8, sticky="nsew")

    # --------------------------------------------------
    # Worker Callbacks thread-sicher
    # --------------------------------------------------

    def _on_worker_event(self, event: ComponentEvent):
        self.after(0, lambda: self._handle_worker_event(event))

    def _on_worker_state_changed(self, state: XYZRobotState):
        self.after(0, lambda: self._apply_state(state))

    def _handle_worker_event(self, event: ComponentEvent):
        self.log(event.format_for_log())

        if event.level == EventLevel.ERROR:
            messagebox.showerror("XYZ-Roboter Fehler", event.message)

    def _apply_state(self, state: XYZRobotState):
        if state.connected:
            self.connection_indicator_var.set("● Connected")
            self.connection_label.configure(text_color="green")
        else:
            self.connection_indicator_var.set("● Not Connected")
            self.connection_label.configure(text_color="red")

        self.homed_var.set("Ja" if state.homed else "Nein")
        self.busy_var.set("Ja" if state.busy else "Nein")

        self.pos_x_var.set("-" if state.x is None else f"{state.x:.3f}")
        self.pos_y_var.set("-" if state.y is None else f"{state.y:.3f}")
        self.pos_z_var.set("-" if state.z is None else f"{state.z:.3f}")

        if state.connected and not state.busy:
            self._set_hardware_buttons_state("normal")
        else:
            self._set_hardware_buttons_state("disabled")

    # --------------------------------------------------
    # Hilfsfunktionen
    # --------------------------------------------------

    def _make_hardware_button(self, master, text: str, command, row: int, column: int):
        button = ctk.CTkButton(master, text=text, command=command)
        button.grid(row=row, column=column, padx=8, pady=8)
        self._add_hardware_button(button)
        return button

    def _add_hardware_button(self, button: ctk.CTkButton):
        self.hardware_buttons.append(button)
        button.configure(state="disabled")

    def _set_hardware_buttons_state(self, state: str):
        for button in self.hardware_buttons:
            button.configure(state=state)

    def _set_disconnected_ui(self):
        self.connection_indicator_var.set("● Not Connected")
        self.connection_label.configure(text_color="red")
        self.homed_var.set("Nein")
        self.busy_var.set("Nein")
        self.pos_x_var.set("-")
        self.pos_y_var.set("-")
        self.pos_z_var.set("-")
        self._set_hardware_buttons_state("disabled")

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

    def _get_step(self) -> float:
        return float(self.step_var.get().replace(",", "."))

    def _get_feedrate_xy(self) -> float:
        return float(self.feedrate_xy_var.get().replace(",", "."))

    def _get_feedrate_z(self) -> float:
        return float(self.feedrate_z_var.get().replace(",", "."))

    def log(self, text: str):
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")

    def shutdown(self):
        self.worker.stop()

    # --------------------------------------------------
    # GUI Aktionen -> Worker Commands
    # --------------------------------------------------

    def connect_robot(self):
        port = self.port_var.get().strip()
        baudrate = int(self.baudrate_var.get())

        self.worker.send_command(
            "connect",
            port=port,
            baudrate=baudrate
        )

    def disconnect_robot(self):
        self.worker.send_command("disconnect")

    def read_position(self):
        self.worker.send_command("read_position")

    def home_all(self):
        self.worker.send_command("home_all")

    def jog(self, dx=None, dy=None, dz=None):
        if dz is not None:
            feedrate = self._get_feedrate_z()
        else:
            feedrate = self._get_feedrate_xy()

        self.worker.send_command(
            "jog",
            dx=dx,
            dy=dy,
            dz=dz,
            feedrate=feedrate
        )

    def mark_point(self):
        x = float(self.mark_x_var.get().replace(",", "."))
        y = float(self.mark_y_var.get().replace(",", "."))
        label = self.label_var.get().strip()
        size = float(self.marker_size_var.get().replace(",", "."))
        marker_shape = self.marker_shape_var.get()

        self.worker.send_command(
            "mark_point",
            x=x,
            y=y,
            label=label,
            marker_size=size,
            marker_shape=marker_shape,
        )

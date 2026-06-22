# lasertracker_panel.py

import customtkinter as ctk
from tkinter import messagebox

from Lasertracker.lasertracker_receiver import LasertrackerReceiver
from Lasertracker.lasertracker_state import LasertrackerState


class LasertrackerPanel(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)

        self.port_var = ctk.StringVar(value="10000")
        self.stale_threshold_var = ctk.StringVar(value="3.0")
        self.stable_threshold_var = ctk.StringVar(value="0.1")
        self.stable_count_var = ctk.StringVar(value="3")

        self.receiver_status_var = ctk.StringVar(value="● Stopped")
        self.receiving_var = ctk.StringVar(value="Nein")
        self.stale_var = ctk.StringVar(value="Ja")
        self.stable_var = ctk.StringVar(value="Nein")
        self.age_var = ctk.StringVar(value="-")

        self.x_var = ctk.StringVar(value="-")
        self.y_var = ctk.StringVar(value="-")
        self.z_var = ctk.StringVar(value="-")
        self.unit_var = ctk.StringVar(value="-")
        self.count_var = ctk.StringVar(value="0")

        self.receiver: LasertrackerReceiver | None = None

        self._build_gui()

    # --------------------------------------------------
    # GUI
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
        self._build_measurement_frame()
        self._build_log_frame()

    def _build_connection_frame(self):
        frame = ctk.CTkFrame(self.main_frame)
        frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(frame, text="UDP Port").grid(row=0, column=0, padx=8, pady=8)
        ctk.CTkEntry(frame, textvariable=self.port_var, width=100).grid(row=0, column=1, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Stale [s]").grid(row=0, column=2, padx=8, pady=8)
        ctk.CTkEntry(frame, textvariable=self.stale_threshold_var, width=100).grid(row=0, column=3, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Stable [mm]").grid(row=1, column=0, padx=8, pady=8)
        ctk.CTkEntry(frame, textvariable=self.stable_threshold_var, width=100).grid(row=1, column=1, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Stable Count").grid(row=1, column=2, padx=8, pady=8)
        ctk.CTkEntry(frame, textvariable=self.stable_count_var, width=100).grid(row=1, column=3, padx=8, pady=8)

        ctk.CTkButton(frame, text="Start Receiver", command=self.start_receiver).grid(
            row=2, column=0, padx=8, pady=8
        )

        ctk.CTkButton(frame, text="Stop Receiver", command=self.stop_receiver).grid(
            row=2, column=1, padx=8, pady=8
        )

    def _build_status_frame(self):
        frame = ctk.CTkFrame(self.main_frame)
        frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        self.receiver_status_label = ctk.CTkLabel(
            frame,
            textvariable=self.receiver_status_var,
            text_color="red"
        )
        self.receiver_status_label.grid(row=0, column=0, padx=8, pady=8, sticky="w")

        ctk.CTkLabel(frame, text="Receiving:").grid(row=0, column=1, padx=8, pady=8)
        ctk.CTkLabel(frame, textvariable=self.receiving_var).grid(row=0, column=2, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Stale:").grid(row=0, column=3, padx=8, pady=8)
        ctk.CTkLabel(frame, textvariable=self.stale_var).grid(row=0, column=4, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Stable:").grid(row=0, column=5, padx=8, pady=8)
        ctk.CTkLabel(frame, textvariable=self.stable_var).grid(row=0, column=6, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Alter [s]:").grid(row=1, column=0, padx=8, pady=8)
        ctk.CTkLabel(frame, textvariable=self.age_var).grid(row=1, column=1, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Anzahl:").grid(row=1, column=2, padx=8, pady=8)
        ctk.CTkLabel(frame, textvariable=self.count_var).grid(row=1, column=3, padx=8, pady=8)

    def _build_measurement_frame(self):
        frame = ctk.CTkFrame(self.main_frame)
        frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

        ctk.CTkLabel(frame, text="X").grid(row=0, column=0, padx=8, pady=8)
        ctk.CTkLabel(frame, textvariable=self.x_var, font=("Arial", 20)).grid(row=0, column=1, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Y").grid(row=1, column=0, padx=8, pady=8)
        ctk.CTkLabel(frame, textvariable=self.y_var, font=("Arial", 20)).grid(row=1, column=1, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Z").grid(row=2, column=0, padx=8, pady=8)
        ctk.CTkLabel(frame, textvariable=self.z_var, font=("Arial", 20)).grid(row=2, column=1, padx=8, pady=8)

        ctk.CTkLabel(frame, text="Einheit").grid(row=3, column=0, padx=8, pady=8)
        ctk.CTkLabel(frame, textvariable=self.unit_var).grid(row=3, column=1, padx=8, pady=8)

    def _build_log_frame(self):
        self.log_frame.grid_rowconfigure(1, weight=1)
        self.log_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.log_frame, text="Log").grid(
            row=0, column=0, padx=8, pady=(8, 0), sticky="w"
        )

        self.log_text = ctk.CTkTextbox(self.log_frame, width=300)
        self.log_text.grid(row=1, column=0, padx=8, pady=8, sticky="nsew")

    # --------------------------------------------------
    # Receiver
    # --------------------------------------------------

    def start_receiver(self):
        try:
            if self.receiver is not None:
                self.receiver.stop()

            port = int(self.port_var.get())
            stale_threshold = float(self.stale_threshold_var.get().replace(",", "."))
            stable_threshold = float(self.stable_threshold_var.get().replace(",", "."))
            stable_count = int(self.stable_count_var.get())

            self.receiver = LasertrackerReceiver(
                port=port,
                stale_threshold_seconds=stale_threshold,
                stable_threshold_mm=stable_threshold,
                stable_required_count=stable_count,
                on_state_changed=self._on_state_changed,
                on_log=self._on_log,
                on_error=self._on_error,
            )

            self.receiver.start()

            self.receiver_status_var.set("● Running")
            self.receiver_status_label.configure(text_color="green")

        except Exception as e:
            messagebox.showerror("Lasertracker Fehler", str(e))
            self.log(f"Startfehler: {e}")

    def stop_receiver(self):
        if self.receiver is not None:
            self.receiver.stop()
            self.receiver = None

        self.receiver_status_var.set("● Stopped")
        self.receiver_status_label.configure(text_color="red")

    def shutdown(self):
        self.stop_receiver()

    # --------------------------------------------------
    # Thread-safe Callbacks
    # --------------------------------------------------

    def _on_state_changed(self, state: LasertrackerState):
        self.after(0, lambda: self._apply_state(state))

    def _on_log(self, text: str):
        self.after(0, lambda: self.log(text))

    def _on_error(self, text: str):
        self.after(0, lambda: self._handle_error(text))

    def _handle_error(self, text: str):
        self.log(f"ERROR: {text}")
        messagebox.showerror("Lasertracker Fehler", text)

    # --------------------------------------------------
    # State anwenden
    # --------------------------------------------------

    def _apply_state(self, state: LasertrackerState):
        self.receiving_var.set("Ja" if state.receiving else "Nein")
        self.stale_var.set("Ja" if state.stale else "Nein")
        self.stable_var.set("Ja" if state.stable else "Nein")

        if state.data_age_seconds is None:
            self.age_var.set("-")
        else:
            self.age_var.set(f"{state.data_age_seconds:.2f}")

        self.count_var.set(str(state.measurement_count))

        self.x_var.set("-" if state.x is None else f"{state.x:.3f}")
        self.y_var.set("-" if state.y is None else f"{state.y:.3f}")
        self.z_var.set("-" if state.z is None else f"{state.z:.3f}")
        self.unit_var.set(state.unit)

    # --------------------------------------------------
    # Log
    # --------------------------------------------------

    def log(self, text: str):
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
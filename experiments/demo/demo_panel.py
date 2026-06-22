# demo_panel.py

import customtkinter as ctk
from tkinter import messagebox

from demo_worker import DemoWorker


class DemoPanel(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)

        self.status_var = ctk.StringVar(value="Nicht verbunden")
        self.value_var = ctk.StringVar(value="0")

        self.worker = DemoWorker(
            on_log=self.log_threadsafe,
            on_status=self.set_status_threadsafe,
            on_value=self.set_value_threadsafe,
            on_error=self.show_error_threadsafe
        )
        self.worker.start()

        self._build_gui()

    def _build_gui(self):
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Demo-Komponente", font=("Arial", 20)).grid(
            row=0, column=0, padx=10, pady=10
        )

        ctk.CTkLabel(self, text="Status").grid(row=1, column=0, padx=10, pady=(10, 0))
        ctk.CTkLabel(self, textvariable=self.status_var).grid(row=2, column=0, padx=10, pady=5)

        ctk.CTkLabel(self, text="Wert").grid(row=3, column=0, padx=10, pady=(10, 0))
        ctk.CTkLabel(self, textvariable=self.value_var, font=("Arial", 24)).grid(
            row=4, column=0, padx=10, pady=5
        )

        ctk.CTkButton(
            self,
            text="Connect",
            command=lambda: self.worker.send_command("connect")
        ).grid(row=5, column=0, padx=10, pady=5, sticky="ew")

        ctk.CTkButton(
            self,
            text="Disconnect",
            command=lambda: self.worker.send_command("disconnect")
        ).grid(row=6, column=0, padx=10, pady=5, sticky="ew")

        ctk.CTkButton(
            self,
            text="Langsame Arbeit starten",
            command=lambda: self.worker.send_command("slow_work")
        ).grid(row=7, column=0, padx=10, pady=5, sticky="ew")

        ctk.CTkButton(
            self,
            text="Reset",
            command=lambda: self.worker.send_command("reset")
        ).grid(row=8, column=0, padx=10, pady=5, sticky="ew")

        self.log_text = ctk.CTkTextbox(self, height=160)
        self.log_text.grid(row=9, column=0, padx=10, pady=10, sticky="nsew")

        self.grid_rowconfigure(9, weight=1)

    # --------------------------------------------------
    # Thread-sichere GUI Updates
    # --------------------------------------------------

    def log_threadsafe(self, text: str):
        self.after(0, lambda: self._log(text))

    def set_status_threadsafe(self, text: str):
        self.after(0, lambda: self.status_var.set(text))

    def set_value_threadsafe(self, value: int):
        self.after(0, lambda: self.value_var.set(str(value)))

    def show_error_threadsafe(self, text: str):
        self.after(0, lambda: messagebox.showerror("Fehler", text))

    def _log(self, text: str):
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")

    def shutdown(self):
        self.worker.stop()
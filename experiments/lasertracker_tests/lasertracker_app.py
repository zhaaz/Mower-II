# lasertracker_app.py

import customtkinter as ctk

from lasertracker_panel import LasertrackerPanel


class LasertrackerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Lasertracker UDP Receiver")
        self.geometry("1000x650")
        self.minsize(900, 600)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.panel = LasertrackerPanel(self)
        self.panel.grid(row=0, column=0, sticky="nsew")

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        self.panel.shutdown()
        self.destroy()


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = LasertrackerApp()
    app.mainloop()
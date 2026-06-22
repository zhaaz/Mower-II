# demo_app.py

import customtkinter as ctk
from demo_panel import DemoPanel


class DemoApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Worker GUI Beispiel")
        self.geometry("500x600")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.panel = DemoPanel(self)
        self.panel.grid(row=0, column=0, sticky="nsew")

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        self.panel.shutdown()
        self.destroy()


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = DemoApp()
    app.mainloop()
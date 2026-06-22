# xyz_robot_app_worker.py

import customtkinter as ctk

from xyz_robot_panel_worker import XYZRobotPanelWorker


class XYZRobotAppWorker(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("XYZ-Roboter Worker-Test")
        self.geometry("1000x700")
        self.minsize(1000, 700)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.xyz_panel = XYZRobotPanelWorker(self)
        self.xyz_panel.grid(row=0, column=0, sticky="nsew")

        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_close(self):
        self.xyz_panel.shutdown()
        self.destroy()


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = XYZRobotAppWorker()
    app.mainloop()
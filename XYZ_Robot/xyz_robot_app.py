# xyz_robot_app.py

import customtkinter as ctk

from xyz_robot_panel import XYZRobotPanel


class XYZRobotApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("XYZ-Roboter")
        self.geometry("1000x700")
        self.minsize(1000, 700)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.xyz_panel = XYZRobotPanel(self)
        self.xyz_panel.grid(row=0, column=0, sticky="nsew")

        self._bind_hotkeys()

    def _bind_hotkeys(self):
        self.bind("<Left>", lambda event: self.xyz_panel.hotkey_jog(dy=self.xyz_panel._get_step()))
        self.bind("<Right>", lambda event: self.xyz_panel.hotkey_jog(dy=-self.xyz_panel._get_step()))
        self.bind("<Down>", lambda event: self.xyz_panel.hotkey_jog(dx=-self.xyz_panel._get_step()))
        self.bind("<Up>", lambda event: self.xyz_panel.hotkey_jog(dx=self.xyz_panel._get_step()))

        self.bind("<Prior>", lambda event: self.xyz_panel.hotkey_jog(dz=self.xyz_panel._get_step()))
        self.bind("<Next>", lambda event: self.xyz_panel.hotkey_jog(dz=-self.xyz_panel._get_step()))


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = XYZRobotApp()
    app.mainloop()
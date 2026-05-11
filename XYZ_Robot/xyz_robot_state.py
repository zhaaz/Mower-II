# xyz_robot_state.py

from dataclasses import dataclass


@dataclass
class XYZRobotState:
    connected: bool = False
    homed: bool = False
    busy: bool = False

    status_text: str = "Not Connected"
    error_text: str | None = None

    x: float | None = None
    y: float | None = None
    z: float | None = None

    port: str | None = None
    baudrate: int | None = None

    def clear_position(self) -> None:
        self.x = None
        self.y = None
        self.z = None

    def set_position(self, position: dict[str, float]) -> None:
        self.x = position.get("X")
        self.y = position.get("Y")
        self.z = position.get("Z")
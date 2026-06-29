from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class GyemsState:
    """Runtime state for a GYEMS/RMD RS-485 motor test stand."""

    connected: bool = False
    busy: bool = False

    status_text: str = "Not connected"
    error_text: str | None = None

    port: str | None = None
    baudrate: int | None = None
    motor_id: int = 1

    angle_deg: float | None = None
    reference_offset_deg: float = 0.0
    relative_angle_deg: float | None = None

    temperature_C: int | None = None
    torque_current: int | None = None
    speed_raw: int | None = None
    encoder_pos: int | None = None

    last_speed_cmd_dps: float = 0.0
    last_abs_target_deg: float | None = None

    model_driver: str = ""
    model_motor: str = ""
    hw_version: float | None = None
    fw_version: float | None = None

    error_flags: dict[str, Any] | None = None

    ok_count: int = 0
    error_count: int = 0

    def clear_measurement(self) -> None:
        self.angle_deg = None
        self.relative_angle_deg = None
        self.temperature_C = None
        self.torque_current = None
        self.speed_raw = None
        self.encoder_pos = None
        self.last_speed_cmd_dps = 0.0
        self.last_abs_target_deg = None
        self.error_flags = None
        self.ok_count = 0
        self.error_count = 0

    def update_relative_angle(self) -> None:
        if self.angle_deg is None:
            self.relative_angle_deg = None
        else:
            self.relative_angle_deg = self.angle_deg - self.reference_offset_deg

# experiments/kvh_tests/kvh_dsp_state.py

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class KVHDSPState:
    connected: bool = False
    busy: bool = False

    status_text: str = "Not Connected"
    error_text: str | None = None

    port: str | None = None
    baudrate: int | None = None

    angle_deg: float = 0.0
    rate_dps: float = 0.0
    drift_dps: float = 0.0

    valid_packets: int = 0
    skipped_bytes: int = 0
    drift_active: bool = False

    def clear_measurement(self) -> None:
        self.angle_deg = 0.0
        self.rate_dps = 0.0
        self.drift_dps = 0.0
        self.valid_packets = 0
        self.skipped_bytes = 0
        self.drift_active = False

# config/mower_config.py

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path


# --------------------------------------------------
# Dataclasses
# --------------------------------------------------

@dataclass
class XYZConfig:
    port: str = "COM5"
    baudrate: int = 115200

    x_min: float = 0.0
    x_max: float = 500.0

    y_min: float = 0.0
    y_max: float = 400.0

    z_min: float = 150.0
    z_max: float = 200.0

    default_feedrate: float = 1500.0
    fast_feedrate: float = 6000.0

    tolerance_mm: float = 0.05


@dataclass
class TrackerConfig:
    udp_port: int = 10000

    capture_timeout_s: float = 30.0

    ccr_radius_mm: float = 19.05


@dataclass
class MarkerConfig:
    shape: str = "plus"

    size_mm: float = 20.0

    angle_deg: float = 0.0


@dataclass
class TransformationConfig:
    marker_to_reflector_robot: tuple[float, float, float] = (
        -31.703266,
        -3.776229,
        295.472290,
    )


@dataclass
class MowerConfig:
    xyz: XYZConfig
    tracker: TrackerConfig
    marker: MarkerConfig
    transformation: TransformationConfig


# --------------------------------------------------
# Defaults
# --------------------------------------------------

DEFAULT_CONFIG = MowerConfig(
    xyz=XYZConfig(),
    tracker=TrackerConfig(),
    marker=MarkerConfig(),
    transformation=TransformationConfig(),
)


# --------------------------------------------------
# Pfade
# --------------------------------------------------

CONFIG_PATH = Path(__file__).with_name("mower_config.json")


# --------------------------------------------------
# Laden
# --------------------------------------------------

def load_config() -> MowerConfig:
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    return MowerConfig(
        xyz=XYZConfig(**data["xyz"]),
        tracker=TrackerConfig(**data["tracker"]),
        marker=MarkerConfig(**data["marker"]),
        transformation=TransformationConfig(**data["transformation"]),
    )


# --------------------------------------------------
# Speichern
# --------------------------------------------------

def save_config(config: MowerConfig) -> None:
    data = asdict(config)

    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=4,
        )


# --------------------------------------------------
# Komfortfunktionen
# --------------------------------------------------

def update_marker_to_reflector_robot(
    vector: tuple[float, float, float],
) -> None:
    config = load_config()

    config.transformation.marker_to_reflector_robot = vector

    save_config(config)


# --------------------------------------------------
# Globale aktive Config
# --------------------------------------------------

CONFIG = load_config()
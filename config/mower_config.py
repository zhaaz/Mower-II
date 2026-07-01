# config/mower_config.py

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


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
class GyroConfig:
    port: str = "COM3"
    baudrate: int = 375000
    default_drift_seconds: float = 30.0


@dataclass
class ArnConfig:
    # Proportionalfaktor fuer die aktive Reflektornachfuehrung.
    # speed_cmd_deg_s = kp * error_deg
    kp: float = 5.0

    # Maximale GYEMS-Geschwindigkeit im ARN-Betrieb [deg/s].
    max_speed_deg_s: float = 45.0

    # Totband gegen Zittern um die Sollrichtung [deg].
    deadband_deg: float = 0.5

    # Mindestabstand zwischen Speed-Kommandos [ms].
    command_interval_ms: int = 200

    # Vorzeichen fuer die Umrechnung der geometrischen Sollrichtung in
    # GYEMS-Motorwinkel. Bei umgekehrter Mechanik auf -1.0 setzen.
    direction_sign: float = 1.0


@dataclass
class MarkerConfig:
    shape: str = "plus"

    size_mm: float = 80.0

    angle_deg: float = 0.0

    # Markierhoehen der Z-Achse [mm].
    # Alle drei Werte sind echte Config-Parameter.
    # Z_MARK = Stift unten / Markierkontakt.
    # Z_CLEAR = kurze Abhebehoehe zwischen Linien.
    # Z_TRAVEL = sichere Fahrhoehe fuer laengere XY-Bewegungen.
    z_mark_mm: float = 166.0
    z_clear_mm: float = 171.0
    z_travel_mm: float = 176.0


@dataclass
class TransformationConfig:
    marker_to_reflector_robot: tuple[float, float, float] = (
        -34.258937,
        -2.728703,
        300.037719,
    )

    # Maximale zulaessige KVH-Winkelaenderung nach einer gueltigen
    # Transformation. Wird der Betrag ueberschritten, wird die
    # Transformation invalidiert.
    gyro_invalid_threshold_deg: float = 0.03


@dataclass
class PathsConfig:
    """
    Zentrale Projektpfade.

    Relative Pfade werden vom Projektroot aus interpretiert.
    Absolute Pfade bleiben absolute Pfade.
    """

    tracker_station_file: str = "data/tracker_station.txt"
    log_dir: str = "logs"
    measurement_plans_dir: str = "measurement_plans"


@dataclass
class MowerConfig:
    xyz: XYZConfig
    tracker: TrackerConfig
    gyro: GyroConfig
    arn: ArnConfig
    marker: MarkerConfig
    transformation: TransformationConfig
    paths: PathsConfig


# --------------------------------------------------
# Defaults
# --------------------------------------------------

DEFAULT_CONFIG = MowerConfig(
    xyz=XYZConfig(),
    tracker=TrackerConfig(),
    gyro=GyroConfig(),
    arn=ArnConfig(),
    marker=MarkerConfig(),
    transformation=TransformationConfig(),
    paths=PathsConfig(),
)


# --------------------------------------------------
# Pfade
# --------------------------------------------------

CONFIG_PATH = Path(__file__).with_name("mower_config.json")


# --------------------------------------------------
# Hilfsfunktionen
# --------------------------------------------------

def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    """
    Liefert einen Config-Abschnitt oder ein leeres Dict.

    Dadurch bleiben alte JSON-Dateien ohne neue Abschnitte kompatibel.
    """
    value = data.get(name, {})
    if isinstance(value, dict):
        return value
    return {}


def _as_tuple3(value: Any) -> tuple[float, float, float]:
    """
    Wandelt JSON-Listen oder Tupel in ein 3er-Float-Tupel um.
    """
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return DEFAULT_CONFIG.transformation.marker_to_reflector_robot

    return (float(value[0]), float(value[1]), float(value[2]))


# --------------------------------------------------
# Laden
# --------------------------------------------------

def load_config() -> MowerConfig:
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    xyz_data = _section(data, "xyz")
    tracker_data = _section(data, "tracker")
    gyro_data = _section(data, "gyro")
    arn_data = _section(data, "arn")
    marker_data = _section(data, "marker")
    transformation_data = _section(data, "transformation")
    paths_data = _section(data, "paths")

    transformation = TransformationConfig(
        **{
            **transformation_data,
            "marker_to_reflector_robot": _as_tuple3(
                transformation_data.get(
                    "marker_to_reflector_robot",
                    DEFAULT_CONFIG.transformation.marker_to_reflector_robot,
                )
            ),
        }
    )

    return MowerConfig(
        xyz=XYZConfig(**xyz_data),
        tracker=TrackerConfig(**tracker_data),
        gyro=GyroConfig(**gyro_data),
        arn=ArnConfig(**arn_data),
        marker=MarkerConfig(**marker_data),
        transformation=transformation,
        paths=PathsConfig(**paths_data),
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


def update_marker_z_heights_mm(
    *,
    z_mark_mm: float,
    z_clear_mm: float,
    z_travel_mm: float,
) -> None:
    """Speichert die Markierhoehen Z_MARK, Z_CLEAR und Z_TRAVEL in mower_config.json."""

    config = load_config()
    config.marker.z_mark_mm = float(z_mark_mm)
    config.marker.z_clear_mm = float(z_clear_mm)
    config.marker.z_travel_mm = float(z_travel_mm)
    save_config(config)


def update_marker_z_mark_mm(z_mark_mm: float) -> None:
    """Kompatibilitaetsfunktion: speichert Z_MARK und behaelt Z_CLEAR/Z_TRAVEL bei."""

    config = load_config()
    config.marker.z_mark_mm = float(z_mark_mm)
    save_config(config)


# --------------------------------------------------
# Globale aktive Config
# --------------------------------------------------

CONFIG = load_config()

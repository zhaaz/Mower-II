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

    # Vor jeder Transformation nur die Z-Achse neu referenzieren und danach
    # auf die sichere Fahrhoehe fahren. So wird ein moeglicher Schrittverlust
    # der Z-Achse nicht in die Transformationsfahrt uebernommen.
    home_z_before_transformation: bool = True


@dataclass
class TrackerConfig:
    udp_port: int = 10000

    capture_timeout_s: float = 30.0

    ccr_radius_mm: float = 19.05


@dataclass
class MurataConfig:
    port: str = "COM9"
    baudrate: int = 115200
    default_drift_seconds: float = 10.0

    # Vorzeichen fuer den im Mower verwendeten Winkel. Falls der Winkel bei
    # der endgueltigen Einbaulage in die falsche Richtung laeuft, auf -1.0
    # setzen.
    direction_sign: float = 1.0


@dataclass
class GyemsConfig:
    port: str = "COM4"
    baudrate: int = 115200
    motor_id: int = 1


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

    # Wenn aktiv, werden Markerformen und Beschriftungen an der
    # X-Achse des Lasertracker-Koordinatensystems ausgerichtet.
    # CONFIG.marker.angle_deg bleibt ein zusaetzlicher Winkeloffset.
    align_to_tracker_axes: bool = False

    # Wenn aktiv, wird nach jeder Markierung automatisch der obere Reflektor
    # gemessen und daraus die geschaetzte Markierpunktposition berechnet.
    measure_after_marking: bool = False

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

    # Maximale zulaessige Murata-Winkelaenderung nach einer gueltigen
    # Transformation. Wird der Betrag ueberschritten, wird die
    # Transformation invalidiert.
    gyro_invalid_threshold_deg: float = 0.03

    # Qualitaetsgrenzen der Transformation [mm]. Fuer jede Stufe muessen
    # sowohl RMS als auch maximale Restklaffung innerhalb des Grenzwerts
    # liegen. Alles bis einschliesslich OK wird technisch freigegeben.
    very_good_rms_mm: float = 0.05
    very_good_max_residual_mm: float = 0.10

    good_rms_mm: float = 0.10
    good_max_residual_mm: float = 0.20

    ok_rms_mm: float = 0.25
    ok_max_residual_mm: float = 0.50

    # Parameter des Transformationsworkflows.
    calibration_points: tuple[tuple[str, float, float], ...] = (
        ("K1", 100.0, 100.0),
        ("K2", 100.0, 350.0),
        ("K3", 350.0, 350.0),
        ("K4", 400.0, 100.0),
        ("K5", 200.0, 200.0),
    )
    calibration_random_radius_mm: float = 50.0
    minimum_required_measurements: int = 4
    min_geometry_rank: int = 2

    # Bei allow_scale=true wird der Massstab geschaetzt, aber nur innerhalb
    # der maximalen Abweichung von 1.0 akzeptiert. 0.0005 entspricht 0.05 %.
    allow_scale: bool = True
    max_scale_deviation: float = 0.0005


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
    murata: MurataConfig
    gyems: GyemsConfig
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
    murata=MurataConfig(),
    gyems=GyemsConfig(),
    arn=ArnConfig(),
    marker=MarkerConfig(),
    transformation=TransformationConfig(),
    paths=PathsConfig(),
)


# --------------------------------------------------
# Pfade
# --------------------------------------------------

CONFIG_PATH = Path(__file__).with_name("mower_config.json")


class ConfigValidationError(ValueError):
    """Fasst alle erkannten Konfigurationsfehler verständlich zusammen."""


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


def _as_calibration_points(value: Any) -> tuple[tuple[str, float, float], ...]:
    if not isinstance(value, (list, tuple)):
        return DEFAULT_CONFIG.transformation.calibration_points

    points: list[tuple[str, float, float]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            raise ConfigValidationError(
                "Ungültiger Transformationspunkt "
                f"{index}: erwartet wird [Name, X, Y]."
            )
        points.append((str(item[0]), float(item[1]), float(item[2])))
    return tuple(points)


def validate_config(config: MowerConfig) -> None:
    """Prüft sicherheits- und ablaufrelevante Configwerte beim Programmstart."""
    errors: list[str] = []

    def number(value: Any, label: str) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            errors.append(f"{label} muss eine Zahl sein.")
            return None

    def positive(value: Any, label: str, *, allow_zero: bool = False) -> float | None:
        result = number(value, label)
        if result is not None:
            valid = result >= 0.0 if allow_zero else result > 0.0
            if not valid:
                relation = "größer oder gleich 0" if allow_zero else "größer als 0"
                errors.append(f"{label} muss {relation} sein.")
        return result

    for label, port in (
        ("xyz.port", config.xyz.port),
        ("murata.port", config.murata.port),
        ("gyems.port", config.gyems.port),
    ):
        if not isinstance(port, str) or not port.strip():
            errors.append(f"{label} darf nicht leer sein.")

    positive(config.xyz.baudrate, "xyz.baudrate")
    positive(config.xyz.default_feedrate, "xyz.default_feedrate")
    positive(config.xyz.fast_feedrate, "xyz.fast_feedrate")
    positive(config.xyz.tolerance_mm, "xyz.tolerance_mm")

    axis_limits: dict[str, tuple[float | None, float | None]] = {}
    for axis in ("x", "y", "z"):
        lower = number(getattr(config.xyz, f"{axis}_min"), f"xyz.{axis}_min")
        upper = number(getattr(config.xyz, f"{axis}_max"), f"xyz.{axis}_max")
        axis_limits[axis] = (lower, upper)
        if lower is not None and upper is not None and lower >= upper:
            errors.append(f"xyz.{axis}_min muss kleiner als xyz.{axis}_max sein.")

    if not isinstance(config.xyz.home_z_before_transformation, bool):
        errors.append("xyz.home_z_before_transformation muss true oder false sein.")

    try:
        udp_port = int(config.tracker.udp_port)
        if not 1 <= udp_port <= 65535:
            errors.append("tracker.udp_port muss zwischen 1 und 65535 liegen.")
    except (TypeError, ValueError):
        errors.append("tracker.udp_port muss eine ganze Zahl sein.")
    positive(config.tracker.capture_timeout_s, "tracker.capture_timeout_s")
    positive(config.tracker.ccr_radius_mm, "tracker.ccr_radius_mm")

    positive(config.murata.baudrate, "murata.baudrate")
    positive(config.murata.default_drift_seconds, "murata.default_drift_seconds")
    positive(config.gyems.baudrate, "gyems.baudrate")
    positive(config.gyems.motor_id, "gyems.motor_id")

    positive(config.arn.kp, "arn.kp", allow_zero=True)
    positive(config.arn.max_speed_deg_s, "arn.max_speed_deg_s", allow_zero=True)
    positive(config.arn.deadband_deg, "arn.deadband_deg", allow_zero=True)
    positive(config.arn.command_interval_ms, "arn.command_interval_ms")
    arn_direction = number(config.arn.direction_sign, "arn.direction_sign")
    if arn_direction == 0.0:
        errors.append("arn.direction_sign darf nicht 0 sein.")

    positive(config.marker.size_mm, "marker.size_mm")
    z_values = {
        "marker.z_mark_mm": number(config.marker.z_mark_mm, "marker.z_mark_mm"),
        "marker.z_clear_mm": number(config.marker.z_clear_mm, "marker.z_clear_mm"),
        "marker.z_travel_mm": number(config.marker.z_travel_mm, "marker.z_travel_mm"),
    }
    z_min, z_max = axis_limits["z"]
    if z_min is not None and z_max is not None:
        for label, value in z_values.items():
            if value is not None and not z_min <= value <= z_max:
                errors.append(f"{label} muss innerhalb des Z-Arbeitsraums liegen.")
    if all(value is not None for value in z_values.values()):
        z_mark = float(z_values["marker.z_mark_mm"])
        z_clear = float(z_values["marker.z_clear_mm"])
        z_travel = float(z_values["marker.z_travel_mm"])
        if not z_mark <= z_clear <= z_travel:
            errors.append("Es muss Z_MARK <= Z_CLEAR <= Z_TRAVEL gelten.")

    trafo = config.transformation
    positive(trafo.gyro_invalid_threshold_deg, "transformation.gyro_invalid_threshold_deg")
    quality_values = {
        "very_good_rms_mm": positive(trafo.very_good_rms_mm, "transformation.very_good_rms_mm", allow_zero=True),
        "good_rms_mm": positive(trafo.good_rms_mm, "transformation.good_rms_mm", allow_zero=True),
        "ok_rms_mm": positive(trafo.ok_rms_mm, "transformation.ok_rms_mm", allow_zero=True),
        "very_good_max_residual_mm": positive(trafo.very_good_max_residual_mm, "transformation.very_good_max_residual_mm", allow_zero=True),
        "good_max_residual_mm": positive(trafo.good_max_residual_mm, "transformation.good_max_residual_mm", allow_zero=True),
        "ok_max_residual_mm": positive(trafo.ok_max_residual_mm, "transformation.ok_max_residual_mm", allow_zero=True),
    }
    rms_order = [quality_values[name] for name in ("very_good_rms_mm", "good_rms_mm", "ok_rms_mm")]
    max_order = [quality_values[name] for name in ("very_good_max_residual_mm", "good_max_residual_mm", "ok_max_residual_mm")]
    if all(value is not None for value in rms_order) and not rms_order[0] <= rms_order[1] <= rms_order[2]:
        errors.append("RMS-Grenzen müssen SEHR GUT <= GUT <= OK erfüllen.")
    if all(value is not None for value in max_order) and not max_order[0] <= max_order[1] <= max_order[2]:
        errors.append("Max-Grenzen müssen SEHR GUT <= GUT <= OK erfüllen.")

    positive(trafo.calibration_random_radius_mm, "transformation.calibration_random_radius_mm", allow_zero=True)
    positive(trafo.max_scale_deviation, "transformation.max_scale_deviation", allow_zero=True)
    if not isinstance(trafo.allow_scale, bool):
        errors.append("transformation.allow_scale muss true oder false sein.")
    try:
        geometry_rank = int(trafo.min_geometry_rank)
        if geometry_rank not in (2, 3):
            errors.append("transformation.min_geometry_rank muss 2 oder 3 sein.")
    except (TypeError, ValueError):
        errors.append("transformation.min_geometry_rank muss 2 oder 3 sein.")

    points = trafo.calibration_points
    if len(points) < 3:
        errors.append("Mindestens drei Transformationspunkte müssen definiert sein.")
    names = [str(point[0]).strip() for point in points]
    if any(not name for name in names):
        errors.append("Transformationspunktnamen dürfen nicht leer sein.")
    if len(set(names)) != len(names):
        errors.append("Transformationspunktnamen müssen eindeutig sein.")
    try:
        minimum = int(trafo.minimum_required_measurements)
        if minimum < 3 or minimum > len(points):
            errors.append(
                "transformation.minimum_required_measurements muss zwischen 3 "
                "und der Anzahl der Transformationspunkte liegen."
            )
    except (TypeError, ValueError):
        errors.append("transformation.minimum_required_measurements muss eine ganze Zahl sein.")

    if errors:
        raise ConfigValidationError(
            "Ungültige mower_config.json:\n- " + "\n- ".join(errors)
        )


# --------------------------------------------------
# Laden
# --------------------------------------------------

def load_config() -> MowerConfig:
    if not CONFIG_PATH.exists():
        validate_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG

    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = json.load(f)

    xyz_data = _section(data, "xyz")
    tracker_data = _section(data, "tracker")
    murata_data = _section(data, "murata")
    gyems_data = _section(data, "gyems")
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
            "calibration_points": _as_calibration_points(
                transformation_data.get(
                    "calibration_points",
                    DEFAULT_CONFIG.transformation.calibration_points,
                )
            ),
        }
    )

    config = MowerConfig(
        xyz=XYZConfig(**xyz_data),
        tracker=TrackerConfig(**tracker_data),
        murata=MurataConfig(**murata_data),
        gyems=GyemsConfig(**gyems_data),
        arn=ArnConfig(**arn_data),
        marker=MarkerConfig(**marker_data),
        transformation=transformation,
        paths=PathsConfig(**paths_data),
    )
    validate_config(config)
    return config


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


def update_marker_align_to_tracker_axes(enabled: bool) -> None:
    """Speichert, ob Markierungen an der LT-X-Achse ausgerichtet werden."""

    config = load_config()
    config.marker.align_to_tracker_axes = bool(enabled)
    save_config(config)


def update_marker_measure_after_marking(enabled: bool) -> None:
    """Speichert, ob nach dem Markieren automatisch gemessen wird."""

    config = load_config()
    config.marker.measure_after_marking = bool(enabled)
    save_config(config)


# --------------------------------------------------
# Globale aktive Config
# --------------------------------------------------

CONFIG = load_config()


# Transformation/marker_offset_calibration.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from Transformation.helmert_3d import Helmert3DResult, estimate_helmert_3d


@dataclass
class CalibrationSample:
    """
    Ein vollständiger Kalibrierpunkt für die Marker-/Reflektoroffset-Auswertung.

    Koordinatensysteme:
        robot_marker:
            Soll-/Zielkoordinate des markierten Punktes im Robotersystem.

        reflector_lt:
            Lasertracker-Messung des oberen Reflektors, während der Roboter auf
            robot_marker steht.

        marker_lt:
            Lasertracker-Messung des real markierten Punktes mit manuell
            aufgesetztem CCR.

        offset_robot:
            Ergebnis je Punkt:
                marker_to_reflector_robot = reflector_robot - marker_robot

            Wird durch compute_marker_to_reflector_offset(...) gesetzt.
    """

    label: str
    robot_marker: np.ndarray
    reflector_lt: np.ndarray
    marker_lt: np.ndarray
    offset_robot: np.ndarray | None = None


@dataclass(frozen=True)
class MarkerOffsetCalibrationResult:
    """
    Ergebnis der Marker-/Reflektoroffset-Kalibrierung.

    mean_offset_robot ist der gesuchte Vektor:
        marker_to_reflector_robot = reflector_robot - marker_robot
    """

    helmert: Helmert3DResult
    samples: list[CalibrationSample]
    mean_offset_robot: np.ndarray
    std_offset_robot: np.ndarray
    rms_offset: float
    max_deviation: float
    deviation_norms: np.ndarray


def compute_marker_to_reflector_offset(
    samples: Iterable[CalibrationSample],
    *,
    allow_scale: bool = True,
    min_geometry_rank: int = 2,
) -> MarkerOffsetCalibrationResult:
    """
    Berechnet den realen Offset zwischen markiertem Punkt und oberem Reflektor.

    Gesuchter Vektor:
        marker_to_reflector_robot = reflector_robot - marker_robot

    Mathematischer Ablauf:
        1. Helmert-3D aus robot_marker -> reflector_lt berechnen

           tracker = translation + scale * rotation @ robot

        2. Fuer jeden Punkt:

           diff_lt = reflector_lt - marker_lt
           diff_robot = rotation.T @ diff_lt / scale

           Wichtig:
               Es wird absichtlich KEINE Translation verwendet, weil hier ein
               Differenzvektor transformiert wird, kein absoluter Punkt.

    Parameter
    ---------
    samples:
        Vollstaendige Kalibrierpunkte.

    allow_scale:
        True: Massstab wird in der Helmert-Transformation geschaetzt.
        False: Massstab wird auf 1.0 fixiert.

    min_geometry_rank:
        Mindest-Rang der Roboterpunkt-Geometrie fuer estimate_helmert_3d.
        Fuer flaechenhafte XY-Punkte ist 2 sinnvoll.

    Returns
    -------
    MarkerOffsetCalibrationResult
        Enthaelt Einzeloffsets, Mittelwert, Standardabweichung und Qualitaetsmasse.
    """

    sample_list = list(samples)
    _validate_samples(sample_list)

    helmert = estimate_helmert_3d(
        robot_points=[sample.robot_marker for sample in sample_list],
        tracker_points=[sample.reflector_lt for sample in sample_list],
        allow_scale=allow_scale,
        min_geometry_rank=min_geometry_rank,
    )

    offsets: list[np.ndarray] = []

    for sample in sample_list:
        diff_lt = sample.reflector_lt - sample.marker_lt

        # Nur Rotation und Massstab verwenden, keine Translation.
        sample.offset_robot = helmert.rotation.T @ diff_lt / helmert.scale
        offsets.append(sample.offset_robot)

    offset_matrix = np.vstack(offsets)

    mean_offset_robot = offset_matrix.mean(axis=0)

    if len(sample_list) > 1:
        std_offset_robot = offset_matrix.std(axis=0, ddof=1)
    else:
        std_offset_robot = np.zeros(3, dtype=float)

    deviations = offset_matrix - mean_offset_robot
    deviation_norms = np.linalg.norm(deviations, axis=1)

    rms_offset = float(np.sqrt(np.mean(deviation_norms ** 2)))
    max_deviation = float(np.max(deviation_norms))

    return MarkerOffsetCalibrationResult(
        helmert=helmert,
        samples=sample_list,
        mean_offset_robot=mean_offset_robot,
        std_offset_robot=std_offset_robot,
        rms_offset=rms_offset,
        max_deviation=max_deviation,
        deviation_norms=deviation_norms,
    )


def make_calibration_sample(
    label: str,
    robot_marker: Sequence[float],
    reflector_lt: Sequence[float],
    marker_lt: Sequence[float],
) -> CalibrationSample:
    """
    Komfortfunktion zum Erzeugen eines CalibrationSample aus Listen/Tupeln.
    """

    return CalibrationSample(
        label=str(label),
        robot_marker=_as_point3(robot_marker, "robot_marker"),
        reflector_lt=_as_point3(reflector_lt, "reflector_lt"),
        marker_lt=_as_point3(marker_lt, "marker_lt"),
    )


def offsets_as_matrix(samples: Iterable[CalibrationSample]) -> np.ndarray:
    """
    Gibt die berechneten Einzeloffsets als n x 3 Matrix zurueck.

    Voraussetzung:
        compute_marker_to_reflector_offset(...) wurde bereits ausgefuehrt.
    """

    offsets: list[np.ndarray] = []

    for sample in samples:
        if sample.offset_robot is None:
            raise ValueError(f"Sample {sample.label!r} hat noch keinen offset_robot.")
        offsets.append(_as_point3(sample.offset_robot, f"{sample.label}.offset_robot"))

    if not offsets:
        raise ValueError("Keine Samples vorhanden.")

    return np.vstack(offsets)


def format_offset_result(result: MarkerOffsetCalibrationResult) -> str:
    """
    Erstellt eine kompakte Textausgabe fuer Logdatei, Konsole oder GUI.
    """

    lines: list[str] = []
    lines.append("Marker-/Reflektoroffset-Kalibrierung")
    lines.append("")
    lines.append(result.helmert.format_summary())
    lines.append("")
    lines.append("Einzeloffsets marker_to_reflector_robot [mm]")

    for sample, deviation_norm in zip(result.samples, result.deviation_norms):
        offset = _require_offset(sample)
        lines.append(
            f"{sample.label}: "
            f"X={offset[0]:.6f}, "
            f"Y={offset[1]:.6f}, "
            f"Z={offset[2]:.6f}, "
            f"Abw={deviation_norm:.6f}"
        )

    mean = result.mean_offset_robot
    std = result.std_offset_robot

    lines.append("")
    lines.append(
        "Mittelwert marker_to_reflector_robot [mm]: "
        f"X={mean[0]:.6f}, Y={mean[1]:.6f}, Z={mean[2]:.6f}"
    )
    lines.append(
        "Standardabweichung [mm]: "
        f"X={std[0]:.6f}, Y={std[1]:.6f}, Z={std[2]:.6f}"
    )
    lines.append(
        "Offset-Qualitaet: "
        f"RMS={result.rms_offset:.6f} mm, "
        f"Max={result.max_deviation:.6f} mm"
    )

    return "\n".join(lines)


def _validate_samples(samples: list[CalibrationSample]) -> None:
    if len(samples) < 3:
        raise ValueError(
            "Fuer die Kalibrierung werden mindestens 3 Punktpaare benoetigt. "
            "Empfohlen sind mindestens 5 Punkte."
        )

    labels: set[str] = set()

    for index, sample in enumerate(samples):
        if not sample.label:
            raise ValueError(f"Sample {index} hat kein Label.")

        if sample.label in labels:
            raise ValueError(f"Label {sample.label!r} kommt mehrfach vor.")
        labels.add(sample.label)

        sample.robot_marker = _as_point3(sample.robot_marker, f"{sample.label}.robot_marker")
        sample.reflector_lt = _as_point3(sample.reflector_lt, f"{sample.label}.reflector_lt")
        sample.marker_lt = _as_point3(sample.marker_lt, f"{sample.label}.marker_lt")


def _as_point3(value: Sequence[float] | np.ndarray, name: str) -> np.ndarray:
    point = np.asarray(value, dtype=float).reshape(-1)

    if point.shape != (3,):
        raise ValueError(f"{name} muss genau 3 Koordinaten enthalten, erhalten: shape={point.shape}")

    if not np.all(np.isfinite(point)):
        raise ValueError(f"{name} enthaelt ungueltige oder nicht endliche Werte: {point}")

    return point


def _require_offset(sample: CalibrationSample) -> np.ndarray:
    if sample.offset_robot is None:
        raise ValueError(f"Sample {sample.label!r} hat noch keinen berechneten offset_robot.")

    return _as_point3(sample.offset_robot, f"{sample.label}.offset_robot")

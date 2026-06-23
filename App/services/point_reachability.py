# App/services/point_reachability.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable

import numpy as np

try:
    from Transformation.coordinate_mapper import CoordinateMapper, RobotWorkspace
except Exception:
    CoordinateMapper = None
    RobotWorkspace = None


LogFunction = Callable[[str], None]


@dataclass(frozen=True)
class PointReachability:
    """Auswertung eines Projektpunktes gegen die aktive Transformation und den XY-Arbeitsraum."""

    point: Any
    name: str
    reachable: bool
    marked: bool
    robot_x: float | None = None
    robot_y: float | None = None
    robot_z: float | None = None
    reason: str = ""

    @property
    def status_text(self) -> str:
        if self.marked:
            return "markiert"
        return "nicht markiert"


def evaluate_points_reachability(
        *,
        points: Iterable[Any],
        trafo_manager: Any,
        config: Any,
        log: LogFunction | None = None,
        debug: bool = False,
) -> list[PointReachability]:
    """Berechnet fuer alle Punkte die Erreichbarkeit im Robotersystem.

    Aktueller bewusst einfacher Stand:
        - Punkt-X/Y werden aus der Punktliste des Hauptprogramms verwendet.
        - Punkt-Z wird NICHT verwendet, weil die Punkt-Z-Koordinaten unzuverlaessig sein koennen.
        - Die LT-Markierhoehe wird aus der aktiven Markierebene der Transformation bestimmt.
        - Geprueft wird fuer die Reichweite vorerst nur X/Y gegen CONFIG.xyz.x_min/x_max/y_min/y_max.

    Die berechneten robot_z-Werte werden gespeichert und koennen geloggt werden, sind aber
    fuer reachable=True/False aktuell nicht entscheidend.
    """

    point_list = list(points)

    if trafo_manager is None or not bool(getattr(trafo_manager, "valid", False)):
        _debug(log, debug, "Reachability: keine gueltige Trafo")
        return [_result_for_unreachable(point, "keine gueltige Trafo") for point in point_list]

    if getattr(trafo_manager, "active_trafo", None) is None:
        _debug(log, debug, "Reachability: aktive Trafo fehlt")
        return [_result_for_unreachable(point, "aktive Trafo fehlt") for point in point_list]

    mapper = _build_coordinate_mapper(trafo_manager=trafo_manager, config=config)

    results: list[PointReachability] = []

    for point in point_list:
        name = _point_name(point)
        marked = bool(getattr(point, "marked", False))

        try:
            tracker_x = float(getattr(point, "x"))
            tracker_y = float(getattr(point, "y"))

            mapping = mapper.tracker_xy_to_robot_target(
                tracker_x=tracker_x,
                tracker_y=tracker_y,
            )

            robot = mapping.robot_target_point
            if robot is None:
                reason = mapping.message or "keine Roboterkoordinate berechnet"
                _debug(log, debug, f"Reachability {name}: NICHT erreichbar | {reason}")
                results.append(_result_for_unreachable(point, reason))
                continue

            robot_x = float(robot[0])
            robot_y = float(robot[1])
            robot_z = float(robot[2])

            reachable, reason = is_robot_xy_in_workspace(
                robot_x=robot_x,
                robot_y=robot_y,
                config=config,
            )

            if not reachable and not reason:
                reason = mapping.message or "Zielpunkt liegt ausserhalb des Arbeitsraums"

            _debug(
                log,
                debug,
                (
                    f"Reachability {name}: LT=({tracker_x:.3f}, {tracker_y:.3f}) -> "
                    f"Robot=({robot_x:.3f}, {robot_y:.3f}, {robot_z:.3f}) | "
                    f"reachable={reachable} | {reason}"
                ),
            )

            results.append(
                PointReachability(
                    point=point,
                    name=name,
                    reachable=reachable,
                    marked=marked,
                    robot_x=robot_x,
                    robot_y=robot_y,
                    robot_z=robot_z,
                    reason=reason,
                )
            )

        except Exception as exc:
            reason = f"Trafo-Fehler: {exc}"
            _debug(log, debug, f"Reachability {name}: FEHLER | {reason}")
            results.append(_result_for_unreachable(point, reason))

    return results


def apply_reachability_to_points(results: Iterable[PointReachability]) -> None:
    """Schreibt die berechneten Reichweiteninformationen zurueck in die Punktobjekte."""

    for result in results:
        point = result.point

        try:
            point.reachable = result.reachable
        except Exception:
            pass

        try:
            point.last_robot_x = result.robot_x
            point.last_robot_y = result.robot_y
            if hasattr(point, "last_robot_z"):
                point.last_robot_z = result.robot_z
        except Exception:
            pass

        try:
            point.residual_mm = None
        except Exception:
            pass


def reachable_points_only(results: Iterable[PointReachability]) -> list[PointReachability]:
    """Filtert auf aktuell markierbare Punkte im XY-Arbeitsraum."""

    return [result for result in results if result.reachable]


def project_point_to_robot_marker(*, point: Any, trafo_manager: Any, config: Any | None = None) -> np.ndarray:
    """Transformiert einen Projekt-/Trackerpunkt in eine Roboter-Zielkoordinate.

    Diese Hilfsfunktion nutzt bewusst nur Punkt-X/Y. Punkt-Z wird ignoriert.
    """

    if config is None:
        from config.mower_config import CONFIG as config  # lokale Import-Abhaengigkeit vermeiden

    mapper = _build_coordinate_mapper(trafo_manager=trafo_manager, config=config)
    mapping = mapper.tracker_xy_to_robot_target(
        tracker_x=float(getattr(point, "x")),
        tracker_y=float(getattr(point, "y")),
    )

    if mapping.robot_target_point is None:
        raise RuntimeError(mapping.message or "keine Roboterkoordinate berechnet")

    return np.asarray(mapping.robot_target_point, dtype=float)


def is_robot_xy_in_workspace(
        *,
        robot_x: float,
        robot_y: float,
        config: Any,
) -> tuple[bool, str]:
    """Prueft eine Roboterkoordinate nur gegen den konfigurierten XY-Arbeitsraum."""

    xyz = getattr(config, "xyz")

    x_min = float(getattr(xyz, "x_min"))
    x_max = float(getattr(xyz, "x_max"))
    y_min = float(getattr(xyz, "y_min"))
    y_max = float(getattr(xyz, "y_max"))

    if not (x_min <= robot_x <= x_max):
        return False, f"X ausserhalb Arbeitsraum: {robot_x:.3f} nicht in [{x_min:.3f}, {x_max:.3f}]"

    if not (y_min <= robot_y <= y_max):
        return False, f"Y ausserhalb Arbeitsraum: {robot_y:.3f} nicht in [{y_min:.3f}, {y_max:.3f}]"

    return True, ""


def is_robot_point_in_workspace(
        *,
        robot_x: float,
        robot_y: float,
        robot_z: float | None = None,
        config: Any,
) -> tuple[bool, str]:
    """Rueckwaertskompatibler Alias: aktuell wird nur X/Y geprueft."""

    return is_robot_xy_in_workspace(robot_x=robot_x, robot_y=robot_y, config=config)


def _build_coordinate_mapper(*, trafo_manager: Any, config: Any) -> Any:
    if CoordinateMapper is None or RobotWorkspace is None:
        raise RuntimeError("CoordinateMapper konnte nicht importiert werden.")

    xyz = getattr(config, "xyz")
    workspace = RobotWorkspace(
        x_min=float(getattr(xyz, "x_min")),
        x_max=float(getattr(xyz, "x_max")),
        y_min=float(getattr(xyz, "y_min")),
        y_max=float(getattr(xyz, "y_max")),
    )

    return CoordinateMapper(
        trafo_manager=trafo_manager,
        workspace=workspace,
    )


def _result_for_unreachable(point: Any, reason: str) -> PointReachability:
    return PointReachability(
        point=point,
        name=_point_name(point),
        reachable=False,
        marked=bool(getattr(point, "marked", False)),
        reason=reason,
    )


def _point_name(point: Any) -> str:
    return str(getattr(point, "name", "<ohne Name>"))


def _debug(log: LogFunction | None, debug: bool, text: str) -> None:
    if debug and log is not None:
        log(text)

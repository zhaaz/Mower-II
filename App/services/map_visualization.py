from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class MapVisualizationState:
    """Geometrie fuer die Kartenansicht im Tracker-/Projektkoordinatensystem."""

    workspace_polygon: list[tuple[float, float]] | None = None
    wagon_outline_polygon: list[tuple[float, float]] | None = None
    front_arrow: tuple[tuple[float, float], tuple[float, float]] | None = None
    reflector_position: tuple[float, float] | None = None
    marker_position: tuple[float, float] | None = None
    message: str = ""


def build_map_visualization_state(
        *,
        trafo_manager: Any,
        config: Any,
        xyz_state: Any | None = None,
        live_reflector_lt_xyz: tuple[float, float, float] | None = None,
        live_orientation_lt_deg: float | None = None,
) -> MapVisualizationState:
    """Berechnet Markierbereich, Frontpfeil und aktuelle Werkzeugpunkte fuer die Karte.

    Grundlogik:
        - Ohne Live-Pose wird wie bisher die aktive Transformation verwendet.
        - Mit Live-Pose wird nur die Kartenvisualisierung aktualisiert:
          aktuelle Tracker-Reflektormessung + KVH-orientierte Wagenrichtung.
        - Die eigentliche Transformation und Markierlogik werden dadurch nicht veraendert.

    Annahmen:
        - +X im Robotersystem ist vorne.
        - X=0/Y=0 liegt hinten rechts.
        - Der innere Rahmen ist der Markierbereich des Werkzeugs.
        - marker_to_reflector_robot = reflector_robot - marker_robot.
    """

    if config is None:
        return MapVisualizationState(message="CONFIG fehlt.")

    if trafo_manager is None or not bool(getattr(trafo_manager, "valid", False)):
        return MapVisualizationState(message="Keine gueltige Transformation.")

    trafo = getattr(trafo_manager, "active_trafo", None)
    if trafo is None:
        return MapVisualizationState(message="Aktive Transformation fehlt.")

    xyz = getattr(config, "xyz")
    x_min = float(getattr(xyz, "x_min"))
    x_max = float(getattr(xyz, "x_max"))
    y_min = float(getattr(xyz, "y_min"))
    y_max = float(getattr(xyz, "y_max"))

    z_plane = _visualization_z(config=config, xyz_state=xyz_state)
    marker_to_reflector = _marker_to_reflector_robot(trafo_manager, config)
    if marker_to_reflector is None:
        marker_to_reflector = np.zeros(3, dtype=float)

    reflector_corners = [
        np.array([x_min, y_min, z_plane], dtype=float),  # hinten rechts
        np.array([x_max, y_min, z_plane], dtype=float),  # vorne rechts
        np.array([x_max, y_max, z_plane], dtype=float),  # vorne links
        np.array([x_min, y_max, z_plane], dtype=float),  # hinten links
    ]
    marker_corners = [corner - marker_to_reflector for corner in reflector_corners]

    wagon_reflector_corners = [
        np.array([x_min - 400.0, y_min - 50.0, z_plane], dtype=float),
        np.array([x_max + 50.0, y_min - 50.0, z_plane], dtype=float),
        np.array([x_max + 50.0, y_max + 50.0, z_plane], dtype=float),
        np.array([x_min - 400.0, y_max + 50.0, z_plane], dtype=float),
    ]
    wagon_marker_corners = [corner - marker_to_reflector for corner in wagon_reflector_corners]

    try:
        pose = _build_live_pose(
            trafo=trafo,
            xyz_state=xyz_state,
            live_reflector_lt_xyz=live_reflector_lt_xyz,
            live_orientation_lt_deg=live_orientation_lt_deg,
        )

        to_tracker_xy = pose.robot_to_tracker_xy if pose is not None else lambda point: _robot_to_tracker_xy(trafo, point)

        workspace_polygon = [to_tracker_xy(corner) for corner in marker_corners]
        wagon_outline_polygon = [to_tracker_xy(corner) for corner in wagon_marker_corners]

        center_y = (y_min + y_max) / 2.0
        front_margin_mm = 50.0
        arrow_start_reflector = np.array([x_max + front_margin_mm * 0.15, center_y, z_plane], dtype=float)
        arrow_end_reflector = np.array([x_max + front_margin_mm * 0.85, center_y, z_plane], dtype=float)
        arrow_start_marker = arrow_start_reflector - marker_to_reflector
        arrow_end_marker = arrow_end_reflector - marker_to_reflector
        front_arrow = (
            to_tracker_xy(arrow_start_marker),
            to_tracker_xy(arrow_end_marker),
        )

        reflector_position = None
        marker_position = None

        reflector_robot = _current_reflector_robot(xyz_state)
        if reflector_robot is not None:
            if pose is not None:
                reflector_position = (float(pose.anchor_tracker_xy[0]), float(pose.anchor_tracker_xy[1]))
            else:
                reflector_position = _robot_to_tracker_xy(trafo, reflector_robot)

            marker_robot = np.asarray(reflector_robot, dtype=float) - marker_to_reflector
            marker_position = to_tracker_xy(marker_robot)

        return MapVisualizationState(
            workspace_polygon=workspace_polygon,
            wagon_outline_polygon=wagon_outline_polygon,
            front_arrow=front_arrow,
            reflector_position=reflector_position,
            marker_position=marker_position,
            message="OK live" if pose is not None else "OK",
        )

    except Exception as exc:
        return MapVisualizationState(message=f"Kartenvisualisierung konnte nicht berechnet werden: {exc}")


@dataclass(frozen=True)
class _LivePose2D:
    anchor_robot_xy: np.ndarray
    anchor_tracker_xy: np.ndarray
    rotation_2d: np.ndarray

    def robot_to_tracker_xy(self, robot_point: Any) -> tuple[float, float]:
        p = np.asarray(robot_point, dtype=float).reshape(3)
        delta_robot_xy = p[:2] - self.anchor_robot_xy
        tracker_xy = self.anchor_tracker_xy + self.rotation_2d @ delta_robot_xy
        return float(tracker_xy[0]), float(tracker_xy[1])


def _build_live_pose(
        *,
        trafo: Any,
        xyz_state: Any | None,
        live_reflector_lt_xyz: tuple[float, float, float] | None,
        live_orientation_lt_deg: float | None,
) -> _LivePose2D | None:
    """Erzeugt eine 2D-Live-Pose fuer die Kartenansicht.

    Die Pose ankert die aktuelle Roboter-Reflektorposition an der aktuellen
    Tracker-Reflektormessung und verwendet die KVH-basierte Orientierung fuer
    die XY-Rotation.
    """

    if live_reflector_lt_xyz is None or live_orientation_lt_deg is None:
        return None

    reflector_robot = _current_reflector_robot(xyz_state)
    if reflector_robot is None:
        return None

    try:
        anchor_tracker_xy = np.asarray(live_reflector_lt_xyz, dtype=float).reshape(3)[:2]
        anchor_robot_xy = np.asarray(reflector_robot, dtype=float).reshape(3)[:2]
        angle = math.radians(float(live_orientation_lt_deg))
    except Exception:
        return None

    # Die Orientierung beschreibt die Richtung der Roboter-+X-Achse im LT-XY-System.
    c = math.cos(angle)
    s = math.sin(angle)
    rotation_2d = np.array([
        [c, -s],
        [s, c],
    ], dtype=float)

    # Bei stark abweichendem Trafo-Massstab waere die Live-Pose fuer die Karte
    # bewusst trotzdem massstabstreu im Millimeterraum. Die Helmert-Skalierung
    # bleibt der eigentlichen Transformation vorbehalten.
    _ = trafo

    return _LivePose2D(
        anchor_robot_xy=anchor_robot_xy,
        anchor_tracker_xy=anchor_tracker_xy,
        rotation_2d=rotation_2d,
    )


def _visualization_z(*, config: Any, xyz_state: Any | None) -> float:
    """Z-Ebene fuer die XY-Rahmenvisualisierung."""

    if xyz_state is not None:
        z = getattr(xyz_state, "z", None)
        if z is not None:
            try:
                return float(z)
            except Exception:
                pass

    marker = getattr(config, "marker", None)
    if marker is not None:
        z_mark = getattr(marker, "z_mark_mm", None)
        if z_mark is not None:
            try:
                return float(z_mark)
            except Exception:
                pass

    return 0.0


def _current_reflector_robot(xyz_state: Any | None) -> np.ndarray | None:
    if xyz_state is None:
        return None

    x = getattr(xyz_state, "x", None)
    y = getattr(xyz_state, "y", None)
    z = getattr(xyz_state, "z", None)

    if x is None or y is None or z is None:
        return None

    return np.array([float(x), float(y), float(z)], dtype=float)


def _marker_to_reflector_robot(trafo_manager: Any, config: Any) -> np.ndarray | None:
    value = getattr(trafo_manager, "marker_to_reflector_robot", None)

    if value is None:
        transformation = getattr(config, "transformation", None)
        value = getattr(transformation, "marker_to_reflector_robot", None)

    if value is None:
        return None

    arr = np.asarray(value, dtype=float).reshape(3)
    return arr


def _robot_to_tracker_xy(trafo: Any, robot_point: Any) -> tuple[float, float]:
    tracker_point = trafo.robot_to_tracker(robot_point)
    return float(tracker_point[0]), float(tracker_point[1])

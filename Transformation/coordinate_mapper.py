# Transformation/coordinate_mapper.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np


@dataclass
class RobotWorkspace:
    x_min: float
    x_max: float
    y_min: float
    y_max: float

    def contains_xy(
        self,
        x: float,
        y: float,
    ) -> bool:
        return (
            self.x_min <= x <= self.x_max
            and self.y_min <= y <= self.y_max
        )


@dataclass
class CoordinateMappingResult:
    success: bool
    message: str

    tracker_marker_point: Optional[np.ndarray] = None
    tracker_reflector_point: Optional[np.ndarray] = None

    robot_target_point: Optional[np.ndarray] = None

    inside_workspace: bool = False


class CoordinateMapper:
    def __init__(
        self,
        trafo_manager,
        workspace: RobotWorkspace,
    ):
        self.trafo_manager = trafo_manager
        self.workspace = workspace

    def tracker_xy_to_robot_target(
        self,
        tracker_x: float,
        tracker_y: float,
    ) -> CoordinateMappingResult:
        """
        Wandelt einen LT-X/Y-Markierpunkt in ein Roboterziel um.

        Ablauf:
        1. LT-Z auf Markierebene bestimmen
        2. Reflektorpunkt berechnen
        3. inverse Trafo
        4. Arbeitsraumprüfung
        """

        if not self.trafo_manager.valid:
            return CoordinateMappingResult(
                success=False,
                message="Keine gültige Transformation vorhanden.",
            )

        trafo = self.trafo_manager.active_trafo
        marker_plane_lt = self.trafo_manager.marker_plane_lt
        marker_to_reflector_lt = (
            self.trafo_manager.marker_to_reflector_lt
        )

        if marker_plane_lt is None:
            return CoordinateMappingResult(
                success=False,
                message="Keine Markierebene vorhanden.",
            )

        if marker_to_reflector_lt is None:
            return CoordinateMappingResult(
                success=False,
                message="Kein Werkzeugoffset vorhanden.",
            )

        # ----------------------------------------------------
        # 1. LT-Z auf Markierebene bestimmen
        # ----------------------------------------------------

        marker_z = marker_plane_lt.z_at_xy(
            x=tracker_x,
            y=tracker_y,
        )

        tracker_marker_point = np.array([
            tracker_x,
            tracker_y,
            marker_z,
        ], dtype=float)

        # ----------------------------------------------------
        # 2. Reflektor-Sollpunkt berechnen
        # ----------------------------------------------------

        tracker_reflector_point = (
            tracker_marker_point
            + marker_to_reflector_lt
        )

        # ----------------------------------------------------
        # 3. inverse Trafo
        # ----------------------------------------------------

        robot_target_point = trafo.tracker_to_robot(
            tracker_reflector_point
        )

        robot_x = float(robot_target_point[0])
        robot_y = float(robot_target_point[1])

        # ----------------------------------------------------
        # 4. Arbeitsraumprüfung
        # ----------------------------------------------------

        inside_workspace = self.workspace.contains_xy(
            x=robot_x,
            y=robot_y,
        )

        if not inside_workspace:
            return CoordinateMappingResult(
                success=False,
                message=(
                    "Zielpunkt liegt außerhalb des Roboterarbeitsraums."
                ),
                tracker_marker_point=tracker_marker_point,
                tracker_reflector_point=tracker_reflector_point,
                robot_target_point=robot_target_point,
                inside_workspace=False,
            )

        return CoordinateMappingResult(
            success=True,
            message="Koordinaten erfolgreich umgerechnet.",
            tracker_marker_point=tracker_marker_point,
            tracker_reflector_point=tracker_reflector_point,
            robot_target_point=robot_target_point,
            inside_workspace=True,
        )
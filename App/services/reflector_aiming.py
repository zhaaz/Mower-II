from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class Point2D:
    x: float
    y: float


@dataclass(frozen=True)
class ReflectorAimConfig:
    """
    Configuration for the reflector aiming calculation.

    Coordinate convention:
      - LT coordinates: lasertracker/station coordinate system.
      - Robot coordinates: wagon coordinate system, +X = forward, +Y = left/right depending project convention.
      - orientation_lt_deg: direction of robot +X axis in LT coordinates.

    gyems_zero_offset_deg:
      Motor angle that corresponds to bearing_robot_deg = 0 deg.

    gyems_direction_sign:
      +1 if increasing motor angle rotates in positive robot bearing direction.
      -1 if the motor rotates opposite to positive robot bearing direction.

    pivot_from_reflector_robot_mm:
      Offset from measured reflector point to GYEMS rotation/pivot point in robot coordinates.
      Use (0, 0) for first tests if pivot and measured reflector point are close enough.
    """

    gyems_zero_offset_deg: float = 0.0
    gyems_direction_sign: float = 1.0
    pivot_from_reflector_robot_mm: Point2D = Point2D(0.0, 0.0)


@dataclass(frozen=True)
class ReflectorAimResult:
    tracker_station_lt: Point2D
    reflector_lt: Point2D
    pivot_lt: Point2D
    orientation_lt_deg: float
    vector_to_tracker_lt: Point2D
    vector_to_tracker_robot: Point2D
    bearing_robot_deg: float
    gyems_target_deg: float
    gyems_angle_deg: Optional[float]
    gyems_error_deg: Optional[float]
    distance_to_tracker_mm: float


def normalize_360(angle_deg: float) -> float:
    return angle_deg % 360.0


def normalize_180(angle_deg: float) -> float:
    return (angle_deg + 180.0) % 360.0 - 180.0


def rotate_robot_to_lt(point_robot: Point2D, orientation_lt_deg: float) -> Point2D:
    """Rotate a robot-frame 2D vector into the LT frame."""
    a = math.radians(orientation_lt_deg)
    ca = math.cos(a)
    sa = math.sin(a)
    return Point2D(
        x=ca * point_robot.x - sa * point_robot.y,
        y=sa * point_robot.x + ca * point_robot.y,
    )


def rotate_lt_to_robot(vector_lt: Point2D, orientation_lt_deg: float) -> Point2D:
    """Rotate an LT-frame 2D vector into the robot frame."""
    a = math.radians(orientation_lt_deg)
    ca = math.cos(a)
    sa = math.sin(a)
    # inverse rotation = transpose of R
    return Point2D(
        x=ca * vector_lt.x + sa * vector_lt.y,
        y=-sa * vector_lt.x + ca * vector_lt.y,
    )


class ReflectorAimCalculator:
    def __init__(self, config: ReflectorAimConfig | None = None):
        self.config = config or ReflectorAimConfig()

    def calculate(
        self,
        *,
        tracker_station_lt: Tuple[float, float] | Point2D = Point2D(0.0, 0.0),
        reflector_lt: Tuple[float, float] | Point2D,
        orientation_lt_deg: float,
        gyems_angle_deg: float | None = None,
    ) -> ReflectorAimResult:
        """
        Calculate the desired GYEMS angle for reflector tracking.

        The desired direction is the bearing from the reflector/pivot point to the
        lasertracker station, expressed in the current robot/wagon coordinate system.
        """
        station = _as_point2d(tracker_station_lt)
        reflector = _as_point2d(reflector_lt)

        pivot_offset_lt = rotate_robot_to_lt(
            self.config.pivot_from_reflector_robot_mm,
            orientation_lt_deg,
        )
        pivot_lt = Point2D(
            x=reflector.x + pivot_offset_lt.x,
            y=reflector.y + pivot_offset_lt.y,
        )

        vec_lt = Point2D(
            x=station.x - pivot_lt.x,
            y=station.y - pivot_lt.y,
        )
        distance = math.hypot(vec_lt.x, vec_lt.y)
        if distance < 1e-9:
            raise ValueError("Tracker station and reflector pivot are identical; direction is undefined.")

        vec_robot = rotate_lt_to_robot(vec_lt, orientation_lt_deg)
        bearing_robot_deg = normalize_360(math.degrees(math.atan2(vec_robot.y, vec_robot.x)))

        target = normalize_360(
            self.config.gyems_zero_offset_deg
            + self.config.gyems_direction_sign * bearing_robot_deg
        )

        err = None
        if gyems_angle_deg is not None:
            err = normalize_180(target - gyems_angle_deg)

        return ReflectorAimResult(
            tracker_station_lt=station,
            reflector_lt=reflector,
            pivot_lt=pivot_lt,
            orientation_lt_deg=normalize_360(orientation_lt_deg),
            vector_to_tracker_lt=vec_lt,
            vector_to_tracker_robot=vec_robot,
            bearing_robot_deg=bearing_robot_deg,
            gyems_target_deg=target,
            gyems_angle_deg=gyems_angle_deg,
            gyems_error_deg=err,
            distance_to_tracker_mm=distance,
        )


def _as_point2d(value: Tuple[float, float] | Point2D) -> Point2D:
    if isinstance(value, Point2D):
        return value
    return Point2D(float(value[0]), float(value[1]))


if __name__ == "__main__":
    calc = ReflectorAimCalculator(
        ReflectorAimConfig(
            gyems_zero_offset_deg=0.0,
            gyems_direction_sign=1.0,
            pivot_from_reflector_robot_mm=Point2D(0.0, 0.0),
        )
    )

    result = calc.calculate(
        tracker_station_lt=(0.0, 0.0),
        reflector_lt=(1500.0, 1000.0),
        orientation_lt_deg=30.0,
        gyems_angle_deg=120.0,
    )

    print(f"Bearing robot:  {result.bearing_robot_deg:8.3f} deg")
    print(f"GYEMS target:   {result.gyems_target_deg:8.3f} deg")
    print(f"GYEMS error:    {result.gyems_error_deg:8.3f} deg")
    print(f"Distance:       {result.distance_to_tracker_mm:8.1f} mm")

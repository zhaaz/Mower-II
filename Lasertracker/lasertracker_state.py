# lasertracker_state.py

from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
import math


@dataclass
class TrackerMeasurement:
    timestamp: float
    x: float
    y: float
    z: float
    unit: str = "unknown"
    raw: str = ""


@dataclass
class LasertrackerState:
    receiving: bool = False
    data_valid: bool = False
    stale: bool = True
    stable: bool = False

    x: float | None = None
    y: float | None = None
    z: float | None = None
    unit: str = "unknown"

    last_measurement_timestamp: float | None = None
    data_age_seconds: float | None = None
    measurement_count: int = 0

    stale_threshold_seconds: float = 3.0
    stable_threshold_mm: float = 0.1
    stable_required_count: int = 3

    recent_measurements: deque[TrackerMeasurement] = field(
        default_factory=lambda: deque(maxlen=20)
    )

    def update_measurement(self, measurement: TrackerMeasurement) -> None:
        self.receiving = True
        self.data_valid = True
        self.stale = False

        self.x = measurement.x
        self.y = measurement.y
        self.z = measurement.z
        self.unit = measurement.unit

        self.last_measurement_timestamp = measurement.timestamp
        self.data_age_seconds = 0.0
        self.measurement_count += 1

        self.recent_measurements.append(measurement)
        self.stable = self._calculate_stable()

    def update_age(self, now_timestamp: float) -> None:
        if self.last_measurement_timestamp is None:
            self.data_age_seconds = None
            self.stale = True
            self.stable = False
            return

        self.data_age_seconds = now_timestamp - self.last_measurement_timestamp
        self.stale = self.data_age_seconds > self.stale_threshold_seconds

        if self.stale:
            self.receiving = False
            self.stable = False

    def _calculate_stable(self) -> bool:
        if len(self.recent_measurements) < self.stable_required_count:
            return False

        points = list(self.recent_measurements)[-self.stable_required_count:]
        return self.points_are_stable(points)

    def points_are_stable(self, points: list[TrackerMeasurement]) -> bool:
        if len(points) < self.stable_required_count:
            return False

        xs = [p.x for p in points]
        ys = [p.y for p in points]
        zs = [p.z for p in points]

        mean_x = sum(xs) / len(xs)
        mean_y = sum(ys) / len(ys)
        mean_z = sum(zs) / len(zs)

        max_distance = 0.0

        for p in points:
            distance = math.sqrt(
                (p.x - mean_x) ** 2 +
                (p.y - mean_y) ** 2 +
                (p.z - mean_z) ** 2
            )
            max_distance = max(max_distance, distance)

        return max_distance <= self.stable_threshold_mm

    def clear(self) -> None:
        self.receiving = False
        self.data_valid = False
        self.stale = True
        self.stable = False

        self.x = None
        self.y = None
        self.z = None
        self.unit = "unknown"

        self.last_measurement_timestamp = None
        self.data_age_seconds = None
        self.measurement_count = 0
        self.recent_measurements.clear()
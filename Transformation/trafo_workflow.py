# Transformation/trafo_workflow.py

from __future__ import annotations

import time
import random
import math
import threading
from dataclasses import dataclass, field
from itertools import combinations
from typing import Callable, Optional, Any

from Transformation.helmert_3d import estimate_helmert_3d


@dataclass
class TrafoWorkflowConfig:
    base_points: list[tuple[str, float, float]] = field(default_factory=lambda: [
        ("K1", 100.0, 100.0),
        ("K2", 100.0, 350.0),
        ("K3", 350.0, 350.0),
        ("K4", 400.0, 100.0),
        ("K5", 200.0, 200.0),
    ])

    random_radius_mm: float = 50.0
    random_seed: Optional[int] = None

    xyz_feedrate: float = 6000.0
    xyz_position_tolerance_mm: float = 0.05
    xyz_position_timeout_s: float = 60.0

    tracker_capture_timeout_s: float = 10.0

    allow_scale: bool = True
    min_geometry_rank: int = 2

    minimum_required_measurements: int = 4

    max_allowed_rms_mm: float = 0.10
    max_allowed_max_residual_mm: float = 0.15


@dataclass
class TrafoWorkflowResult:
    success: bool
    status: str
    message: str

    trafo: Optional[Any] = None
    measurements: list[dict] = field(default_factory=list)
    used_measurements: list[dict] = field(default_factory=list)
    failed_measurements: list[dict] = field(default_factory=list)
    excluded_measurement: Optional[dict] = None
    candidate_results: list[dict] = field(default_factory=list)

    duration_s: float = 0.0
    error: str = ""


class TrafoCancelledError(Exception):
    pass


class TrafoWorkflow:
    def __init__(
        self,
        xyz_worker,
        tracker_receiver,
        xyz_state_getter: Callable[[], Any],
        config: Optional[TrafoWorkflowConfig] = None,
        on_status: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
    ):
        self.xyz_worker = xyz_worker
        self.tracker_receiver = tracker_receiver
        self.xyz_state_getter = xyz_state_getter
        self.config = config or TrafoWorkflowConfig()

        self.on_status = on_status
        self.on_progress = on_progress
        self.on_log = on_log

        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self) -> TrafoWorkflowResult:
        start_time = time.time()

        measurements = []
        failed_measurements = []

        try:
            self._check_cancelled()

            if self.config.random_seed is not None:
                random.seed(self.config.random_seed)

            target_points = self._generate_target_points()
            total_steps = len(target_points)

            self._status("Starte Transformation.")
            self._log("Zielpunkte:")

            for name, x, y in target_points:
                self._log(f"  {name}: X={x:.3f}, Y={y:.3f}")

            for index, (point_name, x, y) in enumerate(target_points, start=1):
                self._check_cancelled()
                self._progress(index, total_steps, f"{point_name}: fahre Punkt an")

                try:
                    measurement = self._move_to_position_and_capture(
                        point_name=point_name,
                        target_x=x,
                        target_y=y,
                    )
                    measurements.append(measurement)

                except TimeoutError as exc:
                    failed = {
                        "name": point_name,
                        "robot_target_x": x,
                        "robot_target_y": y,
                        "reason": str(exc),
                    }

                    failed_measurements.append(failed)

                    self._status(f"{point_name}: kein stabiler Trackerpunkt.")
                    self._log(f"WARNUNG {point_name}: {exc}")
                    self._log("Fahre mit nächstem Punkt fort.")

                    continue

            if len(measurements) < self.config.minimum_required_measurements:
                duration_s = time.time() - start_time

                message = (
                    f"Transformation ungültig. "
                    f"Nur {len(measurements)}/{len(target_points)} Punkte messbar. "
                    f"Mindestens erforderlich: "
                    f"{self.config.minimum_required_measurements}."
                )

                self._status(message)

                return TrafoWorkflowResult(
                    success=False,
                    status="INVALID_NOT_ENOUGH_POINTS",
                    message=message,
                    measurements=measurements,
                    used_measurements=[],
                    failed_measurements=failed_measurements,
                    duration_s=duration_s,
                )

            self._status("Berechne Transformation.")

            assessment = self._calculate_best_transformation_with_outlier_check(
                measurements
            )

            duration_s = time.time() - start_time
            success = assessment["status"].startswith("OK_")

            result = TrafoWorkflowResult(
                success=success,
                status=assessment["status"],
                message=assessment["message"],
                trafo=assessment["trafo"],
                measurements=measurements,
                used_measurements=assessment["used_measurements"],
                failed_measurements=failed_measurements,
                excluded_measurement=assessment["excluded_measurement"],
                candidate_results=assessment["candidate_results"],
                duration_s=duration_s,
            )

            if success:
                self._status("Transformation erfolgreich berechnet.")
            else:
                self._status("Transformation ungültig.")

            return result

        except TrafoCancelledError:
            duration_s = time.time() - start_time
            self._status("Transformation abgebrochen.")

            return TrafoWorkflowResult(
                success=False,
                status="CANCELLED",
                message="Transformation wurde abgebrochen.",
                measurements=measurements,
                used_measurements=[],
                failed_measurements=failed_measurements,
                duration_s=duration_s,
            )

        except Exception as exc:
            duration_s = time.time() - start_time
            self._status("Transformation fehlgeschlagen.")

            return TrafoWorkflowResult(
                success=False,
                status="ERROR",
                message="Transformation fehlgeschlagen.",
                measurements=measurements,
                used_measurements=[],
                failed_measurements=failed_measurements,
                duration_s=duration_s,
                error=str(exc),
            )

    def _generate_target_points(self) -> list[tuple[str, float, float]]:
        points = []

        for name, center_x, center_y in self.config.base_points:
            x, y = self._random_point_in_radius(
                center_x=center_x,
                center_y=center_y,
                radius_mm=self.config.random_radius_mm,
            )
            points.append((name, x, y))

        return points

    @staticmethod
    def _random_point_in_radius(
        center_x: float,
        center_y: float,
        radius_mm: float,
    ) -> tuple[float, float]:
        angle = random.uniform(0.0, 2.0 * math.pi)
        radius = radius_mm * math.sqrt(random.uniform(0.0, 1.0))

        return (
            center_x + radius * math.cos(angle),
            center_y + radius * math.sin(angle),
        )

    def _move_to_position_and_capture(
        self,
        point_name: str,
        target_x: float,
        target_y: float,
    ) -> dict:
        self._check_cancelled()

        self._status(f"{point_name}: fahre X={target_x:.3f}, Y={target_y:.3f}")

        self.xyz_worker.send_command(
            "move_absolute_verified",
            x=target_x,
            y=target_y,
            z=None,
            feedrate=self.config.xyz_feedrate,
        )

        self._wait_for_xyz_position(
            target_x=target_x,
            target_y=target_y,
            tolerance_mm=self.config.xyz_position_tolerance_mm,
            timeout_s=self.config.xyz_position_timeout_s,
        )

        self._check_cancelled()

        xyz_state = self.xyz_state_getter()
        robot_z = xyz_state.z if xyz_state.z is not None else 0.0

        self._status(
            f"{point_name}: warte max. "
            f"{self.config.tracker_capture_timeout_s:.1f} s "
            f"auf stabilen Trackerpunkt."
        )

        try:
            measurement = self.tracker_receiver.capture_stable_point(
                timeout_s=self.config.tracker_capture_timeout_s,
                min_age_after_start_s=0.0,
            )
        except TimeoutError as exc:
            raise TimeoutError(
                f"Kein stabiler Trackerpunkt für {point_name}: {exc}"
            ) from exc

        self._check_cancelled()

        self._log(
            f"{point_name}: "
            f"Robot=({xyz_state.x:.3f}, {xyz_state.y:.3f}, {robot_z:.3f}) | "
            f"Tracker=({measurement.x:.3f}, {measurement.y:.3f}, {measurement.z:.3f})"
        )

        return {
            "name": point_name,

            "robot_target_x": target_x,
            "robot_target_y": target_y,

            "robot_actual_x": xyz_state.x,
            "robot_actual_y": xyz_state.y,
            "robot_actual_z": robot_z,

            "tracker_x": measurement.x,
            "tracker_y": measurement.y,
            "tracker_z": measurement.z,

            "tracker_unit": measurement.unit,
            "tracker_timestamp": measurement.timestamp,
        }

    def _wait_for_xyz_position(
        self,
        target_x: float,
        target_y: float,
        tolerance_mm: float,
        timeout_s: float,
    ):
        start = time.time()

        while time.time() - start < timeout_s:
            self._check_cancelled()

            state = self.xyz_state_getter()

            if (
                not state.busy
                and state.x is not None
                and state.y is not None
            ):
                dx = state.x - target_x
                dy = state.y - target_y

                if abs(dx) <= tolerance_mm and abs(dy) <= tolerance_mm:
                    return

            time.sleep(0.05)

        state = self.xyz_state_getter()

        raise TimeoutError(
            f"XYZ-Zielposition nicht erreicht: "
            f"Soll=({target_x:.3f}, {target_y:.3f}), "
            f"Ist=({state.x}, {state.y})"
        )

    def _calculate_transformation(self, measurements: list[dict]):
        robot_points = []
        tracker_points = []

        for m in measurements:
            robot_points.append([
                m["robot_actual_x"],
                m["robot_actual_y"],
                m["robot_actual_z"],
            ])

            tracker_points.append([
                m["tracker_x"],
                m["tracker_y"],
                m["tracker_z"],
            ])

        return estimate_helmert_3d(
            robot_points=robot_points,
            tracker_points=tracker_points,
            allow_scale=self.config.allow_scale,
            min_geometry_rank=self.config.min_geometry_rank,
        )

    def _is_trafo_ok(self, trafo) -> bool:
        return (
            trafo.rms <= self.config.max_allowed_rms_mm
            and trafo.max_residual <= self.config.max_allowed_max_residual_mm
        )

    def _calculate_best_transformation_with_outlier_check(
        self,
        measurements: list[dict],
    ) -> dict:
        point_count = len(measurements)

        if point_count < self.config.minimum_required_measurements:
            return {
                "status": "INVALID_NOT_ENOUGH_POINTS",
                "message": (
                    f"Nicht genug messbare Punkte: {point_count}. "
                    f"Mindestens erforderlich: "
                    f"{self.config.minimum_required_measurements}."
                ),
                "trafo": None,
                "used_measurements": [],
                "excluded_measurement": None,
                "candidate_results": [],
            }

        trafo_all = self._calculate_transformation(measurements)

        if self._is_trafo_ok(trafo_all):
            return {
                "status": f"OK_{point_count}_POINTS",
                "message": f"Trafo OK mit {point_count} Punkten.",
                "trafo": trafo_all,
                "used_measurements": measurements,
                "excluded_measurement": None,
                "candidate_results": [],
            }

        if point_count <= self.config.minimum_required_measurements:
            return {
                "status": "INVALID",
                "message": (
                    f"Trafo mit {point_count} Punkten erfüllt die "
                    f"Schwellwerte nicht und es sind keine weiteren Punkte "
                    f"zum Ausschluss verfügbar."
                ),
                "trafo": trafo_all,
                "used_measurements": measurements,
                "excluded_measurement": None,
                "candidate_results": [],
            }

        candidate_results = []

        for used_indices in combinations(
            range(point_count),
            self.config.minimum_required_measurements,
        ):
            used_indices = list(used_indices)
            used_measurements = [measurements[i] for i in used_indices]

            excluded_indices = [
                i for i in range(point_count)
                if i not in used_indices
            ]

            excluded_measurement = (
                measurements[excluded_indices[0]]
                if len(excluded_indices) == 1
                else None
            )

            excluded_names = [
                measurements[i]["name"]
                for i in excluded_indices
            ]

            try:
                candidate_trafo = self._calculate_transformation(
                    used_measurements
                )

                candidate_results.append({
                    "used_indices": used_indices,
                    "excluded_measurement": excluded_measurement,
                    "excluded_names": excluded_names,
                    "trafo": candidate_trafo,
                    "ok": self._is_trafo_ok(candidate_trafo),
                    "error": None,
                })

            except Exception as exc:
                candidate_results.append({
                    "used_indices": used_indices,
                    "excluded_measurement": excluded_measurement,
                    "excluded_names": excluded_names,
                    "trafo": None,
                    "ok": False,
                    "error": str(exc),
                })

        valid_candidates = [
            c for c in candidate_results
            if c["ok"] and c["trafo"] is not None
        ]

        if valid_candidates:
            best_candidate = min(
                valid_candidates,
                key=lambda c: (
                    c["trafo"].rms,
                    c["trafo"].max_residual,
                ),
            )

            excluded_text = ", ".join(best_candidate["excluded_names"])

            return {
                "status": (
                    f"OK_{self.config.minimum_required_measurements}_POINTS"
                ),
                "message": (
                    f"Trafo OK mit "
                    f"{self.config.minimum_required_measurements} Punkten. "
                    f"Ausgeschlossene Punkte: {excluded_text}."
                ),
                "trafo": best_candidate["trafo"],
                "used_measurements": [
                    measurements[i]
                    for i in best_candidate["used_indices"]
                ],
                "excluded_measurement": best_candidate["excluded_measurement"],
                "candidate_results": candidate_results,
            }

        return {
            "status": "INVALID",
            "message": (
                "Trafo ungültig. Keine Punktkombination erfüllt die Schwellwerte."
            ),
            "trafo": trafo_all,
            "used_measurements": measurements,
            "excluded_measurement": None,
            "candidate_results": candidate_results,
        }

    def _check_cancelled(self):
        if self.cancel_event.is_set():
            raise TrafoCancelledError()

    def _status(self, text: str):
        if self.on_status:
            self.on_status(text)

    def _progress(self, current: int, total: int, label: str):
        if self.on_progress:
            self.on_progress(current, total, label)

    def _log(self, text: str):
        if self.on_log:
            self.on_log(text)
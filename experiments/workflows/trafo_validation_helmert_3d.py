# workflows/trafo_validation_helmert_3d.py

import sys
from pathlib import Path
import time
import random
import math
import csv
from datetime import datetime
from itertools import combinations

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from XYZ_Robot.xyz_robot_worker import XYZRobotWorker
from XYZ_Robot.xyz_robot_state import XYZRobotState

from Lasertracker.lasertracker_receiver import LasertrackerReceiver
from Lasertracker.lasertracker_state import LasertrackerState, TrackerMeasurement

from Transformation.helmert_3d import estimate_helmert_3d


# ============================================================
# KONFIGURATION
# ============================================================

XYZ_PORT = "COM5"
XYZ_BAUDRATE = 115200
TRACKER_UDP_PORT = 10000

NUMBER_OF_RUNS = 10

BASE_POINTS = [
    ("K1", 100.0, 100.0),
    ("K2", 100.0, 350.0),
    ("K3", 350.0, 350.0),
    ("K4", 400.0, 100.0),
    ("K5", 200.0, 200.0),
]

RANDOM_RADIUS_MM = 50.0

CONTROL_POINT_COUNT = 2
WORKSPACE_X_MIN = 50.0
WORKSPACE_X_MAX = 450.0
WORKSPACE_Y_MIN = 50.0
WORKSPACE_Y_MAX = 450.0

RANDOM_SEED = None

XYZ_FEEDRATE = 6000.0
XYZ_POSITION_TOLERANCE_MM = 0.05

TRACKER_STALE_THRESHOLD_S = 5.0
TRACKER_STABLE_THRESHOLD_MM = 0.1
TRACKER_STABLE_REQUIRED_COUNT = 3
TRACKER_CAPTURE_TIMEOUT_S = 60.0

ALLOW_SCALE = True
MIN_GEOMETRY_RANK = 2

MAX_ALLOWED_RMS_MM = 0.10
MAX_ALLOWED_MAX_RESIDUAL_MM = 0.15

MAX_ALLOWED_CONTROL_ERROR_MM = 0.20

RESULT_DIR = PROJECT_ROOT / "results" / "trafo_validation"


# ============================================================
# GLOBAL STATE
# ============================================================

xyz_state = XYZRobotState()


# ============================================================
# CALLBACKS
# ============================================================

def on_xyz_event(event):
    print(event.format_for_log())


def on_xyz_state_changed(state: XYZRobotState):
    global xyz_state
    xyz_state = state


def on_tracker_state_changed(state: LasertrackerState):
    pass


def on_tracker_log(text: str):
    print(f"[Lasertracker] {text}")


def on_tracker_error(text: str):
    print(f"[Lasertracker ERROR] {text}")


# ============================================================
# PUNKTE
# ============================================================

def random_point_in_radius(
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


def generate_calibration_points() -> list[tuple[str, float, float]]:
    return [
        (name, *random_point_in_radius(center_x, center_y, RANDOM_RADIUS_MM))
        for name, center_x, center_y in BASE_POINTS
    ]


def generate_control_points() -> list[tuple[str, float, float]]:
    points = []

    for i in range(1, CONTROL_POINT_COUNT + 1):
        x = random.uniform(WORKSPACE_X_MIN, WORKSPACE_X_MAX)
        y = random.uniform(WORKSPACE_Y_MIN, WORKSPACE_Y_MAX)
        points.append((f"C{i}", x, y))

    return points


# ============================================================
# XYZ WAITS
# ============================================================

def wait_for_xyz_not_busy(timeout_s: float = 60.0):
    start = time.time()

    while time.time() - start < timeout_s:
        if not xyz_state.busy:
            return

        time.sleep(0.05)

    raise TimeoutError("XYZ ist nach Timeout noch busy.")


def wait_for_xyz_position(
    target_x: float,
    target_y: float,
    tolerance_mm: float = XYZ_POSITION_TOLERANCE_MM,
    timeout_s: float = 60.0,
):
    start = time.time()

    while time.time() - start < timeout_s:
        if (
            not xyz_state.busy
            and xyz_state.x is not None
            and xyz_state.y is not None
        ):
            dx = xyz_state.x - target_x
            dy = xyz_state.y - target_y

            if abs(dx) <= tolerance_mm and abs(dy) <= tolerance_mm:
                return

        time.sleep(0.05)

    raise TimeoutError(
        f"XYZ-Zielposition nicht erreicht: "
        f"Soll=({target_x:.3f}, {target_y:.3f}), "
        f"Ist=({xyz_state.x}, {xyz_state.y})"
    )


# ============================================================
# MESSUNG
# ============================================================

def move_to_position_and_capture(
    point_name: str,
    target_x: float,
    target_y: float,
    xyz_worker: XYZRobotWorker,
    tracker_receiver: LasertrackerReceiver,
) -> dict:
    print(f"[{point_name}] Fahre auf X={target_x:.3f}, Y={target_y:.3f}")

    xyz_worker.send_command(
        "move_absolute_verified",
        x=target_x,
        y=target_y,
        z=None,
        feedrate=XYZ_FEEDRATE,
    )

    wait_for_xyz_position(
        target_x=target_x,
        target_y=target_y,
        tolerance_mm=XYZ_POSITION_TOLERANCE_MM,
        timeout_s=60.0,
    )

    robot_z = xyz_state.z if xyz_state.z is not None else 0.0

    print(
        f"[{point_name}] Robot=({xyz_state.x:.3f}, "
        f"{xyz_state.y:.3f}, {robot_z:.3f})"
    )

    measurement: TrackerMeasurement = tracker_receiver.capture_stable_point(
        timeout_s=TRACKER_CAPTURE_TIMEOUT_S,
        min_age_after_start_s=0.0,
    )

    print(
        f"[{point_name}] Tracker=({measurement.x:.3f}, "
        f"{measurement.y:.3f}, {measurement.z:.3f}) [{measurement.unit}]"
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


# ============================================================
# TRANSFORMATION
# ============================================================

def calculate_transformation(measurements: list[dict]):
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
        allow_scale=ALLOW_SCALE,
        min_geometry_rank=MIN_GEOMETRY_RANK,
    )


def is_trafo_ok(trafo) -> bool:
    return (
        trafo.rms <= MAX_ALLOWED_RMS_MM
        and trafo.max_residual <= MAX_ALLOWED_MAX_RESIDUAL_MM
    )


def calculate_best_transformation_with_outlier_check(
    measurements: list[dict],
) -> dict:
    trafo_5 = calculate_transformation(measurements)

    if is_trafo_ok(trafo_5):
        return {
            "status": "OK_5_POINTS",
            "message": "Trafo OK mit 5 Punkten.",
            "trafo": trafo_5,
            "used_measurements": measurements,
            "excluded_measurement": None,
            "candidate_results": [],
        }

    candidate_results = []

    for used_indices in combinations(range(len(measurements)), 4):
        used_indices = list(used_indices)
        used_measurements = [measurements[i] for i in used_indices]
        excluded_indices = [i for i in range(len(measurements)) if i not in used_indices]
        excluded_measurement = measurements[excluded_indices[0]]

        try:
            candidate_trafo = calculate_transformation(used_measurements)

            candidate_results.append({
                "used_indices": used_indices,
                "excluded_measurement": excluded_measurement,
                "trafo": candidate_trafo,
                "ok": is_trafo_ok(candidate_trafo),
                "error": None,
            })

        except Exception as exc:
            candidate_results.append({
                "used_indices": used_indices,
                "excluded_measurement": excluded_measurement,
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

        excluded = best_candidate["excluded_measurement"]

        return {
            "status": "OK_4_POINTS",
            "message": (
                f"Trafo OK mit 4 Punkten. "
                f"Ausgeschlossener instabiler Punkt: {excluded['name']}."
            ),
            "trafo": best_candidate["trafo"],
            "used_measurements": [
                measurements[i]
                for i in best_candidate["used_indices"]
            ],
            "excluded_measurement": excluded,
            "candidate_results": candidate_results,
        }

    return {
        "status": "INVALID",
        "message": (
            "Trafo ungültig. "
            "Auch keine 4-Punkt-Kombination erfüllt die Schwellwerte."
        ),
        "trafo": trafo_5,
        "used_measurements": measurements,
        "excluded_measurement": None,
        "candidate_results": candidate_results,
    }


# ============================================================
# VALIDIERUNG
# ============================================================

def evaluate_control_points(
    trafo,
    control_measurements: list[dict],
) -> list[dict]:
    results = []

    for m in control_measurements:
        robot_point = [
            m["robot_actual_x"],
            m["robot_actual_y"],
            m["robot_actual_z"],
        ]

        tracker_computed = trafo.robot_to_tracker(robot_point)

        dx = m["tracker_x"] - tracker_computed[0]
        dy = m["tracker_y"] - tracker_computed[1]
        dz = m["tracker_z"] - tracker_computed[2]
        error_norm = math.sqrt(dx * dx + dy * dy + dz * dz)

        results.append({
            "name": m["name"],
            "measurement": m,
            "tracker_computed_x": tracker_computed[0],
            "tracker_computed_y": tracker_computed[1],
            "tracker_computed_z": tracker_computed[2],
            "dx": dx,
            "dy": dy,
            "dz": dz,
            "error_norm": error_norm,
            "ok": error_norm <= MAX_ALLOWED_CONTROL_ERROR_MM,
        })

    return results


def is_validation_ok(control_results: list[dict]) -> bool:
    return all(r["ok"] for r in control_results)


# ============================================================
# RUN
# ============================================================

def print_candidate_results(candidate_results: list[dict]):
    if not candidate_results:
        return

    print("\n4-Punkt-Kandidaten:")

    for c in candidate_results:
        excluded = c["excluded_measurement"]["name"]

        if c["trafo"] is None:
            print(f"  ohne {excluded}: FEHLER - {c.get('error')}")
            continue

        trafo = c["trafo"]
        status = "OK" if c["ok"] else "nicht OK"

        print(
            f"  ohne {excluded}: {status} | "
            f"RMS={trafo.rms:.4f} mm | "
            f"Max={trafo.max_residual:.4f} mm | "
            f"Scale={trafo.scale:.9f}"
        )


def run_single_validation(
    run_index: int,
    xyz_worker: XYZRobotWorker,
    tracker_receiver: LasertrackerReceiver,
) -> dict:
    print("\n" + "=" * 60)
    print(f"VALIDIERUNG {run_index}")
    print("=" * 60)

    calibration_points = generate_calibration_points()
    control_points = generate_control_points()

    print("Kalibrierpunkte:")
    for point_name, x, y in calibration_points:
        print(f"  {point_name}: X={x:.3f}, Y={y:.3f}")

    print("Kontrollpunkte:")
    for point_name, x, y in control_points:
        print(f"  {point_name}: X={x:.3f}, Y={y:.3f}")

    start_time = time.time()

    calibration_measurements = []

    print("\n--- Kalibrierung ---")

    for point_name, x, y in calibration_points:
        measurement = move_to_position_and_capture(
            point_name=point_name,
            target_x=x,
            target_y=y,
            xyz_worker=xyz_worker,
            tracker_receiver=tracker_receiver,
        )
        calibration_measurements.append(measurement)

    assessment = calculate_best_transformation_with_outlier_check(
        calibration_measurements
    )

    trafo = assessment["trafo"]

    print()
    print(assessment["message"])
    print(trafo.format_summary())

    print("\nRestklaffungen verwendeter Kalibrierpunkte:")

    for m, v, vn in zip(
        assessment["used_measurements"],
        trafo.residuals,
        trafo.residual_norms,
    ):
        print(
            f"  {m['name']}: "
            f"vx={v[0]: .4f}, "
            f"vy={v[1]: .4f}, "
            f"vz={v[2]: .4f}, "
            f"|v|={vn:.4f} mm"
        )

    print_candidate_results(assessment["candidate_results"])

    control_measurements = []
    control_results = []

    if assessment["status"] == "INVALID":
        print("\nTrafo ungültig. Kontrollpunkte werden nicht gemessen.")
        validation_status = "INVALID_TRAFO"

    else:
        print("\n--- Kontrollpunkte ---")

        for point_name, x, y in control_points:
            measurement = move_to_position_and_capture(
                point_name=point_name,
                target_x=x,
                target_y=y,
                xyz_worker=xyz_worker,
                tracker_receiver=tracker_receiver,
            )
            control_measurements.append(measurement)

        control_results = evaluate_control_points(
            trafo=trafo,
            control_measurements=control_measurements,
        )

        print("\nKontrollpunktfehler:")

        for r in control_results:
            status = "OK" if r["ok"] else "NICHT OK"

            print(
                f"  {r['name']}: "
                f"dx={r['dx']: .4f}, "
                f"dy={r['dy']: .4f}, "
                f"dz={r['dz']: .4f}, "
                f"|d|={r['error_norm']:.4f} mm -> {status}"
            )

        validation_status = (
            "VALIDATION_OK"
            if is_validation_ok(control_results)
            else "VALIDATION_FAILED"
        )

    duration_s = time.time() - start_time

    print(f"\nBenötigte Zeit Durchgang: {duration_s:.2f} s")
    print(f"Status: {assessment['status']} / {validation_status}")

    return {
        "run_index": run_index,
        "duration_s": duration_s,

        "calibration_measurements": calibration_measurements,
        "used_measurements": assessment["used_measurements"],
        "excluded_measurement": assessment["excluded_measurement"],

        "control_measurements": control_measurements,
        "control_results": control_results,

        "trafo_status": assessment["status"],
        "trafo_message": assessment["message"],
        "validation_status": validation_status,

        "candidate_results": assessment["candidate_results"],
        "trafo": trafo,
    }


# ============================================================
# STATISTIK / EXPORT
# ============================================================

def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0

    m = mean(values)

    return math.sqrt(
        sum((v - m) ** 2 for v in values) / (len(values) - 1)
    )


def write_results(results: list[dict]):
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    summary_csv = RESULT_DIR / f"trafo_validation_summary_{timestamp}.csv"
    calibration_csv = RESULT_DIR / f"trafo_validation_calibration_{timestamp}.csv"
    control_csv = RESULT_DIR / f"trafo_validation_control_{timestamp}.csv"
    candidates_csv = RESULT_DIR / f"trafo_validation_candidates_{timestamp}.csv"
    report_txt = RESULT_DIR / f"trafo_validation_report_{timestamp}.txt"

    # --------------------------------------------------------
    # Summary CSV
    # --------------------------------------------------------

    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")

        writer.writerow([
            "run",
            "trafo_status",
            "validation_status",
            "excluded_point",
            "duration_s",
            "used_calibration_points",
            "measured_calibration_points",
            "control_point_count",
            "tx_mm",
            "ty_mm",
            "tz_mm",
            "scale",
            "q0",
            "q1",
            "q2",
            "q3",
            "calibration_rms_mm",
            "calibration_max_residual_mm",
            "control_mean_error_mm",
            "control_max_error_mm",
        ])

        for r in results:
            trafo = r["trafo"]
            t = trafo.translation
            q = trafo.quaternion
            excluded = (
                r["excluded_measurement"]["name"]
                if r["excluded_measurement"] is not None
                else ""
            )

            control_errors = [
                c["error_norm"]
                for c in r["control_results"]
            ]

            writer.writerow([
                r["run_index"],
                r["trafo_status"],
                r["validation_status"],
                excluded,
                f"{r['duration_s']:.6f}",
                len(r["used_measurements"]),
                len(r["calibration_measurements"]),
                len(r["control_results"]),
                f"{t[0]:.6f}",
                f"{t[1]:.6f}",
                f"{t[2]:.6f}",
                f"{trafo.scale:.12f}",
                f"{q[0]:.12f}",
                f"{q[1]:.12f}",
                f"{q[2]:.12f}",
                f"{q[3]:.12f}",
                f"{trafo.rms:.6f}",
                f"{trafo.max_residual:.6f}",
                f"{mean(control_errors):.6f}" if control_errors else "",
                f"{max(control_errors):.6f}" if control_errors else "",
            ])

    # --------------------------------------------------------
    # Calibration CSV
    # --------------------------------------------------------

    with calibration_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")

        writer.writerow([
            "run",
            "trafo_status",
            "point",
            "used_in_final_trafo",
            "robot_target_x",
            "robot_target_y",
            "robot_actual_x",
            "robot_actual_y",
            "robot_actual_z",
            "tracker_x",
            "tracker_y",
            "tracker_z",
            "vx_mm",
            "vy_mm",
            "vz_mm",
            "v_norm_mm",
        ])

        for r in results:
            used_names = {
                m["name"]
                for m in r["used_measurements"]
            }

            residual_by_name = {}

            for m, v, vn in zip(
                r["used_measurements"],
                r["trafo"].residuals,
                r["trafo"].residual_norms,
            ):
                residual_by_name[m["name"]] = (v, vn)

            for m in r["calibration_measurements"]:
                used = m["name"] in used_names

                if used:
                    v, vn = residual_by_name[m["name"]]
                    vx = f"{v[0]:.6f}"
                    vy = f"{v[1]:.6f}"
                    vz = f"{v[2]:.6f}"
                    vnorm = f"{vn:.6f}"
                else:
                    vx = ""
                    vy = ""
                    vz = ""
                    vnorm = ""

                writer.writerow([
                    r["run_index"],
                    r["trafo_status"],
                    m["name"],
                    used,
                    f"{m['robot_target_x']:.6f}",
                    f"{m['robot_target_y']:.6f}",
                    f"{m['robot_actual_x']:.6f}",
                    f"{m['robot_actual_y']:.6f}",
                    f"{m['robot_actual_z']:.6f}",
                    f"{m['tracker_x']:.6f}",
                    f"{m['tracker_y']:.6f}",
                    f"{m['tracker_z']:.6f}",
                    vx,
                    vy,
                    vz,
                    vnorm,
                ])

    # --------------------------------------------------------
    # Control CSV
    # --------------------------------------------------------

    with control_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")

        writer.writerow([
            "run",
            "trafo_status",
            "validation_status",
            "point",
            "point_ok",
            "robot_target_x",
            "robot_target_y",
            "robot_actual_x",
            "robot_actual_y",
            "robot_actual_z",
            "tracker_measured_x",
            "tracker_measured_y",
            "tracker_measured_z",
            "tracker_computed_x",
            "tracker_computed_y",
            "tracker_computed_z",
            "dx_mm",
            "dy_mm",
            "dz_mm",
            "error_norm_mm",
        ])

        for r in results:
            for c in r["control_results"]:
                m = c["measurement"]

                writer.writerow([
                    r["run_index"],
                    r["trafo_status"],
                    r["validation_status"],
                    c["name"],
                    c["ok"],
                    f"{m['robot_target_x']:.6f}",
                    f"{m['robot_target_y']:.6f}",
                    f"{m['robot_actual_x']:.6f}",
                    f"{m['robot_actual_y']:.6f}",
                    f"{m['robot_actual_z']:.6f}",
                    f"{m['tracker_x']:.6f}",
                    f"{m['tracker_y']:.6f}",
                    f"{m['tracker_z']:.6f}",
                    f"{c['tracker_computed_x']:.6f}",
                    f"{c['tracker_computed_y']:.6f}",
                    f"{c['tracker_computed_z']:.6f}",
                    f"{c['dx']:.6f}",
                    f"{c['dy']:.6f}",
                    f"{c['dz']:.6f}",
                    f"{c['error_norm']:.6f}",
                ])

    # --------------------------------------------------------
    # Candidates CSV
    # --------------------------------------------------------

    with candidates_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")

        writer.writerow([
            "run",
            "excluded_point",
            "candidate_ok",
            "error",
            "used_points",
            "rms_mm",
            "max_residual_mm",
            "scale",
        ])

        for r in results:
            for c in r["candidate_results"]:
                excluded = c["excluded_measurement"]["name"]
                used_points = ",".join(
                    r["calibration_measurements"][i]["name"]
                    for i in c["used_indices"]
                )

                if c["trafo"] is None:
                    writer.writerow([
                        r["run_index"],
                        excluded,
                        False,
                        c.get("error", ""),
                        used_points,
                        "",
                        "",
                        "",
                    ])
                else:
                    trafo = c["trafo"]

                    writer.writerow([
                        r["run_index"],
                        excluded,
                        c["ok"],
                        "",
                        used_points,
                        f"{trafo.rms:.6f}",
                        f"{trafo.max_residual:.6f}",
                        f"{trafo.scale:.12f}",
                    ])

    # --------------------------------------------------------
    # TXT Report
    # --------------------------------------------------------

    durations = [r["duration_s"] for r in results]
    calibration_rms = [r["trafo"].rms for r in results]
    calibration_max = [r["trafo"].max_residual for r in results]
    control_errors = [
        c["error_norm"]
        for r in results
        for c in r["control_results"]
    ]

    validation_ok_count = sum(
        1 for r in results
        if r["validation_status"] == "VALIDATION_OK"
    )

    with report_txt.open("w", encoding="utf-8") as f:
        f.write("Trafo Validation Helmert 3D\n")
        f.write("=" * 60 + "\n\n")

        f.write(f"Anzahl Durchgänge: {len(results)}\n")
        f.write(f"Kalibrierpunkte je Durchgang: {len(BASE_POINTS)}\n")
        f.write(f"Kontrollpunkte je Durchgang: {CONTROL_POINT_COUNT}\n")
        f.write(f"Tracker Captures je Punkt: 1\n")
        f.write(f"Random Radius Kalibrierpunkte [mm]: {RANDOM_RADIUS_MM:.3f}\n")
        f.write(
            f"Arbeitsraum X/Y [mm]: "
            f"{WORKSPACE_X_MIN:.1f}..{WORKSPACE_X_MAX:.1f} / "
            f"{WORKSPACE_Y_MIN:.1f}..{WORKSPACE_Y_MAX:.1f}\n"
        )
        f.write(f"Allow Scale: {ALLOW_SCALE}\n")
        f.write(f"Min Geometry Rank: {MIN_GEOMETRY_RANK}\n")
        f.write(f"Max allowed RMS [mm]: {MAX_ALLOWED_RMS_MM:.3f}\n")
        f.write(
            f"Max allowed residual [mm]: "
            f"{MAX_ALLOWED_MAX_RESIDUAL_MM:.3f}\n"
        )
        f.write(
            f"Max allowed control error [mm]: "
            f"{MAX_ALLOWED_CONTROL_ERROR_MM:.3f}\n\n"
        )

        f.write("Zusammenfassung\n")
        f.write("-" * 60 + "\n")
        f.write(f"Validation OK: {validation_ok_count}/{len(results)}\n\n")

        f.write(f"Zeit Mittel [s]: {mean(durations):.3f}\n")
        f.write(f"Zeit Std [s]:    {std(durations):.3f}\n")
        f.write(f"Zeit Min [s]:    {min(durations):.3f}\n")
        f.write(f"Zeit Max [s]:    {max(durations):.3f}\n\n")

        f.write(f"Kalibrier-RMS Mittel [mm]: {mean(calibration_rms):.6f}\n")
        f.write(f"Kalibrier-RMS Std [mm]:    {std(calibration_rms):.6f}\n")
        f.write(f"Kalibrier-RMS Max [mm]:    {max(calibration_rms):.6f}\n\n")

        f.write(f"Kalibrier-Max Mittel [mm]: {mean(calibration_max):.6f}\n")
        f.write(f"Kalibrier-Max Std [mm]:    {std(calibration_max):.6f}\n")
        f.write(f"Kalibrier-Max Max [mm]:    {max(calibration_max):.6f}\n\n")

        if control_errors:
            f.write(f"Kontrollfehler Mittel [mm]: {mean(control_errors):.6f}\n")
            f.write(f"Kontrollfehler Std [mm]:    {std(control_errors):.6f}\n")
            f.write(f"Kontrollfehler Min [mm]:    {min(control_errors):.6f}\n")
            f.write(f"Kontrollfehler Max [mm]:    {max(control_errors):.6f}\n\n")

        f.write("Einzelergebnisse\n")
        f.write("-" * 60 + "\n")

        for r in results:
            trafo = r["trafo"]
            excluded = (
                r["excluded_measurement"]["name"]
                if r["excluded_measurement"] is not None
                else "-"
            )

            control_errors_run = [
                c["error_norm"]
                for c in r["control_results"]
            ]

            f.write(f"\nDurchgang {r['run_index']}\n")
            f.write(f"  Trafo Status: {r['trafo_status']}\n")
            f.write(f"  Validation Status: {r['validation_status']}\n")
            f.write(f"  Ausgeschlossener Punkt: {excluded}\n")
            f.write(f"  Zeit [s]: {r['duration_s']:.3f}\n")
            f.write(f"  Kalibrier-RMS [mm]: {trafo.rms:.6f}\n")
            f.write(f"  Kalibrier-Max [mm]: {trafo.max_residual:.6f}\n")

            if control_errors_run:
                f.write(
                    f"  Kontrollfehler Mittel/Max [mm]: "
                    f"{mean(control_errors_run):.6f} / "
                    f"{max(control_errors_run):.6f}\n"
                )

    print("\nErgebnisdateien geschrieben:")
    print(f"  {summary_csv}")
    print(f"  {calibration_csv}")
    print(f"  {control_csv}")
    print(f"  {candidates_csv}")
    print(f"  {report_txt}")


# ============================================================
# MAIN
# ============================================================

def main():
    if RANDOM_SEED is not None:
        random.seed(RANDOM_SEED)

    print("Starte Trafo-Validation Helmert 3D...")

    xyz_worker = XYZRobotWorker(
        on_event=on_xyz_event,
        on_state_changed=on_xyz_state_changed,
    )
    xyz_worker.start()

    tracker_receiver = LasertrackerReceiver(
        port=TRACKER_UDP_PORT,
        stale_threshold_seconds=TRACKER_STALE_THRESHOLD_S,
        stable_threshold_mm=TRACKER_STABLE_THRESHOLD_MM,
        stable_required_count=TRACKER_STABLE_REQUIRED_COUNT,
        on_state_changed=on_tracker_state_changed,
        on_log=on_tracker_log,
        on_error=on_tracker_error,
    )
    tracker_receiver.start()

    results = []

    try:
        print("\nVerbinde XYZ...")

        xyz_worker.send_command(
            "connect",
            port=XYZ_PORT,
            baudrate=XYZ_BAUDRATE,
        )

        wait_for_xyz_not_busy(timeout_s=10.0)

        print("Homing...")

        xyz_worker.send_command("home_all")

        wait_for_xyz_position(
            target_x=0.0,
            target_y=0.0,
            tolerance_mm=XYZ_POSITION_TOLERANCE_MM,
            timeout_s=90.0,
        )

        print("Homing abgeschlossen.")

        total_start = time.time()

        for run_index in range(1, NUMBER_OF_RUNS + 1):
            result = run_single_validation(
                run_index=run_index,
                xyz_worker=xyz_worker,
                tracker_receiver=tracker_receiver,
            )
            results.append(result)

        total_duration = time.time() - total_start

        print("\n" + "=" * 60)
        print("GESAMTÜBERSICHT")
        print("=" * 60)

        for r in results:
            trafo = r["trafo"]
            excluded = (
                r["excluded_measurement"]["name"]
                if r["excluded_measurement"] is not None
                else "-"
            )

            control_errors = [
                c["error_norm"]
                for c in r["control_results"]
            ]

            control_max = max(control_errors) if control_errors else None

            control_text = (
                f"{control_max:.4f} mm"
                if control_max is not None
                else "-"
            )

            print(
                f"Run {r['run_index']:02d}: "
                f"{r['trafo_status']} / {r['validation_status']} | "
                f"Excluded={excluded} | "
                f"Zeit={r['duration_s']:.2f} s | "
                f"CalRMS={trafo.rms:.4f} mm | "
                f"CalMax={trafo.max_residual:.4f} mm | "
                f"CtrlMax={control_text}"
            )

        print(f"\nGesamtzeit: {total_duration:.2f} s")

        write_results(results)

    finally:
        print("\nStoppe Komponenten...")
        tracker_receiver.stop()
        xyz_worker.stop()


if __name__ == "__main__":
    main()
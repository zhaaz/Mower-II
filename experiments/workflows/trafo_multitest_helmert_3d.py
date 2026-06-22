# workflows/trafo_multitest_helmert_3d.py

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

NUMBER_OF_TRANSFORMATIONS = 3

MIN_REQUIRED_POINTS = 4
TRACKER_CAPTURE_TIMEOUT_S = 10.0

BASE_POINTS = [
    ("P1", 100.0, 100.0),
    ("P2", 100.0, 350.0),
    ("P3", 350.0, 350.0),
    ("P4", 400.0, 100.0),
    ("P5", 200.0, 200.0),
]

RANDOM_RADIUS_MM = 50.0
RANDOM_SEED = None

XYZ_FEEDRATE = 6000.0
XYZ_POSITION_TOLERANCE_MM = 0.05

TRACKER_STALE_THRESHOLD_S = 5.0
TRACKER_STABLE_THRESHOLD_MM = 0.1
TRACKER_STABLE_REQUIRED_COUNT = 3

ALLOW_SCALE = True
MIN_GEOMETRY_RANK = 2

MAX_ALLOWED_RMS_MM = 0.10
MAX_ALLOWED_MAX_RESIDUAL_MM = 0.15

RESULT_DIR = PROJECT_ROOT / "results" / "trafo_multitest"


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
# ZUFALLSPUNKTE
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


def generate_target_points() -> list[tuple[str, float, float]]:
    return [
        (name, *random_point_in_radius(center_x, center_y, RANDOM_RADIUS_MM))
        for name, center_x, center_y in BASE_POINTS
    ]


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

    print(
        f"[{point_name}] Warte max. {TRACKER_CAPTURE_TIMEOUT_S:.1f} s "
        f"auf stabilen Trackerpunkt..."
    )

    try:
        measurement: TrackerMeasurement = tracker_receiver.capture_stable_point(
            timeout_s=TRACKER_CAPTURE_TIMEOUT_S,
            min_age_after_start_s=0.0,
        )

    except TimeoutError as exc:
        raise TimeoutError(
            f"{point_name}: Kein stabiler Trackerpunkt innerhalb "
            f"{TRACKER_CAPTURE_TIMEOUT_S:.1f} s. {exc}"
        ) from exc

    print(
        f"[{point_name}] "
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


# ============================================================
# TRANSFORMATION / BEWERTUNG
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
    point_count = len(measurements)

    if point_count < MIN_REQUIRED_POINTS:
        return {
            "status": "INVALID_NOT_ENOUGH_POINTS",
            "message": (
                f"Nicht genug messbare Punkte: {point_count}. "
                f"Mindestens erforderlich: {MIN_REQUIRED_POINTS}."
            ),
            "trafo": None,
            "used_measurements": [],
            "excluded_measurement": None,
            "candidate_results": [],
        }

    trafo_all = calculate_transformation(measurements)

    if is_trafo_ok(trafo_all):
        return {
            "status": f"OK_{point_count}_POINTS",
            "message": f"Trafo OK mit {point_count} Punkten.",
            "trafo": trafo_all,
            "used_measurements": measurements,
            "excluded_measurement": None,
            "candidate_results": [],
        }

    if point_count <= MIN_REQUIRED_POINTS:
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

    for used_indices in combinations(range(point_count), MIN_REQUIRED_POINTS):
        used_indices = list(used_indices)

        used_measurements = [
            measurements[i]
            for i in used_indices
        ]

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
            candidate_trafo = calculate_transformation(used_measurements)

            candidate_results.append({
                "used_indices": used_indices,
                "excluded_measurement": excluded_measurement,
                "excluded_names": excluded_names,
                "trafo": candidate_trafo,
                "ok": is_trafo_ok(candidate_trafo),
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
            "status": f"OK_{MIN_REQUIRED_POINTS}_POINTS",
            "message": (
                f"Trafo OK mit {MIN_REQUIRED_POINTS} Punkten. "
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


def print_candidate_results(candidate_results: list[dict]):
    if not candidate_results:
        return

    print("\n4-Punkt-Kandidaten:")

    for c in candidate_results:
        excluded = (
            c["excluded_measurement"]["name"]
            if c["excluded_measurement"] is not None
            else ", ".join(c.get("excluded_names", []))
        )

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


# ============================================================
# RUN
# ============================================================

def run_single_transformation(
    run_index: int,
    xyz_worker: XYZRobotWorker,
    tracker_receiver: LasertrackerReceiver,
) -> dict:
    print("\n" + "=" * 60)
    print(f"TRAFO {run_index}")
    print("=" * 60)

    target_points = generate_target_points()

    print("Zielpunkte:")
    for point_name, x, y in target_points:
        print(f"  {point_name}: X={x:.3f}, Y={y:.3f}")

    start_time = time.time()

    measurements = []
    failed_measurements = []

    for point_name, x, y in target_points:
        try:
            measurement = move_to_position_and_capture(
                point_name=point_name,
                target_x=x,
                target_y=y,
                xyz_worker=xyz_worker,
                tracker_receiver=tracker_receiver,
            )
            measurements.append(measurement)

        except TimeoutError as exc:
            print(f"[{point_name}] WARNUNG: {exc}")
            print(f"[{point_name}] Punkt wird übersprungen.")

            failed_measurements.append({
                "name": point_name,
                "robot_target_x": x,
                "robot_target_y": y,
                "reason": str(exc),
            })

            continue

    if len(measurements) < MIN_REQUIRED_POINTS:
        duration_s = time.time() - start_time

        print(
            f"\nTrafo ungültig: Nur {len(measurements)}/{len(target_points)} "
            f"Punkte messbar. Mindestens erforderlich: {MIN_REQUIRED_POINTS}."
        )

        return {
            "run_index": run_index,
            "duration_s": duration_s,
            "measurements": measurements,
            "failed_measurements": failed_measurements,
            "used_measurements": [],
            "excluded_measurement": None,
            "assessment_status": "INVALID_NOT_ENOUGH_POINTS",
            "assessment_message": (
                f"Nur {len(measurements)}/{len(target_points)} Punkte messbar."
            ),
            "candidate_results": [],
            "trafo": None,
        }

    assessment = calculate_best_transformation_with_outlier_check(measurements)
    trafo = assessment["trafo"]
    used_measurements = assessment["used_measurements"]
    excluded_measurement = assessment["excluded_measurement"]

    duration_s = time.time() - start_time

    print()
    print(assessment["message"])

    if trafo is not None:
        print(trafo.format_summary())
        print(f"Benötigte Zeit: {duration_s:.2f} s")

        print("\nRestklaffungen verwendeter Punkte:")

        for m, v, vn in zip(
            used_measurements,
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

    return {
        "run_index": run_index,
        "duration_s": duration_s,
        "measurements": measurements,
        "failed_measurements": failed_measurements,
        "used_measurements": used_measurements,
        "excluded_measurement": excluded_measurement,
        "assessment_status": assessment["status"],
        "assessment_message": assessment["message"],
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

    summary_csv = RESULT_DIR / f"trafo_multitest_summary_{timestamp}.csv"
    residuals_csv = RESULT_DIR / f"trafo_multitest_residuals_{timestamp}.csv"
    failed_csv = RESULT_DIR / f"trafo_multitest_failed_points_{timestamp}.csv"
    candidates_csv = RESULT_DIR / f"trafo_multitest_candidates_{timestamp}.csv"
    report_txt = RESULT_DIR / f"trafo_multitest_report_{timestamp}.txt"

    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")

        writer.writerow([
            "run",
            "status",
            "excluded_point",
            "duration_s",
            "used_point_count",
            "measured_point_count",
            "failed_point_count",
            "tx_mm",
            "ty_mm",
            "tz_mm",
            "scale",
            "q0",
            "q1",
            "q2",
            "q3",
            "rms_mm",
            "max_residual_mm",
        ])

        for r in results:
            trafo = r["trafo"]
            excluded = (
                r["excluded_measurement"]["name"]
                if r["excluded_measurement"] is not None
                else ""
            )

            if trafo is None:
                writer.writerow([
                    r["run_index"],
                    r["assessment_status"],
                    excluded,
                    f"{r['duration_s']:.6f}",
                    len(r["used_measurements"]),
                    len(r["measurements"]),
                    len(r["failed_measurements"]),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ])
                continue

            t = trafo.translation
            q = trafo.quaternion

            writer.writerow([
                r["run_index"],
                r["assessment_status"],
                excluded,
                f"{r['duration_s']:.6f}",
                len(r["used_measurements"]),
                len(r["measurements"]),
                len(r["failed_measurements"]),
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
            ])

    with residuals_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")

        writer.writerow([
            "run",
            "status",
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
            if r["trafo"] is None:
                continue

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

            for m in r["measurements"]:
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
                    r["assessment_status"],
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

    with failed_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")

        writer.writerow([
            "run",
            "point",
            "robot_target_x",
            "robot_target_y",
            "reason",
        ])

        for r in results:
            for failed in r["failed_measurements"]:
                writer.writerow([
                    r["run_index"],
                    failed["name"],
                    f"{failed['robot_target_x']:.6f}",
                    f"{failed['robot_target_y']:.6f}",
                    failed["reason"],
                ])

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
                excluded = (
                    c["excluded_measurement"]["name"]
                    if c["excluded_measurement"] is not None
                    else ",".join(c.get("excluded_names", []))
                )

                used_points = ",".join(
                    r["measurements"][i]["name"]
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

    durations = [r["duration_s"] for r in results]
    valid_results = [r for r in results if r["trafo"] is not None]

    rms_values = [r["trafo"].rms for r in valid_results]
    max_values = [r["trafo"].max_residual for r in valid_results]
    scales = [r["trafo"].scale for r in valid_results]

    with report_txt.open("w", encoding="utf-8") as f:
        f.write("Trafo Multitest Helmert 3D\n")
        f.write("=" * 60 + "\n\n")

        f.write(f"Anzahl Transformationen: {len(results)}\n")
        f.write(f"Punkte je Messung geplant: {len(BASE_POINTS)}\n")
        f.write(f"Mindestanzahl Punkte: {MIN_REQUIRED_POINTS}\n")
        f.write(f"Tracker Capture Timeout [s]: {TRACKER_CAPTURE_TIMEOUT_S:.1f}\n")
        f.write("Tracker Captures je Punkt: 1\n")
        f.write(f"Random Radius [mm]: {RANDOM_RADIUS_MM:.3f}\n")
        f.write(f"Allow Scale: {ALLOW_SCALE}\n")
        f.write(f"Min Geometry Rank: {MIN_GEOMETRY_RANK}\n")
        f.write(f"Max allowed RMS [mm]: {MAX_ALLOWED_RMS_MM:.3f}\n")
        f.write(
            f"Max allowed residual [mm]: "
            f"{MAX_ALLOWED_MAX_RESIDUAL_MM:.3f}\n\n"
        )

        f.write("Zusammenfassung\n")
        f.write("-" * 60 + "\n")
        f.write(f"Zeit Mittel [s]: {mean(durations):.3f}\n")
        f.write(f"Zeit Std [s]:    {std(durations):.3f}\n")
        f.write(f"Zeit Min [s]:    {min(durations):.3f}\n")
        f.write(f"Zeit Max [s]:    {max(durations):.3f}\n\n")

        f.write(f"Gültige Transformationen: {len(valid_results)}/{len(results)}\n\n")

        if valid_results:
            f.write(f"RMS Mittel [mm]: {mean(rms_values):.6f}\n")
            f.write(f"RMS Std [mm]:    {std(rms_values):.6f}\n")
            f.write(f"RMS Min [mm]:    {min(rms_values):.6f}\n")
            f.write(f"RMS Max [mm]:    {max(rms_values):.6f}\n\n")

            f.write(f"Max Residual Mittel [mm]: {mean(max_values):.6f}\n")
            f.write(f"Max Residual Std [mm]:    {std(max_values):.6f}\n")
            f.write(f"Max Residual Min [mm]:    {min(max_values):.6f}\n")
            f.write(f"Max Residual Max [mm]:    {max(max_values):.6f}\n\n")

            f.write(f"Scale Mittel: {mean(scales):.12f}\n")
            f.write(f"Scale Std:    {std(scales):.12f}\n")
            f.write(f"Scale Min:    {min(scales):.12f}\n")
            f.write(f"Scale Max:    {max(scales):.12f}\n\n")

        f.write("Einzelergebnisse\n")
        f.write("-" * 60 + "\n")

        for r in results:
            trafo = r["trafo"]
            excluded = (
                r["excluded_measurement"]["name"]
                if r["excluded_measurement"] is not None
                else "-"
            )

            f.write(f"\nTrafo {r['run_index']}\n")
            f.write(f"  Status: {r['assessment_status']}\n")
            f.write(f"  Hinweis: {r['assessment_message']}\n")
            f.write(f"  Ausgeschlossener Punkt: {excluded}\n")
            f.write(f"  Nicht messbare Punkte: {len(r['failed_measurements'])}\n")
            f.write(f"  Zeit [s]: {r['duration_s']:.3f}\n")
            f.write(f"  Verwendete Punkte: {len(r['used_measurements'])}\n")

            if r["failed_measurements"]:
                f.write("  Fehlgeschlagene Punkte:\n")
                for failed in r["failed_measurements"]:
                    f.write(
                        f"    {failed['name']}: "
                        f"X={failed['robot_target_x']:.3f}, "
                        f"Y={failed['robot_target_y']:.3f} | "
                        f"{failed['reason']}\n"
                    )

            if trafo is not None:
                t = trafo.translation
                q = trafo.quaternion

                f.write(
                    f"  Translation [mm]: "
                    f"{t[0]:.6f}; {t[1]:.6f}; {t[2]:.6f}\n"
                )
                f.write(f"  Scale: {trafo.scale:.12f}\n")
                f.write(
                    f"  Quaternion: "
                    f"{q[0]:.12f}; {q[1]:.12f}; "
                    f"{q[2]:.12f}; {q[3]:.12f}\n"
                )
                f.write(f"  RMS [mm]: {trafo.rms:.6f}\n")
                f.write(f"  Max Residual [mm]: {trafo.max_residual:.6f}\n")

    print("\nErgebnisdateien geschrieben:")
    print(f"  {summary_csv}")
    print(f"  {residuals_csv}")
    print(f"  {failed_csv}")
    print(f"  {candidates_csv}")
    print(f"  {report_txt}")


# ============================================================
# MAIN
# ============================================================

def main():
    if RANDOM_SEED is not None:
        random.seed(RANDOM_SEED)

    print("Starte Trafo-Multitest Helmert 3D...")

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

        for run_index in range(1, NUMBER_OF_TRANSFORMATIONS + 1):
            result = run_single_transformation(
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

            if trafo is None:
                print(
                    f"Trafo {r['run_index']:02d}: "
                    f"{r['assessment_status']} | "
                    f"Zeit={r['duration_s']:.2f} s | "
                    f"{r['assessment_message']}"
                )
                continue

            excluded = (
                r["excluded_measurement"]["name"]
                if r["excluded_measurement"] is not None
                else "-"
            )

            print(
                f"Trafo {r['run_index']:02d}: "
                f"{r['assessment_status']} | "
                f"Excluded={excluded} | "
                f"Zeit={r['duration_s']:.2f} s | "
                f"RMS={trafo.rms:.4f} mm | "
                f"Max={trafo.max_residual:.4f} mm | "
                f"Scale={trafo.scale:.9f}"
            )

        print(f"\nGesamtzeit: {total_duration:.2f} s")

        write_results(results)

    finally:
        print("\nStoppe Komponenten...")
        tracker_receiver.stop()
        xyz_worker.stop()


if __name__ == "__main__":
    main()
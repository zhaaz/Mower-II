# Transformation/manual_marker_offset_measurement.py

from __future__ import annotations

import csv
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from config.mower_config import CONFIG
from Lasertracker.lasertracker_receiver import LasertrackerReceiver
from Transformation.marker_offset_calibration import (
    compute_marker_to_reflector_offset,
    format_offset_result,
    make_calibration_sample,
)
from XYZ_Robot.xyz_robot_worker import XYZRobotWorker


# --------------------------------------------------
# Einstellungen aus zentraler Config
# --------------------------------------------------

XYZ_PORT = CONFIG.xyz.port
XYZ_BAUDRATE = CONFIG.xyz.baudrate

TRACKER_PORT = CONFIG.tracker.udp_port
CAPTURE_TIMEOUT_S = CONFIG.tracker.capture_timeout_s

FEEDRATE = CONFIG.xyz.default_feedrate
TOLERANCE_MM = CONFIG.xyz.tolerance_mm

MARKER_SHAPE = CONFIG.marker.shape
MARKER_SIZE = CONFIG.marker.size_mm
ANGLE_DEG = CONFIG.marker.angle_deg

CCR_RADIUS_MM = CONFIG.tracker.ccr_radius_mm


# --------------------------------------------------
# Lokale Test-/Kalibrierpunkte
# --------------------------------------------------

ROBOT_POINTS = [
    ("P1", 160.0, 130.0, 180.0),
    ("P2", 330.0, 145.0, 180.0),
    ("P3", 350.0, 265.0, 180.0),
    ("P4", 185.0, 285.0, 180.0),
    ("P5", 255.0, 205.0, 180.0),
]


# --------------------------------------------------
# Hilfsfunktionen
# --------------------------------------------------

def wait_robot_done(worker: XYZRobotWorker, timeout_s: float = 180.0) -> None:
    start = time.time()

    while time.time() - start < timeout_s:
        if worker.command_queue.empty() and not worker.state.busy:
            if worker.state.error_text:
                raise RuntimeError(worker.state.error_text)
            return

        time.sleep(0.05)

    raise TimeoutError("Timeout beim Warten auf XYZRobotWorker.")


def send_robot_command(
    worker: XYZRobotWorker,
    command: str,
    timeout_s: float = 180.0,
    **kwargs,
) -> None:
    worker.send_command(command, **kwargs)
    wait_robot_done(worker, timeout_s=timeout_s)


def measurement_to_array(measurement) -> np.ndarray:
    return np.array([measurement.x, measurement.y, measurement.z], dtype=float)


def capture_tracker_point(
    tracker: LasertrackerReceiver,
    label: str,
) -> np.ndarray:
    print(f"Messe {label} ...")
    measurement = tracker.capture_stable_point(
        timeout_s=CAPTURE_TIMEOUT_S,
        min_age_after_start_s=0.1,
    )
    point = measurement_to_array(measurement)
    print(f"{label}: X={point[0]:.6f}, Y={point[1]:.6f}, Z={point[2]:.6f}")
    return point


def save_result(result) -> None:
    out_dir = Path("marker_offset_calibration_results")
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    csv_path = out_dir / f"marker_offset_calibration_{timestamp}.csv"
    txt_path = out_dir / f"marker_offset_calibration_{timestamp}.txt"

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(
            [
                "label",
                "robot_x", "robot_y", "robot_z",
                "reflector_lt_x", "reflector_lt_y", "reflector_lt_z",
                "marker_lt_x", "marker_lt_y", "marker_lt_z",
                "offset_robot_x", "offset_robot_y", "offset_robot_z",
            ]
        )

        for sample in result.samples:
            writer.writerow(
                [
                    sample.label,
                    *[f"{v:.6f}" for v in sample.robot_marker],
                    *[f"{v:.6f}" for v in sample.reflector_lt],
                    *[f"{v:.6f}" for v in sample.marker_lt],
                    *[f"{v:.6f}" for v in sample.offset_robot],
                ]
            )

        writer.writerow([])
        writer.writerow(["mean_offset_robot", *[f"{v:.6f}" for v in result.mean_offset_robot]])
        writer.writerow(["std_offset_robot", *[f"{v:.6f}" for v in result.std_offset_robot]])
        writer.writerow(["rms_offset", f"{result.rms_offset:.6f}"])
        writer.writerow(["max_deviation", f"{result.max_deviation:.6f}"])
        writer.writerow(["helmert_rms", f"{result.helmert.rms:.6f}"])
        writer.writerow(["helmert_max_residual", f"{result.helmert.max_residual:.6f}"])
        writer.writerow(["helmert_scale", f"{result.helmert.scale:.12f}"])

    with txt_path.open("w", encoding="utf-8") as f:
        f.write(format_offset_result(result))
        f.write("\n")

    print()
    print(f"CSV gespeichert: {csv_path}")
    print(f"TXT gespeichert: {txt_path}")


# --------------------------------------------------
# Hauptablauf
# --------------------------------------------------

def main() -> None:
    worker = XYZRobotWorker(
        on_event=lambda e: print(f"XYZ: {e.level.name}: {e.message}"),
        on_state_changed=None,
    )

    tracker = LasertrackerReceiver(
        port=TRACKER_PORT,
        on_log=lambda text: print(f"Tracker: {text}"),
        on_error=lambda text: print(f"Tracker FEHLER: {text}"),
    )

    reflector_lt_points: dict[str, np.ndarray] = {}
    marker_lt_points: dict[str, np.ndarray] = {}

    try:
        print("Aktive Konfiguration:")
        print(f"  XYZ_PORT={XYZ_PORT}")
        print(f"  TRACKER_PORT={TRACKER_PORT}")
        print(f"  FEEDRATE={FEEDRATE}")
        print(f"  TOLERANCE_MM={TOLERANCE_MM}")
        print(f"  MARKER={MARKER_SHAPE}, size={MARKER_SIZE}")
        print(f"  CCR_RADIUS_MM={CCR_RADIUS_MM}")
        print()

        print("Starte XYZRobotWorker ...")
        worker.start()

        print("Verbinde XYZ ...")
        send_robot_command(
            worker,
            "connect",
            timeout_s=30.0,
            port=XYZ_PORT,
            baudrate=XYZ_BAUDRATE,
        )

        print("Starte LasertrackerReceiver ...")
        tracker.start()
        time.sleep(0.5)

        if not tracker.running:
            raise RuntimeError("LasertrackerReceiver konnte nicht gestartet werden.")

        input("Pruefe Tracker-Datenstrom. Dann ENTER fuer Homing ...")

        print("Homing ...")
        send_robot_command(worker, "home_all", timeout_s=180.0)

        print()
        print("=== Trafo-Markierlauf: Reflektor oben messen ===")

        for label, x, y, z in ROBOT_POINTS:
            print()
            print(f"--- {label} ---")

            print(f"Fahre Punktmitte {label}: X={x:.3f}, Y={y:.3f}, Z={z:.3f}")
            send_robot_command(
                worker,
                "move_absolute_verified",
                timeout_s=180.0,
                x=x,
                y=y,
                z=z,
                feedrate=FEEDRATE,
                tolerance_mm=TOLERANCE_MM,
            )

            print(f"Markiere {label}")
            send_robot_command(
                worker,
                "mark_point",
                timeout_s=180.0,
                x=x,
                y=y,
                label=label,
                marker_size=MARKER_SIZE,
                marker_shape=MARKER_SHAPE,
                angle_deg=ANGLE_DEG,
            )

            print(f"Fahre erneut Punktmitte {label}")
            send_robot_command(
                worker,
                "move_absolute_verified",
                timeout_s=180.0,
                x=x,
                y=y,
                z=z,
                feedrate=FEEDRATE,
                tolerance_mm=TOLERANCE_MM,
            )

            reflector_lt_points[label] = capture_tracker_point(
                tracker,
                f"{label} reflector_lt",
            )

        print()
        input("Reflektor oben entfernen/Roboter sichern. ENTER fuer Homing ...")

        print("Homing ...")
        send_robot_command(worker, "home_all", timeout_s=180.0)

        print()
        print("=== Manuelle CCR-Messung: markierte Punkte messen ===")

        for label, _, _, _ in ROBOT_POINTS:
            print()
            input(f"CCR mit Schablone exakt auf {label} setzen, dann ENTER ...")

            marker_lt_ccr = capture_tracker_point(
                tracker,
                f"{label} marker_lt CCR center",
            )

            marker_lt_points[label] = marker_lt_ccr.copy()
            marker_lt_points[label][2] -= CCR_RADIUS_MM

            print(
                f"{label} marker_lt Bodenpunkt korrigiert: "
                f"X={marker_lt_points[label][0]:.6f}, "
                f"Y={marker_lt_points[label][1]:.6f}, "
                f"Z={marker_lt_points[label][2]:.6f}"
            )

        samples = []

        for label, x, y, z in ROBOT_POINTS:
            samples.append(
                make_calibration_sample(
                    label=label,
                    robot_marker=[x, y, z],
                    reflector_lt=reflector_lt_points[label],
                    marker_lt=marker_lt_points[label],
                )
            )

        result = compute_marker_to_reflector_offset(samples)

        print()
        print("=" * 80)
        print("ERGEBNIS")
        print("=" * 80)
        print(format_offset_result(result))

        save_result(result)

    finally:
        print()
        print("Stoppe Tracker und XYZWorker ...")
        tracker.stop()
        worker.stop()


if __name__ == "__main__":
    main()


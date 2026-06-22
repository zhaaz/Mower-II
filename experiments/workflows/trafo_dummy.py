# trafo_dummy.py

import sys
from pathlib import Path
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from XYZ_Robot.xyz_robot_worker import XYZRobotWorker
from XYZ_Robot.xyz_robot_state import XYZRobotState

from Lasertracker.lasertracker_receiver import LasertrackerReceiver
from Lasertracker.lasertracker_state import LasertrackerState, TrackerMeasurement


XYZ_PORT = "COM5"
XYZ_BAUDRATE = 115200
TRACKER_UDP_PORT = 10000

TARGET_POINTS = [
    ("P1", 86.0, 94.0),
    ("P2", 200.0, 64.0),
    ("P3", 210.0, 234.0),
    ("P4", 92.0, 198.0),
]

XYZ_FEEDRATE = 6000.0
XYZ_POSITION_TOLERANCE_MM = 0.05

TRACKER_STALE_THRESHOLD_S = 5.0
TRACKER_STABLE_THRESHOLD_MM = 0.1
TRACKER_STABLE_REQUIRED_COUNT = 3
TRACKER_CAPTURE_TIMEOUT_S = 60.0


xyz_state = XYZRobotState()


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


def move_to_position_and_capture(
        point_name: str,
        target_x: float,
        target_y: float,
        xyz_worker: XYZRobotWorker,
        tracker_receiver: LasertrackerReceiver,
) -> dict:
    print(f"\n[{point_name}] Fahre auf X={target_x:.3f}, Y={target_y:.3f}")

    xyz_worker.send_command(
        "move_absolute_verified",
        x=target_x,
        y=target_y,
        z=None,
        feedrate=XYZ_FEEDRATE,
    )


    print(
        f"[{point_name}] XYZ-Ziel erreicht: "
        f"X={xyz_state.x:.3f}, "
        f"Y={xyz_state.y:.3f}, "
        f"Z={xyz_state.z:.3f}"
    )

    print(f"[{point_name}] Warte auf neuen stabilen Lasertrackerpunkt...")

    measurement: TrackerMeasurement = tracker_receiver.capture_stable_point(
        timeout_s=TRACKER_CAPTURE_TIMEOUT_S,
        min_age_after_start_s=0.0,
    )

    print(
        f"[{point_name}] Tracker stabil: "
        f"X={measurement.x:.3f}, "
        f"Y={measurement.y:.3f}, "
        f"Z={measurement.z:.3f} "
        f"[{measurement.unit}]"
    )

    return {
        "name": point_name,

        "robot_target_x": target_x,
        "robot_target_y": target_y,

        "robot_actual_x": xyz_state.x,
        "robot_actual_y": xyz_state.y,
        "robot_actual_z": xyz_state.z,

        "tracker_x": measurement.x,
        "tracker_y": measurement.y,
        "tracker_z": measurement.z,
        "tracker_unit": measurement.unit,
        "tracker_timestamp": measurement.timestamp,
    }


def main():
    print("Starte Trafo-Dummy minimal/robust...")

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

    measurements = []

    try:
        print("Verbinde XYZ...")
        xyz_worker.send_command(
            "connect",
            port=XYZ_PORT,
            baudrate=XYZ_BAUDRATE,
        )

        wait_for_xyz_position(
            target_x=xyz_state.x if xyz_state.x is not None else 0.0,
            target_y=xyz_state.y if xyz_state.y is not None else 0.0,
            tolerance_mm=999999.0,
            timeout_s=10.0,
        )

        print("Homing...")
        xyz_worker.send_command("home_all")

        wait_for_xyz_position(
            target_x=0.0,
            target_y=0.0,
            tolerance_mm=XYZ_POSITION_TOLERANCE_MM,
            timeout_s=90.0,
        )

        print("Homing abgeschlossen. Starte Messpunkte.")

        for point_name, x, y in TARGET_POINTS:
            result = move_to_position_and_capture(
                point_name=point_name,
                target_x=x,
                target_y=y,
                xyz_worker=xyz_worker,
                tracker_receiver=tracker_receiver,
            )
            measurements.append(result)

        print("\nMesspunkte abgeschlossen:\n")

        for m in measurements:
            print(
                f"{m['name']}: "
                f"Robot Soll=({m['robot_target_x']:.3f}, {m['robot_target_y']:.3f}) | "
                f"Robot Ist=({m['robot_actual_x']:.3f}, {m['robot_actual_y']:.3f}, {m['robot_actual_z']:.3f}) | "
                f"Tracker=({m['tracker_x']:.3f}, {m['tracker_y']:.3f}, {m['tracker_z']:.3f}) "
                f"{m['tracker_unit']}"
            )

    finally:
        print("\nStoppe Komponenten...")
        tracker_receiver.stop()
        xyz_worker.stop()


if __name__ == "__main__":
    main()
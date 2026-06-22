# Transformation/trafo_workflow_multitest.py

from __future__ import annotations

import sys
from pathlib import Path
import time
import csv
import math
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from XYZ_Robot.xyz_robot_worker import XYZRobotWorker
from XYZ_Robot.xyz_robot_state import XYZRobotState

from Lasertracker.lasertracker_receiver import LasertrackerReceiver
from Lasertracker.lasertracker_state import LasertrackerState

from Transformation.trafo_manager import TrafoManager
from Transformation.trafo_workflow import (
    TrafoWorkflow,
    TrafoWorkflowConfig,
)


# ============================================================
# KONFIGURATION
# ============================================================

XYZ_PORT = "COM5"
XYZ_BAUDRATE = 115200
TRACKER_UDP_PORT = 10000

NUMBER_OF_TRANSFORMATIONS = 3

TRACKER_STALE_THRESHOLD_S = 5.0
TRACKER_STABLE_THRESHOLD_MM = 0.1
TRACKER_STABLE_REQUIRED_COUNT = 3

TRAFO_CAPTURE_TIMEOUT_S = 10.0

RESULT_DIR = PROJECT_ROOT / "Transformation" / "results" / "workflow_multitest"


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
# UTILS
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
    tolerance_mm: float = 0.05,
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


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0

    m = mean(values)

    return math.sqrt(
        sum((v - m) ** 2 for v in values) / (len(values) - 1)
    )


# ============================================================
# WORKFLOW RUN
# ============================================================

def run_single_workflow(
    run_index: int,
    xyz_worker: XYZRobotWorker,
    tracker_receiver: LasertrackerReceiver,
    trafo_manager: TrafoManager,
):
    print("\n" + "=" * 60)
    print(f"WORKFLOW TEST {run_index}")
    print("=" * 60)

    workflow_logs = []

    config = TrafoWorkflowConfig(
        tracker_capture_timeout_s=TRAFO_CAPTURE_TIMEOUT_S,
        minimum_required_measurements=4,
        allow_scale=True,
        min_geometry_rank=2,
        max_allowed_rms_mm=0.10,
        max_allowed_max_residual_mm=0.15,
    )

    workflow = TrafoWorkflow(
        xyz_worker=xyz_worker,
        tracker_receiver=tracker_receiver,
        xyz_state_getter=lambda: xyz_state,
        config=config,
        on_status=lambda text: print(f"[STATUS] {text}"),
        on_progress=lambda current, total, label:
            print(f"[PROGRESS] {current}/{total}: {label}"),
        on_log=lambda text: workflow_logs.append(text),
    )

    result = workflow.run()

    print("\nERGEBNIS")
    print("-" * 60)

    print(f"Status: {result.status}")
    print(f"Message: {result.message}")
    print(f"Dauer: {result.duration_s:.2f} s")

    if result.error:
        print(f"Fehler: {result.error}")

    print(f"Messbare Punkte: {len(result.measurements)}")
    print(f"Failed Punkte: {len(result.failed_measurements)}")

    if result.failed_measurements:
        print("\nNicht messbare Punkte:")

        for failed in result.failed_measurements:
            print(
                f"  {failed['name']}: "
                f"X={failed['robot_target_x']:.3f}, "
                f"Y={failed['robot_target_y']:.3f} | "
                f"{failed['reason']}"
            )

    if result.trafo is not None:
        print()
        print(result.trafo.format_summary())

        print("\nRestklaffungen:")

        for m, v, vn in zip(
            result.used_measurements,
            result.trafo.residuals,
            result.trafo.residual_norms,
        ):
            print(
                f"  {m['name']}: "
                f"vx={v[0]: .4f}, "
                f"vy={v[1]: .4f}, "
                f"vz={v[2]: .4f}, "
                f"|v|={vn:.4f} mm"
            )

    if result.success:
        trafo_manager.set_pending(result)
        trafo_manager.accept_pending()

        print("\nTrafo übernommen -> valid = True")

        # für Multitest direkt wieder invalidieren
        trafo_manager.invalidate("Workflow Multitest Reset")

    else:
        print("\nTrafo NICHT übernommen.")

    return {
        "run_index": run_index,
        "result": result,
        "workflow_logs": workflow_logs,
    }


# ============================================================
# EXPORT
# ============================================================

def write_results(results: list[dict]):
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    summary_csv = RESULT_DIR / f"workflow_multitest_summary_{timestamp}.csv"
    failed_csv = RESULT_DIR / f"workflow_multitest_failed_{timestamp}.csv"
    report_txt = RESULT_DIR / f"workflow_multitest_report_{timestamp}.txt"

    # --------------------------------------------------------
    # SUMMARY CSV
    # --------------------------------------------------------

    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")

        writer.writerow([
            "run",
            "success",
            "status",
            "duration_s",
            "measured_points",
            "used_points",
            "failed_points",
            "excluded_point",
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
            result = r["result"]
            trafo = result.trafo

            excluded = (
                result.excluded_measurement["name"]
                if result.excluded_measurement is not None
                else ""
            )

            if trafo is None:
                writer.writerow([
                    r["run_index"],
                    result.success,
                    result.status,
                    f"{result.duration_s:.6f}",
                    len(result.measurements),
                    len(result.used_measurements),
                    len(result.failed_measurements),
                    excluded,
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
                result.success,
                result.status,
                f"{result.duration_s:.6f}",
                len(result.measurements),
                len(result.used_measurements),
                len(result.failed_measurements),
                excluded,
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

    # --------------------------------------------------------
    # FAILED CSV
    # --------------------------------------------------------

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
            result = r["result"]

            for failed in result.failed_measurements:
                writer.writerow([
                    r["run_index"],
                    failed["name"],
                    f"{failed['robot_target_x']:.6f}",
                    f"{failed['robot_target_y']:.6f}",
                    failed["reason"],
                ])

    # --------------------------------------------------------
    # REPORT TXT
    # --------------------------------------------------------

    valid_results = [
        r for r in results
        if r["result"].trafo is not None
    ]

    durations = [
        r["result"].duration_s
        for r in results
    ]

    rms_values = [
        r["result"].trafo.rms
        for r in valid_results
    ]

    max_values = [
        r["result"].trafo.max_residual
        for r in valid_results
    ]

    with report_txt.open("w", encoding="utf-8") as f:
        f.write("Workflow Multitest Helmert 3D\n")
        f.write("=" * 60 + "\n\n")

        f.write(f"Anzahl Tests: {len(results)}\n")
        f.write(f"Tracker Timeout [s]: {TRAFO_CAPTURE_TIMEOUT_S:.1f}\n")
        f.write("Allow Scale: True\n")
        f.write("Minimum Required Points: 4\n\n")

        f.write(f"Zeit Mittel [s]: {mean(durations):.3f}\n")
        f.write(f"Zeit Std [s]:    {std(durations):.3f}\n")
        f.write(f"Zeit Min [s]:    {min(durations):.3f}\n")
        f.write(f"Zeit Max [s]:    {max(durations):.3f}\n\n")

        f.write(
            f"Gültige Transformationen: "
            f"{len(valid_results)}/{len(results)}\n\n"
        )

        if valid_results:
            f.write(f"RMS Mittel [mm]: {mean(rms_values):.6f}\n")
            f.write(f"RMS Std [mm]:    {std(rms_values):.6f}\n")
            f.write(f"RMS Max [mm]:    {max(rms_values):.6f}\n\n")

            f.write(
                f"Max Residual Mittel [mm]: "
                f"{mean(max_values):.6f}\n"
            )
            f.write(
                f"Max Residual Std [mm]:    "
                f"{std(max_values):.6f}\n"
            )
            f.write(
                f"Max Residual Max [mm]:    "
                f"{max(max_values):.6f}\n\n"
            )

        f.write("Einzelergebnisse\n")
        f.write("-" * 60 + "\n")

        for r in results:
            result = r["result"]

            f.write(f"\nRun {r['run_index']}\n")
            f.write(f"  Success: {result.success}\n")
            f.write(f"  Status: {result.status}\n")
            f.write(f"  Message: {result.message}\n")
            f.write(f"  Dauer [s]: {result.duration_s:.3f}\n")
            f.write(
                f"  Messbare Punkte: {len(result.measurements)}\n"
            )
            f.write(
                f"  Failed Punkte: {len(result.failed_measurements)}\n"
            )

            if result.failed_measurements:
                f.write("  Fehlgeschlagene Punkte:\n")

                for failed in result.failed_measurements:
                    f.write(
                        f"    {failed['name']}: "
                        f"X={failed['robot_target_x']:.3f}, "
                        f"Y={failed['robot_target_y']:.3f} | "
                        f"{failed['reason']}\n"
                    )

            if result.trafo is not None:
                trafo = result.trafo
                t = trafo.translation

                f.write(
                    f"  Translation [mm]: "
                    f"{t[0]:.6f}; {t[1]:.6f}; {t[2]:.6f}\n"
                )

                f.write(f"  Scale: {trafo.scale:.12f}\n")
                f.write(f"  RMS [mm]: {trafo.rms:.6f}\n")
                f.write(
                    f"  Max Residual [mm]: "
                    f"{trafo.max_residual:.6f}\n"
                )

    print("\nErgebnisdateien geschrieben:")
    print(f"  {summary_csv}")
    print(f"  {failed_csv}")
    print(f"  {report_txt}")


# ============================================================
# MAIN
# ============================================================

def main():
    print("Starte Workflow Multitest...")

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

    trafo_manager = TrafoManager()

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
            tolerance_mm=0.05,
            timeout_s=90.0,
        )

        print("Homing abgeschlossen.")

        total_start = time.time()

        for run_index in range(1, NUMBER_OF_TRANSFORMATIONS + 1):
            result = run_single_workflow(
                run_index=run_index,
                xyz_worker=xyz_worker,
                tracker_receiver=tracker_receiver,
                trafo_manager=trafo_manager,
            )

            results.append(result)

        total_duration = time.time() - total_start

        print("\n" + "=" * 60)
        print("GESAMTÜBERSICHT")
        print("=" * 60)

        for r in results:
            result = r["result"]
            trafo = result.trafo

            if trafo is None:
                print(
                    f"Run {r['run_index']:02d}: "
                    f"{result.status} | "
                    f"Dauer={result.duration_s:.2f} s | "
                    f"{result.message}"
                )
                continue

            excluded = (
                result.excluded_measurement["name"]
                if result.excluded_measurement is not None
                else "-"
            )

            print(
                f"Run {r['run_index']:02d}: "
                f"{result.status} | "
                f"Excluded={excluded} | "
                f"Dauer={result.duration_s:.2f} s | "
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
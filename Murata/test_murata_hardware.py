"""Manueller Hardwaretest fuer Murata SCH16T-K01 und Arduino.

Aus dem Projektstamm starten:

    python -m Murata.test_murata_hardware --port COM3

Mit zusaetzlicher Driftmessung (Sensor dabei ruhig stehen lassen):

    python -m Murata.test_murata_hardware --port COM3 --drift-seconds 10

Dieser Test wird bewusst nicht automatisch durch unittest ausgefuehrt.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from typing import Callable

try:
    from Murata.murata_worker import MurataWorker
    from Murata.sch16t import DEFAULT_BAUDRATE
except ModuleNotFoundError as exc:
    if exc.name == "serial":
        raise SystemExit(
            "PySerial fehlt. Installation: python -m pip install pyserial"
        ) from exc
    raise


def wait_until(
    predicate: Callable[[], bool],
    *,
    timeout_s: float,
    error_getter: Callable[[], str | None] | None = None,
) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if error_getter is not None:
            error = error_getter()
            if error:
                raise RuntimeError(error)
        if predicate():
            return True
        time.sleep(0.05)
    return False


def print_state(worker: MurataWorker) -> None:
    state = worker.state
    sensor_time = "-" if state.sensor_time_s is None else f"{state.sensor_time_s:.3f}"
    print(
        f"Sensorzeit={sensor_time:>10} s | "
        f"Gyro Z={state.rate_dps:+10.5f} deg/s | "
        f"Yaw roh={state.raw_yaw_deg:+10.4f} deg | "
        f"Winkel={state.angle_deg:+10.4f} deg | "
        f"Datensaetze={state.valid_packets} | "
        f"ungueltig={state.invalid_lines}"
    )


def validate_numeric_values(worker: MurataWorker) -> None:
    state = worker.state
    values = {
        "raw_yaw_deg": state.raw_yaw_deg,
        "angle_deg": state.angle_deg,
        "rate_dps": state.rate_dps,
        "drift_dps": state.drift_dps,
    }
    invalid = [name for name, value in values.items() if not math.isfinite(float(value))]
    if invalid:
        raise RuntimeError(f"Nicht-endliche Sensorwerte: {', '.join(invalid)}")


def run_hardware_test(
    *,
    port: str,
    baudrate: int,
    measurement_seconds: float,
    drift_seconds: float,
) -> None:
    print("Murata SCH16T-K01 Hardwaretest")
    print(f"Port={port}, Baudrate={baudrate}")
    print("Erwartetes Format: time_us;gyro_z_dps;yaw_raw_deg")
    print()

    worker = MurataWorker(on_log=lambda message: print(f"[Murata] {message}"))
    worker.start()

    try:
        print("1/4 Verbindung wird aufgebaut ...")
        worker.send_command("connect", port=port, baudrate=baudrate)
        connected = wait_until(
            lambda: worker.state.connected,
            timeout_s=8.0,
            error_getter=lambda: worker.state.error_text,
        )
        if not connected:
            raise RuntimeError(f"Keine Verbindung zu {port} innerhalb von 8 Sekunden.")
        print("    Verbindung hergestellt.")

        print("2/4 Warte auf den ersten vollstaendigen Datensatz ...")
        first_packet = wait_until(
            lambda: worker.state.valid_packets > 0,
            timeout_s=5.0,
            error_getter=lambda: worker.state.error_text,
        )
        if not first_packet:
            raise RuntimeError(
                "Verbindung steht, aber es kommen keine gueltigen Daten an. "
                "Arduino-Ausgabe und Baudrate pruefen."
            )
        print("    Erster Datensatz empfangen.")

        start_packets = worker.state.valid_packets
        start_invalid = worker.state.invalid_lines
        start_sensor_time = worker.state.sensor_time_s
        start_wall_time = time.monotonic()
        last_print = 0.0

        print(f"3/4 Messe Datenstrom fuer {measurement_seconds:.1f} Sekunden ...")
        while time.monotonic() - start_wall_time < measurement_seconds:
            elapsed = time.monotonic() - start_wall_time
            if elapsed - last_print >= 0.5:
                print_state(worker)
                last_print = elapsed
            if worker.state.error_text:
                raise RuntimeError(worker.state.error_text)
            time.sleep(0.05)

        end_packets = worker.state.valid_packets
        end_invalid = worker.state.invalid_lines
        end_sensor_time = worker.state.sensor_time_s
        received = end_packets - start_packets
        invalid = end_invalid - start_invalid
        wall_duration = max(time.monotonic() - start_wall_time, 1e-9)
        wall_rate_hz = received / wall_duration

        if start_sensor_time is not None and end_sensor_time is not None:
            sensor_duration = end_sensor_time - start_sensor_time
            sensor_rate_hz = received / sensor_duration if sensor_duration > 0 else 0.0
        else:
            sensor_duration = 0.0
            sensor_rate_hz = 0.0

        validate_numeric_values(worker)
        if received < max(5, int(measurement_seconds * 20)):
            raise RuntimeError(
                f"Zu wenige Messwerte: {received} in {wall_duration:.1f} s "
                f"({wall_rate_hz:.1f} Hz)."
            )
        if sensor_duration <= 0.0:
            raise RuntimeError("Sensorzeit ist nicht weitergelaufen.")

        print()
        print(f"    Gueltige Datensaetze: {received}")
        print(f"    Ungueltige Zeilen:    {invalid}")
        print(f"    Datenrate PC-Zeit:    {wall_rate_hz:.1f} Hz")
        print(f"    Datenrate Sensorzeit: {sensor_rate_hz:.1f} Hz")
        if not 80.0 <= sensor_rate_hz <= 120.0:
            print("    HINWEIS: Erwartet werden ungefaehr 100 Hz.")

        print("4/4 Software-Nullpunkt wird geprueft ...")
        worker.send_command("reset_angle")
        # Der Befehl wird asynchron im Worker verarbeitet.
        time.sleep(0.25)
        reset_done = wait_until(
            lambda: not worker.state.busy and abs(worker.state.angle_deg) < 0.5,
            timeout_s=3.0,
            error_getter=lambda: worker.state.error_text,
        )
        if not reset_done:
            raise RuntimeError(
                "Winkel konnte nicht auf etwa 0 Grad gesetzt werden. "
                "Sensor waehrend der Pruefung ruhig halten."
            )
        print(f"    Winkel nach Nullsetzen: {worker.state.angle_deg:+.5f} deg")

        if drift_seconds > 0.0:
            print()
            print(
                f"Optionale Driftmessung fuer {drift_seconds:.1f} Sekunden. "
                "Sensor jetzt ruhig stehen lassen."
            )
            worker.send_command("determine_drift", seconds=drift_seconds)
            started = wait_until(
                lambda: worker.state.drift_active,
                timeout_s=3.0,
                error_getter=lambda: worker.state.error_text,
            )
            if not started:
                raise RuntimeError("Driftmessung wurde nicht gestartet.")

            finished = wait_until(
                lambda: (
                    not worker.state.drift_active
                    and worker.state.pending_drift_dps is not None
                ),
                timeout_s=drift_seconds + 5.0,
                error_getter=lambda: worker.state.error_text,
            )
            if not finished:
                raise RuntimeError("Driftmessung wurde nicht abgeschlossen.")

            measured_drift = float(worker.state.pending_drift_dps)
            print(f"    Gemessene Drift: {measured_drift:+.10f} deg/s")
            print(f"                      {measured_drift * 60:+.6f} deg/min")
            print(f"                      {measured_drift * 3600:+.3f} deg/h")

            worker.send_command("set_drift")
            drift_set = wait_until(
                lambda: worker.state.pending_drift_dps is None,
                timeout_s=3.0,
                error_getter=lambda: worker.state.error_text,
            )
            if not drift_set:
                raise RuntimeError("Gemessener Driftwert konnte nicht gesetzt werden.")
            print(f"    Aktive Drift:    {worker.state.drift_dps:+.10f} deg/s")

        print()
        print("ERGEBNIS: Hardwaretest erfolgreich.")

    finally:
        worker.stop()
        wait_until(lambda: not worker.running, timeout_s=3.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Murata SCH16T-K01 Hardwaretest")
    parser.add_argument("--port", default="COM3", help="Serieller Port, z. B. COM3")
    parser.add_argument(
        "--baudrate",
        type=int,
        default=DEFAULT_BAUDRATE,
        help=f"Baudrate (Standard: {DEFAULT_BAUDRATE})",
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=10.0,
        help="Dauer der Datenstrompruefung in Sekunden",
    )
    parser.add_argument(
        "--drift-seconds",
        type=float,
        default=0.0,
        help="Optionale Driftmessdauer; 0 deaktiviert die Driftmessung",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.seconds <= 0.0:
        print("FEHLER: --seconds muss groesser 0 sein.", file=sys.stderr)
        return 2
    if args.drift_seconds < 0.0:
        print("FEHLER: --drift-seconds darf nicht negativ sein.", file=sys.stderr)
        return 2

    try:
        run_hardware_test(
            port=args.port,
            baudrate=args.baudrate,
            measurement_seconds=args.seconds,
            drift_seconds=args.drift_seconds,
        )
    except KeyboardInterrupt:
        print("\nHardwaretest abgebrochen.")
        return 130
    except Exception as exc:
        print(f"\nERGEBNIS: Hardwaretest fehlgeschlagen: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

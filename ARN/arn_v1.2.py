import time

from GYEMS.gyems_rs485 import GyemsRmdRs485
from KVH_DSP_3100.dsp3100 import DSP3100

GYEMS_PORT = "COM4"
DSP_PORT   = "COM3"

LOOP_HZ = 10.0
DT = 1.0 / LOOP_HZ

MAX_DPS = 180.0
K_P = 1.0
DEADBAND_DPS = 0.05
GYRO_SIGN = -1.0

# Robustheit
MAX_CONSEC_TIMEOUTS = 5      # nach 5 Timeouts hintereinander -> Stop & Exit
RECONNECT_ON_TIMEOUT = True  # einmal reconnect versuchen


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def safe_set_speed(gyems: GyemsRmdRs485, speed_cmd: float) -> bool:
    """
    Returns True if command was acknowledged, False on timeout.
    """
    try:
        gyems.set_speed_deg_s(speed_cmd)
        return True
    except TimeoutError:
        return False


def main():
    print("=== ARN v1.2 (P + Deadband + Robust RS485) Start ===")

    dsp = DSP3100()
    dsp.connect(port=DSP_PORT, baudrate=375000)
    print("DSP3100 läuft")
    time.sleep(1.0)

    gyems = GyemsRmdRs485(port=GYEMS_PORT, motor_id=0x01, baudrate=115200, timeout=0.25)
    gyems.connect()
    print("GYEMS verbunden")

    # Testfahrt
    print("Testfahrt: 2s rechts")
    gyems.set_speed_deg_s(+90.0)
    time.sleep(2.0)
    print("Testfahrt: 2s links")
    gyems.set_speed_deg_s(-90.0)
    time.sleep(2.0)
    print("Stop")
    gyems.set_speed_deg_s(0.0)
    time.sleep(1.0)

    print("Starte Regelkreis (Ctrl+C zum Abbruch)")
    consecutive_timeouts = 0
    last_print = time.time()

    try:
        while True:
            t0 = time.time()

            rate_dps = dsp.rate_dps
            error = GYRO_SIGN * (-rate_dps)

            if abs(error) < DEADBAND_DPS:
                error = 0.0

            speed_cmd = clamp(K_P * error, -MAX_DPS, +MAX_DPS)

            ok = safe_set_speed(gyems, speed_cmd)

            if not ok:
                consecutive_timeouts += 1
                print(f"\n[WARN] GYEMS timeout #{consecutive_timeouts} (no reply)")

                # best-effort stop (ohne reply ist das nicht garantiert, aber versuchen)
                try:
                    gyems.ser.reset_input_buffer()  # flush junk if possible
                except Exception:
                    pass

                if RECONNECT_ON_TIMEOUT:
                    try:
                        gyems.close()
                    except Exception:
                        pass
                    try:
                        time.sleep(0.2)
                        gyems.connect()
                        print("[INFO] GYEMS reconnected")
                    except Exception as e:
                        print("[ERROR] reconnect failed:", e)

                if consecutive_timeouts >= MAX_CONSEC_TIMEOUTS:
                    raise RuntimeError("Zu viele Timeouts hintereinander -> Stop")

            else:
                consecutive_timeouts = 0

            # Debug-Ausgabe max 5 Hz, damit Console nicht bremst
            if time.time() - last_print >= 0.2:
                print(
                    f"\rω_gyro: {rate_dps:+7.3f} °/s | e: {error:+7.3f} | cmd: {speed_cmd:+7.2f}  ",
                    end=""
                )
                last_print = time.time()

            # Loop timing
            dt_sleep = DT - (time.time() - t0)
            if dt_sleep > 0:
                time.sleep(dt_sleep)

    except KeyboardInterrupt:
        print("\nAbbruch durch Benutzer")

    except Exception as e:
        print("\n[ERROR]", e)

    finally:
        print("Stoppe Motor & schließe Verbindungen")
        try:
            # im Zweifel mehrfach versuchen
            for _ in range(3):
                try:
                    gyems.set_speed_deg_s(0.0)
                    break
                except Exception:
                    time.sleep(0.05)
        except Exception:
            pass

        try:
            gyems.close()
        except Exception:
            pass
        try:
            dsp.disconnect()
        except Exception:
            pass

        print("=== ARN v1.2 Ende ===")


if __name__ == "__main__":
    main()

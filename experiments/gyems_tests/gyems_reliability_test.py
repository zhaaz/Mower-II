import csv
import time
import math
from datetime import datetime

from gyems_rs485 import GyemsRmdRs485, GyemsProtocolError

# ---------- CONFIG ----------
PORT = "COM4"
MOTOR_ID = 0x01
BAUD = 115200

DURATION_S = 30 * 60          # 30 minutes
LOOP_HZ = 10                  # "regelkreis" update rate
MAX_RPS = 2                 # max 0.5 rotations per second
MAX_DPS = MAX_RPS * 360.0     # = 180 deg/s

# simulated motion profile (like continuous small corrections)
# sinus, so it is smooth: speed_cmd = MAX_DPS * sin(2*pi*f*t)
PROFILE_FREQ_HZ = 0.05        # 0.05 Hz -> period 20 s (slow sweeping)
READ_ANGLE = True
READ_STATUS = True
READ_ERRORS_EVERY_S = 5.0     # read error flags periodically (0x9A)
CLEAR_ERRORS_ON_START = True
CLEAR_ERRORS_ON_END = False   # usually keep for post-mortem, but can set True

CSV_FILE = f"gyems_reliability_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
# --------------------------


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def main():
    print("GYEMS Reliability Test")
    print(f"Port={PORT}  ID=0x{MOTOR_ID:02X}  Baud={BAUD}")
    print(f"Duration={DURATION_S/60:.1f} min  Loop={LOOP_HZ} Hz  Max={MAX_DPS:.1f} °/s")
    print(f"Logging to: {CSV_FILE}")
    print("Ctrl+C to stop (motor will be stopped).")

    motor = GyemsRmdRs485(
        port=PORT,
        motor_id=MOTOR_ID,
        baudrate=BAUD,
        timeout=0.25,          # conservative
        inter_cmd_delay=0.01,  # keep it small but non-zero
    )

    # Stats
    counts = {
        "loops": 0,
        "ok": 0,
        "timeouts": 0,
        "proto_err": 0,
        "other_err": 0,
        "status_none": 0,
        "err_reads": 0,
    }

    t0 = time.time()
    next_tick = t0
    next_err_read = t0

    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow([
            "t_s",
            "speed_cmd_dps",
            "angle_deg",
            "temp_C",
            "iq",
            "speed_raw",
            "enc",
            "err_voltage_guess_V",
            "err_flags_guess_byte",
            "event",
        ])

        try:
            motor.connect()
            info = motor.read_model_info()
            print(f"Connected. Driver='{info.driver}' Motor='{info.motor}' HW={info.hw_version} FW={info.fw_version}")

            if CLEAR_ERRORS_ON_START:
                try:
                    motor.clear_error_flags()
                    print("Errors cleared on start.")
                except Exception as e:
                    print("Warn: could not clear errors on start:", e)

            # Make sure stopped first
            try:
                motor.set_speed_deg_s(0.0)
            except Exception:
                pass

            while True:
                now = time.time()
                if now - t0 >= DURATION_S:
                    print("\nReached duration. Stopping.")
                    break

                # pacing
                if now < next_tick:
                    time.sleep(min(0.01, next_tick - now))
                    continue
                next_tick += 1.0 / LOOP_HZ

                t = now - t0
                counts["loops"] += 1

                # simulate "regelkreis output"
                speed_cmd = MAX_DPS * math.sin(2 * math.pi * PROFILE_FREQ_HZ * t)
                speed_cmd = clamp(speed_cmd, -MAX_DPS, MAX_DPS)

                # periodic error read
                err_voltage = ""
                err_flags = ""
                if now >= next_err_read:
                    next_err_read += READ_ERRORS_EVERY_S
                    try:
                        err = motor.read_error_flags()
                        counts["err_reads"] += 1
                        err_voltage = err.get("voltage_V_guess", "")
                        err_flags = err.get("flags_guess_byte", "")
                    except TimeoutError:
                        counts["timeouts"] += 1
                        w.writerow([f"{t:.3f}", f"{speed_cmd:.2f}", "", "", "", "", "", "", "", "timeout_read_errors"])
                    except GyemsProtocolError as e:
                        counts["proto_err"] += 1
                        w.writerow([f"{t:.3f}", f"{speed_cmd:.2f}", "", "", "", "", "", "", "", f"proto_err_read_errors:{e}"])
                    except Exception as e:
                        counts["other_err"] += 1
                        w.writerow([f"{t:.3f}", f"{speed_cmd:.2f}", "", "", "", "", "", "", "", f"err_read_errors:{e}"])

                try:
                    # command speed (like controller)
                    motor.set_speed_deg_s(speed_cmd)

                    angle = ""
                    temp = ""
                    iq = ""
                    spd_raw = ""
                    enc = ""

                    if READ_ANGLE:
                        angle = motor.read_singleturn_angle_deg()

                    if READ_STATUS:
                        st = motor.read_status()
                        temp = st.temperature_C
                        iq = st.torque_current
                        spd_raw = st.speed_raw
                        enc = st.encoder_pos

                    w.writerow([
                        f"{t:.3f}",
                        f"{speed_cmd:.2f}",
                        f"{angle:.2f}" if angle != "" else "",
                        temp,
                        iq,
                        spd_raw,
                        enc,
                        err_voltage,
                        err_flags,
                        "ok",
                    ])
                    counts["ok"] += 1

                except TimeoutError:
                    counts["timeouts"] += 1
                    w.writerow([f"{t:.3f}", f"{speed_cmd:.2f}", "", "", "", "", "", err_voltage, err_flags, "timeout"])
                except GyemsProtocolError as e:
                    counts["proto_err"] += 1
                    w.writerow([f"{t:.3f}", f"{speed_cmd:.2f}", "", "", "", "", "", err_voltage, err_flags, f"proto_err:{e}"])
                except Exception as e:
                    counts["other_err"] += 1
                    w.writerow([f"{t:.3f}", f"{speed_cmd:.2f}", "", "", "", "", "", err_voltage, err_flags, f"err:{e}"])

                # small live print every ~2 seconds
                if counts["loops"] % int(2 * LOOP_HZ) == 0:
                    print(
                        f"\rT={t/60:5.1f} min | cmd={speed_cmd:7.1f} °/s | ok={counts['ok']} "
                        f"| to={counts['timeouts']} | proto={counts['proto_err']} | other={counts['other_err']}",
                        end=""
                    )

        except KeyboardInterrupt:
            print("\nCtrl+C received. Stopping.")
            w.writerow([f"{time.time()-t0:.3f}", "", "", "", "", "", "", "", "", "keyboard_interrupt"])
        finally:
            # Always stop motor
            try:
                motor.set_speed_deg_s(0.0)
            except Exception:
                pass

            if CLEAR_ERRORS_ON_END:
                try:
                    motor.clear_error_flags()
                except Exception:
                    pass

            motor.close()

    print("\nDone.")
    print("Summary:")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    print(f"CSV: {CSV_FILE}")


if __name__ == "__main__":
    main()

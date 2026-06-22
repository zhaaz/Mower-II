import csv
import time
import math
from datetime import datetime

from GYEMS.gyems_rs485 import GyemsRmdRs485
from KVH_DSP_3100.dsp3100 import DSP3100

# =====================
# FESTE PORTS
# =====================
GYEMS_PORT = "COM4"
DSP_PORT   = "COM3"

# =====================
# TESTPARAMETER
# =====================
DURATION_S = 40 * 60          # 40 Minuten (wie dein Test)
LOOP_HZ = 10.0                # Regelkreis
STATUS_HZ = 1.0               # Health Check
WINDOW_S = 60.0               # Statistik alle 60s

MAX_DPS = 180.0               # 0.5 U/s
K_P = 1.0
DEADBAND_DPS = 0.05
GYRO_SIGN = -1.0              # bei dir: Vorzeichen umgedreht

# Watchdog für Statusabfragen
MAX_STATUS_TIMEOUTS_IN_ROW = 3

CSV_FILE = f"arn_dauertest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def main():
    print("=== ARN Dauertest (TX-only @10Hz, Status@1Hz) ===")
    print(f"GYEMS={GYEMS_PORT}, DSP={DSP_PORT}")
    print(f"Dauer={DURATION_S/60:.1f} min, Loop={LOOP_HZ}Hz, Status={STATUS_HZ}Hz")
    print("CSV:", CSV_FILE)

    # --- DSP ---
    dsp = DSP3100()
    dsp.connect(port=DSP_PORT, baudrate=375000)
    time.sleep(1.0)

    # --- GYEMS ---
    gy = GyemsRmdRs485(port=GYEMS_PORT, motor_id=0x01, baudrate=115200, timeout=0.25)
    gy.connect()

    # --- counters ---
    loops = 0
    speed_cmd_sent = 0

    status_ok = 0
    status_timeouts_total = 0
    status_timeouts_row = 0
    other_errors = 0

    # window stats
    win_start = time.time()
    win_status_timeouts = 0
    win_other_errors = 0

    # scheduling
    dt = 1.0 / LOOP_HZ
    status_dt = 1.0 / STATUS_HZ
    next_status = time.time()

    t0 = time.time()
    next_tick = t0

    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow([
            "t_s",
            "gyro_rate_dps",
            "error_dps",
            "speed_cmd_dps",
            "status_event",
            "status_temp_C",
            "status_speed_raw",
            "status_enc",
        ])

        try:
            while True:
                now = time.time()
                t = now - t0
                if t >= DURATION_S:
                    print("\nReached duration.")
                    break

                # --- 10 Hz pacing ---
                if now < next_tick:
                    time.sleep(min(0.01, next_tick - now))
                    continue
                next_tick += dt
                loops += 1

                # --- control (P + deadband) ---
                rate = dsp.rate_dps
                error = GYRO_SIGN * (-rate)
                if abs(error) < DEADBAND_DPS:
                    error = 0.0

                speed_cmd = clamp(K_P * error, -MAX_DPS, +MAX_DPS)

                # --- TX-only command (no ACK) ---
                gy.set_speed_deg_s_tx_only(speed_cmd)
                speed_cmd_sent += 1

                # --- status check @1Hz (ACK) ---
                status_event = ""
                st_temp = ""
                st_spd = ""
                st_enc = ""

                if now >= next_status:
                    next_status += status_dt
                    try:
                        st = gy.read_status()
                        status_ok += 1
                        status_timeouts_row = 0
                        status_event = "ok"
                        if st:
                            st_temp = st.temperature_C
                            st_spd = st.speed_raw
                            st_enc = st.encoder_pos
                    except TimeoutError:
                        status_timeouts_total += 1
                        win_status_timeouts += 1
                        status_timeouts_row += 1
                        status_event = "timeout"
                        if status_timeouts_row >= MAX_STATUS_TIMEOUTS_IN_ROW:
                            raise RuntimeError("Status watchdog: zu viele Timeouts in Folge")
                    except Exception as e:
                        other_errors += 1
                        win_other_errors += 1
                        status_event = f"err:{type(e).__name__}"

                # --- log one line each loop (10Hz) ---
                w.writerow([
                    f"{t:.3f}",
                    f"{rate:.6f}",
                    f"{error:.6f}",
                    f"{speed_cmd:.3f}",
                    status_event,
                    st_temp,
                    st_spd,
                    st_enc
                ])

                # --- stats window ---
                if now - win_start >= WINDOW_S:
                    elapsed = now - win_start
                    st_to_per_min = (win_status_timeouts / elapsed) * 60.0 if elapsed > 0 else 0.0
                    print(
                        f"\n[STATS] t={t/60:.1f}min | sent={speed_cmd_sent} | "
                        f"status_ok={status_ok} | status_to={status_timeouts_total} "
                        f"({st_to_per_min:.2f}/min window) | other_err={other_errors}"
                    )
                    win_start = now
                    win_status_timeouts = 0
                    win_other_errors = 0

                # small live line every ~0.2s
                if loops % int(0.2 * LOOP_HZ) == 0:
                    print(
                        f"\rω={rate:+7.3f} °/s | cmd={speed_cmd:+7.2f} °/s | status_to={status_timeouts_total}  ",
                        end=""
                    )

        except KeyboardInterrupt:
            print("\nCtrl+C")
        finally:
            print("\nStopping motor...")
            try:
                # try a few times
                for _ in range(3):
                    try:
                        gy.set_speed_deg_s_tx_only(0.0)
                        break
                    except Exception:
                        time.sleep(0.05)
            except Exception:
                pass

            try:
                gy.close()
            except Exception:
                pass
            try:
                dsp.disconnect()
            except Exception:
                pass

    print("Done.")
    print(f"loops={loops}, speed_cmd_sent={speed_cmd_sent}")
    print(f"status_ok={status_ok}, status_timeouts_total={status_timeouts_total}, other_errors={other_errors}")
    print("CSV:", CSV_FILE)


if __name__ == "__main__":
    main()
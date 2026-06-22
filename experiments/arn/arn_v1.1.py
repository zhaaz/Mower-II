# ARN/arn_v1_1_p_deadband.py
import time

from GYEMS.gyems_rs485 import GyemsRmdRs485
from KVH_DSP_3100.dsp3100 import DSP3100


# =====================
# FESTE PORT-ZUORDNUNG
# =====================
GYEMS_PORT = "COM4"
DSP_PORT   = "COM3"

# =====================
# LOOP / LIMITS
# =====================
LOOP_HZ = 10.0
DT = 1.0 / LOOP_HZ

MAX_DPS = 180.0      # 0.5 U/s

# =====================
# P-REGLER PARAMETER
# =====================
K_P = 1.0            # Verstärkung
DEADBAND_DPS = 0.05  # Totzone für Gyro (°/s)

# Vorzeichen (du hast gesagt: umdrehen!)
GYRO_SIGN = -1.0     # <- falls doch falsch: +1.0


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def main():
    print("=== ARN v1.1 (P + Deadband) Start ===")

    # -----------------
    # 1) DSP3100 starten
    # -----------------
    dsp = DSP3100()
    dsp.connect(port=DSP_PORT, baudrate=375000)
    print("DSP3100 läuft")

    # Thread anlaufen lassen
    time.sleep(1.0)

    # -----------------
    # 2) GYEMS starten
    # -----------------
    gyems = GyemsRmdRs485(
        port=GYEMS_PORT,
        motor_id=0x01,
        baudrate=115200,
        timeout=0.25
    )
    gyems.connect()
    print("GYEMS verbunden")

    # -----------------
    # 3) Testfahrt
    # -----------------
    print("Testfahrt: 2s rechts")
    gyems.set_speed_deg_s(+90.0)
    time.sleep(2.0)

    print("Testfahrt: 2s links")
    gyems.set_speed_deg_s(-90.0)
    time.sleep(2.0)

    print("Stop")
    gyems.set_speed_deg_s(0.0)
    time.sleep(1.0)

    # -----------------
    # 4) REGELKREIS (P)
    # -----------------
    print("Starte Regelkreis (P + Deadband, Ctrl+C zum Abbruch)")
    t_last = time.time()

    try:
        while True:
            t_now = time.time()
            dt = t_now - t_last
            t_last = t_now

            # a) Gyro-Rate (°/s)
            rate_dps = dsp.rate_dps

            # b) Fehler (Soll = 0)
            error = GYRO_SIGN * (-rate_dps)

            # c) Deadband
            if abs(error) < DEADBAND_DPS:
                error = 0.0

            # d) P-Regler
            speed_cmd = K_P * error

            # e) Begrenzen
            speed_cmd = clamp(speed_cmd, -MAX_DPS, +MAX_DPS)

            # f) An Motor senden
            gyems.set_speed_deg_s(speed_cmd)

            # Debug
            print(
                f"\rω_gyro: {rate_dps:+7.3f} °/s | "
                f"e: {error:+7.3f} | "
                f"cmd: {speed_cmd:+7.2f}",
                end=""
            )

            # 10 Hz halten
            sleep_time = DT - (time.time() - t_now)
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\nAbbruch durch Benutzer")

    finally:
        print("Stoppe Motor & schließe Verbindungen")
        try:
            gyems.set_speed_deg_s(0.0)
        except Exception:
            pass

        gyems.close()
        dsp.disconnect()

        print("=== ARN v1.1 Ende ===")


if __name__ == "__main__":
    main()

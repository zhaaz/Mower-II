# ARN/arn_v0.py
import time

from GYEMS.gyems_rs485 import GyemsRmdRs485
from KVH_DSP_3100.dsp3100 import DSP3100


# =====================
# FESTE PORT-ZUORDNUNG
# =====================
GYEMS_PORT = "COM4"
DSP_PORT   = "COM3"

# =====================
# PARAMETER
# =====================
LOOP_HZ = 10.0
DT = 1.0 / LOOP_HZ

MAX_DPS = 180.0      # 0.5 U/s
K_GYRO  = 1.0        # Verstärkung
GYRO_SIGN = 1.0      # falls Drehsinn falsch -> -1.0


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def main():
    print("=== ARN v0 Start ===")

    # -----------------
    # 1) DSP3100 starten
    # -----------------
    dsp = DSP3100()
    dsp.connect(port=DSP_PORT, baudrate=375000)
    print("DSP3100 läuft")

    # kleine Wartezeit, damit Thread Daten sammelt
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
    # 3) GYEMS-Testfahrt
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
    # 4) REGELKREIS (10 Hz)
    # -----------------
    print("Starte Regelkreis (Ctrl+C zum Abbruch)")
    t_last = time.time()

    try:
        while True:
            t_now = time.time()
            dt = t_now - t_last
            t_last = t_now

            # a) Gyro-Rate aus DSP3100
            rate_dps = dsp.rate_dps    # direkt aus deiner Klasse

            # b) Gegendrehen berechnen
            speed_cmd = -K_GYRO * GYRO_SIGN * rate_dps

            # c) Begrenzen
            speed_cmd = clamp(speed_cmd, -MAX_DPS, +MAX_DPS)

            # d) An GYEMS senden
            gyems.set_speed_deg_s(speed_cmd)

            # Debug-Ausgabe
            print(
                f"\rDSP rate: {rate_dps:+7.2f} °/s | "
                f"GYEMS cmd: {speed_cmd:+7.2f} °/s",
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

        print("=== ARN v0 Ende ===")


if __name__ == "__main__":
    main()

import csv
import time
import math
from datetime import datetime

import serial
import serial.tools.list_ports

# =======================
# CONFIG
# =======================
PORT = "COM3"            # <-- anpassen
BAUD = 115200            # <-- anpassen falls nötig
TIMEOUT = 0.2

DURATION_S = 10 * 60     # 10 min
LOOP_HZ = 10             # 10 Hz
CSV_FILE = f"dsp3100_reliability_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

# Wenn dein DSP3100 ASCII-Zeilen ausgibt, die als Zahl interpretierbar sind: True.
# Wenn binär: False und die Funktion read_gyro_rate_dps() anpassen.
ASSUME_ASCII_LINE = True
# =======================


def list_ports():
    return [p.device for p in serial.tools.list_ports.comports()]


def read_gyro_rate_dps(ser: serial.Serial) -> float:
    """
    Lese Drehrate vom DSP3100 und gib °/s als float zurück.

    Standard: ASCII-Line Mode (eine Zeile enthält eine Zahl, z.B. "0.1234\\n").
    Wenn dein Output anders aussieht (mehr Spalten / binär), passe diese Funktion an.
    """
    if ASSUME_ASCII_LINE:
        line = ser.readline()
        if not line:
            raise TimeoutError("DSP3100 readline timeout")
        s = line.decode(errors="ignore").strip()

        # Falls Zeile mehrere Felder enthält, hier anpassen, z.B.:
        # s = s.split(",")[0]

        return float(s.replace(",", "."))
    else:
        raise NotImplementedError("Binary parsing not implemented. Implement read_gyro_rate_dps().")


def main():
    print("DSP3100 Reliability Test (10 min)")
    print("Ports verfügbar:", ", ".join(list_ports()) or "(keine)")
    print(f"Port={PORT} Baud={BAUD} Loop={LOOP_HZ} Hz Dauer={DURATION_S/60:.1f} min")
    print(f"CSV: {CSV_FILE}")
    print("Ctrl+C zum Abbrechen.")

    counts = {
        "loops": 0,
        "ok": 0,
        "timeouts": 0,
        "parse_err": 0,
        "other_err": 0,
        "nan_inf": 0,
        "min_dps": None,
        "max_dps": None,
    }

    t0 = time.time()
    next_tick = t0

    with serial.Serial(PORT, BAUD, timeout=TIMEOUT) as ser, \
         open(CSV_FILE, "w", newline="", encoding="utf-8") as f:

        w = csv.writer(f, delimiter=";")
        w.writerow(["t_s", "gyro_rate_dps", "event", "raw_or_msg"])

        try:
            ser.reset_input_buffer()
        except Exception:
            pass

        try:
            while True:
                now = time.time()
                t = now - t0
                if t >= DURATION_S:
                    print("\nReached duration.")
                    break

                if now < next_tick:
                    time.sleep(min(0.01, next_tick - now))
                    continue
                next_tick += 1.0 / LOOP_HZ
                counts["loops"] += 1

                try:
                    rate = read_gyro_rate_dps(ser)

                    if not math.isfinite(rate):
                        counts["nan_inf"] += 1
                        w.writerow([f"{t:.3f}", "", "nan_or_inf", str(rate)])
                        continue

                    if counts["min_dps"] is None or rate < counts["min_dps"]:
                        counts["min_dps"] = rate
                    if counts["max_dps"] is None or rate > counts["max_dps"]:
                        counts["max_dps"] = rate

                    w.writerow([f"{t:.3f}", f"{rate:.6f}", "ok", ""])
                    counts["ok"] += 1

                except TimeoutError as e:
                    counts["timeouts"] += 1
                    w.writerow([f"{t:.3f}", "", "timeout", str(e)])
                except ValueError as e:
                    counts["parse_err"] += 1
                    w.writerow([f"{t:.3f}", "", "parse_err", str(e)])
                except Exception as e:
                    counts["other_err"] += 1
                    w.writerow([f"{t:.3f}", "", "other_err", str(e)])

                if counts["loops"] % int(2 * LOOP_HZ) == 0:
                    print(
                        f"\rT={t/60:4.1f} min | ok={counts['ok']} | to={counts['timeouts']} "
                        f"| parse={counts['parse_err']} | other={counts['other_err']}",
                        end=""
                    )

        except KeyboardInterrupt:
            print("\nCtrl+C received.")
            w.writerow([f"{time.time()-t0:.3f}", "", "keyboard_interrupt", ""])

    print("\nDone.\nSummary:")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    print(f"CSV: {CSV_FILE}")


if __name__ == "__main__":
    main()

import serial
import struct
import time
import threading
import queue

PORT = "COM4"
BAUD = 115200
TIMEOUT = 0.15
MOTOR_ID = 0x01

POLL_DT = 0.2          # Anzeige-Update
SPEED_STEP_DPS = 30.0
MAX_DPS = 720.0

def checksum(data: bytes) -> int:
    return sum(data) & 0xFF

def build_frame(cmd: int, motor_id: int, data: bytes = b"") -> bytes:
    header = bytes([0x3E, cmd, motor_id, len(data)])
    frame = header + bytes([checksum(header)])
    if data:
        frame += data + bytes([checksum(data)])
    return frame

def txrx(ser: serial.Serial, cmd: int, data: bytes = b"", resp_len: int = 16, wait: float = 0.03) -> bytes:
    # flush old bytes to avoid mixing frames
    try:
        ser.reset_input_buffer()
    except Exception:
        pass

    ser.write(build_frame(cmd, MOTOR_ID, data))
    ser.flush()
    time.sleep(wait)

    # read up to resp_len bytes, bounded by TIMEOUT
    return ser.read(resp_len)

def read_singleturn_angle_deg(ser: serial.Serial) -> float:
    resp = txrx(ser, 0x94, resp_len=16)
    if len(resp) < 7:
        raise IOError(f"angle resp too short ({len(resp)} bytes)")
    raw = struct.unpack("<H", resp[5:7])[0]
    return raw * 0.01

def set_speed_dps(ser: serial.Serial, dps: float):
    dps = max(-MAX_DPS, min(MAX_DPS, dps))
    val = int(dps * 100)           # 0.01 deg/s
    data = struct.pack("<i", val)  # int32 LE
    resp = txrx(ser, 0xA2, data=data, resp_len=32)
    return dps, resp

def input_thread(cmd_queue: queue.Queue):
    # This works reliably in PyCharm: type a command and press Enter
    while True:
        try:
            line = input().strip()
        except EOFError:
            return
        cmd_queue.put(line)

def main():
    cmd_queue = queue.Queue()
    threading.Thread(target=input_thread, args=(cmd_queue,), daemon=True).start()

    speed = 0.0

    print("GYEMS Live Control (Enter-based, PyCharm-sicher)")
    print("Befehle (tippen + Enter): w=schneller, s=langsamer, 0=stop, q=quit, oder Zahl z.B. 360")
    print(f"Port: {PORT} @ {BAUD}")

    with serial.Serial(PORT, BAUD, timeout=TIMEOUT) as ser:
        # Stop at start
        try:
            set_speed_dps(ser, 0.0)
        except Exception:
            pass

        t_next = time.time()

        try:
            while True:
                # process all queued commands
                while not cmd_queue.empty():
                    cmd = cmd_queue.get_nowait().lower()

                    if cmd == "w":
                        speed += SPEED_STEP_DPS
                        speed, _ = set_speed_dps(ser, speed)
                        print(f"Speed set: {speed:.1f} °/s")
                    elif cmd == "s":
                        speed -= SPEED_STEP_DPS
                        speed, _ = set_speed_dps(ser, speed)
                        print(f"Speed set: {speed:.1f} °/s")
                    elif cmd == "0":
                        speed = 0.0
                        speed, _ = set_speed_dps(ser, speed)
                        print(f"Speed set: {speed:.1f} °/s")
                    elif cmd == "q":
                        print("Quit -> stop")
                        speed = 0.0
                        try:
                            set_speed_dps(ser, 0.0)
                        except Exception:
                            pass
                        return
                    else:
                        # direct numeric speed input
                        try:
                            val = float(cmd.replace(",", "."))
                            speed = val
                            speed, _ = set_speed_dps(ser, speed)
                            print(f"Speed set: {speed:.1f} °/s")
                        except ValueError:
                            print("Unbekannter Befehl. Nutze: w, s, 0, q oder Zahl (z.B. 360)")

                now = time.time()
                if now >= t_next:
                    t_next = now + POLL_DT
                    try:
                        ang = read_singleturn_angle_deg(ser)
                        print(f"Angle: {ang:8.2f}° | SpeedCmd: {speed:7.1f} °/s")
                    except Exception as e:
                        print(f"COMM ERROR: {e}")

                time.sleep(0.01)

        except KeyboardInterrupt:
            # clean exit on Ctrl+C
            print("\nCtrl+C -> stop")
            try:
                set_speed_dps(ser, 0.0)
            except Exception:
                pass

if __name__ == "__main__":
    main()

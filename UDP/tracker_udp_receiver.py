"""
tracker_udp_receiver.py

Erster Versuch für UDP Trackerdaten Empfang.
Liest Daten aus WatchWindow.
Port 10000

Autor: Andreas Wehner
Datum: 2026-02-03
"""


import socket
import time
import math

PORT = 10000
BUFFER_SIZE = 8192
NO_DATA_TIMEOUT_S = 5.0

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("0.0.0.0", PORT))

# Damit wir "seit X Sekunden keine Daten" erkennen können:
sock.settimeout(0.5)

print(f"Lausche auf UDP Port {PORT} ...")


def decode_udp_payload(data: bytes) -> str:
    try:
        return data.decode("utf-8").strip()
    except UnicodeDecodeError:
        return data.decode("latin-1").strip()


def parse_sa_watch_line(line: str):
    """
    Erwartet ungefähr:
    '...| X,    3744.50, | Y,    1309.42, | Z,      54.65, | ... Units: (mm) ...'

    Rückgabe: dict mit timestamp/x/y/z/unit/measurement_valid
    """
    parts = [p.strip() for p in line.split("|")]

    x = y = z = None
    unit = None

    for p in parts:
        if not p:
            continue

        # Einheit finden, z.B. "Units: (mm)"
        if "Units:" in p:
            tail = p.split("Units:", 1)[1].strip().strip(",").strip()
            if tail.startswith("(") and tail.endswith(")"):
                tail = tail[1:-1].strip()
            unit = tail if tail else "unknown"
            continue

        # X/Y/Z finden: typischerweise "X, 3744.50," etc.
        if p.startswith("X"):
            tokens = [t.strip() for t in p.split(",")]
            if len(tokens) >= 2 and tokens[1]:
                x = float(tokens[1])
            continue

        if p.startswith("Y"):
            tokens = [t.strip() for t in p.split(",")]
            if len(tokens) >= 2 and tokens[1]:
                y = float(tokens[1])
            continue

        if p.startswith("Z"):
            tokens = [t.strip() for t in p.split(",")]
            if len(tokens) >= 2 and tokens[1]:
                z = float(tokens[1])
            continue

    # measurement_valid: wir brauchen x,y,z und sie dürfen nicht NaN/Inf sein
    measurement_valid = (
        x is not None and y is not None and z is not None
        and math.isfinite(x) and math.isfinite(y) and math.isfinite(z)
    )

    return {
        "timestamp": time.time(),
        "x": x,
        "y": y,
        "z": z,
        "unit": unit or "unknown",
        "measurement_valid": measurement_valid,
        "raw": line,  # optional: hilfreich fürs Debuggen
    }


last_rx_time = None
no_data_reported = False

while True:
    now = time.time()

    # "Keine Daten seit X Sekunden" melden (einmalig, bis wieder Daten kommen)
    if last_rx_time is not None:
        gap = now - last_rx_time
        if gap >= NO_DATA_TIMEOUT_S and not no_data_reported:
            print(f"\nWARNUNG: Seit {gap:.1f} s keine UDP-Daten empfangen.")
            no_data_reported = True

    try:
        data, addr = sock.recvfrom(BUFFER_SIZE)
    except TimeoutError:
        continue

    last_rx_time = time.time()
    no_data_reported = False

    line = decode_udp_payload(data)
    m = parse_sa_watch_line(line)

    if m["measurement_valid"]:
        print(
            f't={m["timestamp"]:.3f}  '
            f'X={m["x"]:.2f}  Y={m["y"]:.2f}  Z={m["z"]:.2f}  '
            f'[{m["unit"]}]  '
            f'(src {addr[0]}:{addr[1]})'
        )
    else:
        print(
            f't={m["timestamp"]:.3f}  INVALID  '
            f'(src {addr[0]}:{addr[1]})  raw="{m["raw"]}"'
        )

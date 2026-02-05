# gyems_rs485.py
from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any

import serial
import serial.tools.list_ports


class GyemsProtocolError(Exception):
    pass


@dataclass
class GyemsStatus:
    temperature_C: int
    torque_current: int
    speed_raw: int
    encoder_pos: int


@dataclass
class GyemsModelInfo:
    driver: str
    motor: str
    hw_version: Optional[float]
    fw_version: Optional[float]
    raw_data: bytes


class GyemsRmdRs485:
    """
    Minimal GYEMS RMD-S RS-485 driver (Frame-based, length-aware, checksummed).

    Implemented commands (minimal subset + absolute position):
      - 0x12 Read Model Info
      - 0x9C Read Status
      - 0x9A Read Error Flags (raw parse, basic fields)
      - 0x9B Clear Error Flags
      - 0x80 Shutdown (stop)
      - 0x94 Read Singleturn Angle
      - 0xA2 Set Speed (deg/s)
      - 0xA3 Move to Absolute Position (deg)

    Frame format used:
      [0]=0x3E, [1]=CMD, [2]=ID, [3]=LEN, [4]=CHK_HEAD, [5..]=DATA(LEN), [end]=CHK_DATA (if LEN>0)
    Checksums: sum(bytes) & 0xFF
    """

    HEADER_BYTE = 0x3E

    def __init__(
        self,
        port: str,
        motor_id: int = 0x01,
        baudrate: int = 115200,
        timeout: float = 0.2,
        inter_cmd_delay: float = 0.02,
    ):
        self.port = port
        self.motor_id = motor_id & 0xFF
        self.baudrate = baudrate
        self.timeout = float(timeout)
        self.inter_cmd_delay = float(inter_cmd_delay)
        self.ser: Optional[serial.Serial] = None

    # ---------- utilities ----------
    @staticmethod
    def list_ports() -> list[str]:
        return [p.device for p in serial.tools.list_ports.comports()]

    @staticmethod
    def _chk(data: bytes) -> int:
        return sum(data) & 0xFF

    def is_connected(self) -> bool:
        return self.ser is not None and self.ser.is_open

    def connect(self) -> None:
        if self.is_connected():
            return
        self.ser = serial.Serial(
            self.port,
            self.baudrate,
            timeout=self.timeout,
            bytesize=8,
            parity="N",
            stopbits=1,
        )
        # Clear any garbage
        try:
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
        except Exception:
            pass

    def close(self) -> None:
        if self.ser is not None:
            try:
                self.ser.close()
            finally:
                self.ser = None

    # ---------- frame I/O ----------
    def _build_frame(self, cmd: int, data: bytes = b"") -> bytes:
        cmd &= 0xFF
        data_len = len(data)
        header = bytes([self.HEADER_BYTE, cmd, self.motor_id, data_len])
        head_chk = self._chk(header)
        frame = header + bytes([head_chk])
        if data_len:
            frame += data + bytes([self._chk(data)])
        return frame

    def _read_exact(self, n: int) -> bytes:
        assert self.ser is not None
        buf = bytearray()
        deadline = time.time() + self.timeout
        while len(buf) < n and time.time() < deadline:
            chunk = self.ser.read(n - len(buf))
            if chunk:
                buf.extend(chunk)
            else:
                time.sleep(0.001)
        return bytes(buf)

    def _read_frame(self) -> Tuple[int, int, bytes]:
        """
        Read one response frame and return (cmd, motor_id, data).
        """
        assert self.ser is not None

        # Sync to 0x3E (protect against noise/partial bytes)
        deadline = time.time() + self.timeout
        while True:
            b = self.ser.read(1)
            if b == b"":
                if time.time() >= deadline:
                    raise TimeoutError("Timeout waiting for frame header (0x3E)")
                continue
            if b[0] == self.HEADER_BYTE:
                break

        # Read remaining fixed header fields: CMD, ID, LEN, CHK_HEAD
        rest = self._read_exact(4)
        if len(rest) < 4:
            raise TimeoutError("Timeout reading header fields")
        cmd, mid, length, chk_head = rest[0], rest[1], rest[2], rest[3]

        header = bytes([self.HEADER_BYTE, cmd, mid, length])
        if self._chk(header) != chk_head:
            raise GyemsProtocolError(
                f"Header checksum mismatch (got 0x{chk_head:02X}, expected 0x{self._chk(header):02X})"
            )

        data = b""
        if length > 0:
            payload = self._read_exact(length + 1)  # data + chk_data
            if len(payload) < length + 1:
                raise TimeoutError("Timeout reading payload")
            data = payload[:length]
            chk_data = payload[length]
            if self._chk(data) != chk_data:
                raise GyemsProtocolError(
                    f"Data checksum mismatch (got 0x{chk_data:02X}, expected 0x{self._chk(data):02X})"
                )

        return cmd, mid, data

    def _txrx(self, cmd: int, data: bytes = b"") -> Tuple[int, int, bytes]:
        """
        Send command and read one response frame.
        """
        if not self.is_connected():
            raise RuntimeError("Not connected")

        assert self.ser is not None
        frame = self._build_frame(cmd, data)


        self.ser.write(frame)
        self.ser.flush()
        time.sleep(self.inter_cmd_delay)

        return self._read_frame()

    # ---------- high-level commands ----------
    def read_model_info(self) -> GyemsModelInfo:
        cmd, mid, data = self._txrx(0x12)
        # data length is typically 58 (as you saw), but we parse defensively
        driver = data[0:20].decode(errors="ignore").strip("\x00").strip() if len(data) >= 20 else ""
        motor = data[20:40].decode(errors="ignore").strip("\x00").strip() if len(data) >= 40 else ""
        hw_version = None
        fw_version = None
        if len(data) >= 42:
            hw_version = data[40] / 10.0
            fw_version = data[41] / 10.0
        return GyemsModelInfo(driver=driver, motor=motor, hw_version=hw_version, fw_version=fw_version, raw_data=data)

    def read_status(self, retries: int = 2) -> GyemsStatus:
        last_exc = None
        for attempt in range(retries + 1):
            try:
                cmd, mid, data = self._txrx(0x9C)
                if len(data) < 7:
                    raise GyemsProtocolError(f"Status payload too short: {len(data)} bytes")
                temp = struct.unpack("b", data[0:1])[0]
                iq = struct.unpack("<h", data[1:3])[0]
                spd = struct.unpack("<h", data[3:5])[0]
                enc = struct.unpack("<H", data[5:7])[0]
                return GyemsStatus(temperature_C=temp, torque_current=iq, speed_raw=spd, encoder_pos=enc)

            except TimeoutError as e:
                last_exc = e
                # nur bei Fehler: resync/flush
                try:
                    if self.ser:
                        self.ser.reset_input_buffer()
                except Exception:
                    pass
                time.sleep(0.02)  # kurzer Abstand vor Retry

        raise last_exc  # type: ignore

    def read_error_flags(self) -> Dict[str, Any]:
        """
        Error frame structure varies by firmware. We expose raw fields + a couple of
        best-effort parses.
        """
        cmd, mid, data = self._txrx(0x9A)
        out: Dict[str, Any] = {"raw_data": data}
        if len(data) >= 1:
            out["temperature_C"] = struct.unpack("b", data[0:1])[0]
        # Some firmwares encode voltage in bytes 2..3 (uint16, 0.1V/LSB). Best-effort:
        if len(data) >= 4:
            out["voltage_raw_u16"] = struct.unpack("<H", data[2:4])[0]
            out["voltage_V_guess"] = out["voltage_raw_u16"] * 0.1
        # Often a flags byte exists; we expose last byte as guess:
        if len(data) >= 7:
            out["flags_guess_byte"] = data[6]
        return out

    def clear_error_flags(self) -> None:
        self._txrx(0x9B)

    def shutdown(self) -> None:
        # Immediate stop / shutdown
        self._txrx(0x80)

    def read_singleturn_angle_deg(self) -> float:
        cmd, mid, data = self._txrx(0x94)
        if len(data) < 2:
            raise GyemsProtocolError(f"Angle payload too short: {len(data)} bytes")
        ang_u16 = struct.unpack("<H", data[0:2])[0]
        return ang_u16 * 0.01

    def set_speed_deg_s(self, speed_deg_s: float) -> None:
        val = int(speed_deg_s * 100)  # 0.01 deg/s units
        payload = struct.pack("<i", val)
        self._txrx(0xA2, payload)

    def move_to_abs_angle_deg(self, angle_deg: float) -> None:
        """
        Absolute position move. Payload is int64 of 0.01° units.
        """
        val = int(angle_deg * 100)  # 0.01 deg
        payload = struct.pack("<q", val)
        self._txrx(0xA3, payload)

    def set_speed_deg_s_tx_only(self, speed_dps: float):
        """
        Speed command ohne Antwort abzuwarten (TX-only).
        Ideal für Regelkreis bei 10 Hz, weil Windows/USB ACKs sporadisch ausbleiben können.
        """
        val = int(speed_dps * 100)  # 0.01 °/s LSB
        payload = struct.pack("<i", val)  # <<< FIX
        frame = self._build_frame(0xA2, payload)
        self.ser.write(frame)
        self.ser.flush()

    def drain_rx(self, settle_s: float = 0.01, rounds: int = 2) -> int:
        """
        Liest alle aktuell anstehenden Bytes aus dem RX-Buffer und verwirft sie.
        Nützlich, wenn TX-only Commands trotzdem Antworten erzeugen, die wir nicht auswerten.
        Returns: Anzahl verworfener Bytes.
        """
        if not self.is_connected():
            return 0
        assert self.ser is not None

        drained = 0
        for _ in range(rounds):
            time.sleep(settle_s)  # kurz warten, damit evtl. Antwortbytes eintreffen
            n = getattr(self.ser, "in_waiting", 0)
            if n and n > 0:
                _ = self.ser.read(n)
                drained += n
            else:
                break
        return drained
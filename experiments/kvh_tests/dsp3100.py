# experiments/kvh_tests/dsp3100.py

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable

import serial


LSB_TO_DEG = 2.384e-8
DEFAULT_BAUDRATE = 375000
DEFAULT_SAMPLING_RATE_HZ = 1024.0

LogCallback = Callable[[str], None]


@dataclass(frozen=True)
class DSP3100Snapshot:
    connected: bool
    angle_deg: float
    rate_dps: float
    drift_dps: float
    valid_packets: int
    skipped_bytes: int
    drift_active: bool


class DSP3100:
    """Minimaler Treiber fuer KVH DSP-3100.

    Der Sensor liefert 5-Byte-Pakete. Aus den ersten drei Bytes wird eine
    inkrementelle Winkelanderung berechnet. Diese Klasse integriert daraus
    einen relativen Winkel in Grad.

    Diese Version ist bewusst testfreundlich:
        - keine print-Ausgaben im Treiber
        - Thread-sicherer Snapshot
        - optionaler Log-Callback
        - Connect wirft Fehler, statt sie nur zu drucken
    """

    def __init__(
            self,
            *,
            sampling_rate_hz: float = DEFAULT_SAMPLING_RATE_HZ,
            on_log: LogCallback | None = None,
    ) -> None:
        self.ser: serial.Serial | None = None
        self.thread: threading.Thread | None = None
        self.running = False

        self.angle_deg = 0.0
        self.rate_dps = 0.0
        self.valid_packets = 0
        self.skipped_bytes = 0
        self.lock = threading.Lock()

        self.drift_dps = 0.0
        self.sampling_rate_hz = float(sampling_rate_hz)

        self._drift_active = False
        self._drift_sum_deg = 0.0
        self._drift_count = 0
        self._drift_start = 0.0
        self._drift_duration_s = 0.0

        self.on_log = on_log

    @property
    def connected(self) -> bool:
        return self.ser is not None and bool(getattr(self.ser, "is_open", False)) and self.running

    def connect(self, port: str, baudrate: int = DEFAULT_BAUDRATE) -> None:
        if self.connected:
            return

        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_ODD,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.2,
        )

        self.running = True
        self.thread = threading.Thread(target=self._read_loop, daemon=True)
        self.thread.start()
        self._log(f"Verbunden mit {port} @ {baudrate} Baud.")

    def disconnect(self) -> None:
        self.running = False

        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

        if self.ser is not None:
            try:
                if self.ser.is_open:
                    self.ser.close()
            finally:
                self.ser = None

        self._log("Verbindung geschlossen.")

    def _read_loop(self) -> None:
        buffer = bytearray()
        skipped = 0

        while self.running:
            ser = self.ser
            if ser is None:
                time.sleep(0.05)
                continue

            try:
                data = ser.read(1)
            except Exception as exc:
                self._log(f"Lesefehler: {exc}")
                self.running = False
                break

            if not data:
                continue

            buffer += data

            while len(buffer) >= 5:
                block = bytes(buffer[:5])
                checksum = (~sum(block[0:4])) & 0xFF
                status_ok = (block[3] & 0x01) == 0

                if block[4] == checksum and status_ok:
                    angle_change_deg = self._decode_angle_change_deg(block)
                    corrected_change_deg = self._apply_drift(angle_change_deg)
                    rate_dps = corrected_change_deg * self.sampling_rate_hz

                    with self.lock:
                        self.angle_deg += corrected_change_deg
                        self.rate_dps = rate_dps
                        self.valid_packets += 1
                        self.skipped_bytes += skipped

                    skipped = 0
                    buffer = buffer[5:]
                else:
                    buffer = buffer[1:]
                    skipped += 1
                    with self.lock:
                        self.skipped_bytes += 1

    def _apply_drift(self, angle_change_deg: float) -> float:
        if self._drift_active:
            now = time.time()
            self._drift_sum_deg += angle_change_deg
            self._drift_count += 1

            if now - self._drift_start >= self._drift_duration_s:
                duration = now - self._drift_start
                if duration > 0.0 and self._drift_count > 0:
                    drift = self._drift_sum_deg / duration
                    with self.lock:
                        self.drift_dps = drift
                    self._log(f"Driftmessung abgeschlossen: {drift:.10f} deg/s aus {self._drift_count} Paketen.")
                else:
                    self._log("Driftmessung fehlgeschlagen.")
                self._drift_active = False

        drift_correction_deg = self.drift_dps / self.sampling_rate_hz
        return angle_change_deg - drift_correction_deg

    @staticmethod
    def _decode_angle_change_deg(packet: bytes) -> float:
        raw = int.from_bytes(packet[0:3][::-1], byteorder="little", signed=True)
        return raw * LSB_TO_DEG * -2.0

    def snapshot(self) -> DSP3100Snapshot:
        with self.lock:
            return DSP3100Snapshot(
                connected=self.connected,
                angle_deg=float(self.angle_deg),
                rate_dps=float(self.rate_dps),
                drift_dps=float(self.drift_dps),
                valid_packets=int(self.valid_packets),
                skipped_bytes=int(self.skipped_bytes),
                drift_active=bool(self._drift_active),
            )

    def get_angle(self) -> float:
        return self.snapshot().angle_deg

    def get_rate(self) -> float:
        return self.snapshot().rate_dps

    def get_drift(self) -> float:
        return self.snapshot().drift_dps

    def reset_angle(self) -> None:
        with self.lock:
            self.angle_deg = 0.0
            self.rate_dps = 0.0
        self._log("Winkel auf 0 gesetzt.")

    def determine_drift(self, seconds: float) -> None:
        if seconds <= 0.0:
            raise ValueError("Driftdauer muss groesser 0 sein.")

        with self.lock:
            self._drift_sum_deg = 0.0
            self._drift_count = 0
            self._drift_duration_s = float(seconds)
            self._drift_start = time.time()
            self._drift_active = True
            self.drift_dps = 0.0

        self._log(f"Driftmessung gestartet: {seconds:.1f} s. Sensor ruhig halten.")

    def _log(self, text: str) -> None:
        if self.on_log is not None:
            self.on_log(text)

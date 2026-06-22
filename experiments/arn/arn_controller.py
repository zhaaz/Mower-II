# ARN/arn_controller.py
from __future__ import annotations

import time
import threading
from dataclasses import dataclass
from typing import Optional

from GYEMS.gyems_rs485 import GyemsRmdRs485, GyemsStatus
from KVH_DSP_3100.dsp3100 import DSP3100


@dataclass
class ArnParams:
    loop_hz: float = 10.0
    status_hz: float = 1.0

    kp: float = 1.0
    deadband_dps: float = 0.05
    gyro_sign: float = -1.0          # bei dir: umgedreht
    max_dps: float = 180.0           # 0.5 rps

    # Status watchdog: nur wenn Status X-mal in Folge final scheitert -> stop
    status_fail_max_in_row: int = 5


@dataclass
class ArnSnapshot:
    t_s: float = 0.0
    running: bool = False
    connected: bool = False

    dsp_rate_dps: float = 0.0
    dsp_angle_deg: float = 0.0
    dsp_heading_deg: float = 0.0     # 0° = Nord (nach Zero)

    cmd_dps: float = 0.0

    gyems_status: Optional[GyemsStatus] = None
    gyems_angle_deg: float = 0.0     # raw singleturn (0..360)
    gyems_heading_deg: float = 0.0   # 0° = Nord (nach Zero)

    status_ok: int = 0
    status_timeouts: int = 0
    status_fail_row: int = 0

    last_error: str = ""


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class ArnController:
    """
    Headless ARN controller:
      - DSP3100 läuft in eigener Thread-Logik (deine Klasse)
      - 10 Hz: Speed command TX-only (keine ACK-Abhängigkeit)
      - 1 Hz: read_status() + read_singleturn_angle_deg() (ACK), Watchdog
      - snapshot für GUI (thread-safe)
      - Zero-Funktion setzt aktuelle Orientierung auf 0° (= Nord)
    """

    def __init__(self, params: Optional[ArnParams] = None):
        self.params = params or ArnParams()

        self.dsp: Optional[DSP3100] = None
        self.gy: Optional[GyemsRmdRs485] = None

        self._t0 = 0.0
        self._run_evt = threading.Event()

        self._control_thread: Optional[threading.Thread] = None
        self._status_thread: Optional[threading.Thread] = None

        self._lock = threading.Lock()          # schützt snapshot + offsets + error
        self._io_lock = threading.Lock()       # schützt ACK-I/O (Status/Angle)

        self._snap = ArnSnapshot()

        self._status_ok = 0
        self._status_to = 0
        self._status_fail_row = 0

        # Zero offsets: heading = (angle - offset) mod 360
        self._dsp_zero_offset = 0.0
        self._gyems_zero_offset = 0.0

    # ---------- lifecycle ----------
    def connect(self, dsp_port: str, gyems_port: str) -> None:
        with self._lock:
            self._snap = ArnSnapshot()
            self._snap.connected = False
            self._snap.last_error = ""

        # DSP
        self.dsp = DSP3100()
        self.dsp.connect(port=dsp_port, baudrate=375000)

        # GYEMS
        self.gy = GyemsRmdRs485(port=gyems_port, motor_id=0x01, baudrate=115200, timeout=0.25)
        self.gy.connect()

        # initial zero = current pose
        self.zero_orientation()

        with self._lock:
            self._snap.connected = True

    def disconnect(self) -> None:
        self.stop()

        if self.gy:
            try:
                self.gy.set_speed_deg_s_tx_only(0.0)
            except Exception:
                pass
            try:
                self.gy.close()
            except Exception:
                pass
            self.gy = None

        if self.dsp:
            try:
                self.dsp.disconnect()
            except Exception:
                pass
            self.dsp = None

        with self._lock:
            self._snap.connected = False

    def start(self) -> None:
        if not (self.dsp and self.gy):
            raise RuntimeError("Not connected")

        if self._run_evt.is_set():
            return

        self._t0 = time.time()
        self._run_evt.set()

        # reset counters
        self._status_ok = 0
        self._status_to = 0
        self._status_fail_row = 0

        self._control_thread = threading.Thread(target=self._control_loop, daemon=True)
        self._status_thread = threading.Thread(target=self._status_loop, daemon=True)
        self._control_thread.start()
        self._status_thread.start()

        with self._lock:
            self._snap.running = True

    def stop(self) -> None:
        if not self._run_evt.is_set():
            return

        self._run_evt.clear()

        if self.gy:
            try:
                self.gy.set_speed_deg_s_tx_only(0.0)
            except Exception:
                pass

        with self._lock:
            self._snap.running = False

    # ---------- params ----------
    def set_params(
        self,
        kp: Optional[float] = None,
        deadband_dps: Optional[float] = None,
        gyro_sign: Optional[float] = None,
        max_dps: Optional[float] = None,
    ) -> None:
        if kp is not None:
            self.params.kp = float(kp)
        if deadband_dps is not None:
            self.params.deadband_dps = float(deadband_dps)
        if gyro_sign is not None:
            self.params.gyro_sign = float(gyro_sign)
        if max_dps is not None:
            self.params.max_dps = float(max_dps)

    # ---------- zero / heading ----------
    def zero_orientation(self) -> None:
        """
        Setzt aktuelle Orientierung auf 0° (Nord) für DSP und GYEMS
        und synchronisiert sofort den Snapshot (GUI).
        """
        dsp_angle = 0.0
        if self.dsp:
            try:
                dsp_angle = float(self.dsp.get_angle())
            except Exception:
                dsp_angle = 0.0

        gy_angle = 0.0
        if self.gy:
            try:
                with self._io_lock:
                    gy_angle = float(self.gy.read_singleturn_angle_deg())
            except Exception:
                gy_angle = 0.0

        with self._lock:
            # Offsets setzen
            self._dsp_zero_offset = dsp_angle
            self._gyems_zero_offset = gy_angle

            # <<< WICHTIG: Snapshot sofort auf 0° setzen >>>
            self._snap.dsp_heading_deg = 0.0
            self._snap.gyems_heading_deg = 0.0
            self._snap.dsp_angle_deg = dsp_angle
            self._snap.gyems_angle_deg = gy_angle

    # ---------- snapshot ----------
    def get_snapshot(self) -> ArnSnapshot:
        with self._lock:
            return ArnSnapshot(**self._snap.__dict__)

    # ---------- internals ----------
    def _set_error(self, msg: str) -> None:
        with self._lock:
            self._snap.last_error = msg

    def _control_loop(self) -> None:
        assert self.dsp is not None and self.gy is not None

        dt = 1.0 / self.params.loop_hz
        next_tick = time.time()

        while self._run_evt.is_set():
            now = time.time()
            if now < next_tick:
                time.sleep(min(0.01, next_tick - now))
                continue
            next_tick += dt

            # DSP values
            rate = float(getattr(self.dsp, "rate_dps", 0.0))
            try:
                angle = float(self.dsp.get_angle())
            except Exception:
                angle = 0.0

            with self._lock:
                dsp_heading = (angle - self._dsp_zero_offset) % 360.0

            # P + deadband (Sollrate = 0)
            error = self.params.gyro_sign * (-rate)
            if abs(error) < self.params.deadband_dps:
                error = 0.0
            cmd = _clamp(self.params.kp * error, -self.params.max_dps, +self.params.max_dps)

            # TX-only command
            try:
                self.gy.set_speed_deg_s_tx_only(cmd)
            except Exception as e:
                self._set_error(f"TX-only send failed: {type(e).__name__}: {e}")

            with self._lock:
                self._snap.t_s = now - self._t0
                self._snap.dsp_rate_dps = rate
                self._snap.dsp_angle_deg = angle
                self._snap.dsp_heading_deg = dsp_heading
                self._snap.cmd_dps = cmd

    def _status_loop(self) -> None:
        assert self.gy is not None

        dt = 1.0 / self.params.status_hz
        next_tick = time.time()

        while self._run_evt.is_set():
            now = time.time()
            if now < next_tick:
                time.sleep(min(0.05, next_tick - now))
                continue
            next_tick += dt

            try:
                with self._io_lock:
                    self.gy.drain_rx()
                    st = self.gy.read_status()
                    gy_ang = float(self.gy.read_singleturn_angle_deg())

                self._status_ok += 1
                self._status_fail_row = 0

                with self._lock:
                    self._snap.gyems_status = st
                    self._snap.gyems_angle_deg = gy_ang
                    self._snap.gyems_heading_deg = (gy_ang - self._gyems_zero_offset) % 360.0
                    self._snap.status_ok = self._status_ok
                    self._snap.status_timeouts = self._status_to
                    self._snap.status_fail_row = self._status_fail_row

            except TimeoutError:
                self._status_to += 1
                self._status_fail_row += 1

                with self._lock:
                    self._snap.status_ok = self._status_ok
                    self._snap.status_timeouts = self._status_to
                    self._snap.status_fail_row = self._status_fail_row

                if self._status_fail_row >= self.params.status_fail_max_in_row:
                    self._set_error("Status watchdog triggered (too many timeouts in a row)")
                    self.stop()
                    return

            except Exception as e:
                self._set_error(f"read_status/angle failed: {type(e).__name__}: {e}")
                # weiter versuchen
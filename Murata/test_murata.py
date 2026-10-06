"""Hardwarefreie Unit-Tests für die Murata-Integration."""

from __future__ import annotations

import sys
import types
import unittest
from types import SimpleNamespace

# Ermöglicht die Logiktests auch ohne installiertes PySerial.
try:
    import serial  # noqa: F401
except ModuleNotFoundError:
    serial_stub = types.ModuleType("serial")
    serial_stub.SerialException = OSError
    serial_stub.Serial = object
    sys.modules["serial"] = serial_stub

from Murata.murata_state import MurataState
from Murata.murata_worker import MurataWorker
from Murata.sch16t import MICROS_WRAP, SCH16T


class SCH16TTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sensor = SCH16T()

    def test_first_sample_sets_software_zero(self) -> None:
        self.sensor._handle_sample(1.0, 0.125, 42.5)

        snapshot = self.sensor.snapshot()
        self.assertEqual(snapshot.valid_packets, 1)
        self.assertAlmostEqual(snapshot.sensor_time_s or 0.0, 1.0)
        self.assertAlmostEqual(snapshot.raw_yaw_deg, 42.5)
        self.assertAlmostEqual(snapshot.angle_deg, 0.0)
        self.assertAlmostEqual(snapshot.rate_dps, 0.125)

    def test_reset_angle_uses_latest_measurement(self) -> None:
        self.sensor._handle_sample(1.0, 0.0, 10.0)
        self.sensor._handle_sample(2.0, 1.0, 13.0)
        self.assertAlmostEqual(self.sensor.snapshot().angle_deg, 3.0)

        self.sensor.reset_angle()
        self.assertAlmostEqual(self.sensor.snapshot().angle_deg, 0.0)

        self.sensor._handle_sample(3.0, 1.0, 14.0)
        self.assertAlmostEqual(self.sensor.snapshot().angle_deg, 1.0)

    def test_micros_wrap_is_extended_monotonically(self) -> None:
        before_wrap = self.sensor._extend_micros(MICROS_WRAP - 5)
        after_wrap = self.sensor._extend_micros(3)

        self.assertGreater(after_wrap, before_wrap)
        self.assertEqual(after_wrap - before_wrap, 8)

    def test_drift_is_determined_by_linear_regression(self) -> None:
        self.sensor._handle_sample(0.0, 0.02, 10.0)
        self.sensor.determine_drift(2.0)

        # 0.02 Grad Drift pro Sekunde, mit leicht ungleichmaessiger Abtastung.
        for sensor_time_s in (1.0, 1.4, 2.2, 3.0):
            yaw = 10.0 + 0.02 * sensor_time_s
            self.sensor._handle_sample(sensor_time_s, 0.02, yaw)

        snapshot = self.sensor.snapshot()
        self.assertFalse(snapshot.drift_active)
        self.assertIsNotNone(snapshot.pending_drift_dps)
        self.assertAlmostEqual(snapshot.pending_drift_dps or 0.0, 0.02, places=10)
        self.assertEqual(snapshot.drift_packet_count, 4)

    def test_applied_drift_removes_stationary_yaw_change(self) -> None:
        self.sensor._handle_sample(0.0, 0.02, 10.0)
        self.sensor.determine_drift(2.0)
        for sensor_time_s in (1.0, 2.0, 3.0):
            self.sensor._handle_sample(
                sensor_time_s,
                0.02,
                10.0 + 0.02 * sensor_time_s,
            )

        self.sensor.set_drift()
        self.sensor.reset_angle()
        self.sensor._handle_sample(4.0, 0.02, 10.08)

        snapshot = self.sensor.snapshot()
        self.assertAlmostEqual(snapshot.drift_dps, 0.02, places=10)
        self.assertAlmostEqual(snapshot.angle_deg, 0.0, places=10)
        self.assertAlmostEqual(snapshot.rate_dps, 0.0, places=10)

    def test_invalid_line_counter(self) -> None:
        self.sensor._count_invalid_line()
        self.sensor._count_invalid_line()
        self.assertEqual(self.sensor.snapshot().invalid_lines, 2)


class MurataStateTests(unittest.TestCase):
    def test_clear_measurement_resets_values(self) -> None:
        state = MurataState(
            sensor_time_s=12.0,
            raw_yaw_deg=7.0,
            angle_deg=5.0,
            valid_packets=100,
            invalid_lines=3,
            drift_active=True,
            pending_drift_dps=0.1,
        )

        state.clear_measurement()

        self.assertIsNone(state.sensor_time_s)
        self.assertEqual(state.angle_deg, 0.0)
        self.assertEqual(state.valid_packets, 0)
        self.assertEqual(state.invalid_lines, 0)
        self.assertFalse(state.drift_active)
        self.assertIsNone(state.pending_drift_dps)


class MurataWorkerTests(unittest.TestCase):
    def test_worker_copies_sensor_snapshot_to_state(self) -> None:
        snapshot = SimpleNamespace(
            connected=True,
            sensor_time_s=12.5,
            raw_yaw_deg=33.0,
            angle_deg=2.5,
            rate_dps=0.4,
            drift_dps=0.001,
            valid_packets=250,
            invalid_lines=2,
            drift_active=False,
            drift_elapsed_s=10.0,
            drift_duration_s=10.0,
            drift_progress=1.0,
            pending_drift_dps=0.001,
            drift_packet_count=1000,
        )

        class FakeSensor:
            connected = True

            @staticmethod
            def snapshot():
                return snapshot

        worker = MurataWorker()
        worker.sensor = FakeSensor()
        worker._update_state_from_sensor()

        self.assertTrue(worker.state.connected)
        self.assertAlmostEqual(worker.state.angle_deg, 2.5)
        self.assertAlmostEqual(worker.state.raw_yaw_deg, 33.0)
        self.assertEqual(worker.state.valid_packets, 250)
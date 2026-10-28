from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from App.services.session_autosave import SessionAutosaveManager


@dataclass
class DummyPoint:
    name: str
    x: float
    y: float
    z: float
    marked: bool = False


class SessionAutosaveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary_directory.name)
        self.manager = SessionAutosaveManager(self.directory)
        self.config = SimpleNamespace()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_save_and_restore_in_progress_point(self) -> None:
        point = DummyPoint("P_1", 1.0, 2.0, 3.0)
        point.marking_state = "in_progress"
        point.marking_state_updated_at = "2026-10-28T10:00:00"
        point.marking_error = None

        self.manager.save(
            points=[point],
            status={"trafo_valid": True},
            config=self.config,
            project_path="data/projekte/test.mower.json",
            selected_point_name="P_1",
            reason="Markierung gestartet",
            in_progress_point="P_1",
        )

        recovery = self.manager.load_recovery(point_class=DummyPoint)

        self.assertIsNotNone(recovery)
        assert recovery is not None
        self.assertEqual(recovery.points[0].name, "P_1")
        self.assertEqual(recovery.points[0].marking_state, "in_progress")
        self.assertEqual(recovery.metadata["in_progress_point"], "P_1")
        self.assertFalse(recovery.used_backup)
        self.assertFalse(self.manager.active_path.with_name(self.manager.active_path.name + ".tmp").exists())

    def test_corrupt_active_file_falls_back_to_previous_backup(self) -> None:
        first_point = DummyPoint("P_1", 1.0, 2.0, 3.0)
        second_point = DummyPoint("P_2", 4.0, 5.0, 6.0)

        common = {
            "status": {},
            "config": self.config,
            "project_path": None,
            "selected_point_name": None,
            "in_progress_point": None,
        }
        self.manager.save(points=[first_point], reason="Stand 1", **common)
        self.manager.save(points=[second_point], reason="Stand 2", **common)
        self.manager.active_path.write_text("{ beschädigt", encoding="utf-8")

        recovery = self.manager.load_recovery(point_class=DummyPoint)

        self.assertIsNotNone(recovery)
        assert recovery is not None
        self.assertTrue(recovery.used_backup)
        self.assertEqual([point.name for point in recovery.points], ["P_1"])

    def test_clean_shutdown_is_not_offered_for_recovery(self) -> None:
        self.manager.save(
            points=[DummyPoint("P_1", 1.0, 2.0, 3.0)],
            status={},
            config=self.config,
            project_path=None,
            selected_point_name="P_1",
            reason="Programm beendet",
            clean_shutdown=True,
        )

        self.assertIsNone(self.manager.load_recovery(point_class=DummyPoint))


if __name__ == "__main__":
    unittest.main()

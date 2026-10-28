from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import config.mower_config as mower_config


class ConfigReloadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.active_config = mower_config.CONFIG
        self.backup = copy.deepcopy(self.active_config)

    def tearDown(self) -> None:
        for section_name in (
            "xyz",
            "tracker",
            "murata",
            "gyems",
            "arn",
            "marker",
            "transformation",
            "paths",
        ):
            setattr(
                self.active_config,
                section_name,
                copy.deepcopy(getattr(self.backup, section_name)),
            )

    def test_reload_updates_existing_config_object(self) -> None:
        refreshed = copy.deepcopy(self.active_config)
        refreshed.xyz.port = "COM77"
        refreshed.arn.kp = 7.5
        refreshed.marker.size_mm = 123.0

        with patch.object(mower_config, "load_config", return_value=refreshed):
            result = mower_config.reload_active_config()

        self.assertIs(result, self.active_config)
        self.assertEqual(self.active_config.xyz.port, "COM77")
        self.assertEqual(self.active_config.arn.kp, 7.5)
        self.assertEqual(self.active_config.marker.size_mm, 123.0)

    def test_reload_error_keeps_previous_config(self) -> None:
        previous_port = self.active_config.xyz.port

        with patch.object(
            mower_config,
            "load_config",
            side_effect=ValueError("ungültige Test-Config"),
        ):
            with self.assertRaisesRegex(ValueError, "ungültige Test-Config"):
                mower_config.reload_active_config()

        self.assertEqual(self.active_config.xyz.port, previous_port)


if __name__ == "__main__":
    unittest.main()

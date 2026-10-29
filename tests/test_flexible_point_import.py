import tempfile
import unittest
from pathlib import Path

from App.services.flexible_point_import import (
    FlexibleImportSettings,
    load_points_flexible,
    preview_rows,
    read_source_text,
)


class FlexiblePointImportTests(unittest.TestCase):
    def _write(self, text: str, *, encoding: str = "utf-8") -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "punkte.txt"
        path.write_text(text, encoding=encoding)
        return path

    def test_minimum_xyz_creates_running_ids_and_fixed_values(self) -> None:
        path = self._write("1.25 2.5 3.75\n4 5 6\n")
        settings = FlexibleImportSettings(
            id_prefix="P",
            id_start=7,
            fixed_marker_code=3,
            fixed_remark="Labor",
        )

        points = load_points_flexible(path, settings)

        self.assertEqual([point.name for point in points], ["P7", "P8"])
        self.assertEqual(points[0].x, 1.25)
        self.assertEqual(points[0].marker_code, 3)
        self.assertEqual(points[0].remark, "Labor")

    def test_columns_can_be_freely_assigned(self) -> None:
        path = self._write(
            "Titelzeile\n"
            "Kommentar;Z;ID;Y;X;Marker\n"
            "Achse A;9,25;P-12;-10619,5;41007,5;2\n"
        )
        settings = FlexibleImportSettings(
            delimiter=";",
            skip_rows=2,
            decimal_separator=",",
            id_column=2,
            x_column=4,
            y_column=3,
            z_column=1,
            marker_column=5,
            remark_column=0,
        )

        points = load_points_flexible(path, settings)

        self.assertEqual(points[0].name, "P-12")
        self.assertEqual(points[0].x, 41007.5)
        self.assertEqual(points[0].y, -10619.5)
        self.assertEqual(points[0].z, 9.25)
        self.assertEqual(points[0].marker_code, 2)
        self.assertEqual(points[0].remark, "Achse A")

    def test_quoted_whitespace_comment_is_one_column(self) -> None:
        path = self._write('P1 10 20 30 4 "Rand links"\n')
        settings = FlexibleImportSettings(
            id_column=0,
            x_column=1,
            y_column=2,
            z_column=3,
            marker_column=4,
            remark_column=5,
        )

        point = load_points_flexible(path, settings)[0]

        self.assertEqual(point.remark, "Rand links")
        self.assertEqual(point.marker_code, 4)

    def test_duplicate_mapping_is_rejected(self) -> None:
        path = self._write("1;2;3\n")
        settings = FlexibleImportSettings(delimiter=";", x_column=0, y_column=0, z_column=2)

        with self.assertRaisesRegex(ValueError, "unterschiedliche"):
            load_points_flexible(path, settings)

    def test_duplicate_ids_are_rejected(self) -> None:
        path = self._write("P1;1;2;3\nP1;4;5;6\n")
        settings = FlexibleImportSettings(
            delimiter=";", id_column=0, x_column=1, y_column=2, z_column=3
        )

        with self.assertRaisesRegex(ValueError, "doppelt"):
            load_points_flexible(path, settings)

    def test_cp1252_file_and_preview_are_supported(self) -> None:
        path = self._write("1;2;3;Außen\n", encoding="cp1252")
        settings = FlexibleImportSettings(
            delimiter=";", remark_column=3, fixed_marker_code=1
        )

        point = load_points_flexible(path, settings)[0]

        self.assertEqual(point.remark, "Außen")
        self.assertIn("Außen", read_source_text(path))
        self.assertEqual(preview_rows(path, ";", 0)[0].columns[3], "Außen")

    def test_delimiter_must_not_equal_decimal_separator(self) -> None:
        path = self._write("1,2,3\n")
        settings = FlexibleImportSettings(delimiter=",", decimal_separator=",")

        with self.assertRaisesRegex(ValueError, "nicht identisch"):
            load_points_flexible(path, settings)


if __name__ == "__main__":
    unittest.main()

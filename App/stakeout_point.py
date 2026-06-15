# App/stakeout_point.py

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class StakeoutPoint:
    """
    Abzusteckender Punkt im Lasertracker-/Projektkoordinatensystem.

    marked:
        Dauerhafter Status: Punkt wurde bereits markiert.

    reachable:
        Dynamischer Status: Punkt liegt aktuell im erreichbaren Bereich des
        Absteckwagens. Wird spaeter aus CoordinateMapper/Trafo berechnet.
    """

    name: str
    x: float
    y: float
    z: float | None = None

    marked: bool = False
    reachable: bool = False
    selected: bool = False

    last_robot_x: float | None = None
    last_robot_y: float | None = None
    residual_mm: float | None = None

    @property
    def status_text(self) -> str:
        if self.marked:
            return "markiert"

        if self.reachable:
            return "erreichbar"

        return "offen"

    def xyz_text(self) -> str:
        if self.z is None:
            return f"X={self.x:.3f}, Y={self.y:.3f}"

        return f"X={self.x:.3f}, Y={self.y:.3f}, Z={self.z:.3f}"


def parse_point_line(line: str, line_number: int) -> StakeoutPoint | None:
    """
    Erwartetes Format, flexibel geparst:

        ID X Y Z
        p1, 1586.249824, -2058.430832, -495.155659
        p2  1628.150547  -2002.600049  -495.525822

    Leere Zeilen, Kommentare und Header werden ignoriert.
    """

    raw = line.strip()

    if not raw:
        return None

    if raw.startswith("#"):
        return None

    normalized = raw.replace(",", " ").replace(";", " ").replace("\t", " ")
    parts = [p for p in normalized.split(" ") if p]

    if not parts:
        return None

    first = parts[0].lower()
    if first in {"id", "name", "punkt", "punktname"}:
        return None

    if len(parts) < 3:
        raise ValueError(
            f"Zeile {line_number}: zu wenige Spalten. Erwartet: ID X Y [Z]."
        )

    name = parts[0]

    try:
        x = float(parts[1].replace(",", "."))
        y = float(parts[2].replace(",", "."))
        z = float(parts[3].replace(",", ".")) if len(parts) >= 4 else None
    except ValueError as exc:
        raise ValueError(
            f"Zeile {line_number}: Koordinaten konnten nicht gelesen werden: {raw}"
        ) from exc

    return StakeoutPoint(name=name, x=x, y=y, z=z)


def load_points_from_txt(path: str | Path) -> list[StakeoutPoint]:
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(f"Punktdatei nicht gefunden: {file_path}")

    points: list[StakeoutPoint] = []

    with file_path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            point = parse_point_line(line, line_number)
            if point is not None:
                points.append(point)

    if not points:
        raise ValueError(f"Keine Punkte in Datei gefunden: {file_path}")

    return points


def create_demo_points() -> list[StakeoutPoint]:
    points = [
        StakeoutPoint("p1", 1586.249824, -2058.430832, -495.155659),
        StakeoutPoint("p2", 1628.150547, -2002.600049, -495.525822),
        StakeoutPoint("p3", 1637.745777, -1872.112943, -496.330981),
    ]

    return points

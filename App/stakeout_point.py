from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


MARKER_CODE_TO_SHAPE: dict[int, str] = {
    1: "plus",
    2: "cross",
    3: "circle_point",
    4: "plus_circle",
}

DEFAULT_MARKER_CODE = 1
DEFAULT_MARKER_SHAPE = MARKER_CODE_TO_SHAPE[DEFAULT_MARKER_CODE]


@dataclass
class StakeoutPoint:
    """
    Abzusteckender Punkt im Lasertracker-/Projektkoordinatensystem.

    marker_code:
        Optionale Kennziffer aus der Punktdatei. Aktuell gilt:
            1 = plus
            2 = cross
            3 = circle_point
            4 = plus_circle
        Wenn keine Kennziffer vorhanden ist, wird 1 / plus verwendet.

    remark:
        Optionale Bemerkung aus der Punktdatei. Diese kann als Beschriftung
        fuer die Punktmarkierung verwendet werden.
    """

    name: str
    x: float
    y: float
    z: float | None = None
    marker_code: int = DEFAULT_MARKER_CODE
    remark: str = ""

    marked: bool = False
    reachable: bool = False
    selected: bool = False

    last_robot_x: float | None = None
    last_robot_y: float | None = None
    last_robot_z: float | None = None
    residual_mm: float | None = None

    @property
    def marker_shape(self) -> str:
        return MARKER_CODE_TO_SHAPE.get(int(self.marker_code), DEFAULT_MARKER_SHAPE)

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

    def remark_text(self) -> str:
        return self.remark if self.remark else "-"

    def marker_text(self) -> str:
        return f"{self.marker_code} / {self.marker_shape}"


def parse_point_line(line: str, line_number: int) -> StakeoutPoint | None:
    """
    Liest eine Punktzeile.

    Neues Standardformat:
        punktnummer x y z [kennziffer] ["bemerkung"] // Kommentar

    Beispiele:
        P101 123.456 -789.012 10.000 1 "A1"
        P102 123,456 -789,012 10,000 2 "B2" // Kommentar
        P103 123.456 -789.012 10.000 "C3"

    Kennziffern:
        1 = plus
        2 = cross
        3 = circle_point
        4 = plus_circle

    Hinweise:
        - Header- und Kommentarzeilen mit // oder # werden ignoriert.
        - Inline-Kommentare nach // werden ignoriert, sofern sie nicht in
          Anfuehrungszeichen stehen.
        - Wenn keine Kennziffer vorhanden ist, wird 1 / plus verwendet.
        - Bemerkungen werden bevorzugt aus Anfuehrungszeichen gelesen.
        - Alte komma-/semicolongetrennte Zeilen ohne Kennziffer/Bemerkung
          werden weiter akzeptiert.
    """

    raw = line.strip()

    if not raw:
        return None

    if raw.startswith("#") or raw.startswith("//"):
        return None

    without_comment = _strip_inline_comment(raw)
    if not without_comment.strip():
        return None

    quoted_remarks = re.findall(r'"([^"]*)"', without_comment)
    remark_from_quotes = quoted_remarks[0].strip() if quoted_remarks else ""

    # Quoted text vor der Spaltentrennung entfernen, damit Bemerkungen mit
    # Leerzeichen die Koordinaten- und Kennzifferspalten nicht stoeren.
    parse_part = re.sub(r'"[^"]*"', " ", without_comment)

    # Dezimalkomma erhalten, aber echte Trennkommas unterstuetzen:
    # 200,94 -> 200.94, danach verbleibende Kommas als Separatoren behandeln.
    parse_part = re.sub(r'(?<=\d),(?=\d)', ".", parse_part)
    normalized = (
        parse_part
        .replace(",", " ")
        .replace(";", " ")
        .replace("\t", " ")
    )
    parts = [p for p in normalized.split() if p]

    if not parts:
        return None

    first = parts[0].lower().strip(".:")
    if first in {"id", "name", "punkt", "punktname", "point", "pointnumber", "punktnummer"}:
        return None

    if len(parts) < 4:
        raise ValueError(
            f"Zeile {line_number}: zu wenige Spalten. Erwartet: Punktnummer X Y Z [Kennziffer] [Bemerkung]."
        )

    name = parts[0]

    try:
        x = _parse_float(parts[1])
        y = _parse_float(parts[2])
        z = _parse_float(parts[3])
    except ValueError as exc:
        # Nicht-numerische Header ohne Kommentar robust ignorieren.
        if line_number <= 10:
            return None
        raise ValueError(
            f"Zeile {line_number}: Koordinaten konnten nicht gelesen werden: {raw}"
        ) from exc

    marker_code = DEFAULT_MARKER_CODE
    rest_parts = parts[4:]

    if rest_parts and _looks_like_integer(rest_parts[0]):
        marker_code = int(rest_parts[0])
        rest_parts = rest_parts[1:]

    if marker_code not in MARKER_CODE_TO_SHAPE:
        raise ValueError(
            f"Zeile {line_number}: unbekannte Marker-Kennziffer {marker_code}. "
            "Erlaubt sind aktuell 1=plus, 2=cross, 3=circle_point, 4=plus_circle."
        )

    remark = remark_from_quotes
    if not remark:
        remark = " ".join(rest_parts).strip()

    return StakeoutPoint(
        name=name,
        x=x,
        y=y,
        z=z,
        marker_code=marker_code,
        remark=remark,
    )


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
        StakeoutPoint("p1", 1586.249824, -2058.430832, -495.155659, 1, "Demo 1"),
        StakeoutPoint("p2", 1628.150547, -2002.600049, -495.525822, 2, "Demo 2"),
        StakeoutPoint("p3", 1637.745777, -1872.112943, -496.330981, 3, "Demo 3"),
    ]

    return points


def marker_shape_from_code(marker_code: int | str | None) -> str:
    try:
        code = int(marker_code) if marker_code is not None else DEFAULT_MARKER_CODE
    except (TypeError, ValueError):
        code = DEFAULT_MARKER_CODE
    return MARKER_CODE_TO_SHAPE.get(code, DEFAULT_MARKER_SHAPE)


def _parse_float(text: str) -> float:
    return float(text.strip().replace(",", "."))


def _looks_like_integer(text: str) -> bool:
    try:
        int(text)
        return True
    except (TypeError, ValueError):
        return False


def _strip_inline_comment(text: str) -> str:
    """Entfernt //-Kommentare ausserhalb von Anfuehrungszeichen."""

    in_quotes = False
    i = 0
    while i < len(text):
        char = text[i]
        if char == '"':
            in_quotes = not in_quotes
            i += 1
            continue
        if not in_quotes and text[i:i + 2] == "//":
            return text[:i].rstrip()
        i += 1
    return text.rstrip()

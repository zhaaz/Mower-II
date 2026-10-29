from __future__ import annotations

import csv
import shlex
from dataclasses import dataclass
from pathlib import Path

from App.stakeout_point import MARKER_CODE_TO_SHAPE, StakeoutPoint


@dataclass(frozen=True)
class FlexibleImportSettings:
    """Beschreibung eines frei konfigurierbaren Punktimports."""

    delimiter: str = "whitespace"
    skip_rows: int = 0
    decimal_separator: str = "."
    id_column: int | None = None
    id_prefix: str = "P"
    id_start: int = 1
    x_column: int = 0
    y_column: int = 1
    z_column: int = 2
    marker_column: int | None = None
    fixed_marker_code: int = 1
    remark_column: int | None = None
    fixed_remark: str = ""

    def validate(self) -> None:
        if self.skip_rows < 0:
            raise ValueError("Die Anzahl übersprungener Zeilen darf nicht negativ sein.")
        if self.decimal_separator not in {".", ","}:
            raise ValueError("Als Dezimalzeichen ist nur Punkt oder Komma zulässig.")
        if self.delimiter != "whitespace" and len(self.delimiter) != 1:
            raise ValueError("Das Trennzeichen muss genau ein Zeichen lang sein.")
        if self.delimiter == self.decimal_separator:
            raise ValueError("Trennzeichen und Dezimalzeichen dürfen nicht identisch sein.")
        if self.id_start < 0:
            raise ValueError("Die erste laufende Nummer darf nicht negativ sein.")
        if self.fixed_marker_code not in MARKER_CODE_TO_SHAPE:
            raise ValueError("Die Markierung muss zwischen 1 und 4 liegen.")

        required = {"X": self.x_column, "Y": self.y_column, "Z": self.z_column}
        if any(value < 0 for value in required.values()):
            raise ValueError("X, Y und Z müssen jeweils einer Spalte zugeordnet sein.")
        if len(set(required.values())) != len(required):
            raise ValueError("X, Y und Z müssen unterschiedliche Spalten verwenden.")

        assigned = list(required.values())
        assigned.extend(
            value
            for value in (self.id_column, self.marker_column, self.remark_column)
            if value is not None
        )
        if any(value < 0 for value in assigned):
            raise ValueError("Spaltennummern dürfen nicht negativ sein.")
        if len(assigned) != len(set(assigned)):
            raise ValueError("Eine Dateispalte darf nur einmal zugeordnet werden.")


@dataclass(frozen=True)
class PreviewRow:
    physical_line: int
    columns: tuple[str, ...]


def read_source_text(path: str | Path) -> str:
    source = Path(path)
    try:
        return source.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return source.read_text(encoding="cp1252")


def preview_rows(
        path: str | Path,
        delimiter: str,
        skip_rows: int,
        limit: int = 100,
) -> list[PreviewRow]:
    rows: list[PreviewRow] = []
    for physical_line, raw_line in enumerate(read_source_text(path).splitlines(), 1):
        if physical_line <= skip_rows:
            continue
        columns = split_line(raw_line, delimiter)
        if columns is None:
            continue
        rows.append(PreviewRow(physical_line, tuple(columns)))
        if len(rows) >= limit:
            break
    return rows


def load_points_flexible(
        path: str | Path,
        settings: FlexibleImportSettings,
        *,
        limit: int | None = None,
) -> list[StakeoutPoint]:
    settings.validate()
    source = Path(path)
    points: list[StakeoutPoint] = []
    names: set[str] = set()
    columns_in_use = [settings.x_column, settings.y_column, settings.z_column]
    columns_in_use.extend(
        value
        for value in (settings.id_column, settings.marker_column, settings.remark_column)
        if value is not None
    )
    highest_column = max(columns_in_use)

    for physical_line, raw_line in enumerate(read_source_text(source).splitlines(), 1):
        if physical_line <= settings.skip_rows:
            continue
        columns = split_line(raw_line, settings.delimiter)
        if columns is None:
            continue
        if len(columns) <= highest_column:
            raise ValueError(
                f"Zeile {physical_line}: nur {len(columns)} Spalten vorhanden; "
                f"benötigt wird mindestens Spalte {highest_column + 1}."
            )

        point_number = settings.id_start + len(points)
        name = (
            columns[settings.id_column].strip()
            if settings.id_column is not None
            else f"{settings.id_prefix}{point_number}"
        )
        if not name:
            raise ValueError(f"Zeile {physical_line}: Die Punkt-ID ist leer.")
        if name in names:
            raise ValueError(f"Zeile {physical_line}: Die Punkt-ID {name!r} ist doppelt vorhanden.")

        try:
            x = _parse_number(columns[settings.x_column], settings.decimal_separator)
            y = _parse_number(columns[settings.y_column], settings.decimal_separator)
            z = _parse_number(columns[settings.z_column], settings.decimal_separator)
        except ValueError as exc:
            raise ValueError(f"Zeile {physical_line}: {exc}") from exc

        marker_code = settings.fixed_marker_code
        if settings.marker_column is not None:
            marker_text = columns[settings.marker_column].strip()
            try:
                marker_code = int(marker_text)
            except ValueError as exc:
                raise ValueError(
                    f"Zeile {physical_line}: Markierung {marker_text!r} ist keine Ganzzahl."
                ) from exc
        if marker_code not in MARKER_CODE_TO_SHAPE:
            raise ValueError(
                f"Zeile {physical_line}: Unbekannte Markierung {marker_code}; erlaubt sind 1 bis 4."
            )

        remark = (
            columns[settings.remark_column].strip()
            if settings.remark_column is not None
            else settings.fixed_remark.strip()
        )
        if "\r" in remark or "\n" in remark:
            raise ValueError(f"Zeile {physical_line}: Der Kommentar enthält einen Zeilenumbruch.")

        points.append(
            StakeoutPoint(
                name=name,
                x=x,
                y=y,
                z=z,
                marker_code=marker_code,
                remark=remark,
            )
        )
        names.add(name)
        if limit is not None and len(points) >= limit:
            break

    if not points:
        raise ValueError(f"Keine importierbaren Punkte in der Datei gefunden: {source}")
    return points


def split_line(raw_line: str, delimiter: str) -> list[str] | None:
    text = _strip_inline_comment(raw_line).strip()
    if not text or text.startswith("#") or text.startswith("//"):
        return None
    if delimiter == "whitespace":
        try:
            return shlex.split(text, comments=False, posix=True)
        except ValueError as exc:
            raise ValueError(f"Ungültige Anführungszeichen: {exc}") from exc
    if len(delimiter) != 1:
        raise ValueError("Das Trennzeichen muss genau ein Zeichen lang sein.")
    try:
        return next(
            csv.reader(
                [text],
                delimiter=delimiter,
                quotechar='"',
                skipinitialspace=True,
            )
        )
    except csv.Error as exc:
        raise ValueError(f"Dateizeile kann nicht gelesen werden: {exc}") from exc


def _parse_number(text: str, decimal_separator: str) -> float:
    normalized = text.strip()
    if decimal_separator == ",":
        normalized = normalized.replace(".", "").replace(",", ".")
    try:
        return float(normalized)
    except ValueError as exc:
        raise ValueError(f"{text!r} ist keine gültige Zahl") from exc


def _strip_inline_comment(text: str) -> str:
    in_quotes = False
    index = 0
    while index < len(text) - 1:
        if text[index] == '"':
            in_quotes = not in_quotes
        if not in_quotes and text[index:index + 2] == "//":
            return text[:index]
        index += 1
    return text

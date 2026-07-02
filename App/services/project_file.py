from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from config.mower_config import CONFIG
except Exception:  # pragma: no cover - fallback for isolated tests
    CONFIG = None

PROJECT_FORMAT = "mower_project"
PROJECT_VERSION = 1

_POINT_FIELDS = (
    "name",
    "x",
    "y",
    "z",
    "marker_code",
    "marker_shape",
    "remark",
    "marked",
    "reachable",
    "last_robot_x",
    "last_robot_y",
    "residual_mm",
)


def point_to_dict(point: Any) -> dict[str, Any]:
    """Serializes a stakeout point defensively without depending on its exact class."""
    if is_dataclass(point):
        data = asdict(point)
    else:
        data = {}

    for field in _POINT_FIELDS:
        if hasattr(point, field):
            value = getattr(point, field)
            try:
                json.dumps(value)
            except TypeError:
                value = str(value)
            data[field] = value

    return data


def point_from_dict(data: dict[str, Any], point_class: type[Any]) -> Any:
    """Creates a StakeoutPoint while tolerating constructor differences."""
    base = {
        "name": str(data.get("name", "")),
        "x": float(data.get("x", 0.0)),
        "y": float(data.get("y", 0.0)),
        "z": float(data.get("z", 0.0)),
    }

    optional = {
        "marker_code": data.get("marker_code"),
        "marker_shape": data.get("marker_shape"),
        "remark": data.get("remark", ""),
        "marked": bool(data.get("marked", False)),
    }

    attempts = [
        {**base, **{k: v for k, v in optional.items() if v is not None}},
        {**base, "remark": optional["remark"], "marked": optional["marked"]},
        base,
    ]

    last_error: Exception | None = None
    for kwargs in attempts:
        try:
            point = point_class(**kwargs)
            break
        except Exception as exc:  # constructor signatures can differ
            last_error = exc
    else:
        raise RuntimeError(f"Punkt konnte nicht erzeugt werden: {base['name']} ({last_error})")

    for key, value in data.items():
        try:
            setattr(point, key, value)
        except Exception:
            pass

    return point


def build_settings_snapshot(config: Any | None = None) -> dict[str, Any]:
    cfg = config if config is not None else CONFIG
    if cfg is None:
        return {}

    marker = getattr(cfg, "marker", None)
    transformation = getattr(cfg, "transformation", None)
    arn = getattr(cfg, "arn", None)
    gyro = getattr(cfg, "gyro", None)

    return {
        "marker": _object_fields(
            marker,
            [
                "shape",
                "size_mm",
                "angle_deg",
                "align_to_tracker_axes",
                "z_mark_mm",
                "z_clear_mm",
                "z_travel_mm",
            ],
        ),
        "transformation": _object_fields(
            transformation,
            ["marker_to_reflector_robot", "gyro_invalid_threshold_deg"],
        ),
        "arn": _object_fields(
            arn,
            ["kp", "max_speed_deg_s", "deadband_deg", "command_interval_ms", "direction_sign"],
        ),
        "gyro": _object_fields(gyro, ["default_drift_seconds"]),
    }


def _object_fields(obj: Any, names: list[str]) -> dict[str, Any]:
    if obj is None:
        return {}
    result: dict[str, Any] = {}
    for name in names:
        if hasattr(obj, name):
            value = getattr(obj, name)
            if isinstance(value, tuple):
                value = list(value)
            result[name] = value
    return result


def build_project_data(
    *,
    points: list[Any],
    status: dict[str, Any] | None = None,
    config: Any | None = None,
) -> dict[str, Any]:
    return {
        "format": PROJECT_FORMAT,
        "version": PROJECT_VERSION,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "points": [point_to_dict(point) for point in points],
        "status": status or {},
        "settings_snapshot": build_settings_snapshot(config),
    }


def save_project_file(
    *,
    path: str | Path,
    points: list[Any],
    status: dict[str, Any] | None = None,
    config: Any | None = None,
) -> None:
    target = Path(path)
    data = build_project_data(points=points, status=status, config=config)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")


def load_project_file(*, path: str | Path, point_class: type[Any]) -> tuple[list[Any], dict[str, Any]]:
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))

    if data.get("format") != PROJECT_FORMAT:
        raise ValueError("Keine gueltige Mower-II-Projektdatei.")

    points = [point_from_dict(item, point_class) for item in data.get("points", [])]
    return points, data


def export_project_txt(
    *,
    path: str | Path,
    points: list[Any],
    status: dict[str, Any] | None = None,
    config: Any | None = None,
    project_path: str | Path | None = None,
) -> None:
    target = Path(path)
    snapshot = build_settings_snapshot(config)
    lines: list[str] = []
    lines.append("Mower II - Projektexport")
    lines.append("=" * 80)
    lines.append(f"Exportiert am: {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"Projektdatei: {project_path if project_path else '-'}")
    lines.append(f"Punkte: {len(points)}")
    lines.append("")

    lines.append("Projektstatus")
    lines.append("-" * 80)
    for key, value in (status or {}).items():
        lines.append(f"{key}: {_format_value(value)}")
    lines.append("")

    lines.append("Einstellungen Snapshot")
    lines.append("-" * 80)
    for section, values in snapshot.items():
        lines.append(f"[{section}]")
        for key, value in values.items():
            lines.append(f"{key}: {_format_value(value)}")
        lines.append("")

    lines.append("Punkte")
    lines.append("-" * 80)
    header = ["name", "x", "y", "z", "marked", "marker_shape", "marker_code", "remark"]
    lines.append(";".join(header))
    for point in points:
        row = []
        for key in header:
            row.append(_format_value(getattr(point, key, "")))
        lines.append(";".join(row))

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6f}"
    if isinstance(value, (list, tuple)):
        return ", ".join(_format_value(item) for item in value)
    return str(value).replace("\n", " ").replace(";", ",")

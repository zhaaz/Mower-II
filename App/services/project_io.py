# App/services/project_io.py

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def build_project_data(
    *,
    points: list[Any],
    status: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": 1,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "points": [
            {
                "name": p.name,
                "x": p.x,
                "y": p.y,
                "z": p.z,
                "marked": p.marked,
                "reachable": p.reachable,
                "last_robot_x": p.last_robot_x,
                "last_robot_y": p.last_robot_y,
                "residual_mm": p.residual_mm,
            }
            for p in points
        ],
        "status": status,
    }


def write_project_file(
    *,
    path: Path,
    points: list[Any],
    status: dict[str, Any],
) -> None:
    data = build_project_data(
        points=points,
        status=status,
    )

    path.write_text(
        json.dumps(data, indent=4, ensure_ascii=False),
        encoding="utf-8",
    )
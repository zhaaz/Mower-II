from __future__ import annotations

import json
import os
import shutil
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from App.services.project_file import build_project_data, point_from_dict


AUTOSAVE_VERSION = 1
AUTOSAVE_FILENAME = "aktive_sitzung.mower.autosave.json"
AUTOSAVE_BACKUP_FILENAME = "aktive_sitzung.mower.autosave.bak.json"


@dataclass(frozen=True)
class RecoverySession:
    points: list[Any]
    project_data: dict[str, Any]
    source_file: Path
    used_backup: bool = False

    @property
    def metadata(self) -> dict[str, Any]:
        value = self.project_data.get("autosave", {})
        return value if isinstance(value, dict) else {}


class SessionAutosaveManager:
    """Schreibt und lädt den absturzsicheren Stand der aktiven Sitzung."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.active_path = self.directory / AUTOSAVE_FILENAME
        self.backup_path = self.directory / AUTOSAVE_BACKUP_FILENAME
        self._lock = threading.RLock()

    def save(
            self,
            *,
            points: list[Any],
            status: dict[str, Any] | None,
            config: Any | None,
            project_path: str | Path | None,
            selected_point_name: str | None,
            reason: str,
            clean_shutdown: bool = False,
            in_progress_point: str | None = None,
    ) -> Path:
        data = build_project_data(points=points, status=status, config=config)
        data["autosave"] = {
            "version": AUTOSAVE_VERSION,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "clean_shutdown": bool(clean_shutdown),
            "reason": str(reason),
            "project_path": str(project_path) if project_path else None,
            "selected_point_name": selected_point_name,
            "in_progress_point": in_progress_point,
        }

        payload = json.dumps(data, indent=4, ensure_ascii=False) + "\n"
        with self._lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary_path = self.active_path.with_name(self.active_path.name + ".tmp")

            with temporary_path.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())

            if self.active_path.exists():
                shutil.copy2(self.active_path, self.backup_path)

            os.replace(temporary_path, self.active_path)

        return self.active_path

    def load_recovery(self, *, point_class: type[Any]) -> RecoverySession | None:
        """Lädt eine unsauber beendete Sitzung, mit Backup als Rückfallebene."""

        with self._lock:
            if self.active_path.exists():
                try:
                    session = self._load_file(self.active_path, point_class=point_class)
                except Exception:
                    session = None
                else:
                    if bool(session.metadata.get("clean_shutdown", False)):
                        return None
                    return session

            if self.backup_path.exists():
                try:
                    session = self._load_file(self.backup_path, point_class=point_class)
                except Exception:
                    return None
                if bool(session.metadata.get("clean_shutdown", False)):
                    return None
                return RecoverySession(
                    points=session.points,
                    project_data=session.project_data,
                    source_file=session.source_file,
                    used_backup=True,
                )

        return None

    def discard(self) -> None:
        with self._lock:
            for path in (self.active_path, self.backup_path):
                try:
                    path.unlink(missing_ok=True)
                except TypeError:  # pragma: no cover - Python < 3.8 fallback
                    if path.exists():
                        path.unlink()

    @staticmethod
    def _load_file(path: Path, *, point_class: type[Any]) -> RecoverySession:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("format") != "mower_project":
            raise ValueError("Keine gültige Mower-II-Autosave-Datei.")
        if not isinstance(data.get("autosave"), dict):
            raise ValueError("Autosave-Metadaten fehlen.")

        raw_points = data.get("points", [])
        if not isinstance(raw_points, list):
            raise ValueError("Autosave-Punktliste ist ungültig.")

        points = [point_from_dict(item, point_class) for item in raw_points]
        return RecoverySession(
            points=points,
            project_data=data,
            source_file=path,
        )

# Transformation/trafo_manager.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Any
from datetime import datetime


@dataclass
class ActiveTrafoState:
    valid: bool = False
    trafo: Optional[Any] = None
    source_result: Optional[Any] = None
    set_timestamp: Optional[float] = None
    invalid_reason: str = ""


class TrafoManager:
    def __init__(self):
        self._active = ActiveTrafoState()
        self._pending_result = None

    @property
    def valid(self) -> bool:
        return self._active.valid

    @property
    def active_trafo(self):
        return self._active.trafo

    @property
    def pending_result(self):
        return self._pending_result

    @property
    def invalid_reason(self) -> str:
        return self._active.invalid_reason

    def set_pending(self, result):
        self._pending_result = result

    def clear_pending(self):
        self._pending_result = None

    def accept_pending(self):
        if self._pending_result is None:
            raise RuntimeError("Keine pending Trafo vorhanden.")

        if not self._pending_result.success:
            raise RuntimeError("Pending Trafo ist nicht erfolgreich.")

        self._active = ActiveTrafoState(
            valid=True,
            trafo=self._pending_result.trafo,
            source_result=self._pending_result,
            set_timestamp=datetime.now().timestamp(),
            invalid_reason="",
        )

        self._pending_result = None

    def invalidate(self, reason: str = ""):
        self._active.valid = False
        self._active.invalid_reason = reason or "Trafo ungültig."

    def clear_active(self):
        self._active = ActiveTrafoState()

    @property
    def reflector_plane_lt(self):
        if self._active.source_result is None:
            return None
        return self._active.source_result.reflector_plane_lt

    @property
    def marker_plane_lt(self):
        if self._active.source_result is None:
            return None
        return self._active.source_result.marker_plane_lt

    @property
    def marker_to_reflector_robot(self):
        if self._active.source_result is None:
            return None
        return self._active.source_result.marker_to_reflector_robot

    @property
    def marker_to_reflector_lt(self):
        if self._active.source_result is None:
            return None
        return self._active.source_result.marker_to_reflector_lt
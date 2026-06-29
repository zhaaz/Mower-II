from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class EventLevel(Enum):
    INFO = auto()
    WARNING = auto()
    ERROR = auto()


@dataclass(frozen=True)
class ComponentEvent:
    source: str
    level: EventLevel
    message: str

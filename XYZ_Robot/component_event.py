# component_event.py

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class EventLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class ComponentEvent:
    component: str
    level: EventLevel
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    data: dict[str, Any] | None = None

    def format_for_log(self) -> str:
        timestamp_text = self.timestamp.strftime("%H:%M:%S")
        return f"[{timestamp_text}] [{self.component}] [{self.level.value.upper()}] {self.message}"
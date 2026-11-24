from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable, Literal, Protocol


class OperationCancelled(Exception):
    """The window was closed before the operation completed."""


@dataclass(frozen=True)
class ApiResponse:
    status_code: int
    body: str
    analysis_mode: str | None = None


@dataclass(frozen=True)
class AppEvent:
    kind: Literal["log", "status", "response"]
    text: str


class Recorder(Protocol):
    def record(self, destination: Path, duration_seconds: int,
               on_remaining: Callable[[int], None], cancelled: Event) -> Path: ...


class AnalysisClient(Protocol):
    def analyze(self, video: Path, on_waiting: Callable[[], None]) -> ApiResponse: ...

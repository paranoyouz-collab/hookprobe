"""Data types. Deliberately the same shape as skillprobe's, so the two tools
read as one family rather than two unrelated scripts."""

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Severity(StrEnum):
    ERROR = "error"
    WARN = "warn"
    INFO = "info"

    @property
    def rank(self) -> int:
        return {"error": 2, "warn": 1, "info": 0}[self.value]


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    message: str


@dataclass
class Hook:
    """One handler, with enough context to explain where it came from."""

    source: Path
    event: str
    index: int
    config: dict[str, Any]
    matcher: str | None = None
    findings: list[Finding] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return str(self.config.get("type") or "?")

    @property
    def label(self) -> str:
        """How this hook is named in output: event, position, and what it runs."""
        target = (
            self.config.get("command")
            or self.config.get("url")
            or self.config.get("tool")
            or self.config.get("prompt")
            or ""
        )
        target = str(target).strip().replace("\n", " ")
        if len(target) > 48:
            target = target[:45] + "..."
        return f"{self.event}[{self.index}] {target}" if target else f"{self.event}[{self.index}]"

    @property
    def worst(self) -> Severity:
        return max((f.severity for f in self.findings), key=lambda s: s.rank, default=Severity.INFO)

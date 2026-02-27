from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable


class Phase(str, Enum):
    # Epic phases
    QUEEN = "phase:queen"
    TRIAD = "phase:triad"
    ARBITER = "phase:arbiter"

    # Story phases
    CONTRACT = "phase:contract"
    SPEC = "sparc:spec"
    PSEUDO = "sparc:pseudo"
    ARCH = "sparc:arch"
    REFINE = "sparc:refine"
    DONE = "sparc:done"
    COMPLETED = "sparc:completed"


PHASE_LABELS = {p.value for p in Phase}

META_LABELS = {
    "needs:human",
    "blocked",
    "restart:contract",
    "restart:spec",
    "restart:pseudo",
    "restart:arch",
    "lock",
    "epic:ready",
}


@dataclass(slots=True)
class LockInfo:
    owner: str


@dataclass(slots=True)
class Issue:
    number: int
    labels: set[str] = field(default_factory=set)
    lock: LockInfo | None = None

    def phase_labels(self) -> set[str]:
        return {label for label in self.labels if label in PHASE_LABELS}

    def meta_labels(self) -> set[str]:
        return {label for label in self.labels if label in META_LABELS}

    def add_labels(self, labels: Iterable[str]) -> None:
        self.labels.update(labels)

    def remove_labels(self, labels: Iterable[str]) -> None:
        for label in labels:
            self.labels.discard(label)

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class WorkItem:
    issue_number: int
    owner: str


@dataclass(slots=True)
class StaggeredQueue:
    """Simple lock-aware queue with deterministic staggering slots."""

    max_parallel: int = 2
    stagger_seconds: float = 1.5
    _items: list[WorkItem] = field(default_factory=list)

    def enqueue(self, item: WorkItem) -> None:
        self._items.append(item)

    def pop_batch(self) -> list[WorkItem]:
        if not self._items:
            return []
        batch = self._items[: self.max_parallel]
        self._items = self._items[self.max_parallel :]
        return batch

    def has_items(self) -> bool:
        return bool(self._items)

    def schedule_offsets(self, count: int) -> list[float]:
        return [i * self.stagger_seconds for i in range(count)]

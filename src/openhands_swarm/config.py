from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    """Runtime knobs for orchestration safety and concurrency."""

    lock_ttl_minutes: int = 30
    max_parallel_issues: int = 2
    triad_max_parallel_personas: int = 3
    stagger_seconds: float = 1.5

"""Tests mirroring the trigger_workflow package."""

from __future__ import annotations

from pathlib import Path


# Keep `tests/trigger_workflow` discoverable without shadowing the real package.
__path__.append(str(Path(__file__).resolve().parents[2] / "trigger_workflow"))

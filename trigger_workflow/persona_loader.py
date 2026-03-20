from __future__ import annotations

from pathlib import Path

from .config import (
    BASE_PERSONA_FILE,
    FUNCTIONAL_MICROAGENT_PERSONA_FILE_MAP,
    MICROAGENT_PERSONAS_DIR,
    PERSONAS_DIR,
    PERSONA_FILE_MAP,
)
from .logging_utils import log_info


def read_required_text_file(path: Path, *, missing_message: str, log_message: str) -> str:
    """Read a required prompt file with consistent logging and failure behavior."""
    if not path.exists():
        raise SystemExit(missing_message)
    log_info(log_message)
    return path.read_text().strip()


def read_functional_microagent_persona(label: str, phase: str | None) -> str:
    """Read the functional `microagent_personas/` prompt used alongside literary personas."""
    del label
    if not phase:
        raise SystemExit("Cannot load a functional microagent_persona without a resolved phase id.")

    microagent_persona_filename = FUNCTIONAL_MICROAGENT_PERSONA_FILE_MAP.get(phase)
    if not microagent_persona_filename:
        raise SystemExit(f"No functional microagent_persona filename is configured for phase {phase.upper()}.")

    microagent_persona_path = MICROAGENT_PERSONAS_DIR / microagent_persona_filename
    return read_required_text_file(
        microagent_persona_path,
        missing_message=f"Functional microagent_persona file is missing: {microagent_persona_filename}",
        log_message=f"Including functional microagent_persona: {microagent_persona_path.name}",
    )


def read_microagent_persona_for_label(label: str, phase: str | None, *, include_base_persona: bool = True) -> str:
    """Build the effective phase prompt from Daneel, the phase persona, and the microagent_persona."""
    if not phase:
        raise SystemExit(f"Cannot load persona stack for label '{label}' without a resolved phase id.")

    sections: list[str] = []

    if include_base_persona:
        base_persona_path = PERSONAS_DIR / BASE_PERSONA_FILE
        sections.append(
            read_required_text_file(
                base_persona_path,
                missing_message=f"Base persona file is missing: {base_persona_path.name}",
                log_message=f"Including base persona: {base_persona_path.name}",
            )
        )

    persona_filename = PERSONA_FILE_MAP.get(phase)
    if not persona_filename:
        raise SystemExit(f"No phase persona filename is configured for phase {phase.upper()}.")
    persona_path = PERSONAS_DIR / persona_filename
    log_info(f"Looking for phase persona file {persona_filename}")
    sections.append(
        read_required_text_file(
            persona_path,
            missing_message=f"Phase persona file is missing: {persona_filename}",
            log_message=f"Including phase persona: {persona_path.name}",
        )
    )

    microagent_persona_content = read_functional_microagent_persona(label, phase)
    sections.append(microagent_persona_content.strip())

    return "\n\n".join(sections)
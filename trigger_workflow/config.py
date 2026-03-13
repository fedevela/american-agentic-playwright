from __future__ import annotations

from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
MICROAGENTS_DIR = WORKSPACE / ".openhands" / "microagents"
PERSONAS_DIR = WORKSPACE / "personas"
DEFAULT_REPO = "fedevela/particle-life-3d"
SESSION_STATE_PATH = WORKSPACE / "workspace" / ".session-state.json"

PHASE_DISPLAY_NAME_MAP = {
    "1": "Keter",
    "2a": "Chokhmah",
    "2b": "Binah",
    "2c": "Chesed",
    "3": "Gevurah",
    "4": "Tiferet",
    "5": "Netzach",
    "6": "Hod",
    "7": "Yesod-Orchestration",
    "8": "Yesod-Embodiment",
    "9": "Malkhut",
}

PHASE_LABEL_METADATA = {
    "phase:keter": {
        "description": "Phase 1 Keter: Intent Formation",
        "color": "6E7781",
    },
    "phase:chokhmah": {
        "description": "Phase 2A Chokhmah: Generative Expansion",
        "color": "A0522D",
    },
    "phase:binah": {
        "description": "Phase 2B Binah: Critical Restriction",
        "color": "B65C00",
    },
    "phase:chesed": {
        "description": "Phase 2C Chesed: Mechanistic Grounding",
        "color": "C2A000",
    },
    "phase:gevurah": {
        "description": "Phase 3 Gevurah: Synthetic Judgment",
        "color": "BF8700",
    },
    "phase:tiferet": {
        "description": "Phase 4 Tiferet: SPARC Specification",
        "color": "1A7F37",
    },
    "phase:netzach": {
        "description": "Phase 5 Netzach: Traceability",
        "color": "0E8A16",
    },
    "phase:hod": {
        "description": "Phase 6 Hod: SPARC Pseudocode",
        "color": "0969DA",
    },
    "phase:yesod-orchestration": {
        "description": "Phase 7 Yesod-Orchestration: SPARC Architecture",
        "color": "5319E7",
    },
    "phase:yesod-embodiment": {
        "description": "Phase 8 Yesod-Embodiment: SPARC Refinement",
        "color": "8250DF",
    },
    "phase:malkhut": {
        "description": "Phase 9 Malkhut: SPARC Completion",
        "color": "D1242F",
    },
}

NEXT_LABEL_MAP = {
    "phase:keter": "phase:chokhmah",
    "phase:chokhmah": "phase:binah",
    "phase:binah": "phase:chesed",
    "phase:chesed": "phase:gevurah",
    "phase:gevurah": "phase:tiferet",
    "phase:tiferet": "phase:netzach",
    "phase:netzach": "phase:hod",
    "phase:hod": "phase:yesod-orchestration",
    "phase:yesod-orchestration": "phase:yesod-embodiment",
    "phase:yesod-embodiment": "phase:malkhut",
    "phase:malkhut": None,
}

PHASE_LABELS = tuple(NEXT_LABEL_MAP.keys())

PERSONA_FILE_MAP = {
    "1": "phase_01.1_keter.md",
    "2a": "phase_02.1_chokhmah.md",
    "2b": "phase_02.2_binah.md",
    "2c": "phase_02.3_chesed.md",
    "3": "phase_03_gevurah.md",
    "4": "phase_04_tiferet.md",
    "5": "phase_05_netzach.md",
    "6": "phase_06_hod.md",
    "7": "phase_07_yesod.md",
    "8": "phase_08_yesod.md",
    "9": "phase_09_malkhut.md",
}

LEGACY_MICROAGENT_FILE_MAP = {
    "1": "phase_01_keter.md",
    "2a": "phase_02_chokhmah.md",
    "2b": "phase_03_binah.md",
    "2c": "phase_04_chesed.md",
    "3": "phase_05_gevurah.md",
    "4": "phase_06_tiferet.md",
    "5": "phase_07_netzach.md",
    "6": "phase_08_hod.md",
    "7": "phase_09_yesod_orchestration.md",
    "8": "phase_10_yesod_embodiment.md",
    "9": "phase_11_malkhut.md",
}

BASE_PERSONA_FILE = "daneel.md"

LABEL_PHASE_MAP = {
    "phase:keter": "1",
    "phase:chokhmah": "2a",
    "phase:binah": "2b",
    "phase:chesed": "2c",
    "phase:gevurah": "3",
    "phase:tiferet": "4",
    "phase:netzach": "5",
    "phase:hod": "6",
    "phase:yesod-orchestration": "7",
    "phase:yesod-embodiment": "8",
    "phase:malkhut": "9",
}

DISCUSSION_PHASES = {"1", "2a", "2b", "2c", "3"}
KETER_DERIVED_PHASES = {"2a", "2b", "2c"}
SPECIFICATION_PHASE = "4"


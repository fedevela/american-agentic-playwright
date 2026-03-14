from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
MICROAGENTS_DIR = WORKSPACE / "microagents"
PERSONAS_DIR = WORKSPACE / "personas"
DEFAULT_REPO = "fedevela/particle-life-3d"
SESSION_STATE_PATH = WORKSPACE / "workspace" / ".session-state.json"


@dataclass(frozen=True)
class TargetRepoConfig:
    """Describe how a GitHub repo maps to the local checkout OpenHands should use."""

    local_path: Path
    main_branch: str
    issue_branch_prefix: str = "issue/"

# Canonical 9-phase workflow order:
# 1 -> 2a -> 2b -> 2c -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9
# Numeric Tree-of-Life positions:
# 1=1, 2a=2, 2b=3, 2c=4, 3=5, 4=6, 5=7, 6=8, 7=9, 8=10, 9=11
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
    "phase:needsHuman": {
        "description": "Workflow halted: requires human intervention",
        "color": "B60205",
    },
}

# Single-successor handoff chain. Each phase advances to exactly one next label.
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
NEEDS_HUMAN_LABEL = "phase:needsHuman"

PERSONA_FILE_MAP = {
    "1": "keter_intentformation.md",
    "2a": "chokhmah_generativeexpansion.md",
    "2b": "binah_criticalrestriction.md",
    "2c": "chesed_mechanisticgrounding.md",
    "3": "gevurah_syntheticjudgment.md",
    "4": "tiferet_specificationharmony.md",
    "5": "netzach_traceabilityendurance.md",
    "6": "hod_analyticalarticulation.md",
    "7": "yesod_integrationfoundation.md",
    "8": "yesod_transmissionembodiment.md",
    "9": "malkhut_completionsovereignty.md",
}

FUNCTIONAL_MICROAGENT_FILE_MAP = {
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

# Canonical label -> phase-id mapping used throughout routing and prompt selection.
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
PRE_IMPLEMENTATION_PHASES = DISCUSSION_PHASES | {SPECIFICATION_PHASE}
IMPLEMENTATION_PHASES = {"5", "6", "7", "8", "9"}
# Session policy: every phase run is conversation-isolated so no phase inherits
# latent context from a previous phase execution.
STRICTLY_INDEPENDENT_PHASES = set(PHASE_DISPLAY_NAME_MAP.keys())

TARGET_REPO_CONFIG_MAP = {
    "fedevela/particle-life-3d": TargetRepoConfig(
        local_path=Path("/Users/macbook/Documents/gitworkspace/particle-life-3d"),
        main_branch="main",
        issue_branch_prefix="issue/",
    ),
}

TIFERET_AUTO_ISSUE_PREFIX = "[AUTO/TIFERET] "

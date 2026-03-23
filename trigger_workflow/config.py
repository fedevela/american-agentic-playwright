from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .domain import WorkflowPhase

WORKSPACE = Path(__file__).resolve().parent.parent
MICROAGENT_PERSONAS_DIR = WORKSPACE / "microagent-personas"
PERSONAS_DIR = WORKSPACE / "personas"
SESSION_STATE_PATH = Path.cwd() / ".swarm" / ".session-state.json"

@dataclass(frozen=True)
class TargetRepoConfig:
    """Describe the target repository configuration."""
    local_path: Path
    main_branch: str
    issue_branch_prefix: str = "issue/"

BASE_PERSONA_FILE = "daneel.md"
NEEDS_HUMAN_LABEL = "phase:needsHuman"
TIFERET_AUTO_ISSUE_PREFIX = "[AUTO/TIFERET] "

# --- Phase Definitions (The Domain Source of Truth) ---
_phases = [
    WorkflowPhase("1", "phase:keter", "Keter", "Phase 1 Keter: Intent Formation", "6E7781", "keter_intentformation.md", "phase_1_keter.md", "phase:chokhmah"),
    WorkflowPhase("2A", "phase:chokhmah", "Chokhmah", "Phase 2A Chokhmah: Generative Expansion", "A0522D", "chokhmah_generativeexpansion.md", "phase_2A_chokhmah.md", "phase:binah"),
    WorkflowPhase("2B", "phase:binah", "Binah", "Phase 2B Binah: Critical Restriction", "B65C00", "binah_criticalrestriction.md", "phase_2B_binah.md", "phase:chesed"),
    WorkflowPhase("2C", "phase:chesed", "Chesed", "Phase 2C Chesed: Mechanistic Grounding", "C2A000", "chesed_mechanisticgrounding.md", "phase_2C_chesed.md", "phase:gevurah"),
    WorkflowPhase("3", "phase:gevurah", "Gevurah", "Phase 3 Gevurah: Synthetic Judgment", "BF8700", "gevurah_syntheticjudgment.md", "phase_3_gevurah.md", "phase:tiferet"),
    WorkflowPhase("4", "phase:tiferet", "Tiferet", "Phase 4 Tiferet: SPARC Specification", "1A7F37", "tiferet_specificationharmony.md", "phase_4_tiferet.md", "phase:netzach"),
    WorkflowPhase("5", "phase:netzach", "Netzach", "Phase 5 Netzach: Traceability", "0E8A16", "netzach_traceabilityendurance.md", "phase_5_netzach.md", "phase:hod"),
    WorkflowPhase("6", "phase:hod", "Hod", "Phase 6 Hod: SPARC Pseudocode", "0969DA", "hod_analyticalarticulation.md", "phase_6_hod.md", "phase:yesod-orchestration"),
    WorkflowPhase("7", "phase:yesod-orchestration", "Yesod-Orchestration", "Phase 7 Yesod-Orchestration: SPARC Architecture", "5319E7", "yesod_integrationfoundation.md", "phase_7_yesod_orchestration.md", "phase:yesod-embodiment"),
    WorkflowPhase("8", "phase:yesod-embodiment", "Yesod-Embodiment", "Phase 8 Yesod-Embodiment: SPARC Refinement", "8250DF", "yesod_transmissionembodiment.md", "phase_8_yesod_embodiment.md", "phase:malkhut"),
    WorkflowPhase("9", "phase:malkhut", "Malkhut", "Phase 9 Malkhut: SPARC Completion", "D1242F", "malkhut_completionsovereignty.md", "phase_9_malkhut.md", "phase:hod-refactoring"),
    WorkflowPhase("10", "phase:hod-refactoring", "Hod-Refactoring", "Phase 10 Hod Refactoring: Structural Clarity", "1F6FEB", "hod_refactoringstructuralclarity.md", "phase_10_hod_refactoring.md", None),
]

class WorkflowPhaseRegistry:
    def __init__(self, phases: list[WorkflowPhase]):
        self._phases = phases
        self._by_id = {p.id: p for p in phases}
        self._by_label = {p.label: p for p in phases}
        
    def get_by_id(self, phase_id: str) -> WorkflowPhase | None:
        return self._by_id.get(phase_id)
        
    def get_by_label(self, label: str) -> WorkflowPhase | None:
        return self._by_label.get(label)
        
    def get_all(self) -> list[WorkflowPhase]:
        return list(self._phases)

PHASE_REGISTRY = WorkflowPhaseRegistry(_phases)

# --- Backward Compatibility Mappings (To be phased out) ---
PHASE_DISPLAY_NAME_MAP = {p.id: p.name for p in _phases}

PHASE_LABEL_METADATA = {p.label: {"description": p.description, "color": p.color} for p in _phases}
PHASE_LABEL_METADATA[NEEDS_HUMAN_LABEL] = {
    "description": "Workflow halted: requires human intervention",
    "color": "B60205",
}

NEXT_LABEL_MAP = {p.label: p.next_phase_label for p in _phases}
PHASE_LABELS = tuple(NEXT_LABEL_MAP.keys())

PERSONA_FILE_MAP = {p.id: p.persona_file for p in _phases}
FUNCTIONAL_MICROAGENT_PERSONA_FILE_MAP = {p.id: p.microagent_persona_file for p in _phases}

LABEL_PHASE_MAP = {p.label: p.id for p in _phases}

DISCUSSION_PHASES = {p.id for p in _phases if p.is_discussion_phase}
KETER_DERIVED_PHASES = {"2A", "2B", "2C"}
SPECIFICATION_PHASE = "4"
PRE_IMPLEMENTATION_PHASES = DISCUSSION_PHASES | {SPECIFICATION_PHASE}
IMPLEMENTATION_PHASES = {p.id for p in _phases if p.is_implementation_phase}

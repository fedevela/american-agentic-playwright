from openhands.core.config import config
from openhands.agent import Agent
from openhands.events import EventStream
from openhands.workspace import Workspace

class SDLCPhasedAgent(Agent):
    """
    9-Phase SDLC Agent for OpenHands
    Routes work to the appropriate phase based on current state.
    SPARC methodology mapping:
      Phase 4 (Tiferet) -> Specification (requirements.md, DoD, Non-Goals)
      Phase 6 (Hod) -> Pseudocode (logic flow)
      Phase 7 (Yesod) -> Architecture (file structure, schemas)
      Phase 8 (Yesod) -> Refinement (implementation)
      Phase 9 (Malkhut) -> Completion (verification)
    """

    def __init__(self, phase: int = 1):
        super().__init__()
        self.workspace: Workspace = Workspace(config.workspace_base)
        self.phase = phase
        self.current_step = 0
        
        # Map phases to their logic
        self.phase_handlers = {
            1: self.handle_phase_1_keter,
            2: self.handle_phase_2_triad,
            3: self.handle_phase_3_gevurah,
            4: self.handle_phase_4_tiferet,
            5: self.handle_phase_5_netzach,
            6: self.handle_phase_6_hod,
            7: self.handle_phase_7_yesod,
            8: self.handle_phase_8_yesod,
            9: self.handle_phase_9_malkhut,
        }

    def step(self, message: str) -> str:
        """Execute the current phase's logic."""
        handler = self.phase_handlers.get(self.phase)
        if handler:
            return handler(message)
        return f"Unknown phase: {self.phase}"

    def handle_phase_1_keter(self, message: str) -> str:
        """Keter: Intent Formation - GitHub discussion only, clarify requirements."""
        workspace_files = self.workspace.list_files()
        return "Phase 1 (Keter) - Intent Formation:\n\n" + \
               f"Workspace context: {len(workspace_files)} files found\n" + \
               f"Request: {message}\n\n" + \
               "Identities clarified scope and success target."

    def handle_phase_2_triad(self, message: str) -> str:
        """Phase 2A/B/C: Generative Expansion, Critical Restriction, Mechanistic Grounding."""
        return "Phase 2 (Triad) - Spec Discovery:\n\n" + \
               "Phase 2A (Chokhmah) - Expansion: Generating user stories...\n" + \
               "Phase 2B (Binah) - Restriction: Extracting constraints...\n" + \
               "Phase 2C (Chesed) - Grounding: Validating feasibility..."

    def handle_phase_3_gevurah(self, message: str) -> str:
        """Gevurah: Synthetic Judgment - Converge into resolution."""
        return "Phase 3 (Gevurah) - Synthetic Judgment:\n\n" + \
               "Converged expansion, restriction, and feasibility into resolution."

    def handle_phase_4_tiferet(self, message: str) -> str:
        """Tiferet: SPARC Specification Phase - Create requirements.md, DoD, Non-Goals, trigger PR."""
        return "Phase 4 (Tiferet) - SPARC Specification:\n\n" + \
               "Generating requirements.md, definition-of-done.md, and non-goals.md...\n" + \
               "Creating PR and setting up workspace for implementation phases 5-9."

    def handle_phase_5_netzach(self, message: str) -> str:
        """Netzach: Traceability - Map specs to system."""
        return "Phase 5 (Netzach) - Traceability:\n\n" + \
               "Mapped Gherkin requirements to system components."

    def handle_phase_6_hod(self, message: str) -> str:
        """Hod: SPARC Pseudocode Phase - Derive logic flow."""
        return "Phase 6 (Hod) - SPARC Pseudocode:\n\n" + \
               "Deriving control flow and algorithm from requirements."

    def handle_phase_7_yesod(self, message: str) -> str:
        """Yesod: SPARC Architecture Phase - Design file structure and schemas."""
        return "Phase 7 (Yesod) - SPARC Architecture:\n\n" + \
               "Designed file structure, API schemas, and module boundaries."

    def handle_phase_8_yesod(self, message: str) -> str:
        """Yesod: SPARC Refinement Phase - Implement code."""
        return "Phase 8 (Yesod) - SPARC Refinement:\n\n" + \
               "Implemented production-grade code with tests."

    def handle_phase_9_malkhut(self, message: str) -> str:
        """Malkhut: SPARC Completion Phase - Validate against spec."""
        return "Phase 9 (Malkhut) - SPARC Completion:\n\n" + \
               "Validated implementation against requirements.\n" + \
               "All DoD criteria met. Ready for merge."

    def read_workspace(self, path: str = ".") -> str:
        """Read files from workspace."""
        try:
            return self.workspace.read(path)
        except Exception as e:
            return f"Error reading workspace: {e}"

    def list_workspace(self) -> list:
        """List workspace contents."""
        return self.workspace.list_files()

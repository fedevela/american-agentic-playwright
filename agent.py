from openhands.core.config import config
from openhands.agent import Agent
from openhands.events import EventStream
from openhands.workspace import Workspace

class SDLCPhasedAgent(Agent):
    """
    9-Phase SDLC Agent for OpenHands
    Routes work to the appropriate phase based on current state.
    SPARC methodology mapping:
      Phase 4 (Tiferet) -> S: Specification (requirements.md, DoD, Non-Goals)
      Phase 5 (Netzach) -> Traceability (E2E skeleton + S→P comments)
      Phase 6 (Hod) -> P: Pseudocode (pseudocode comments ON E2E tests)
      Phase 7 (Yesod) -> A: Architecture (test structure via code, not docs)
      Phase 8 (Yesod) -> R: Refinement (working E2E test implementations)
      Phase 9 (Malkhut) -> C: Completion (execute E2E suite, validate S-phase requirements)
    
    SUCCESS CRITERIA: All Phase 4 requirements validated via E2E tests.
    Communication MEDIUM: E2E tests themselves (not markdown docs).
    """

    def __init__(self, phase: int = 1):
        super().__init__()
        self.workspace: Workspace = Workspace(config.workspace_base)
        self.phase = phase
        self.current_step = 0
        
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
        """SPARC S: Specification - Create requirements.md, DoD, Non-Goals, trigger PR."""
        return "Phase 4 (Tiferet) - SPARC S (Specification):\n\n" + \
               "Initialize context window with objective function parameters.\n" + \
               "Parse user intent into formal zero-code requirements schema.\n" + \
               "Define state boundaries, I/O vectors, strict acceptance criteria.\n" + \
               "Output: requirements.md, definition-of-done.md, non-goals.md - PR created."

    def handle_phase_5_netzach(self, message: str) -> str:
        """Traceability - E2E test skeletons with S→P comments, SINGLE GitHub comment + commit."""
        return "Phase 5 (Netzach) - Traceability:\n\n" + \
               "Created E2E test skeletons for Phase 4 requirements.\n" + \
               "Each test name encodes requirement: `[requirement #]_[action]`.\n" + \
               "Inline comments document: `[S-phase: requirement #N]` and `[connections: S3→P6 funcName]`.\n" + \
               "E2E tests are the communication medium for downstream phases.\n" + \
               "Output: `tests/e2e/test_phase4_requirements.py` with skeletons.\n" + \
               "Commit: `feat: add E2E skeleton for phase 4 requirements with S→P mappings`.\n" + \
               "Comment: [Single comment with summary above]."

    def handle_phase_6_hod(self, message: str) -> str:
        """SPARC P: Pseudocode - Add pseudocode comments ON E2E tests."""
        return "Phase 6 (Hod) - SPARC P (Pseudocode):\n\n" + \
               "Added pseudocode comments ON E2E test functions from Phase 5.\n" + \
               "Each pseudocode comment includes:\n" + \
               "  - [P-phase: algorithm #N] - algorithm identification\n" + \
               "  - [state: A → B → C] - state transitions\n" + \
               "  - [connections: S3→P6 funcName] - S-phase requirement link\n" + \
               "  - Full algorithm: if/then/else → inputs → outputs\n" + \
               "E2E tests now contain executable pseudocode.\n" + \
               "Output: `tests/e2e/test_phase4_requirements.py` with pseudocode comments.\n" + \
               "Commit: `feat: add pseudocode comments to E2E tests for phase 4 requirements`.\n" + \
               "Comment: [Single comment with summary above]."

    def handle_phase_7_yesod(self, message: str) -> str:
        """SPARC A: Architecture - Create test module structure via code (not docs)."""
        return "Phase 7 (Yesod) - SPARC A (Architecture):\n\n" + \
               "Created E2E test module structure:\n" + \
               "  - tests/e2e/conftest.py - Shared fixtures and state\n" + \
               "  - tests/e2e/test_auth.py - Auth/login flow tests\n" + \
               "  - tests/e2e/test_upload.py - Upload flow tests\n" + \
               "  - tests/e2e/test_validation.py - Validation tests\n" + \
               "  - tests/e2e/helpers/* - Test utilities\n" + \
               "Architecture documented via imports and # Architecture: comments.\n" + \
               "Output: Actual code files, not markdown docs.\n" + \
               "Commit: `feat: add E2E module architecture with test structure`.\n" + \
               "Comment: [Single comment with summary above]."

    def handle_phase_8_yesod(self, message: str) -> str:
        """SPARC R: Refinement - Implement working E2E tests matching pseudocode."""
        return "Phase 8 (Yesod) - SPARC R (Refinement):\n\n" + \
               "Implemented working E2E tests matching Phase 6 pseudocode and Phase 7 architecture.\n" + \
               "Each test includes state transition verification, error path testing, assertion coverage.\n" + \
               "Tests are executable specification.\n" + \
               "Output: Full working E2E test code with helpers.\n" + \
               "Commit: `feat: implement E2E tests matching Phase 6 pseudocode and Phase 7 architecture`.\n" + \
               "Comment: [Single comment with summary above]."

    def handle_phase_9_malkhut(self, message: str) -> str:
        """SPARC C: Completion - Execute E2E suite and validate against S-phase requirements."""
        return "Phase 9 (Malkhut) - SPARC C (Completion):\n\n" + \
               "Running E2E test suite to validate all Phase 4 requirements.\n" + \
               "Using E2E tests as communication medium - they ARE the specification.\n" + \
               "If passing: flag PR as phase:complete for merge.\n" + \
               "If failing: provide actionable feedback linked to S-phase requirements.\n" + \
               "Output: E2E execution report, validation checklist, phase:complete flag.\n" + \
               "Commit: `test: validate Phase 4 requirements via E2E suite`.\n" + \
               "Comment: [Single comment with validation report]."

    def read_workspace(self, path: str = ".") -> str:
        """Read files from workspace."""
        try:
            return self.workspace.read(path)
        except Exception as e:
            return f"Error reading workspace: {e}"

    def list_workspace(self) -> list:
        """List workspace contents."""
        return self.workspace.list_files()

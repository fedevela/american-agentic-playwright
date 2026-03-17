"""Prompt-building tests for phase mapping, persona composition, and handoff context.

These tests protect the prompt contract more than formatting details. The
workflow is prompt-driven, so a seemingly small prompt regression can shift the
phase model, remove required traceability instructions, or expose later phases
to the wrong input context.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from trigger_workflow_creative_writer.config import TIFERET_AUTO_ISSUE_PREFIX
from trigger_workflow_creative_writer.runner_utils import resolve_phase_execution_branch
from trigger_workflow_creative_writer.prompts import (
    build_implementation_phase_prompt,
    build_comment_phase_prompt,
    build_phase_2_story_requirements,
    build_phase_prompt_input_context,
    build_tiferet_specification_prompt,
    determine_phase_from_label,
    read_functional_microagent,
    read_microagent_for_label,
)
from trigger_workflow_creative_writer.router import conversation_scope_for_phase


class PhaseWorkflowNamingTests(unittest.TestCase):
    """Guard canonical phase identifiers and session/branch policy helpers.

    These checks pin the stable IDs used throughout routing, branch selection,
    and OpenHands session scoping. If these mappings drift, downstream
    orchestration can silently run the right phase logic against the wrong
    branch or conversation scope.
    """

    def test_determine_phase_from_label_uses_canonical_string_ids(self) -> None:
        self.assertEqual(determine_phase_from_label("phase:keter"), "1")
        self.assertEqual(determine_phase_from_label("phase:chokhmah"), "2A")
        self.assertEqual(determine_phase_from_label("phase:binah"), "2B")
        self.assertEqual(determine_phase_from_label("phase:chesed"), "2C")
        self.assertEqual(determine_phase_from_label("phase:gevurah"), "3")
        self.assertEqual(determine_phase_from_label("phase:tiferet"), "4")
        self.assertEqual(determine_phase_from_label("phase:malkhut"), "9")
        self.assertEqual(determine_phase_from_label("phase:hod-refactoring"), "10")

    def test_branch_name_for_phase_uses_main_before_implementation_and_issue_branch_after(self) -> None:
        self.assertEqual(resolve_phase_execution_branch("fedevela/particle-life-3d", "2B", 12), "main")
        self.assertEqual(resolve_phase_execution_branch("fedevela/particle-life-3d", "4", 12), "main")
        self.assertEqual(resolve_phase_execution_branch("fedevela/particle-life-3d", "5", 12), "issue/12")
        self.assertEqual(resolve_phase_execution_branch("fedevela/particle-life-3d", "9", 12), "issue/12")
        self.assertEqual(resolve_phase_execution_branch("fedevela/particle-life-3d", "10", 12), "issue/12")

    def test_session_scope_for_phase_isolated_for_all_phases(self) -> None:
        self.assertEqual(conversation_scope_for_phase("1"), "phase-1")
        self.assertEqual(conversation_scope_for_phase("2A"), "phase-2A")
        self.assertEqual(conversation_scope_for_phase("2B"), "phase-2B")
        self.assertEqual(conversation_scope_for_phase("2C"), "phase-2C")
        self.assertEqual(conversation_scope_for_phase("4"), "phase-4")
        self.assertEqual(conversation_scope_for_phase("5"), "phase-5")
        self.assertEqual(conversation_scope_for_phase("9"), "phase-9")
        self.assertEqual(conversation_scope_for_phase("10"), "phase-10")


class PromptBuilderTests(unittest.TestCase):
    """Cover the prompt text and context assembly contracts.

    These tests focus on the parts of the prompt stack that encode workflow
    policy: which comments are visible to a phase, which instructions are
    mandatory for Gevurah and Tiferet, and whether downstream implementation
    phases preserve the canonical requirement text they inherit from Tiferet.
    """

    def test_phase_1_prompt_enforces_observable_acceptance_signals(self) -> None:
        prompt = build_comment_phase_prompt(
            "phase:keter",
            12,
            "owner/repo",
            "Keter microagent",
            "1",
            {"title": "Example", "body": "Body", "comments": []},
        )
        self.assertIn("observable, automatable, and verifiable through end-to-end tests", prompt)
        self.assertIn("Do not rely on subjective human judgments", prompt)

    def test_phase_2_story_requirements_enforce_e2e_observable_outcomes(self) -> None:
        requirements = build_phase_2_story_requirements()
        joined = "\n".join(requirements)
        self.assertIn("observable, automatable, and verifiable through end-to-end tests", joined)
        self.assertIn("Write `then` clauses in measurable terms", joined)
        self.assertIn("Do not rely on subjective human judgments", joined)

    def test_phase_3_persona_stack_requires_atomic_id_bearing_requirements_and_justification(self) -> None:
        content = read_microagent_for_label("phase:gevurah", "3")
        self.assertIsNotNone(content)
        assert content is not None
        self.assertIn(
            "Include these exact section headings: `Canonical Narrative Beats`, `Synthesis Decisions`, `Rejected or Deferred`, and `Tiferet Handoff`.",
            content,
        )
        self.assertIn(
            "Each canonical beat bullet must be atomic: exactly one ID, one semaphore, and one single-sentence narrative event",
            content,
        )
        self.assertIn("Use stable requirement IDs in the form `GUID: <TOKEN>-NNN`", content)
        self.assertIn(
            "must explicitly explain which prior ideas were merged, collapsed, narrowed, split, or altered in severity",
            content,
        )

    def test_build_spec_prompt_requires_tiferet_title_prefix_and_consolidation_explanation(self) -> None:
        prompt = build_tiferet_specification_prompt(
            "phase:tiferet",
            12,
            "owner/repo",
            "Tiferet microagent",
            "4",
            {"title": "Example", "body": "Body", "comments": []},
        )
        self.assertIn(f'"title": "{TIFERET_AUTO_ISSUE_PREFIX}Short actionable issue title"', prompt)
        self.assertIn("must explicitly reconcile the Gevurah input against the final child issue set", prompt)
        self.assertIn(
            "If the number of child issues differs from the number of Gevurah suggestions",
            prompt,
        )
        self.assertIn("must state which requirement IDs are covered by each child issue", prompt)
        self.assertIn("Every child issue body must begin with a `Requirement IDs:` line", prompt)
        self.assertIn("Canonical Requirements", prompt)
        self.assertIn("Do not paraphrase or compress them", prompt)

    def test_phase_4_microagent_requires_canonical_requirements_section_verbatim(self) -> None:
        content = read_microagent_for_label("phase:tiferet", "4")

        self.assertIn("`Canonical Beats` section", content)
        self.assertIn("clone the exact canonical beat text", content)

    def test_read_microagent_for_label_composes_base_persona_phase_persona_and_microagent(self) -> None:
        content = read_microagent_for_label("phase:binah", "2B")
        self.assertIsNotNone(content)
        assert content is not None
        self.assertIn("The user is your partner.", content)
        self.assertIn("expanded through Binah", content)
        self.assertIn("functional embodiment of Daneel-through-Binah", content)

    def test_build_phase_input_context_uses_keter_only_for_phase_2_variants(self) -> None:
        # Phase-2 variants are intentionally constrained to the normalized Keter
        # comment so they do not re-interpret the raw issue body independently.
        issue_data = {
            "title": "Example",
            "body": "Original issue body should not be used",
            "comments": [
                {
                    "body": "\n".join(
                        [
                            "<!-- phase:1:start label=phase:keter name=Keter -->",
                            "### Phase 1: Keter",
                            "",
                            "Clarified requirement from Keter.",
                            "",
                            "<!-- phase:1:end label=phase:keter name=Keter -->",
                        ]
                    )
                }
            ],
        }
        context = build_phase_prompt_input_context("phase:binah", 12, "owner/repo", "2B", issue_data)
        self.assertIn("Clarified requirement from Keter.", context)
        self.assertNotIn("Original issue body should not be used", context)

    def test_build_phase_input_context_includes_all_comments_for_phase_3(self) -> None:
        # Gevurah is the first synthesis phase, so it must see the full issue
        # discussion history rather than the narrowed Keter-only context.
        issue_data = {
            "title": "Example",
            "body": "Original body",
            "comments": [
                {"body": "First prior comment."},
                {"body": "Second prior comment."},
            ],
        }

        context = build_phase_prompt_input_context("phase:gevurah", 12, "owner/repo", "3", issue_data)

        self.assertIn("Original body", context)
        self.assertIn("## Issue Comments", context)
        self.assertIn("First prior comment.", context)
        self.assertIn("Second prior comment.", context)

    def test_build_agent_prompt_includes_all_comments_for_phase_5_and_later(self) -> None:
        prompt = build_implementation_phase_prompt(
            "phase:netzach",
            12,
            "owner/repo",
            "Netzach microagent",
            "5",
            {
                "title": "Example",
                "body": "Original body",
                "comments": [{"body": "Implementation context comment."}],
            },
        )

        self.assertIn("## Issue Comments", prompt)
        self.assertIn("Implementation context comment.", prompt)

    def test_phase_5_microagent_enforces_traceability_only_contract_stubs(self) -> None:
        content = read_microagent_for_label("phase:netzach", "5")
        self.assertIn("continuity tracking only", content)
        self.assertIn("placeholder notes", content)
        self.assertIn("YOUR PRECISE DIRECTIVES", content)

    def test_sparc_sister_microagents_include_explicit_alignment_and_boundary_contracts(self) -> None:
        for label, phase in (
            ("phase:hod", "6"),
            ("phase:yesod-orchestration", "7"),
            ("phase:yesod-embodiment", "8"),
            ("phase:malkhut", "9"),
        ):
            content = read_microagent_for_label(label, phase)
            self.assertIn("YOUR NATURE", content)
            self.assertIn("YOUR LAWS", content)

    def test_phase_6_to_9_microagents_include_discovery_procedure_and_completion_gate(self) -> None:
        for label, phase in (
            ("phase:hod", "6"),
            ("phase:yesod-orchestration", "7"),
            ("phase:yesod-embodiment", "8"),
            ("phase:malkhut", "9"),
        ):
            content = read_microagent_for_label(label, phase)
            self.assertIn("YOUR PRECISE DIRECTIVES", content)
            self.assertIn("YOUR NARRATIVE PRODUCTS", content)

    def test_phase_7_microagent_requires_architecture_artifacts_and_non_empty_diff(self) -> None:
        content = read_microagent_for_label("phase:yesod-orchestration", "7")
        self.assertIn("Define the act boundaries and sequence clusters", content)
        self.assertIn("An architectural document establishing act breaks", content)
        self.assertIn("Do not write full dialogue here", content)

    def test_phase_7_prompt_enforces_code_level_artifacts_not_analysis_only(self) -> None:
        prompt = build_implementation_phase_prompt(
            "phase:yesod-orchestration",
            12,
            "owner/repo",
            "Yesod microagent",
            "7",
            {
                "title": "Example",
                "body": "Original body",
                "comments": [{"body": "Architecture context comment."}],
            },
        )
        self.assertIn("Phase-specific requirements:", prompt)
        self.assertIn("Deliver pacing and structural boundaries as actual document changes", prompt)
        self.assertIn("deterministic pacing-discovery pass", prompt)

    def test_phase_10_refactorer_persona_stack_is_resolvable(self) -> None:
        content = read_microagent_for_label("phase:hod-refactoring", "10")
        self.assertIn("expanded through Hod", content)
        self.assertIn("ROLE: Script Revisions", content)
        self.assertIn("show, don't tell", content.lower())
        self.assertIn("preserve the emotional climax", content.lower())

    def test_phase_8_prompt_enforces_deterministic_implementation_discovery_and_completion_gate(self) -> None:
        prompt = build_implementation_phase_prompt(
            "phase:yesod-embodiment",
            12,
            "owner/repo",
            "Yesod embodiment microagent",
            "8",
            {"title": "Example", "body": "Original body", "comments": []},
        )
        self.assertIn("This is Phase 8 (First Draft Execution)", prompt)
        self.assertIn("deterministic scene-discovery pass", prompt)
        self.assertIn("explicit completion gate before finishing", prompt)
        self.assertIn("verify working drafts exist", prompt)

    def test_phase_9_prompt_enforces_deterministic_validation_discovery_and_evidence_gate(self) -> None:
        prompt = build_implementation_phase_prompt(
            "phase:malkhut",
            12,
            "owner/repo",
            "Malkhut microagent",
            "9",
            {"title": "Example", "body": "Original body", "comments": []},
        )
        self.assertIn("This is Phase 9 (The Final Edit)", prompt)
        self.assertIn("deterministic narrative-discovery pass", prompt)
        self.assertIn("evidence-backed readiness status", prompt)

    def test_build_agent_prompt_preserves_canonical_requirements_in_child_issue_body_for_downstream_phases(self) -> None:
        # This fixture models a real Tiferet child issue body. Downstream
        # implementation phases must receive the verbatim Canonical Requirements
        # block, not a stripped-down or normalized variant.
        prompt = build_implementation_phase_prompt(
            "phase:netzach",
            12,
            "owner/repo",
            "Netzach microagent",
            "5",
            {
                "title": "[AUTO/TIFERET] Child issue",
                "body": "\n".join(
                    [
                        "Requirement IDs: CH-001",
                        "",
                        "## Canonical Requirements",
                        "- CH-001: [RED] When user selects third left menu option, WebGL scene initializes with animated dot cloud implementing random walk physics behavior",
                        "",
                        "## Gherkin Scenarios",
                        "Given x, when y, then z.",
                    ]
                ),
                "comments": [],
            },
        )

        self.assertIn("## Canonical Requirements", prompt)
        self.assertIn(
            "- CH-001: [RED] When user selects third left menu option, WebGL scene initializes with animated dot cloud implementing random walk physics behavior",
            prompt,
        )

    def test_build_phase_input_context_errors_when_phase_2_lacks_keter_comment(self) -> None:
        issue_data = {
            "title": "Example",
            "body": "Original body",
            "comments": [],
        }

        with self.assertRaises(SystemExit) as exc:
            build_phase_prompt_input_context("phase:binah", 12, "owner/repo", "2B", issue_data)

        self.assertIn("Phase 2B requires a Phase 1 clarification comment", str(exc.exception))

    @patch("trigger_workflow_creative_writer.prompts.BASE_PERSONA_FILE", "missing-daneel.md")
    def test_read_microagent_for_label_errors_when_base_persona_missing(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            read_microagent_for_label("phase:binah", "2B")

        self.assertIn("Base persona file is missing", str(exc.exception))

    @patch.dict("trigger_workflow_creative_writer.prompts.PERSONA_FILE_MAP", {"2B": "missing-phase-persona.md"}, clear=False)
    def test_read_microagent_for_label_errors_when_phase_persona_missing(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            read_microagent_for_label("phase:binah", "2B")

        self.assertIn("Phase persona file is missing", str(exc.exception))

    @patch.dict(
        "trigger_workflow_creative_writer.prompts.FUNCTIONAL_MICROAGENT_FILE_MAP",
        {"2B": "missing-functional-agent.md"},
        clear=False,
    )
    def test_read_functional_microagent_errors_when_mapped_file_missing(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            read_functional_microagent("phase:binah", "2B")

        self.assertIn("Functional microagent file is missing", str(exc.exception))


if __name__ == "__main__":
    unittest.main()

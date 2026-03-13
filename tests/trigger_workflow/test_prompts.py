"""Prompt-building tests for phase mapping, persona composition, and handoff context.

These tests protect the prompt contract more than formatting details. The
workflow is prompt-driven, so a seemingly small prompt regression can shift the
phase model, remove required traceability instructions, or expose later phases
to the wrong input context.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from trigger_workflow.config import TIFERET_AUTO_ISSUE_PREFIX
from trigger_workflow.openhands_runner import branch_name_for_phase
from trigger_workflow.prompts import (
    build_agent_prompt,
    build_discussion_prompt,
    build_phase_2_story_requirements,
    build_phase_input_context,
    build_spec_prompt,
    determine_phase_from_label,
    read_functional_microagent,
    read_microagent_for_label,
)
from trigger_workflow.router import session_scope_for_phase


class PhaseWorkflowNamingTests(unittest.TestCase):
    """Guard canonical phase identifiers and session/branch policy helpers.

    These checks pin the stable IDs used throughout routing, branch selection,
    and OpenHands session scoping. If these mappings drift, downstream
    orchestration can silently run the right phase logic against the wrong
    branch or conversation scope.
    """

    def test_determine_phase_from_label_uses_canonical_string_ids(self) -> None:
        self.assertEqual(determine_phase_from_label("phase:keter"), "1")
        self.assertEqual(determine_phase_from_label("phase:chokhmah"), "2a")
        self.assertEqual(determine_phase_from_label("phase:binah"), "2b")
        self.assertEqual(determine_phase_from_label("phase:chesed"), "2c")
        self.assertEqual(determine_phase_from_label("phase:gevurah"), "3")
        self.assertEqual(determine_phase_from_label("phase:tiferet"), "4")
        self.assertEqual(determine_phase_from_label("phase:malkhut"), "9")

    def test_branch_name_for_phase_uses_main_before_implementation_and_issue_branch_after(self) -> None:
        self.assertEqual(branch_name_for_phase("fedevela/particle-life-3d", "2b", 12), "main")
        self.assertEqual(branch_name_for_phase("fedevela/particle-life-3d", "4", 12), "main")
        self.assertEqual(branch_name_for_phase("fedevela/particle-life-3d", "5", 12), "issue/12")
        self.assertEqual(branch_name_for_phase("fedevela/particle-life-3d", "9", 12), "issue/12")

    def test_session_scope_for_phase_isolated_for_early_phases_and_shared_for_delivery(self) -> None:
        self.assertEqual(session_scope_for_phase("1"), "phase-1")
        self.assertEqual(session_scope_for_phase("2b"), "phase-2b")
        self.assertEqual(session_scope_for_phase("4"), "phase-4")
        self.assertEqual(session_scope_for_phase("5"), "")
        self.assertEqual(session_scope_for_phase("9"), "")


class PromptBuilderTests(unittest.TestCase):
    """Cover the prompt text and context assembly contracts.

    These tests focus on the parts of the prompt stack that encode workflow
    policy: which comments are visible to a phase, which instructions are
    mandatory for Gevurah and Tiferet, and whether downstream implementation
    phases preserve the canonical requirement text they inherit from Tiferet.
    """

    def test_phase_1_prompt_enforces_observable_acceptance_signals(self) -> None:
        prompt = build_discussion_prompt(
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
            "Include these exact section headings: `Canonical Requirements`, `Synthesis Decisions`, `Rejected or Deferred`, and `Tiferet Handoff`.",
            content,
        )
        self.assertIn(
            "Each canonical requirement bullet must be atomic: exactly one ID, one semaphore, and one single-sentence requirement",
            content,
        )
        self.assertIn("Use stable requirement IDs in the form `GUID: <TOKEN>-NNN`", content)
        self.assertIn("Do not emit domain-specific category headings or capability-family buckets.", content)
        self.assertIn(
            "must explicitly explain which prior requirements were merged, collapsed as duplicates, narrowed, split, re-scoped, or had their semaphore changed",
            content,
        )

    def test_build_spec_prompt_requires_tiferet_title_prefix_and_consolidation_explanation(self) -> None:
        prompt = build_spec_prompt(
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

        self.assertIn("`Canonical Requirements` section", content)
        self.assertIn("clone the exact canonical requirement text", content)

    def test_read_microagent_for_label_composes_base_persona_phase_persona_and_microagent(self) -> None:
        content = read_microagent_for_label("phase:binah", "2b")
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
        context = build_phase_input_context("phase:binah", 12, "owner/repo", "2b", issue_data)
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

        context = build_phase_input_context("phase:gevurah", 12, "owner/repo", "3", issue_data)

        self.assertIn("Original body", context)
        self.assertIn("## Issue Comments", context)
        self.assertIn("First prior comment.", context)
        self.assertIn("Second prior comment.", context)

    def test_build_agent_prompt_includes_all_comments_for_phase_5_and_later(self) -> None:
        prompt = build_agent_prompt(
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

    def test_build_agent_prompt_preserves_canonical_requirements_in_child_issue_body_for_downstream_phases(self) -> None:
        # This fixture models a real Tiferet child issue body. Downstream
        # implementation phases must receive the verbatim Canonical Requirements
        # block, not a stripped-down or normalized variant.
        prompt = build_agent_prompt(
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
            build_phase_input_context("phase:binah", 12, "owner/repo", "2b", issue_data)

        self.assertIn("Phase 2B requires a Phase 1 clarification comment", str(exc.exception))

    @patch("trigger_workflow.prompts.BASE_PERSONA_FILE", "missing-daneel.md")
    def test_read_microagent_for_label_errors_when_base_persona_missing(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            read_microagent_for_label("phase:binah", "2b")

        self.assertIn("Base persona file is missing", str(exc.exception))

    @patch.dict("trigger_workflow.prompts.PERSONA_FILE_MAP", {"2b": "missing-phase-persona.md"}, clear=False)
    def test_read_microagent_for_label_errors_when_phase_persona_missing(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            read_microagent_for_label("phase:binah", "2b")

        self.assertIn("Phase persona file is missing", str(exc.exception))

    @patch.dict(
        "trigger_workflow.prompts.FUNCTIONAL_MICROAGENT_FILE_MAP",
        {"2b": "missing-functional-agent.md"},
        clear=False,
    )
    def test_read_functional_microagent_errors_when_mapped_file_missing(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            read_functional_microagent("phase:binah", "2b")

        self.assertIn("Functional microagent file is missing", str(exc.exception))


if __name__ == "__main__":
    unittest.main()

"""Prompt-building tests for phase mapping, persona composition, and handoff context.

These tests protect the prompt contract more than formatting details. The
workflow is prompt-driven, so a seemingly small prompt regression can shift the
phase model, remove required traceability instructions, or expose later phases
to the wrong input context.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.trigger_workflow_creative_writer.test_dramaturgy import base, established
from trigger_workflow_creative_writer.runner_utils import resolve_phase_execution_branch
from trigger_workflow_creative_writer.prompts import (
    build_implementation_phase_prompt,
    build_comment_phase_prompt,
    build_issue_runtime_context,
    build_phase_2_story_requirements,
    build_phase_prompt_input_context,
    build_tiferet_specification_prompt,
    determine_phase_from_label,
    read_functional_microagent,
    read_microagent_for_label,
)
from trigger_workflow_creative_writer.router import conversation_scope_for_phase


def cycle_issue(*phases):
    from trigger_workflow_creative_writer.cycles import encode_record

    results = established()
    return {
        "title": "Raw title should stay isolated",
        "body": "Original intention should stay isolated",
        "labels": [{"name": "size:season"}],
        "comments": [
            {"body": "Attributed old human discussion."},
            {"body": encode_record({"kind": "cycle", "version": 1, "cycle_id": "cycle-one", "scope": "season"})},
            *[{"body": encode_record(results[phase])} for phase in phases],
        ],
    }


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

    def test_branch_name_for_phase_uses_validated_season_for_all_phases(self) -> None:
        from unittest.mock import patch
        from trigger_workflow_creative_writer.season_branches import SeasonRoot
        with patch("trigger_workflow_creative_writer.runner_utils.resolve_season_root", return_value=SeasonRoot(1, "Season", (12, 1))):
            for phase in ("2B", "4", "5", "9", "10"):
                self.assertEqual(resolve_phase_execution_branch("fedevela/particle-life-3d", phase, 12), "issue/1")

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

    @patch(
        "trigger_workflow_creative_writer.prompts.REQUIRED_CHARACTER_ARTIFACTS",
        ["custom_dimension.md"],
    )
    def test_runtime_context_builds_character_artifact_list_from_validation_contract(self) -> None:
        context = build_issue_runtime_context(
            "phase:keter",
            12,
            "owner/repo",
            "1",
            {"title": "Example", "body": "Body"},
        )

        self.assertIn("6. `bible/characters/[character_name]/custom_dimension.md`", context)
        self.assertNotIn("appearance.md", context)

    def test_phase_1_prompt_establishes_dramatic_axes_without_compliance_prose(self) -> None:
        prompt = build_comment_phase_prompt("phase:keter", 12, "owner/repo", "Keter microagent", "1", cycle_issue())
        for axis in ("pursuit", "opposition", "pressure", "change", "dramatic_question"):
            self.assertIn(axis, prompt)
        self.assertIn("Original intention should stay isolated", prompt)
        for obsolete in ("Clarified Requirement", "Constraints and Invariants", "Acceptance Signals", "Phase 2 Handoff", "Memory Check Directive"):
            self.assertNotIn(obsolete, prompt)

    def test_phase_2_artifacts_have_scope_without_software_story_format(self) -> None:
        joined = "\n".join(build_phase_2_story_requirements())
        self.assertIn("episode", joined)
        self.assertIn("act", joined)
        self.assertIn("scene", joined)
        self.assertIn("season is assigned only by the partner", joined)
        self.assertIn("ready scene leaves", joined)
        self.assertNotIn("Given", joined)
        self.assertNotIn("ORANGE", joined)
        self.assertNotIn("DOM", joined)

    def test_phase_3_persona_stack_preserves_organization_and_human_choice(self) -> None:
        content = read_microagent_for_label("phase:gevurah", "3")
        self.assertIn("dramatic anchors", content)
        self.assertIn("source references", content)
        self.assertIn("partner", content)
        self.assertNotIn("Next Phase Handoff", content)
        self.assertNotIn("GUID", content)

    def test_tiferet_prompt_uses_accepted_synthesis_and_structured_assignments(self) -> None:
        prompt = build_tiferet_specification_prompt("phase:tiferet", 12, "owner/repo", "Tiferet microagent", "4", cycle_issue("1", "2A", "2B", "2C", "3"))
        self.assertIn('"assignments"', prompt)
        self.assertIn("Loyalty at the door", prompt)
        self.assertIn("same scope", prompt)
        self.assertIn("pause advancement and child creation", prompt)
        self.assertNotIn("Resolves Beats:", prompt)
        self.assertNotIn("[SMALL]", prompt)
        self.assertIn("Python owns GitHub dependencies, parent membership, and completion rollup", prompt)

    def test_phase_4_microagent_preserves_accepted_organization_and_recursion(self) -> None:
        content = read_microagent_for_label("phase:tiferet", "4")
        self.assertIn("accepted organization", content)
        self.assertIn("same scope", content)
        self.assertIn("question outcome", content)
        self.assertNotIn("Resolves Beats:", content)

    def test_read_microagent_for_label_composes_base_persona_phase_persona_and_microagent(self) -> None:
        content = read_microagent_for_label("phase:binah", "2B")
        self.assertIsNotNone(content)
        assert content is not None
        self.assertIn("The user is your partner.", content)
        self.assertIn("expanded through Binah", content)
        self.assertIn("You are Daneel-through-Binah", content)

    def test_level_two_sees_accepted_keter_and_canon_without_siblings_or_raw_issue(self) -> None:
        issue_data = cycle_issue("1", "2A", "2B", "2C")
        for phase in ("2A", "2B", "2C"):
            context = build_phase_prompt_input_context("phase:binah", 12, "owner/repo", phase, issue_data)
            self.assertIn("The choice of loyalty", context)
            self.assertIn("bible/characters.md", context)
            self.assertNotIn("Original intention should stay isolated", context)
            self.assertNotIn("Raw title should stay isolated", context)
            self.assertNotIn("Door possibility", context)
            self.assertNotIn("Attributed old human discussion", context)

    def test_gevurah_receives_all_three_current_explorations(self) -> None:
        context = build_phase_prompt_input_context("phase:gevurah", 12, "owner/repo", "3", cycle_issue("1", "2A", "2B", "2C"))
        for phase in ("2A", "2B", "2C"):
            self.assertIn("Door possibility " + phase, context)
        self.assertIn("The choice of loyalty", context)

    def test_downstream_phase_six_retains_preparation_comments(self) -> None:
        prompt = build_implementation_phase_prompt("phase:hod", 12, "owner/repo", "Hod", "6", {"title": "Example", "body": "Outline", "comments": [{"body": "Preparation context comment."}]})
        self.assertIn("Preparation context comment.", prompt)

    def test_phase_5_microagent_requires_ready_assignment_and_episode_manuscript(self) -> None:
        content = read_microagent_for_label("phase:netzach", "5")
        self.assertIn("runtime-validated ready-scene assignment", content)
        self.assertIn("ordered beats", content)
        self.assertIn("one script.md per episode", content)

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

    def test_phase_7_microagent_prepares_action_without_choosing_responses(self) -> None:
        content = read_microagent_for_label("phase:yesod-orchestration", "7")
        self.assertIn("dramatic_action_brief.md", content)
        self.assertIn("what each character can perceive and act upon", content)
        self.assertIn("Do not predetermine discretionary responses", content)

    def test_phase_7_prompt_requires_dramatic_action_brief(self) -> None:
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
        self.assertIn("dramatic_action_brief.md", prompt)
        self.assertIn("stimulus", prompt)

    def test_phase_10_refactorer_persona_stack_is_resolvable(self) -> None:
        content = read_microagent_for_label("phase:hod-refactoring", "10")
        self.assertIn("expanded through Hod", content)
        self.assertIn("ROLE: Script Revisions", content)
        self.assertIn("show, don't tell", content.lower())
        self.assertIn("preserve the emotional climax", content.lower())

    def test_phase_8_prompt_requires_preserved_performance_handoff(self) -> None:
        prompt = build_implementation_phase_prompt(
            "phase:yesod-embodiment",
            12,
            "owner/repo",
            "Yesod embodiment microagent",
            "8",
            {"title": "Example", "body": "Original body", "comments": []},
        )
        self.assertIn("Phase 8 (Performance Materials)", prompt)
        self.assertIn("performance_context.json", prompt)
        self.assertIn("completion gate", prompt)
        self.assertIn("preserve", prompt)

    def test_phase_8_prompt_requires_episode_manuscript_and_version_two_handoff(self) -> None:
        prompt = build_implementation_phase_prompt(
            "phase:yesod-embodiment",
            12,
            "owner/repo",
            "Yesod embodiment microagent",
            "8",
            {"title": "Example", "body": "Original body", "comments": []},
        )
        self.assertIn("scene_template.md", prompt)
        self.assertIn("script.md", prompt)
        self.assertIn("version 3", prompt)
        self.assertIn("actor_safe_bible_paths", prompt)
        self.assertIn("moment_contexts", prompt)
        self.assertIn("scene_materials/<scene_id>", prompt)

    def test_phase_9_prompt_requires_omniscient_director_and_python_orchestration(self) -> None:
        prompt = build_implementation_phase_prompt(
            "phase:malkhut",
            12,
            "owner/repo",
            "Malkhut microagent",
            "9",
            {"title": "Example", "body": "Original body", "comments": []},
        )
        self.assertIn("Phase 9 (Director", prompt)
        self.assertIn("ordered", prompt)
        self.assertIn("thought", prompt)
        self.assertIn("previous_item_observers", prompt)
        self.assertIn("Python", prompt)

    def test_phase_five_receives_validated_beats_and_shared_manuscript_placement(self) -> None:
        from trigger_workflow_creative_writer.cycles import child_assignments
        from trigger_workflow_creative_writer.validation import validate_result

        accepted = established()
        result = validate_result(
            {**base("4"), "assignments": [{"element_id": "cycle-one:e1", "outline": "She opens the door to her enemy."}]},
            phase="4", cycle_id="cycle-one", scope="season", accepted=accepted,
        )
        child = child_assignments(result, parent_issue=1, accepted=accepted)[0]
        issue_data = {"title": child["title"], "body": child["body"], "labels": [{"name": "size:scene"}], "comments": []}
        prompt = build_implementation_phase_prompt("phase:netzach", 12, "owner/repo", "Netzach", "5", issue_data)
        self.assertIn("She opens the door to her enemy.", prompt)
        self.assertIn("She bars the door.", prompt)
        self.assertIn("Script/Season_01/Episode_01", prompt)
        self.assertIn("one script.md per episode", prompt)
        self.assertIn("scene_materials/<scene_id>/", prompt)
        self.assertIn("neighboring scene regions", prompt)

    def test_phase_five_rejects_unstructured_legacy_prose_even_with_phase_label(self) -> None:
        with self.assertRaises(SystemExit):
            build_implementation_phase_prompt("phase:netzach", 12, "owner/repo", "Netzach", "5", {"title": "Legacy [SMALL] scene", "body": "Requirement IDs: CH-001", "labels": [{"name": "phase:netzach"}, {"name": "size:scene"}], "comments": []})

    def test_level_two_requires_structured_current_keter(self) -> None:
        issue_data = {"title": "Example", "body": "Original body", "comments": [{"body": "<!-- phase:1:start -->old prose<!-- phase:1:end -->"}]}
        with self.assertRaises(SystemExit):
            build_phase_prompt_input_context("phase:binah", 12, "owner/repo", "2B", issue_data)

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


class CharacterAuthorshipTests(unittest.TestCase):
    def test_every_phase_stack_assigns_performance_to_character(self):
        from trigger_workflow_creative_writer.config import LABEL_PHASE_MAP
        for label, phase in LABEL_PHASE_MAP.items():
            with self.subTest(phase=phase):
                content = read_microagent_for_label(label, phase)
                self.assertIn("The character is the supreme writer", content)
                self.assertIn("thoughts, dialogue, and actions", content)

    def test_phase_two_contract_and_prompts_agree_on_one_line_ideas(self):
        for phase in ("2A", "2B", "2C"):
            with self.subTest(phase=phase):
                content = read_microagent_for_label("", phase)
                prompt = build_comment_phase_prompt("", 12, "owner/repo", content, phase, cycle_issue("1"))
                self.assertIn("one short sentence on one line per item", prompt)
                self.assertNotIn("independent lyrical possibility with scenes and internal beats", prompt)
                self.assertNotIn("Use lyrical narrative", prompt)

    def test_live_roles_and_revision_preserve_character_authorship(self):
        from trigger_workflow_creative_writer.roundtable import ACTOR_RULES, DIRECTOR_RULES
        self.assertIn("The character is the supreme writer", DIRECTOR_RULES)
        self.assertIn("supreme writer", ACTOR_RULES)
        revision = read_microagent_for_label("", "10")
        self.assertIn("editorial notes", revision)
        self.assertNotIn("sharper dialogue", revision)
        self.assertNotIn("replace by", revision)

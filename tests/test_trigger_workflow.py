from __future__ import annotations

import unittest
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from trigger_workflow.config import TIFERET_AUTO_ISSUE_PREFIX
from trigger_workflow.github_ops import (
    add_blocked_by_dependency,
    add_sub_issue_relationship,
    create_child_issues,
    normalize_tiferet_child_title,
    parse_repo,
    verify_parent_sub_issue_ids,
)
from trigger_workflow.openhands_runner import (
    OpenHandsRunContext,
    branch_name_for_phase,
    load_session_state,
    prepare_openhands_run_context,
    resolve_openhands_model_connection,
    run_openhands,
)
from trigger_workflow.prompts import (
    build_agent_prompt,
    build_phase_input_context,
    build_phase_2_story_requirements,
    build_discussion_prompt,
    build_spec_prompt,
    determine_phase_from_label,
    read_functional_microagent,
    read_microagent_for_label,
)
from trigger_workflow.router import (
    _execute_agent_phase,
    _execute_discussion_phase,
    _execute_specification_phase,
    session_scope_for_phase,
    trigger_agent,
)
from trigger_workflow.validation import validate_phase_four_payload
from trigger_workflow.validation import (
    extract_gevurah_canonical_requirements,
    validate_phase_four_payload_against_gevurah,
)


class PhaseMappingTests(unittest.TestCase):
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


class PromptCompositionTests(unittest.TestCase):
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
        self.assertIn("Include these exact section headings: `Canonical Requirements`, `Synthesis Decisions`, `Rejected or Deferred`, and `Tiferet Handoff`.", content)
        self.assertIn("Each canonical requirement bullet must be atomic: exactly one ID, one semaphore, and one single-sentence requirement", content)
        self.assertIn("Use stable requirement IDs in the form `GUID: <TOKEN>-NNN`", content)
        self.assertIn("Do not emit domain-specific category headings or capability-family buckets.", content)
        self.assertIn("must explicitly explain which prior requirements were merged, collapsed as duplicates, narrowed, split, re-scoped, or had their semaphore changed", content)

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
        self.assertIn("If the number of child issues differs from the number of Gevurah suggestions", prompt)
        self.assertIn("must state which requirement IDs are covered by each child issue", prompt)
        self.assertIn("Every child issue body must begin with a `Requirement IDs:` line", prompt)
        self.assertIn("Canonical Requirements", prompt)
        self.assertIn("Do not paraphrase or compress them", prompt)

    def test_read_microagent_for_label_composes_base_persona_phase_persona_and_microagent(self) -> None:
        content = read_microagent_for_label("phase:binah", "2b")
        self.assertIsNotNone(content)
        assert content is not None
        self.assertIn("The user is your partner.", content)
        self.assertIn("expanded through Binah", content)
        self.assertIn("functional embodiment of Daneel-through-Binah", content)

    def test_build_phase_input_context_uses_keter_only_for_phase_2_variants(self) -> None:
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

    @patch.dict("trigger_workflow.prompts.FUNCTIONAL_MICROAGENT_FILE_MAP", {"2b": "missing-functional-agent.md"}, clear=False)
    def test_read_functional_microagent_errors_when_mapped_file_missing(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            read_functional_microagent("phase:binah", "2b")

        self.assertIn("Functional microagent file is missing", str(exc.exception))


class ChildIssueCreationTests(unittest.TestCase):
    def test_normalize_tiferet_child_title_adds_prefix_once(self) -> None:
        self.assertEqual(
            normalize_tiferet_child_title("Implement Something"),
            f"{TIFERET_AUTO_ISSUE_PREFIX}Implement Something",
        )
        self.assertEqual(
            normalize_tiferet_child_title(f"{TIFERET_AUTO_ISSUE_PREFIX}Implement Something"),
            f"{TIFERET_AUTO_ISSUE_PREFIX}Implement Something",
        )

    @patch("trigger_workflow.github_ops.fetch_parent_sub_issue_ids", return_value={1001, 1002, 1003})
    @patch("trigger_workflow.github_ops.add_blocked_by_dependency")
    @patch("trigger_workflow.github_ops.add_sub_issue_relationship")
    @patch("trigger_workflow.github_ops.create_issue_via_api")
    def test_create_child_issues_creates_in_order_and_links_predecessors(
        self,
        create_issue_via_api_mock,
        add_sub_issue_relationship_mock,
        add_blocked_by_dependency_mock,
        fetch_parent_sub_issue_ids_mock,
    ) -> None:
        create_issue_via_api_mock.side_effect = [
            {"number": 101, "id": 1001, "html_url": "https://example.test/101"},
            {"number": 102, "id": 1002, "html_url": "https://example.test/102"},
            {"number": 103, "id": 1003, "html_url": "https://example.test/103"},
        ]

        created = create_child_issues(
            "owner/repo",
            77,
            [
                {"title": "First", "body": "Body one"},
                {"title": "Second", "body": "Body two"},
                {"title": "Third", "body": "Body three"},
            ],
        )

        self.assertEqual([item["number"] for item in created], [101, 102, 103])
        self.assertEqual(create_issue_via_api_mock.call_count, 3)
        self.assertEqual(
            create_issue_via_api_mock.call_args_list[0].args[1],
            f"{TIFERET_AUTO_ISSUE_PREFIX}First",
        )
        first_body = create_issue_via_api_mock.call_args_list[0].args[2]
        self.assertIn("Automatically created by Phase 4/Tiferet from parent issue #77.", first_body)
        self.assertIn("Parent issue: #77", first_body)
        self.assertEqual(created[0]["title"], f"{TIFERET_AUTO_ISSUE_PREFIX}First")

        add_sub_issue_relationship_mock.assert_any_call("owner/repo", 77, 1001)
        add_sub_issue_relationship_mock.assert_any_call("owner/repo", 77, 1002)
        add_sub_issue_relationship_mock.assert_any_call("owner/repo", 77, 1003)
        self.assertEqual(add_sub_issue_relationship_mock.call_count, 3)

        add_blocked_by_dependency_mock.assert_any_call("owner/repo", 102, 1001)
        add_blocked_by_dependency_mock.assert_any_call("owner/repo", 103, 1002)
        self.assertEqual(add_blocked_by_dependency_mock.call_count, 2)
        fetch_parent_sub_issue_ids_mock.assert_called_once_with("owner/repo", 77)

    @patch("trigger_workflow.github_ops.time.sleep")
    @patch("trigger_workflow.github_ops.fetch_parent_sub_issue_ids")
    def test_verify_parent_sub_issue_ids_retries_until_links_appear(
        self,
        fetch_parent_sub_issue_ids_mock,
        sleep_mock,
    ) -> None:
        fetch_parent_sub_issue_ids_mock.side_effect = [
            set(),
            {1001},
            {1001, 1002},
        ]

        missing = verify_parent_sub_issue_ids(
            "owner/repo",
            77,
            [1001, 1002],
            attempts=3,
            delay_seconds=0.01,
        )

        self.assertEqual(missing, [])
        self.assertEqual(fetch_parent_sub_issue_ids_mock.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 2)

    @patch("trigger_workflow.github_ops.time.sleep")
    @patch("trigger_workflow.github_ops.fetch_parent_sub_issue_ids", return_value=set())
    def test_verify_parent_sub_issue_ids_returns_missing_after_retry_budget_exhausted(
        self,
        fetch_parent_sub_issue_ids_mock,
        sleep_mock,
    ) -> None:
        missing = verify_parent_sub_issue_ids(
            "owner/repo",
            77,
            [1001, 1002],
            attempts=3,
            delay_seconds=0.01,
        )

        self.assertEqual(missing, [1001, 1002])
        self.assertEqual(fetch_parent_sub_issue_ids_mock.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 2)

    def test_parse_repo_rejects_invalid_identifier(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            parse_repo("owner")

        self.assertIn("Expected 'owner/repo'", str(exc.exception))

    @patch("trigger_workflow.github_ops.run_gh")
    def test_add_sub_issue_relationship_uses_typed_field_submission(self, run_gh_mock) -> None:
        run_gh_mock.return_value = subprocess.CompletedProcess(args=["gh"], returncode=0, stdout="", stderr="")

        add_sub_issue_relationship("owner/repo", 77, 1001)

        self.assertEqual(
            run_gh_mock.call_args.args[0],
            [
                "api",
                "repos/owner/repo/issues/77/sub_issues",
                "--method",
                "POST",
                "-F",
                "sub_issue_id=1001",
            ],
        )

    @patch("trigger_workflow.github_ops.run_gh")
    def test_add_blocked_by_dependency_uses_typed_field_submission(self, run_gh_mock) -> None:
        run_gh_mock.return_value = subprocess.CompletedProcess(args=["gh"], returncode=0, stdout="", stderr="")

        add_blocked_by_dependency("owner/repo", 102, 1001)

        self.assertEqual(
            run_gh_mock.call_args.args[0],
            [
                "api",
                "repos/owner/repo/issues/102/dependencies/blocked_by",
                "--method",
                "POST",
                "-F",
                "issue_id=1001",
            ],
        )

    @patch("trigger_workflow.github_ops.fetch_parent_sub_issue_ids", return_value=set())
    @patch("trigger_workflow.github_ops.add_blocked_by_dependency")
    @patch("trigger_workflow.github_ops.add_sub_issue_relationship")
    @patch("trigger_workflow.github_ops.create_issue_via_api")
    def test_create_child_issues_errors_when_parent_sub_issue_attachment_is_missing(
        self,
        create_issue_via_api_mock,
        add_sub_issue_relationship_mock,
        add_blocked_by_dependency_mock,
        fetch_parent_sub_issue_ids_mock,
    ) -> None:
        del add_sub_issue_relationship_mock
        del add_blocked_by_dependency_mock
        del fetch_parent_sub_issue_ids_mock
        create_issue_via_api_mock.return_value = {
            "number": 101,
            "id": 1001,
            "html_url": "https://example.test/101",
        }

        with self.assertRaises(SystemExit) as exc:
            create_child_issues(
                "owner/repo",
                77,
                [{"title": "First", "body": "Body one"}],
            )

        self.assertIn("Missing sub-issue links: #101", str(exc.exception))


class PhaseFourValidationTests(unittest.TestCase):
    def test_validate_phase_four_payload_accepts_requirement_id_traceability(self) -> None:
        payload = {
            "comment": "Decomposition rationale.",
            "sub_issues": [
                {
                    "title": f"{TIFERET_AUTO_ISSUE_PREFIX}Example",
                    "body": "\n".join(
                        [
                            "Requirement IDs: CH-001, CH-003",
                            "",
                            "Canonical Requirements:",
                            "- CH-001: [RED] When x, then y",
                            "- CH-003: [RED] When a, then b",
                            "",
                            "Given x, when y, then z.",
                        ]
                    ),
                }
            ],
        }

        validate_phase_four_payload(payload)

    def test_validate_phase_four_payload_rejects_missing_requirement_ids_line(self) -> None:
        payload = {
            "comment": "Decomposition rationale.",
            "sub_issues": [
                {
                    "title": f"{TIFERET_AUTO_ISSUE_PREFIX}Example",
                    "body": "Given x, when y, then z.",
                }
            ],
        }

        with self.assertRaises(SystemExit) as exc:
            validate_phase_four_payload(payload)

        self.assertIn("must begin with a `Requirement IDs:` line", str(exc.exception))

    def test_extract_gevurah_canonical_requirements_reads_phase_three_comment(self) -> None:
        issue_data = {
            "comments": [
                {
                    "body": "\n".join(
                        [
                            "<!-- phase:3:start label=phase:gevurah name=Gevurah -->",
                            "### Phase 3: Gevurah",
                            "",
                            "## Canonical Requirements",
                            "",
                            "- CH-001: [RED] When user selects the option, then the scene initializes",
                            "- CH-003: [RED] When a dot crosses the boundary, then it wraps",
                            "",
                            "## Synthesis Decisions",
                            "",
                            "Decision text.",
                            "",
                            "<!-- phase:3:end label=phase:gevurah name=Gevurah -->",
                        ]
                    )
                }
            ]
        }

        canonical = extract_gevurah_canonical_requirements(issue_data)

        self.assertEqual(
            canonical["CH-001"],
            "- CH-001: [RED] When user selects the option, then the scene initializes",
        )

    def test_validate_phase_four_payload_against_gevurah_accepts_verbatim_clones(self) -> None:
        issue_data = {
            "comments": [
                {
                    "body": "\n".join(
                        [
                            "<!-- phase:3:start label=phase:gevurah name=Gevurah -->",
                            "### Phase 3: Gevurah",
                            "",
                            "## Canonical Requirements",
                            "",
                            "- CH-001: [RED] When user selects the option, then the scene initializes",
                            "- CH-003: [RED] When a dot crosses the boundary, then it wraps",
                            "",
                            "## Synthesis Decisions",
                            "",
                            "Decision text.",
                        ]
                    )
                }
            ]
        }
        payload = {
            "comment": "Decomposition rationale.",
            "sub_issues": [
                {
                    "title": f"{TIFERET_AUTO_ISSUE_PREFIX}Example",
                    "body": "\n".join(
                        [
                            "Requirement IDs: CH-001, CH-003",
                            "",
                            "## Canonical Requirements",
                            "- CH-001: [RED] When user selects the option, then the scene initializes",
                            "- CH-003: [RED] When a dot crosses the boundary, then it wraps",
                            "",
                            "## Behavior Scenarios",
                            "Given x, when y, then z.",
                        ]
                    ),
                }
            ],
        }

        validate_phase_four_payload_against_gevurah(payload, issue_data)

    def test_validate_phase_four_payload_against_gevurah_rejects_paraphrase(self) -> None:
        issue_data = {
            "comments": [
                {
                    "body": "\n".join(
                        [
                            "<!-- phase:3:start label=phase:gevurah name=Gevurah -->",
                            "### Phase 3: Gevurah",
                            "",
                            "## Canonical Requirements",
                            "",
                            "- CH-001: [RED] When user selects the option, then the scene initializes",
                            "",
                            "## Synthesis Decisions",
                            "",
                            "Decision text.",
                        ]
                    )
                }
            ]
        }
        payload = {
            "comment": "Decomposition rationale.",
            "sub_issues": [
                {
                    "title": f"{TIFERET_AUTO_ISSUE_PREFIX}Example",
                    "body": "\n".join(
                        [
                            "Requirement IDs: CH-001",
                            "",
                            "Canonical Requirements:",
                            "- CH-001: [RED] Initialize the scene when selected",
                            "",
                            "Given x, when y, then z.",
                        ]
                    ),
                }
            ],
        }

        with self.assertRaises(SystemExit) as exc:
            validate_phase_four_payload_against_gevurah(payload, issue_data)

        self.assertIn("copy the full Gevurah requirement line", str(exc.exception))


class RouterExecutionTests(unittest.TestCase):
    @patch("trigger_workflow.router.advance_issue_label")
    @patch("trigger_workflow.router.post_issue_comment")
    @patch("trigger_workflow.router.log_multiline")
    @patch("trigger_workflow.router.run_openhands_for_comment", return_value="Line one\nLine two")
    def test_execute_discussion_phase_logs_generated_comment_body(
        self,
        run_openhands_for_comment_mock,
        log_multiline_mock,
        post_issue_comment_mock,
        advance_issue_label_mock,
    ) -> None:
        del post_issue_comment_mock
        del advance_issue_label_mock
        _execute_discussion_phase(
            "phase:keter",
            55,
            "owner/repo",
            "prompt",
            "1",
            {"title": "Issue", "body": "Body", "comments": []},
        )

        log_multiline_mock.assert_called_once_with("Generated comment", "Line one\nLine two")
        self.assertEqual(run_openhands_for_comment_mock.call_args.kwargs["session_scope"], "phase-1")

    @patch("trigger_workflow.router.post_issue_comment")
    @patch("trigger_workflow.router.log_multiline")
    @patch("trigger_workflow.router.build_phase_four_summary", return_value="Summary body")
    @patch("trigger_workflow.router.create_child_issues", return_value=[])
    @patch("trigger_workflow.router.validate_phase_four_payload")
    @patch(
        "trigger_workflow.router.run_openhands_for_json",
        return_value={"comment": "Parent body", "sub_issues": []},
    )
    def test_execute_specification_phase_uses_strict_phase_session_scope(
        self,
        run_openhands_for_json_mock,
        validate_phase_four_payload_mock,
        create_child_issues_mock,
        build_phase_four_summary_mock,
        log_multiline_mock,
        post_issue_comment_mock,
    ) -> None:
        del validate_phase_four_payload_mock
        del create_child_issues_mock
        del build_phase_four_summary_mock
        del log_multiline_mock
        del post_issue_comment_mock
        issue_data = {
            "title": "Issue",
            "body": "Body",
            "comments": [
                {
                    "body": "\n".join(
                        [
                            "<!-- phase:3:start label=phase:gevurah name=Gevurah -->",
                            "### Phase 3: Gevurah",
                            "",
                            "## Canonical Requirements",
                            "",
                            "- CH-001: [RED] When user selects the option, then the scene initializes",
                            "",
                            "## Synthesis Decisions",
                            "",
                            "Decision text.",
                        ]
                    )
                }
            ],
        }
        _execute_specification_phase(
            "phase:tiferet",
            55,
            "owner/repo",
            "prompt",
            "4",
            issue_data,
        )

        self.assertEqual(run_openhands_for_json_mock.call_args.kwargs["session_scope"], "phase-4")

    @patch("trigger_workflow.router.run_openhands_task")
    def test_execute_agent_phase_uses_shared_issue_session_scope(self, run_openhands_task_mock) -> None:
        _execute_agent_phase(
            "phase:netzach",
            55,
            "owner/repo",
            "prompt",
            "5",
            {"title": "Issue", "body": "Body", "comments": []},
        )

        self.assertEqual(run_openhands_task_mock.call_args.kwargs["session_scope"], "")

    @patch("trigger_workflow.router._execute_agent_phase")
    @patch("trigger_workflow.router._execute_specification_phase")
    @patch("trigger_workflow.router._execute_discussion_phase")
    @patch("trigger_workflow.router.fetch_issue_data")
    @patch("trigger_workflow.router.read_microagent_for_label")
    @patch("trigger_workflow.router.ensure_phase_labels")
    def test_trigger_agent_routes_chesed_to_discussion_phase(
        self,
        ensure_phase_labels_mock,
        read_microagent_for_label_mock,
        fetch_issue_data_mock,
        execute_discussion_mock,
        execute_specification_mock,
        execute_agent_mock,
    ) -> None:
        del ensure_phase_labels_mock
        read_microagent_for_label_mock.return_value = "prompt"
        fetch_issue_data_mock.return_value = {
            "title": "Issue",
            "labels": [{"name": "phase:chesed"}],
            "comments": [],
        }

        trigger_agent(label="phase:chesed", issue=55, repo="owner/repo")

        execute_discussion_mock.assert_called_once()
        execute_specification_mock.assert_not_called()
        execute_agent_mock.assert_not_called()

    @patch("trigger_workflow.router.log_error")
    @patch("trigger_workflow.router.fetch_issue_data")
    @patch("trigger_workflow.router.read_microagent_for_label")
    @patch("trigger_workflow.router.ensure_phase_labels")
    def test_trigger_agent_errors_when_issue_lacks_requested_label(
        self,
        ensure_phase_labels_mock,
        read_microagent_for_label_mock,
        fetch_issue_data_mock,
        log_error_mock,
    ) -> None:
        del ensure_phase_labels_mock
        read_microagent_for_label_mock.return_value = "prompt"
        fetch_issue_data_mock.return_value = {
            "title": "Issue",
            "labels": [{"name": "phase:binah"}],
            "comments": [],
        }

        with self.assertRaises(SystemExit) as exc:
            trigger_agent(label="phase:chesed", issue=55, repo="owner/repo")

        self.assertEqual(exc.exception.code, 1)
        log_error_mock.assert_called_once()
        self.assertIn("is not labeled 'phase:chesed'", log_error_mock.call_args.args[0])


class OpenHandsRunnerTests(unittest.TestCase):
    @patch("trigger_workflow.openhands_runner.openhands_env", return_value={"LLM_MODEL": "env-model", "LLM_BASE_URL": "https://llm.example"})
    def test_resolve_openhands_model_connection_prefers_effective_env_values(self, openhands_env_mock) -> None:
        del openhands_env_mock
        model_name, connection = resolve_openhands_model_connection()

        self.assertEqual(model_name, "env-model")
        self.assertEqual(connection, "https://llm.example")

    def test_resolve_openhands_model_connection_errors_on_invalid_config_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config_dir = workspace / ".openhands"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "config.json").write_text("{invalid json")

            with patch("trigger_workflow.openhands_runner.WORKSPACE", workspace):
                with self.assertRaises(SystemExit) as exc:
                    resolve_openhands_model_connection()

        self.assertIn("Invalid OpenHands config JSON", str(exc.exception))

    def test_load_session_state_errors_on_invalid_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            session_state_path = Path(temp_dir) / ".session-state.json"
            session_state_path.write_text("{invalid json")

            with patch("trigger_workflow.openhands_runner.SESSION_STATE_PATH", session_state_path):
                with self.assertRaises(SystemExit) as exc:
                    load_session_state()

        self.assertIn("Session state file is invalid JSON", str(exc.exception))

    def test_load_session_state_errors_on_non_mapping_payload(self) -> None:
        with TemporaryDirectory() as temp_dir:
            session_state_path = Path(temp_dir) / ".session-state.json"
            session_state_path.write_text('["conv-123"]')

            with patch("trigger_workflow.openhands_runner.SESSION_STATE_PATH", session_state_path):
                with self.assertRaises(SystemExit) as exc:
                    load_session_state()

        self.assertIn("must contain a JSON object", str(exc.exception))

    def test_branch_name_for_phase_errors_for_unknown_repo_config(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            branch_name_for_phase("owner/unknown", "5", 12)

        self.assertIn("No local target repository config exists", str(exc.exception))

    @patch("trigger_workflow.openhands_runner.log_info")
    @patch("trigger_workflow.openhands_runner.current_branch", return_value="issue/21")
    @patch("trigger_workflow.openhands_runner.ensure_git_branch")
    @patch("trigger_workflow.openhands_runner.branch_name_for_phase", return_value="issue/21")
    @patch("trigger_workflow.openhands_runner.resolve_target_repo_config")
    def test_prepare_openhands_run_context_logs_loaded_repo_and_verified_branch(
        self,
        resolve_target_repo_config_mock,
        branch_name_for_phase_mock,
        ensure_git_branch_mock,
        current_branch_mock,
        log_info_mock,
    ) -> None:
        del branch_name_for_phase_mock
        del ensure_git_branch_mock
        del current_branch_mock
        local_path = Path("/tmp/particle-life-3d")
        resolve_target_repo_config_mock.return_value = type(
            "Config",
            (),
            {"local_path": local_path, "main_branch": "main", "issue_branch_prefix": "issue/"},
        )()

        with patch.object(Path, "exists", autospec=True) as exists_mock:
            exists_mock.side_effect = lambda path_obj: str(path_obj) in {
                str(local_path),
                str(local_path / ".git"),
            }
            context = prepare_openhands_run_context("fedevela/particle-life-3d", "5", 21)

        self.assertEqual(context.local_path, local_path)
        self.assertEqual(context.branch, "issue/21")
        messages = [call.args[0] for call in log_info_mock.call_args_list]
        self.assertIn(f"Verified target repository path exists: {local_path}", messages)
        self.assertIn("Resolved target branch for phase 5: issue/21", messages)
        self.assertIn("Verified target repository branch loaded: issue/21", messages)

    @patch("trigger_workflow.openhands_runner.resolve_target_repo_config")
    def test_prepare_openhands_run_context_errors_when_target_repo_path_missing(
        self,
        resolve_target_repo_config_mock,
    ) -> None:
        local_path = Path("/tmp/missing-particle-life-3d")
        resolve_target_repo_config_mock.return_value = type(
            "Config",
            (),
            {"local_path": local_path, "main_branch": "main", "issue_branch_prefix": "issue/"},
        )()

        with patch.object(Path, "exists", autospec=True, return_value=False):
            with self.assertRaises(SystemExit) as exc:
                prepare_openhands_run_context("fedevela/particle-life-3d", "5", 21)

        self.assertIn("Configured target repository path does not exist", str(exc.exception))

    @patch("trigger_workflow.openhands_runner.resolve_target_repo_config")
    def test_prepare_openhands_run_context_errors_when_git_directory_missing(
        self,
        resolve_target_repo_config_mock,
    ) -> None:
        local_path = Path("/tmp/particle-life-3d")
        resolve_target_repo_config_mock.return_value = type(
            "Config",
            (),
            {"local_path": local_path, "main_branch": "main", "issue_branch_prefix": "issue/"},
        )()

        with patch.object(Path, "exists", autospec=True) as exists_mock:
            exists_mock.side_effect = lambda path_obj: str(path_obj) == str(local_path)
            with self.assertRaises(SystemExit) as exc:
                prepare_openhands_run_context("fedevela/particle-life-3d", "5", 21)

        self.assertIn("is not a git checkout", str(exc.exception))

    @patch("trigger_workflow.openhands_runner.current_branch", side_effect=["main", "main"])
    @patch("trigger_workflow.openhands_runner.ensure_git_branch")
    @patch("trigger_workflow.openhands_runner.branch_name_for_phase", return_value="issue/21")
    @patch("trigger_workflow.openhands_runner.resolve_target_repo_config")
    def test_prepare_openhands_run_context_errors_when_branch_verification_fails(
        self,
        resolve_target_repo_config_mock,
        branch_name_for_phase_mock,
        ensure_git_branch_mock,
        current_branch_mock,
    ) -> None:
        del branch_name_for_phase_mock
        del ensure_git_branch_mock
        del current_branch_mock
        local_path = Path("/tmp/particle-life-3d")
        resolve_target_repo_config_mock.return_value = type(
            "Config",
            (),
            {"local_path": local_path, "main_branch": "main", "issue_branch_prefix": "issue/"},
        )()

        with patch.object(Path, "exists", autospec=True) as exists_mock:
            exists_mock.side_effect = lambda path_obj: str(path_obj) in {
                str(local_path),
                str(local_path / ".git"),
            }
            with self.assertRaises(SystemExit) as exc:
                prepare_openhands_run_context("fedevela/particle-life-3d", "5", 21)

        self.assertIn("branch verification failed", str(exc.exception))

    @patch("trigger_workflow.openhands_runner.extract_conversation_id", return_value="")
    @patch("trigger_workflow.openhands_runner.prepare_openhands_run_context")
    @patch("trigger_workflow.openhands_runner.subprocess.run")
    def test_run_openhands_uses_target_repo_cwd(
        self,
        subprocess_run_mock,
        prepare_openhands_run_context_mock,
        extract_conversation_id_mock,
    ) -> None:
        del extract_conversation_id_mock
        target_path = Path("/tmp/particle-life-3d")
        prepare_openhands_run_context_mock.return_value = OpenHandsRunContext(
            local_path=target_path,
            branch="main",
        )
        subprocess_run_mock.return_value = subprocess.CompletedProcess(
            args=["openhands"],
            returncode=0,
            stdout="Conversation ID: abc123\n",
            stderr="",
        )

        run_openhands("Test prompt", repo="fedevela/particle-life-3d", issue=21, phase="3")

        subprocess_run_mock.assert_called_once()
        self.assertEqual(subprocess_run_mock.call_args.kwargs["cwd"], target_path)

    @patch("trigger_workflow.openhands_runner.extract_conversation_id", return_value="")
    @patch("trigger_workflow.openhands_runner.load_session_state", return_value={"fedevela/particle-life-3d#21": "conv-123"})
    @patch("trigger_workflow.openhands_runner.prepare_openhands_run_context")
    @patch("trigger_workflow.openhands_runner.subprocess.run")
    def test_run_openhands_resumes_existing_conversation_for_same_repo_and_issue(
        self,
        subprocess_run_mock,
        prepare_openhands_run_context_mock,
        load_session_state_mock,
        extract_conversation_id_mock,
    ) -> None:
        del load_session_state_mock
        del extract_conversation_id_mock
        target_path = Path("/tmp/particle-life-3d")
        prepare_openhands_run_context_mock.return_value = OpenHandsRunContext(
            local_path=target_path,
            branch="issue/21",
        )
        subprocess_run_mock.return_value = subprocess.CompletedProcess(
            args=["openhands"],
            returncode=0,
            stdout="",
            stderr="",
        )

        run_openhands("Test prompt", repo="fedevela/particle-life-3d", issue=21, phase="5")

        command = subprocess_run_mock.call_args.args[0]
        self.assertIn("--resume", command)
        self.assertIn("conv-123", command)

    @patch("trigger_workflow.openhands_runner.extract_conversation_id", return_value="")
    @patch("trigger_workflow.openhands_runner.load_session_state", return_value={"fedevela/particle-life-3d#21": "shared-conv"})
    @patch("trigger_workflow.openhands_runner.prepare_openhands_run_context")
    @patch("trigger_workflow.openhands_runner.subprocess.run")
    def test_run_openhands_does_not_resume_shared_issue_session_when_phase_scope_is_set(
        self,
        subprocess_run_mock,
        prepare_openhands_run_context_mock,
        load_session_state_mock,
        extract_conversation_id_mock,
    ) -> None:
        del load_session_state_mock
        del extract_conversation_id_mock
        target_path = Path("/tmp/particle-life-3d")
        prepare_openhands_run_context_mock.return_value = OpenHandsRunContext(
            local_path=target_path,
            branch="main",
        )
        subprocess_run_mock.return_value = subprocess.CompletedProcess(
            args=["openhands"],
            returncode=0,
            stdout="",
            stderr="",
        )

        run_openhands(
            "Test prompt",
            repo="fedevela/particle-life-3d",
            issue=21,
            phase="2b",
            session_scope="phase-2b",
        )

        command = subprocess_run_mock.call_args.args[0]
        self.assertNotIn("--resume", command)

    @patch("trigger_workflow.openhands_runner.save_session_state")
    @patch("trigger_workflow.openhands_runner.prepare_openhands_run_context")
    @patch("trigger_workflow.openhands_runner.subprocess.run")
    def test_run_openhands_persists_new_conversation_id_under_repo_issue_key(
        self,
        subprocess_run_mock,
        prepare_openhands_run_context_mock,
        save_session_state_mock,
    ) -> None:
        target_path = Path("/tmp/particle-life-3d")
        prepare_openhands_run_context_mock.return_value = OpenHandsRunContext(
            local_path=target_path,
            branch="main",
        )
        subprocess_run_mock.return_value = subprocess.CompletedProcess(
            args=["openhands"],
            returncode=0,
            stdout="Conversation ID: conv-999\n",
            stderr="",
        )

        run_openhands("Test prompt", repo="fedevela/particle-life-3d", issue=21, phase="3")

        save_session_state_mock.assert_called_once()
        saved_state = save_session_state_mock.call_args.args[0]
        self.assertEqual(saved_state["fedevela/particle-life-3d#21"], "conv-999")

    @patch("trigger_workflow.openhands_runner.save_session_state")
    @patch("trigger_workflow.openhands_runner.prepare_openhands_run_context")
    @patch("trigger_workflow.openhands_runner.subprocess.run")
    def test_run_openhands_persists_new_conversation_id_under_phase_scoped_key(
        self,
        subprocess_run_mock,
        prepare_openhands_run_context_mock,
        save_session_state_mock,
    ) -> None:
        target_path = Path("/tmp/particle-life-3d")
        prepare_openhands_run_context_mock.return_value = OpenHandsRunContext(
            local_path=target_path,
            branch="main",
        )
        subprocess_run_mock.return_value = subprocess.CompletedProcess(
            args=["openhands"],
            returncode=0,
            stdout="Conversation ID: conv-phase\n",
            stderr="",
        )

        run_openhands(
            "Test prompt",
            repo="fedevela/particle-life-3d",
            issue=21,
            phase="2b",
            session_scope="phase-2b",
        )

        save_session_state_mock.assert_called_once()
        saved_state = save_session_state_mock.call_args.args[0]
        self.assertEqual(saved_state["fedevela/particle-life-3d#21:phase-2b"], "conv-phase")


if __name__ == "__main__":
    unittest.main()

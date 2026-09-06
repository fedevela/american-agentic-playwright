"""Router tests for phase dispatch and execution policy.

These cases verify that the top-level router sends work to the correct phase
handler and carries the expected session policy into that handler.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from trigger_workflow_creative_writer.router import (
    PhaseExecutionRequest,
    execute_implementation_phase_task,
    execute_comment_phase_handoff,
    execute_tiferet_specification_phase,
    label_for_phase_id,
    resolve_phase_execution_request,
    render_prompt_only_output,
    run_labeled_issue_phase,
    run_labeled_issue_phase_with_mode,
)


class RouterPhaseExecutionTests(unittest.TestCase):
    """Cover dispatch behavior for discussion, specification, and agent phases.

    The router is small, but mistakes here are high impact: the wrong handler,
    the wrong session scope, or the wrong label precondition can advance the
    workflow incorrectly while appearing operationally healthy.
    """

    @patch("trigger_workflow_creative_writer.core.advance_issue_label")
    @patch("trigger_workflow_creative_writer.core.post_issue_comment")
    @patch("trigger_workflow_creative_writer.core.log_multiline")
    @patch("trigger_workflow_creative_writer.core.run_comment_phase", return_value="Line one\nLine two")
    def test_execute_discussion_phase_logs_generated_comment_body(
        self,
        run_comment_phase_mock,
        log_multiline_mock,
        post_issue_comment_mock,
        advance_issue_label_mock,
    ) -> None:
        del post_issue_comment_mock
        del advance_issue_label_mock
        execute_comment_phase_handoff(
            PhaseExecutionRequest(
                label="phase:keter",
                issue=55,
                repo="owner/repo",
                microagent_content="prompt",
                phase="1",
                issue_data={"title": "Issue", "body": "Body", "comments": []},
            )
        )

        log_multiline_mock.assert_called_once_with("Generated comment", "Line one\nLine two")
        self.assertEqual(run_comment_phase_mock.call_args.kwargs["session_scope"], "phase-1")

    @patch("trigger_workflow_creative_writer.core.post_issue_comment")
    @patch("trigger_workflow_creative_writer.core.clear_issue_labels_except")
    @patch("trigger_workflow_creative_writer.core.create_issue_branches_for_child_issues")
    @patch("trigger_workflow_creative_writer.core.log_multiline")
    @patch("trigger_workflow_creative_writer.core.build_phase_four_summary", return_value="Summary body")
    @patch(
        "trigger_workflow_creative_writer.core.create_child_issues",
        return_value=[{"number": 101, "id": 1001, "title": "child", "url": "https://example.com/101"}],
    )
    @patch("trigger_workflow_creative_writer.core.validate_tiferet_specification_payload_structure")
    @patch(
        "trigger_workflow_creative_writer.core.run_json_phase",
        return_value={"comment": "Parent body", "sub_issues": []},
    )
    def test_execute_specification_phase_uses_shared_issue_session_scope(
        self,
        run_json_phase_mock,
        validate_phase_four_payload_mock,
        create_child_issues_mock,
        build_phase_four_summary_mock,
        log_multiline_mock,
        create_issue_branches_for_child_issues_mock,
        clear_issue_labels_except_mock,
        post_issue_comment_mock,
    ) -> None:
        # Phase 4 must validate against a real-looking Gevurah comment, so this
        # fixture includes the canonical requirement block expected by router
        # validation before child issues are posted.
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
        execute_tiferet_specification_phase(
            PhaseExecutionRequest(
                label="phase:tiferet",
                issue=55,
                repo="owner/repo",
                microagent_content="prompt",
                phase="4",
                issue_data=issue_data,
            )
        )

        self.assertEqual(run_json_phase_mock.call_args.kwargs["session_scope"], "phase-4")
        create_issue_branches_for_child_issues_mock.assert_called_once_with("owner/repo", 55, [101])
        clear_issue_labels_except_mock.assert_called_once_with(
            "owner/repo", 55, [], keep=["phase:needsHuman"]
        )

    @patch("trigger_workflow_creative_writer.core.advance_issue_label")
    @patch("trigger_workflow_creative_writer.core.post_issue_comment")
    @patch("trigger_workflow_creative_writer.core.finalize_delivery", return_value="Delivery summary")
    @patch("trigger_workflow_creative_writer.core.run_implementation_phase")
    def test_execute_agent_phase_uses_shared_issue_session_scope(
        self,
        run_implementation_phase_mock,
        finalize_delivery_mock,
        post_issue_comment_mock,
        advance_issue_label_mock,
    ) -> None:
        execute_implementation_phase_task(
            PhaseExecutionRequest(
                label="phase:netzach",
                issue=55,
                repo="owner/repo",
                microagent_content="prompt",
                phase="5",
                issue_data={"title": "Issue", "body": "Body", "comments": []},
            )
        )

        self.assertEqual(run_implementation_phase_mock.call_args.kwargs["session_scope"], "phase-5")
        finalize_delivery_mock.assert_called_once_with(
            repo="owner/repo",
            issue=55,
            phase="5",
            issue_title="Issue",
            issue_data={"title": "Issue", "body": "Body", "comments": []},
        )
        post_issue_comment_mock.assert_called_once()
        advance_issue_label_mock.assert_called_once_with("owner/repo", 55, "phase:netzach")

    @patch("trigger_workflow_creative_writer.core.execute_implementation_phase_task")
    @patch("trigger_workflow_creative_writer.core.execute_tiferet_specification_phase")
    @patch("trigger_workflow_creative_writer.core.execute_comment_phase_handoff")
    @patch("trigger_workflow_creative_writer.core.fetch_issue_data")
    @patch("trigger_workflow_creative_writer.core.read_microagent_for_label")
    @patch("trigger_workflow_creative_writer.core.ensure_phase_labels")
    def test_trigger_agent_routes_chesed_to_discussion_phase(
        self,
        ensure_phase_labels_mock,
        read_microagent_for_label_mock,
        fetch_issue_data_mock,
        execute_discussion_mock,
        execute_specification_mock,
        execute_agent_mock,
    ) -> None:
        # Chesed is still a discussion-only phase. This test keeps the router
        # from accidentally routing it into the specification or implementation
        # execution paths.
        del ensure_phase_labels_mock
        read_microagent_for_label_mock.return_value = "prompt"
        fetch_issue_data_mock.return_value = {
            "title": "Issue",
            "labels": [{"name": "phase:chesed"}],
            "comments": [],
        }

        run_labeled_issue_phase(label="phase:chesed", issue=55, repo="owner/repo")

        execute_discussion_mock.assert_called_once()
        execute_specification_mock.assert_not_called()
        execute_agent_mock.assert_not_called()

    @patch("trigger_workflow_creative_writer.core.log_error")
    @patch("trigger_workflow_creative_writer.core.tag_issue_needs_human")
    @patch("trigger_workflow_creative_writer.core.execute_tiferet_specification_phase", side_effect=SystemExit("phase failed"))
    @patch("trigger_workflow_creative_writer.core.fetch_issue_data")
    @patch("trigger_workflow_creative_writer.core.read_microagent_for_label")
    @patch("trigger_workflow_creative_writer.core.ensure_phase_labels")
    def test_trigger_agent_tags_needs_human_when_pre_netzach_phase_fails(
        self,
        ensure_phase_labels_mock,
        read_microagent_for_label_mock,
        fetch_issue_data_mock,
        execute_tiferet_specification_phase_mock,
        tag_issue_needs_human_mock,
        log_error_mock,
    ) -> None:
        del ensure_phase_labels_mock
        del execute_tiferet_specification_phase_mock
        del log_error_mock
        read_microagent_for_label_mock.return_value = "prompt"
        fetch_issue_data_mock.return_value = {
            "title": "Issue",
            "labels": [{"name": "phase:tiferet"}],
            "comments": [],
        }

        with self.assertRaises(SystemExit) as exc:
            run_labeled_issue_phase(label="phase:tiferet", issue=55, repo="owner/repo")

        self.assertIn("phase failed", str(exc.exception))
        tag_issue_needs_human_mock.assert_called_once_with("owner/repo", 55)

    @patch("trigger_workflow_creative_writer.core.log_error")
    @patch("trigger_workflow_creative_writer.core.fetch_issue_data")
    @patch("trigger_workflow_creative_writer.core.read_microagent_for_label")
    @patch("trigger_workflow_creative_writer.core.ensure_phase_labels")
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
            run_labeled_issue_phase(label="phase:chesed", issue=55, repo="owner/repo")

        self.assertEqual(exc.exception.code, 1)
        log_error_mock.assert_called_once()
        self.assertIn("is not labeled 'phase:chesed'", log_error_mock.call_args.args[0])

    @patch("trigger_workflow_creative_writer.core.preview_phase_execution_plan")
    @patch("trigger_workflow_creative_writer.core.execute_implementation_phase_task")
    @patch("trigger_workflow_creative_writer.core.execute_tiferet_specification_phase")
    @patch("trigger_workflow_creative_writer.core.execute_comment_phase_handoff")
    @patch("trigger_workflow_creative_writer.core.fetch_issue_data")
    @patch("trigger_workflow_creative_writer.core.read_microagent_for_label")
    @patch("trigger_workflow_creative_writer.core.ensure_phase_labels")
    def test_manual_mode_routes_to_preview_only_without_execution_or_label_sync(
        self,
        ensure_phase_labels_mock,
        read_microagent_for_label_mock,
        fetch_issue_data_mock,
        execute_comment_phase_handoff_mock,
        execute_tiferet_specification_phase_mock,
        execute_implementation_phase_task_mock,
        preview_phase_execution_plan_mock,
    ) -> None:
        read_microagent_for_label_mock.return_value = "prompt"
        fetch_issue_data_mock.return_value = {
            "title": "Issue",
            "labels": [{"name": "phase:chesed"}],
            "comments": [],
        }

        run_labeled_issue_phase_with_mode(label="phase:chesed", issue=55, repo="owner/repo", manual=True)

        ensure_phase_labels_mock.assert_not_called()
        preview_phase_execution_plan_mock.assert_called_once()
        execute_comment_phase_handoff_mock.assert_not_called()
        execute_tiferet_specification_phase_mock.assert_not_called()
        execute_implementation_phase_task_mock.assert_not_called()

    @patch("trigger_workflow_creative_writer.core.preview_phase_execution_plan")
    @patch("trigger_workflow_creative_writer.core.fetch_issue_data")
    @patch("trigger_workflow_creative_writer.core.read_microagent_for_label")
    @patch("trigger_workflow_creative_writer.core.ensure_phase_labels")
    def test_manual_mode_forces_requested_label_even_if_issue_labels_do_not_match(
        self,
        ensure_phase_labels_mock,
        read_microagent_for_label_mock,
        fetch_issue_data_mock,
        preview_phase_execution_plan_mock,
    ) -> None:
        read_microagent_for_label_mock.return_value = "prompt"
        fetch_issue_data_mock.return_value = {
            "title": "Issue",
            "labels": [{"name": "phase:hod"}],
            "comments": [],
        }

        run_labeled_issue_phase_with_mode(label="phase:tiferet", issue=55, repo="owner/repo", manual=True)

        ensure_phase_labels_mock.assert_not_called()
        preview_phase_execution_plan_mock.assert_called_once()

    @patch("trigger_workflow_creative_writer.core.log_multiline")
    @patch("trigger_workflow_creative_writer.core.log_info")
    @patch("trigger_workflow_creative_writer.core.build_phase_execution_prompt", return_value=("PROMPT-CONTENT", ""))
    def test_manual_preview_logs_prompt_and_planned_actions_for_implementation(
        self,
        build_phase_execution_prompt_mock,
        log_info_mock,
        log_multiline_mock,
    ) -> None:
        del log_info_mock
        request = PhaseExecutionRequest(
            label="phase:netzach",
            issue=55,
            repo="owner/repo",
            microagent_content="prompt",
            phase="5",
            issue_data={"title": "Issue", "body": "Body", "comments": []},
        )

        from trigger_workflow_creative_writer.router import preview_phase_execution_plan

        preview_phase_execution_plan(request)

        build_phase_execution_prompt_mock.assert_called_once()
        self.assertEqual(log_multiline_mock.call_args_list[0].args[0], "Manual mode prompt for codex (implementation)")
        self.assertEqual(log_multiline_mock.call_args_list[0].args[1], "PROMPT-CONTENT")
        self.assertEqual(log_multiline_mock.call_args_list[1].args[0], "Manual mode planned actions")

    def test_render_prompt_only_output_for_implementation_includes_delivery_steps(self) -> None:
        request = PhaseExecutionRequest(
            label="phase:hod",
            issue=32,
            repo="owner/repo",
            microagent_content="prompt",
            phase="6",
            issue_data={"title": "Issue", "body": "Body", "comments": []},
        )

        rendered = render_prompt_only_output(request, "PROMPT-CONTENT")

        self.assertIn("PROMPT-CONTENT", rendered)
        self.assertIn("Prompt-only planned actions:", rendered)
        self.assertIn("Generate a commit message", rendered)
        self.assertIn("phase:6 issue #32", rendered)
        self.assertIn("Generate a phase delivery comment body", rendered)
        self.assertIn("Commit and push the branch updates.", rendered)

    def test_render_prompt_only_output_for_discussion_preserves_discussion_actions(self) -> None:
        request = PhaseExecutionRequest(
            label="phase:keter",
            issue=10,
            repo="owner/repo",
            microagent_content="prompt",
            phase="1",
            issue_data={"title": "Issue", "body": "Body", "comments": []},
        )

        rendered = render_prompt_only_output(request, "PROMPT-CONTENT")

        self.assertIn("Prepare a commit message", rendered)
        self.assertIn("Generate the gh command to post the comment", rendered)

    @patch("trigger_workflow_creative_writer.core.fetch_issue_data")
    @patch("trigger_workflow_creative_writer.core.read_microagent_for_label")
    def test_resolve_phase_execution_request_can_include_or_exclude_base_persona(
        self,
        read_microagent_for_label_mock,
        fetch_issue_data_mock,
    ) -> None:
        read_microagent_for_label_mock.return_value = "prompt"
        fetch_issue_data_mock.return_value = {
            "title": "Issue",
            "labels": [{"name": "phase:yesod-orchestration"}],
            "comments": [],
        }

        resolve_phase_execution_request(
            label="phase:yesod-orchestration",
            issue=32,
            repo="owner/repo",
            manual=True,
            include_base_persona=False,
        )

        read_microagent_for_label_mock.assert_called_once_with(
            "phase:yesod-orchestration",
            "7",
            include_base_persona=False,
        )

        read_microagent_for_label_mock.reset_mock()
        resolve_phase_execution_request(
            label="phase:yesod-orchestration",
            issue=32,
            repo="owner/repo",
            manual=True,
            include_base_persona=True,
        )
        read_microagent_for_label_mock.assert_called_once_with(
            "phase:yesod-orchestration",
            "7",
            include_base_persona=True,
        )

    def test_label_for_phase_id_resolves_phase_10(self) -> None:
        self.assertEqual(label_for_phase_id("10"), "phase:hod-refactoring")

    def test_label_for_phase_id_unknown_phase_lists_expected_ids(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            label_for_phase_id("bogus")
        self.assertIn("Expected one of:", str(exc.exception))


if __name__ == "__main__":
    unittest.main()

"""Router tests for phase dispatch and execution policy.

These cases verify that the top-level router sends work to the correct phase
handler and carries the expected OpenHands session policy into that handler.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from trigger_workflow.router import (
    execute_implementation_phase_task,
    execute_comment_phase_handoff,
    execute_tiferet_specification_phase,
    run_labeled_issue_phase,
)


class RouterPhaseExecutionTests(unittest.TestCase):
    """Cover dispatch behavior for discussion, specification, and agent phases.

    The router is small, but mistakes here are high impact: the wrong handler,
    the wrong session scope, or the wrong label precondition can advance the
    workflow incorrectly while appearing operationally healthy.
    """

    @patch("trigger_workflow.router.advance_issue_label")
    @patch("trigger_workflow.router.post_issue_comment")
    @patch("trigger_workflow.router.log_multiline")
    @patch("trigger_workflow.router.run_openhands_comment_phase", return_value="Line one\nLine two")
    def test_execute_discussion_phase_logs_generated_comment_body(
        self,
        run_openhands_for_comment_mock,
        log_multiline_mock,
        post_issue_comment_mock,
        advance_issue_label_mock,
    ) -> None:
        del post_issue_comment_mock
        del advance_issue_label_mock
        execute_comment_phase_handoff(
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
    @patch("trigger_workflow.router.validate_tiferet_specification_payload_structure")
    @patch(
        "trigger_workflow.router.run_openhands_json_phase",
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
            "phase:tiferet",
            55,
            "owner/repo",
            "prompt",
            "4",
            issue_data,
        )

        self.assertEqual(run_openhands_for_json_mock.call_args.kwargs["session_scope"], "phase-4")

    @patch("trigger_workflow.router.run_openhands_implementation_phase")
    def test_execute_agent_phase_uses_shared_issue_session_scope(self, run_openhands_task_mock) -> None:
        execute_implementation_phase_task(
            "phase:netzach",
            55,
            "owner/repo",
            "prompt",
            "5",
            {"title": "Issue", "body": "Body", "comments": []},
        )

        self.assertEqual(run_openhands_task_mock.call_args.kwargs["session_scope"], "")

    @patch("trigger_workflow.router.execute_implementation_phase_task")
    @patch("trigger_workflow.router.execute_tiferet_specification_phase")
    @patch("trigger_workflow.router.execute_comment_phase_handoff")
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
            run_labeled_issue_phase(label="phase:chesed", issue=55, repo="owner/repo")

        self.assertEqual(exc.exception.code, 1)
        log_error_mock.assert_called_once()
        self.assertIn("is not labeled 'phase:chesed'", log_error_mock.call_args.args[0])


if __name__ == "__main__":
    unittest.main()

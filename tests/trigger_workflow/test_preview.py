"""Tests for manual and prompt-only preview functions."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from trigger_workflow.context import SfiratPhaseSignal
from trigger_workflow.preview import preview_phase_execution_plan, render_prompt_only_output


class PreviewTests(unittest.TestCase):
    """Test preview features."""

    @patch("trigger_workflow.preview.log_multiline")
    @patch("trigger_workflow.preview.log_info")
    @patch("trigger_workflow.preview.build_phase_execution_prompt", return_value=("PROMPT-CONTENT", ""))
    def test_preview_phase_execution_plan_for_discussion(self, build_mock, log_info_mock, log_multiline_mock) -> None:
        signal = SfiratPhaseSignal(
            label="phase:keter",
            issue=1,
            repo="owner/repo",
            microagent_persona_content="prompt",
            phase="1",
            issue_data={"title": "Issue", "body": "Body", "comments": []},
        )
        preview_phase_execution_plan(signal)
        
        log_multiline_mock.assert_any_call("Manual mode prompt for gemini (discussion)", "PROMPT-CONTENT")
        
        # Check that the planned actions mention posting a comment
        actions_call = log_multiline_mock.call_args_list[1]
        self.assertEqual(actions_call.args[0], "Manual mode planned actions")
        self.assertIn("Post that message to the issue as a phase comment wrapper", actions_call.args[1])

    @patch("trigger_workflow.preview.log_multiline")
    @patch("trigger_workflow.preview.log_info")
    @patch("trigger_workflow.preview.build_phase_execution_prompt", return_value=("PROMPT-CONTENT", ""))
    def test_preview_phase_execution_plan_for_specification(self, build_mock, log_info_mock, log_multiline_mock) -> None:
        signal = SfiratPhaseSignal(
            label="phase:tiferet",
            issue=1,
            repo="owner/repo",
            microagent_persona_content="prompt",
            phase="4",
            issue_data={"title": "Issue", "body": "Body", "comments": []},
        )
        preview_phase_execution_plan(signal)
        
        log_multiline_mock.assert_any_call("Manual mode prompt for gemini (specification JSON)", "PROMPT-CONTENT")
        
        # Check that the planned actions mention creating child issues
        actions_call = log_multiline_mock.call_args_list[1]
        self.assertEqual(actions_call.args[0], "Manual mode planned actions")
        self.assertIn("Create ordered child issues from `payload.sub_issues`", actions_call.args[1])
        self.assertIn("Validate JSON payload structure", actions_call.args[1])

    def test_render_prompt_only_output_for_specification(self) -> None:
        signal = SfiratPhaseSignal(
            label="phase:tiferet",
            issue=1,
            repo="owner/repo",
            microagent_persona_content="prompt",
            phase="4",
            issue_data={"title": "Issue", "body": "Body", "comments": []},
        )
        
        rendered = render_prompt_only_output(signal, "PROMPT-CONTENT")
        
        self.assertIn("PROMPT-CONTENT", rendered)
        self.assertIn("Validate JSON payload structure and requirement traceability", rendered)
        self.assertIn("Create ordered child issues from `payload.sub_issues`", rendered)

if __name__ == "__main__":
    unittest.main()

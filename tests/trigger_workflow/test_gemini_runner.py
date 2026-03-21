"""Tests for the Gemini Runner."""

from __future__ import annotations

import json
import subprocess
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from trigger_workflow.gemini_runner import (
    run_gemini,
    extract_gemini_response,
    extract_json_from_markdown,
    run_gemini_comment_phase,
    run_gemini_json_phase,
)


class GeminiRunnerTests(unittest.TestCase):
    """Test Gemini integration functions."""

    @patch("trigger_workflow.gemini_runner.prepare_phase_execution_context")
    @patch("subprocess.run")
    def test_run_gemini_calls_subprocess_with_args(self, run_mock, prep_mock) -> None:
        context_mock = MagicMock()
        context_mock.local_path = Path("/mock/path")
        context_mock.branch = "branch"
        prep_mock.return_value = context_mock
        
        result_mock = MagicMock()
        result_mock.returncode = 0
        run_mock.return_value = result_mock
        
        run_gemini("Do the thing", repo="owner/repo", issue=1, phase="5")

        run_mock.assert_called_once()
        args = run_mock.call_args.args[0]
        self.assertIn("gemini", args)
        self.assertIn("-p", args)
        self.assertIn("@. @codebase_investigator\n\nDo the thing", args) # Prefix added
    @patch("trigger_workflow.gemini_runner.prepare_phase_execution_context")
    @patch("subprocess.run")
    def test_run_gemini_handles_failure(self, run_mock, prep_mock) -> None:
        context_mock = MagicMock()
        context_mock.local_path = Path("/mock/path")
        prep_mock.return_value = context_mock
        
        result_mock = MagicMock()
        result_mock.returncode = 1
        result_mock.stdout = "Fail out"
        result_mock.stderr = "Fail err"
        run_mock.return_value = result_mock
        
        # Should not raise, just return result
        result = run_gemini("Failing task", repo="owner/repo", issue=1, phase="5")
        self.assertEqual(result.returncode, 1)

    @patch("trigger_workflow.gemini_runner.prepare_phase_execution_context")
    @patch("subprocess.run")
    def test_run_gemini_uses_session_scope_flag(self, run_mock, prep_mock) -> None:
        context_mock = MagicMock()
        context_mock.local_path = Path("/mock/path")
        context_mock.branch = "branch"
        prep_mock.return_value = context_mock
        
        result_mock = MagicMock()
        result_mock.returncode = 0
        run_mock.return_value = result_mock
        
        run_gemini("Do the thing", repo="owner/repo", issue=1, phase="5", session_scope="phase-5")

        run_mock.assert_called_once()
        args = run_mock.call_args.args[0]
        self.assertIn("--resume", args)
        self.assertIn("phase-5", args)

    @patch("trigger_workflow.gemini_runner.prepare_branch_context")
    @patch("subprocess.run")
    def test_run_gemini_uses_branch_override(self, run_mock, prep_mock) -> None:
        context_mock = MagicMock()
        context_mock.local_path = Path("/mock/path")
        prep_mock.return_value = context_mock
        
        result_mock = MagicMock()
        result_mock.returncode = 0
        run_mock.return_value = result_mock
        
        run_gemini("Task", repo="owner/repo", issue=1, phase="5", branch_override="my-branch")
        
        prep_mock.assert_called_once()
        
    def test_extract_gemini_response_success(self) -> None:
        stdout = "Some random logs\n{\"response\": \"Hello World\", \"other\": 1, \"session_id\": \"sess-123\"}"
        self.assertEqual(extract_gemini_response(stdout), ("Hello World", "sess-123"))

    def test_extract_gemini_response_with_prefix_and_suffix(self) -> None:
        stdout = "MCP issues detected.{ \"response\": \"Hello World\", \"other\": 1 }ClearcutLogger"
        self.assertEqual(extract_gemini_response(stdout), ("Hello World", ""))

    def test_extract_gemini_response_no_json(self) -> None:
        stdout = "Some random logs\nWithout any json"
        self.assertEqual(extract_gemini_response(stdout), ("", ""))

    def test_extract_gemini_response_bad_json(self) -> None:
        stdout = "Some random logs\n{bad json"
        self.assertEqual(extract_gemini_response(stdout), ("", ""))

    def test_extract_json_from_markdown(self) -> None:
        text = "Here is json:\n```json\n{\"key\": \"val\"}\n```\nDone."
        self.assertEqual(extract_json_from_markdown(text), '{"key": "val"}')

    def test_extract_json_from_markdown_no_blocks(self) -> None:
        text = '{"key": "val"}'
        self.assertEqual(extract_json_from_markdown(text), '{"key": "val"}')

    @patch("trigger_workflow.gemini_runner.run_gemini")
    def test_run_gemini_comment_phase_success(self, run_mock) -> None:
        res = MagicMock()
        res.returncode = 0
        res.stdout = '{"response": "Hello"}'
        run_mock.return_value = res
        
        result = run_gemini_comment_phase("P", repo="R", issue=1, phase="P")
        self.assertEqual(result, "Hello")

    @patch("trigger_workflow.gemini_runner.run_gemini")
    def test_run_gemini_comment_phase_exits_on_failure(self, run_mock) -> None:
        res = MagicMock()
        res.returncode = 1
        run_mock.return_value = res
        
        with self.assertRaises(SystemExit) as exc:
            run_gemini_comment_phase("P", repo="R", issue=1, phase="P")
        self.assertIn("failed with exit code: 1", str(exc.exception))

    @patch("trigger_workflow.gemini_runner.run_gemini")
    def test_run_gemini_comment_phase_exits_if_no_response(self, run_mock) -> None:
        res = MagicMock()
        res.returncode = 0
        res.stdout = "No json here"
        run_mock.return_value = res
        
        with self.assertRaises(SystemExit) as exc:
            run_gemini_comment_phase("P", repo="R", issue=1, phase="P")
        self.assertIn("returned no response", str(exc.exception))

    @patch("trigger_workflow.gemini_runner.run_gemini_comment_phase")
    def test_run_gemini_json_phase_success(self, run_mock) -> None:
        run_mock.return_value = '```json\n{"val": 1}\n```'
        result = run_gemini_json_phase("P", repo="R", issue=1, phase="P")
        self.assertEqual(result, {"val": 1})

    @patch("trigger_workflow.gemini_runner.run_gemini_comment_phase")
    def test_run_gemini_json_phase_invalid_json(self, run_mock) -> None:
        run_mock.return_value = "Not json"
        with self.assertRaises(SystemExit) as exc:
            run_gemini_json_phase("P", repo="R", issue=1, phase="P")
        self.assertIn("not return valid JSON", str(exc.exception))


if __name__ == "__main__":
    unittest.main()

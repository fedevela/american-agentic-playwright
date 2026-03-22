"""Tests for the agent execution loop."""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from trigger_workflow.execution_loop import run_agent_implementation_loop


class ExecutionLoopTests(unittest.TestCase):
    """Test the agent execution and validation loop."""

    @patch("trigger_workflow.execution_loop.extract_gemini_response")
    @patch("trigger_workflow.execution_loop.run_gemini")
    @patch("trigger_workflow.execution_loop.run_phase_tests")
    def test_run_agent_implementation_loop_success_first_try(self, run_tests_mock, run_gemini_mock, extract_mock) -> None:
        gemini_result = MagicMock()
        gemini_result.returncode = 0
        gemini_result.stdout = '{"response": "Mocked JSON"}'
        run_gemini_mock.return_value = gemini_result
        extract_mock.return_value = "Mocked JSON"
        
        test_result = MagicMock()
        test_result.returncode = 0
        test_result.stdout = "Tests passed"
        run_tests_mock.return_value = test_result
        
        result = run_agent_implementation_loop("Task", repo="owner/repo", issue=1, phase="5")
        
        run_gemini_mock.assert_called_once()
        run_tests_mock.assert_called_once()
        self.assertEqual(result, "Mocked JSON")

    @patch("trigger_workflow.execution_loop.run_gemini")
    def test_run_agent_implementation_loop_exits_on_gemini_error(self, run_gemini_mock) -> None:
        gemini_result = MagicMock()
        gemini_result.returncode = 1
        run_gemini_mock.return_value = gemini_result
        
        with self.assertRaises(SystemExit) as exc:
            run_agent_implementation_loop("Task", repo="owner/repo", issue=1, phase="5")
        
        self.assertIn("Agent execution failed with exit code: 1", str(exc.exception))

    @patch("trigger_workflow.execution_loop.run_gemini")
    @patch("trigger_workflow.execution_loop.run_phase_tests")
    def test_run_agent_implementation_loop_skips_validation_for_non_validation_phase(
        self, run_tests_mock, run_gemini_mock
    ) -> None:
        gemini_result = MagicMock()
        gemini_result.returncode = 0
        gemini_result.stdout = "I did it"
        run_gemini_mock.return_value = gemini_result
        
        # Phase 4 is not in VALIDATION_PHASES (which is 5-9)
        run_agent_implementation_loop("Task", repo="owner/repo", issue=1, phase="4")
        
        run_gemini_mock.assert_called_once()
        run_tests_mock.assert_not_called()

    @patch("trigger_workflow.execution_loop.run_gemini")
    @patch("trigger_workflow.execution_loop.run_phase_tests")
    @patch("trigger_workflow.execution_loop.build_single_retry_fix_task")
    def test_run_agent_implementation_loop_retries_on_test_failure(
        self, build_retry_mock, run_tests_mock, run_gemini_mock
    ) -> None:
        gemini_result = MagicMock()
        gemini_result.returncode = 0
        gemini_result.stdout = "I did it"
        run_gemini_mock.return_value = gemini_result
        
        # First test fails, second passes
        test_fail = MagicMock()
        test_fail.returncode = 1
        test_fail.stdout = "Tests failed"
        test_fail.stderr = "Error"
        
        test_pass = MagicMock()
        test_pass.returncode = 0
        test_pass.stdout = "Tests passed"
        
        run_tests_mock.side_effect = [test_fail, test_pass]
        build_retry_mock.return_value = "Retry Task"
        
        run_agent_implementation_loop("Task", repo="owner/repo", issue=1, phase="5")
        
        self.assertEqual(run_gemini_mock.call_count, 2)
        self.assertEqual(run_tests_mock.call_count, 2)
        build_retry_mock.assert_called_once()

    @patch("trigger_workflow.execution_loop.run_gemini")
    @patch("trigger_workflow.execution_loop.run_phase_tests")
    def test_run_agent_implementation_loop_fails_after_max_retries(
        self, run_tests_mock, run_gemini_mock
    ) -> None:
        gemini_result = MagicMock()
        gemini_result.returncode = 0
        gemini_result.stdout = "I did it"
        run_gemini_mock.return_value = gemini_result
        
        test_fail = MagicMock()
        test_fail.returncode = 1
        test_fail.stdout = "Tests failed"
        test_fail.stderr = ""
        
        run_tests_mock.return_value = test_fail
        
        with self.assertRaises(SystemExit) as exc:
            with patch("trigger_workflow.execution_loop.MAX_VALIDATION_ATTEMPTS", 2):
                run_agent_implementation_loop("Task", repo="owner/repo", issue=1, phase="5")
                
        self.assertIn("Validation command contract failed", str(exc.exception))
        self.assertEqual(run_gemini_mock.call_count, 2)
        self.assertEqual(run_tests_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()

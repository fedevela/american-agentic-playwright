"""Tests for the validation runner module."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from trigger_workflow.validation_runner import (
    run_phase_tests,
    summarize_test_output,
    build_single_retry_fix_task,
    ensure_playwright_test_prerequisites,
)


class ValidationRunnerTests(unittest.TestCase):
    """Test validation runner operations."""

    @patch("trigger_workflow.validation_runner.prepare_phase_execution_context")
    @patch("trigger_workflow.validation_runner.ensure_playwright_test_prerequisites")
    @patch("subprocess.run")
    def test_run_phase_tests_success_all_commands(self, run_mock, ensure_mock, prep_mock) -> None:
        context_mock = MagicMock()
        context_mock.local_path = Path("/mock/path")
        prep_mock.return_value = context_mock
        
        # All commands return 0
        success_result = MagicMock()
        success_result.returncode = 0
        success_result.stdout = "OK"
        success_result.stderr = ""
        run_mock.return_value = success_result
        
        result = run_phase_tests(repo="owner/repo", issue=1, phase="5")
        
        self.assertEqual(result.returncode, 0)
        self.assertEqual(run_mock.call_count, 4)  # 4 commands in VALIDATION_COMMANDS

    @patch("trigger_workflow.validation_runner.prepare_phase_execution_context")
    @patch("trigger_workflow.validation_runner.ensure_playwright_test_prerequisites")
    @patch("subprocess.run")
    def test_run_phase_tests_fails_early_on_error(self, run_mock, ensure_mock, prep_mock) -> None:
        context_mock = MagicMock()
        context_mock.local_path = Path("/mock/path")
        prep_mock.return_value = context_mock
        
        # Second command fails
        success_result = MagicMock()
        success_result.returncode = 0
        success_result.stdout = "OK"
        success_result.stderr = ""
        
        fail_result = MagicMock()
        fail_result.returncode = 1
        fail_result.stdout = "FAIL"
        fail_result.stderr = "ERR"
        
        run_mock.side_effect = [success_result, fail_result]
        
        result = run_phase_tests(repo="owner/repo", issue=1, phase="5")
        
        self.assertEqual(result.returncode, 1)
        self.assertEqual(run_mock.call_count, 2)  # Stopped early
        self.assertIn("FAIL", result.stdout)
        self.assertIn("ERR", result.stderr)

    @patch("trigger_workflow.validation_runner.prepare_branch_context")
    @patch("trigger_workflow.validation_runner.ensure_playwright_test_prerequisites")
    @patch("subprocess.run")
    def test_run_phase_tests_uses_branch_override(self, run_mock, ensure_mock, prep_mock) -> None:
        context_mock = MagicMock()
        context_mock.local_path = Path("/mock/path")
        prep_mock.return_value = context_mock
        
        success_result = MagicMock()
        success_result.returncode = 0
        success_result.stdout = "OK"
        success_result.stderr = ""
        run_mock.return_value = success_result
        
        result = run_phase_tests(repo="owner/repo", issue=1, phase="5", branch_override="feature")
        
        prep_mock.assert_called_once_with("owner/repo", branch="feature", branch_log_label="Resolved explicit target branch", issue_data=None)

    def test_summarize_test_output_combines_and_truncates(self) -> None:
        result = subprocess.CompletedProcess(
            args=["test"],
            returncode=1,
            stdout="A" * 6000,
            stderr="B" * 7000
        )
        
        summary = summarize_test_output(result)
        self.assertLessEqual(len(summary), 12000)
        self.assertTrue(summary.endswith("B" * 6000)) # Should be truncated from start

    def test_summarize_test_output_handles_empty(self) -> None:
        result = subprocess.CompletedProcess(args=["test"], returncode=1, stdout="", stderr="")
        summary = summarize_test_output(result)
        self.assertEqual(summary, "(no test output captured)")

    def test_build_single_retry_fix_task_includes_output(self) -> None:
        task = build_single_retry_fix_task("TEST OUTPUT HERE", retry_number=2)
        self.assertIn("TEST OUTPUT HERE", task)
        self.assertIn("attempt 2", task)
        
    @patch("subprocess.run")
    def test_ensure_playwright_test_prerequisites_skips_if_exists(self, run_mock) -> None:
        with patch("pathlib.Path.exists", return_value=True):
            ensure_playwright_test_prerequisites(Path("/mock/path"))
            run_mock.assert_not_called()

    @patch("subprocess.run")
    def test_ensure_playwright_test_prerequisites_installs_and_succeeds(self, run_mock) -> None:
        # First exists() is false, second is true
        with patch("pathlib.Path.exists", side_effect=[False, True]):
            install_result = MagicMock()
            install_result.returncode = 0
            run_mock.return_value = install_result
            
            ensure_playwright_test_prerequisites(Path("/mock/path"))
            
            run_mock.assert_called_once()
            self.assertEqual(run_mock.call_args.args[0], ["npm", "ci"])

    @patch("subprocess.run")
    def test_ensure_playwright_test_prerequisites_fails_install(self, run_mock) -> None:
        with patch("pathlib.Path.exists", return_value=False):
            install_result = MagicMock()
            install_result.returncode = 1
            install_result.stdout = "Fail"
            install_result.stderr = "Err"
            run_mock.return_value = install_result
            
            with self.assertRaises(SystemExit) as exc:
                ensure_playwright_test_prerequisites(Path("/mock/path"))
            self.assertIn("Failed to install npm dependencies", str(exc.exception))

    @patch("subprocess.run")
    def test_ensure_playwright_test_prerequisites_fails_if_still_missing(self, run_mock) -> None:
        with patch("pathlib.Path.exists", return_value=False):
            install_result = MagicMock()
            install_result.returncode = 0
            
            version_result = MagicMock()
            version_result.returncode = 1
            
            run_mock.side_effect = [install_result, version_result]
            
            with self.assertRaises(SystemExit) as exc:
                ensure_playwright_test_prerequisites(Path("/mock/path"))
            self.assertIn("Playwright CLI is still unavailable", str(exc.exception))


if __name__ == "__main__":
    unittest.main()

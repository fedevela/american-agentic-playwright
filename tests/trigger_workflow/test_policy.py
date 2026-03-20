"""Tests for workflow policy."""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
import subprocess

from trigger_workflow.context_resolver.policy import (
    conversation_scope_for_phase,
    describe_phase_conversation_policy,
    detect_local_repo_name,
)


class PolicyTests(unittest.TestCase):
    """Test policy resolution functions."""

    def test_conversation_scope_for_phase_returns_scope_for_strictly_independent(self) -> None:
        self.assertEqual(conversation_scope_for_phase("1"), "phase-1")
        self.assertEqual(conversation_scope_for_phase("4"), "phase-4")
        self.assertEqual(conversation_scope_for_phase("7"), "phase-7")

    def test_conversation_scope_for_phase_returns_empty_for_shared_phases(self) -> None:
        self.assertEqual(conversation_scope_for_phase("shared-phase"), "")
        
    def test_describe_phase_conversation_policy_for_independent(self) -> None:
        desc = describe_phase_conversation_policy("1", "phase-1")
        self.assertIn("strictly independent phase session", desc)
        self.assertIn("'phase-1'", desc)
        
    def test_describe_phase_conversation_policy_for_shared(self) -> None:
        desc = describe_phase_conversation_policy("shared-phase", "")
        self.assertIn("shared per-issue session policy", desc)

    @patch("subprocess.run")
    def test_detect_local_repo_name_handles_ssh_url(self, run_mock) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "git@github.com:owner/repo.git\n"
        run_mock.return_value = mock_result
        
        self.assertEqual(detect_local_repo_name(), "owner/repo")

    @patch("subprocess.run")
    def test_detect_local_repo_name_handles_https_url(self, run_mock) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://github.com/owner/repo.git\n"
        run_mock.return_value = mock_result
        
        self.assertEqual(detect_local_repo_name(), "owner/repo")

    @patch("subprocess.run")
    def test_detect_local_repo_name_handles_url_without_git_suffix(self, run_mock) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://github.com/owner/repo\n"
        run_mock.return_value = mock_result
        
        self.assertEqual(detect_local_repo_name(), "owner/repo")

    @patch("subprocess.run")
    def test_detect_local_repo_name_returns_empty_on_failure(self, run_mock) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        run_mock.return_value = mock_result
        
        self.assertEqual(detect_local_repo_name(), "")

    @patch("subprocess.run")
    def test_detect_local_repo_name_returns_empty_on_exception(self, run_mock) -> None:
        run_mock.side_effect = subprocess.TimeoutExpired(cmd=["git"], timeout=10)
        
        self.assertEqual(detect_local_repo_name(), "")


if __name__ == "__main__":
    unittest.main()

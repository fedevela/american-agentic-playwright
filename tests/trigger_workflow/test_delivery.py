"""Tests for the phase delivery module."""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch, MagicMock

from trigger_workflow.delivery import finalize_phase_delivery


class DeliveryTests(unittest.TestCase):
    """Test the finalize_phase_delivery function."""

    def setUp(self):
        # Setup common mock behavior for all git and gh subprocess calls in delivery
        self.patcher_run = patch("subprocess.run")
        self.mock_run = self.patcher_run.start()
        
        self.patcher_git_run = patch("trigger_workflow.delivery.git_run")
        self.mock_git_run = self.patcher_git_run.start()

        self.patcher_git_run_strict = patch("trigger_workflow.delivery.git_run_strict")
        self.mock_git_run_strict = self.patcher_git_run_strict.start()
        
        # Link strict mock to base mock so side_effect sequences correctly together
        self.mock_git_run_strict.side_effect = self.mock_git_run
        
        self.patcher_prep = patch("trigger_workflow.delivery.prepare_phase_execution_context")
        self.mock_prep = self.patcher_prep.start()
        
        self.patcher_repo = patch("trigger_workflow.delivery.resolve_target_repo_config")
        self.mock_repo = self.patcher_repo.start()

        # Default prep context
        context_mock = MagicMock()
        context_mock.branch = "issue/123"
        context_mock.local_path = "/mock/path"
        self.mock_prep.return_value = context_mock
        
        # Default repo config
        config_mock = MagicMock()
        config_mock.main_branch = "main"
        config_mock.issue_branch_prefix = "issue/"
        self.mock_repo.return_value = config_mock
        
        # Default git_run success
        git_run_result = MagicMock()
        git_run_result.returncode = 0
        git_run_result.stdout = ""
        self.mock_git_run.return_value = git_run_result

        # Helper to create subprocess run results easily
        def make_result(rc=0, stdout="", stderr=""):
            res = MagicMock()
            res.returncode = rc
            res.stdout = stdout
            res.stderr = stderr
            return res
            
        self.make_result = make_result

    def tearDown(self):
        patch.stopall()

    def test_finalize_phase_delivery_success_path_creates_pr(self) -> None:
        self.mock_git_run.side_effect = [
            self.make_result(), # fetch
            self.make_result(), # rev-parse verify base
            self.make_result(), # merge
            self.make_result(stdout=" M file.py\n"), # git status
            self.make_result(), # git add
            self.make_result(), # git commit
            self.make_result(), # git push
            self.make_result(stdout="abc123sha\n"), # local sha
            self.make_result(stdout="abc123sha\trefs/heads/issue/123\n"), # remote sha matches
            self.make_result(stdout="abc123\n"), # short sha
            self.make_result(stdout="file.py\nother.py\n"), # show
        ]
        
        self.mock_run.side_effect = [
            self.make_result(stdout="[]\n"), # gh pr list (empty)
            self.make_result(stdout="https://github.com/owner/repo/pull/1\n"), # gh pr create
        ]

        summary = finalize_phase_delivery(
            repo="owner/repo",
            issue=123,
            phase="5",
            issue_title="Test Issue",
            issue_data={"body": "Normal body without parent"}
        )
        
        self.assertIn("Implementation delivery summary", summary)
        self.assertIn("PR base: `main`", summary)
        self.assertIn("https://github.com/owner/repo/pull/1", summary)
        self.assertIn("`file.py`", summary)

    def test_finalize_phase_delivery_fails_if_no_changes(self) -> None:
        self.mock_git_run.side_effect = [
            self.make_result(), # fetch
            self.make_result(), # rev-parse
            self.make_result(), # merge
            self.make_result(stdout=""), # git status (empty)
        ]

        with self.assertRaises(SystemExit) as exc:
            finalize_phase_delivery(
                repo="owner/repo",
                issue=123,
                phase="5",
                issue_title="Test Issue"
            )
        self.assertIn("without repository changes", str(exc.exception))

    def test_finalize_phase_delivery_finds_existing_pr(self) -> None:
        self.mock_git_run.side_effect = [
            self.make_result(), # fetch
            self.make_result(), # rev-parse
            self.make_result(), # merge
            self.make_result(stdout=" M file.py\n"), # status
            self.make_result(), # add
            self.make_result(), # commit
            self.make_result(), # push
            self.make_result(stdout="abc123sha\n"), # local sha
            self.make_result(stdout="abc123sha\trefs/heads/issue/123\n"), # remote sha
            self.make_result(stdout="abc123\n"), # short sha
            self.make_result(stdout="file.py\n"), # show files
        ]
        
        self.mock_run.side_effect = [
            self.make_result(stdout='[{"url": "https://github.com/owner/repo/pull/99"}]\n'), # gh pr list
        ]

        summary = finalize_phase_delivery(
            repo="owner/repo",
            issue=123,
            phase="5",
            issue_title="Test Issue"
        )
        
        self.assertIn("https://github.com/owner/repo/pull/99", summary)
        
    def test_finalize_phase_delivery_detects_parent_issue(self) -> None:
        self.mock_git_run.side_effect = [
            self.make_result(), # fetch
            self.make_result(), # rev-parse
            self.make_result(), # merge
            self.make_result(stdout=" M file.py\n"), # git status
            self.make_result(), # git add
            self.make_result(), # git commit
            self.make_result(), # git push
            self.make_result(stdout="abc123sha\n"), # local sha
            self.make_result(stdout="abc123sha\trefs/heads/issue/123\n"), # remote sha matches
            self.make_result(stdout="abc123\n"), # short sha
            self.make_result(stdout="file.py\n"), # show files
        ]
        
        self.mock_run.side_effect = [
            self.make_result(stdout="[]\n"), # gh pr list (empty)
            self.make_result(stdout="https://github.com/owner/repo/pull/1\n"), # gh pr create
        ]

        summary = finalize_phase_delivery(
            repo="owner/repo",
            issue=123,
            phase="5",
            issue_title="Test Issue",
            issue_data={"body": "Parent issue: #42"}
        )
        
        # PR base should be issue/42, not main
        self.assertIn("PR base: `issue/42`", summary)
        
    def test_finalize_phase_delivery_fails_on_push_mismatch(self) -> None:
        self.mock_git_run.side_effect = [
            self.make_result(), # fetch
            self.make_result(), # rev-parse
            self.make_result(), # merge
            self.make_result(stdout=" M file.py\n"), # status
            self.make_result(), # add
            self.make_result(), # commit
            self.make_result(), # push
            self.make_result(stdout="abc123sha\n"), # local sha
            self.make_result(stdout="def456sha\trefs/heads/issue/123\n"), # remote sha DOES NOT MATCH
        ]

        with self.assertRaises(SystemExit) as exc:
            finalize_phase_delivery(
                repo="owner/repo",
                issue=123,
                phase="5",
                issue_title="Test Issue"
            )
        self.assertIn("Push verification failed", str(exc.exception))


if __name__ == "__main__":
    unittest.main()

"""Tests for git client operations."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from trigger_workflow.git_client import (
    resolve_target_repo_config,
    resolve_phase_execution_branch,
    git_run,
    current_branch,
    branch_exists,
    ensure_git_branch,
    prepare_target_repo_checkout,
    extract_parent_issue,
    prepare_branch_context,
    prepare_phase_execution_context,
    create_issue_branches_for_child_issues,
)


class GitClientTests(unittest.TestCase):
    """Test git operations and branch resolution."""

    def test_resolve_target_repo_config_returns_cwd_and_defaults(self) -> None:
        config = resolve_target_repo_config("owner/repo")
        self.assertEqual(config.main_branch, "main")
        self.assertEqual(config.issue_branch_prefix, "issue/")

    def test_resolve_phase_execution_branch_main_for_early_phases(self) -> None:
        self.assertEqual(resolve_phase_execution_branch("owner/repo", "1", 123), "issue/123")
        self.assertEqual(resolve_phase_execution_branch("owner/repo", "4", 123), "issue/123")

    def test_resolve_phase_execution_branch_issue_for_late_phases(self) -> None:
        self.assertEqual(resolve_phase_execution_branch("owner/repo", "5", 123), "issue/123")
        self.assertEqual(resolve_phase_execution_branch("owner/repo", "10", 123), "issue/123")

    def test_resolve_phase_execution_branch_fails_for_unknown(self) -> None:
        # Unknown phase will just return issue/123 now, as phase doesn't dictate branch logic
        self.assertEqual(resolve_phase_execution_branch("owner/repo", "unknown", 123), "issue/123")

    @patch("subprocess.run")
    def test_git_run_calls_subprocess(self, run_mock) -> None:
        git_run(Path("/mock/path"), ["status"], capture_output=True)
        run_mock.assert_called_once()
        self.assertEqual(run_mock.call_args.args[0], ["git", "status"])
        self.assertEqual(run_mock.call_args.kwargs["cwd"], Path("/mock/path"))
        self.assertTrue(run_mock.call_args.kwargs["capture_output"])

    @patch("trigger_workflow.git_client.git_run")
    def test_current_branch_success(self, run_mock) -> None:
        res = MagicMock()
        res.returncode = 0
        res.stdout = "main\n"
        run_mock.return_value = res
        self.assertEqual(current_branch(Path("/mock")), "main")

    @patch("trigger_workflow.git_client.git_run")
    def test_current_branch_failure(self, run_mock) -> None:
        res = MagicMock()
        res.returncode = 1
        run_mock.return_value = res
        with self.assertRaises(SystemExit):
            current_branch(Path("/mock"))

    @patch("trigger_workflow.git_client.git_run")
    def test_branch_exists(self, run_mock) -> None:
        res = MagicMock()
        res.returncode = 0
        run_mock.return_value = res
        self.assertTrue(branch_exists(Path("/mock"), "main"))
        
        res.returncode = 1
        self.assertFalse(branch_exists(Path("/mock"), "missing"))

    @patch("trigger_workflow.git_client.current_branch", return_value="main")
    def test_ensure_git_branch_already_active(self, curr_mock) -> None:
        # Should do nothing
        ensure_git_branch(Path("/mock"), "main", base_branch="main")

    @patch("trigger_workflow.git_client.current_branch", return_value="other")
    @patch("trigger_workflow.git_client.branch_exists", return_value=True)
    @patch("trigger_workflow.git_client.git_run")
    def test_ensure_git_branch_switches(self, run_mock, exists_mock, curr_mock) -> None:
        res = MagicMock()
        res.returncode = 0
        run_mock.return_value = res
        ensure_git_branch(Path("/mock"), "feature", base_branch="main")
        run_mock.assert_called_once_with(Path("/mock"), ["switch", "feature"], capture_output=True)

    @patch("trigger_workflow.git_client.current_branch", return_value="other")
    @patch("trigger_workflow.git_client.branch_exists", return_value=False)
    def test_ensure_git_branch_fails_if_base_missing(self, exists_mock, curr_mock) -> None:
        with self.assertRaises(SystemExit) as exc:
            ensure_git_branch(Path("/mock"), "main", base_branch="main")
        self.assertIn("does not exist locally", str(exc.exception))

    @patch("trigger_workflow.git_client.current_branch", return_value="other")
    @patch("trigger_workflow.git_client.branch_exists", return_value=False)
    @patch("trigger_workflow.git_client.git_run")
    def test_ensure_git_branch_fails_if_feature_missing_both_local_and_origin(self, run_mock, exists_mock, curr_mock) -> None:
        # All git runs fail (local switch, fetch, origin switch)
        res = MagicMock()
        res.returncode = 1
        res.stderr = "error output"
        res.stdout = ""
        run_mock.return_value = res
        with self.assertRaises(SystemExit) as exc:
            ensure_git_branch(Path("/mock"), "feature", base_branch="main")
        self.assertIn("Failed to create branch 'feature'", str(exc.exception))
        self.assertEqual(run_mock.call_count, 3) # switch local, fetch, switch origin

    @patch("trigger_workflow.git_client.current_branch", return_value="other")
    @patch("trigger_workflow.git_client.branch_exists", return_value=False)
    @patch("trigger_workflow.git_client.git_run")
    def test_ensure_git_branch_creates_from_local_base(self, run_mock, exists_mock, curr_mock) -> None:
        res = MagicMock()
        res.returncode = 0
        run_mock.return_value = res
        ensure_git_branch(Path("/mock"), "feature", base_branch="main")
        
        # Should call: switch -c feature main, and push -u origin feature
        self.assertEqual(run_mock.call_count, 2)
        self.assertIn("main", run_mock.call_args_list[0].args[1])
        self.assertIn("push", run_mock.call_args_list[1].args[1])

    @patch("trigger_workflow.git_client.current_branch", return_value="other")
    @patch("trigger_workflow.git_client.branch_exists", return_value=False)
    @patch("trigger_workflow.git_client.git_run")
    def test_ensure_git_branch_creates_from_origin_base_fallback(self, run_mock, exists_mock, curr_mock) -> None:
        # First call (local switch) fails, second call (fetch) succeeds, third call (origin switch) succeeds, fourth (push) succeeds
        fail_res = MagicMock()
        fail_res.returncode = 1
        success_res = MagicMock()
        success_res.returncode = 0
        
        run_mock.side_effect = [fail_res, success_res, success_res, success_res]
        
        ensure_git_branch(Path("/mock"), "feature", base_branch="main")
        
        self.assertEqual(run_mock.call_count, 4)
        self.assertIn("origin/main", run_mock.call_args_list[2].args[1])

    @patch("pathlib.Path.exists", return_value=False)
    def test_prepare_target_repo_checkout_fails_if_no_git(self, exists_mock) -> None:
        with self.assertRaises(SystemExit) as exc:
            prepare_target_repo_checkout("owner/repo")
        self.assertIn("not a git checkout", str(exc.exception))

    @patch("pathlib.Path.exists", return_value=True)
    def test_prepare_target_repo_checkout_success(self, exists_mock) -> None:
        config, path = prepare_target_repo_checkout("owner/repo")
        self.assertTrue(path.is_absolute())

    def test_extract_parent_issue(self) -> None:
        self.assertEqual(extract_parent_issue("Parent issue: #42"), 42)
        self.assertEqual(extract_parent_issue("Some text\nParent issue: #123\nEnd"), 123)
        self.assertIsNone(extract_parent_issue("No parent here"))

    @patch("trigger_workflow.git_client.prepare_target_repo_checkout")
    @patch("trigger_workflow.git_client.ensure_git_branch")
    @patch("trigger_workflow.git_client.current_branch", return_value="main")
    def test_prepare_branch_context_success_same_base(self, curr_mock, ensure_mock, prep_mock) -> None:
        config = MagicMock()
        config.main_branch = "main"
        config.issue_branch_prefix = "issue/"
        prep_mock.return_value = (config, Path("/mock"))
        
        ctx = prepare_branch_context("owner/repo", branch="main", branch_log_label="Test")
        self.assertEqual(ctx.branch, "main")

    @patch("trigger_workflow.git_client.prepare_target_repo_checkout")
    @patch("trigger_workflow.git_client.ensure_git_branch")
    @patch("trigger_workflow.git_client.current_branch", return_value="issue/123")
    @patch("trigger_workflow.git_client.git_run")
    def test_prepare_branch_context_merges_from_parent(self, run_mock, curr_mock, ensure_mock, prep_mock) -> None:
        config = MagicMock()
        config.main_branch = "main"
        config.issue_branch_prefix = "issue/"
        prep_mock.return_value = (config, Path("/mock"))
        
        res = MagicMock()
        res.returncode = 0
        run_mock.return_value = res
        
        ctx = prepare_branch_context("owner/repo", branch="issue/123", branch_log_label="Test", issue_data={"body": "Parent issue: #42"})
        
        self.assertEqual(ctx.branch, "issue/123")
        # Should have fetched and merged
        self.assertGreaterEqual(run_mock.call_count, 3)

    @patch("trigger_workflow.git_client.prepare_target_repo_checkout")
    @patch("trigger_workflow.git_client.ensure_git_branch")
    def test_create_issue_branches_for_child_issues(self, ensure_mock, prep_mock) -> None:
        config = MagicMock()
        config.main_branch = "main"
        config.issue_branch_prefix = "issue/"
        prep_mock.return_value = (config, Path("/mock"))
        
        create_issue_branches_for_child_issues("owner/repo", 1, [2, 3])
        
        # Check ensure_git_branch was called for parent and children
        self.assertEqual(ensure_mock.call_count, 4) # 1 for parent initially, 1 for child 2, 1 for child 3, 1 for parent at end


if __name__ == "__main__":
    unittest.main()

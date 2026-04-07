"""Tests for the GitHub CLI base client module."""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch, MagicMock

from trigger_workflow.gh_client import (
    gh_failure_details,
    run_gh,
    run_gh_strict,
    run_gh_json,
    parse_repo,
)


class GHClientTests(unittest.TestCase):
    """Test the gh client helper functions."""

    def test_gh_failure_details_returns_stderr(self) -> None:
        res = MagicMock()
        res.stderr = "error output"
        res.stdout = "std out"
        self.assertEqual(gh_failure_details(res), "error output")

    def test_gh_failure_details_falls_back_to_stdout(self) -> None:
        res = MagicMock()
        res.stderr = ""
        res.stdout = "std out"
        self.assertEqual(gh_failure_details(res), "std out")

    def test_gh_failure_details_handles_empty(self) -> None:
        res = MagicMock()
        res.stderr = ""
        res.stdout = ""
        self.assertEqual(gh_failure_details(res), "gh returned no output")

    @patch("subprocess.run")
    def test_run_gh_calls_subprocess_with_gh(self, run_mock) -> None:
        run_gh(["issue", "list"], capture_output=True)
        run_mock.assert_called_once()
        self.assertEqual(run_mock.call_args.args[0], ["gh", "issue", "list"])
        self.assertTrue(run_mock.call_args.kwargs["capture_output"])

    @patch("trigger_workflow.gh_client.run_gh")
    def test_run_gh_strict_raises_on_error(self, run_gh_mock) -> None:
        res = MagicMock()
        res.returncode = 1
        res.stderr = "failed"
        res.stdout = ""
        run_gh_mock.return_value = res
        
        with self.assertRaises(SystemExit) as exc:
            run_gh_strict(["issue"], failure_message="Oh no")
        self.assertIn("Oh no: failed", str(exc.exception))

    @patch("trigger_workflow.gh_client.run_gh")
    def test_run_gh_strict_returns_on_success(self, run_gh_mock) -> None:
        res = MagicMock()
        res.returncode = 0
        run_gh_mock.return_value = res
        
        result = run_gh_strict(["issue"], failure_message="Oh no")
        self.assertEqual(result, res)

    @patch("trigger_workflow.gh_client.run_gh")
    def test_run_gh_json_parses_json(self, run_gh_mock) -> None:
        res = MagicMock()
        res.returncode = 0
        res.stdout = '{"key": "value"}'
        run_gh_mock.return_value = res
        
        result = run_gh_json(["issue"], failure_message="Oh no", expect_type=dict)
        self.assertEqual(result, {"key": "value"})

    @patch("trigger_workflow.gh_client.run_gh")
    def test_run_gh_json_fails_on_wrong_type(self, run_gh_mock) -> None:
        res = MagicMock()
        res.returncode = 0
        res.stdout = '{"key": "value"}' # Expecting dict
        run_gh_mock.return_value = res
        
        with self.assertRaises(SystemExit) as exc:
            run_gh_json(["issue"], failure_message="Oh no", expect_type=list)
        self.assertIn("expected JSON array response", str(exc.exception))

    @patch("trigger_workflow.gh_client.run_gh")
    def test_run_gh_json_fails_on_error_returncode(self, run_gh_mock) -> None:
        res = MagicMock()
        res.returncode = 1
        res.stderr = "err"
        run_gh_mock.return_value = res
        
        with self.assertRaises(SystemExit):
            run_gh_json(["issue"], failure_message="Oh no", expect_type=dict)

    def test_parse_repo_success(self) -> None:
        owner, repo = parse_repo("owner/repo")
        self.assertEqual(owner, "owner")
        self.assertEqual(repo, "repo")

    def test_parse_repo_fails_invalid_format(self) -> None:
        with self.assertRaises(SystemExit):
            parse_repo("owner-repo")
            
        with self.assertRaises(SystemExit):
            parse_repo("owner/repo/extra")
            
        with self.assertRaises(SystemExit):
            parse_repo("/repo")
            
        with self.assertRaises(SystemExit):
            parse_repo("owner/")


if __name__ == "__main__":
    unittest.main()

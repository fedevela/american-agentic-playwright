"""Tests for github comments operations."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from trigger_workflow.github.comments import post_issue_comment


class GitHubCommentsTests(unittest.TestCase):
    """Test GitHub comment functions."""

    @patch("trigger_workflow.github.comments.run_gh_strict")
    def test_post_issue_comment_calls_gh_cli(self, run_gh_mock) -> None:
        post_issue_comment("owner/repo", 123, "Test body")
        
        run_gh_mock.assert_called_once()
        args = run_gh_mock.call_args.args[0]
        self.assertIn("issue", args)
        self.assertIn("comment", args)
        self.assertIn("123", args)
        self.assertIn("--repo", args)
        self.assertIn("owner/repo", args)
        self.assertIn("--body", args)
        self.assertIn("Test body", args)


if __name__ == "__main__":
    unittest.main()

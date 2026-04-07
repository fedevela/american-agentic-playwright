"""Tests for github discovery operations."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from trigger_workflow.github.discovery import (
    fetch_issue_data,
    resolve_issue_by_label,
    issue_has_label,
    issue_phase_labels,
    resolve_oldest_phased_issue,
)


class GitHubDiscoveryTests(unittest.TestCase):
    """Test GitHub discovery functions."""

    @patch("trigger_workflow.github.discovery.run_gh_json")
    def test_fetch_issue_data_returns_dict(self, run_json_mock) -> None:
        run_json_mock.return_value = {"id": 1, "title": "Test"}
        
        result = fetch_issue_data("owner/repo", 123)
        self.assertEqual(result, {"id": 1, "title": "Test"})
        
        args = run_json_mock.call_args.args[0]
        self.assertIn("123", args)

    @patch("trigger_workflow.github.discovery.run_gh_json")
    def test_resolve_issue_by_label_success(self, run_json_mock) -> None:
        run_json_mock.return_value = [{"number": 123, "title": "Test"}]
        
        result = resolve_issue_by_label("owner/repo", "phase:1")
        self.assertEqual(result, 123)

    @patch("trigger_workflow.github.discovery.run_gh_json")
    def test_resolve_issue_by_label_fails_if_none(self, run_json_mock) -> None:
        run_json_mock.return_value = []
        
        with self.assertRaises(SystemExit) as exc:
            resolve_issue_by_label("owner/repo", "phase:1")
        self.assertIn("No open issues labeled", str(exc.exception))

    @patch("trigger_workflow.github.discovery.run_gh_json")
    def test_resolve_issue_by_label_fails_if_multiple(self, run_json_mock) -> None:
        run_json_mock.return_value = [{"number": 123}, {"number": 124}]
        
        with self.assertRaises(SystemExit) as exc:
            resolve_issue_by_label("owner/repo", "phase:1")
        self.assertIn("Multiple open issues labeled", str(exc.exception))

    @patch("trigger_workflow.github.discovery.run_gh_json")
    def test_resolve_issue_by_label_fails_if_invalid_payload(self, run_json_mock) -> None:
        run_json_mock.return_value = [{"title": "No number"}]
        
        with self.assertRaises(SystemExit) as exc:
            resolve_issue_by_label("owner/repo", "phase:1")
        self.assertIn("Invalid issue payload", str(exc.exception))

    def test_issue_has_label(self) -> None:
        issue = {"labels": [{"name": "phase:1"}, {"name": "other"}]}
        self.assertTrue(issue_has_label(issue, "phase:1"))
        self.assertFalse(issue_has_label(issue, "phase:2"))
        
        # Test empty labels
        self.assertFalse(issue_has_label({}, "phase:1"))

    def test_issue_phase_labels(self) -> None:
        issue = {"labels": [{"name": "phase:keter"}, {"name": "other"}, {"name": "phase:chokhmah"}]}
        labels = issue_phase_labels(issue)
        self.assertIn("phase:keter", labels)
        self.assertIn("phase:chokhmah", labels)
        self.assertNotIn("other", labels)
        
    @patch("trigger_workflow.github.discovery.run_gh_json")
    def test_resolve_oldest_phased_issue_success(self, run_json_mock) -> None:
        run_json_mock.return_value = [
            {"number": 2, "createdAt": "2023-01-02", "labels": [{"name": "phase:chokhmah"}]},
            {"number": 1, "createdAt": "2023-01-01", "labels": [{"name": "phase:keter"}]}, # Older
            {"number": 3, "createdAt": "2023-01-03", "labels": [{"name": "other"}]}, # Ignored
        ]
        
        issue, label = resolve_oldest_phased_issue("owner/repo")
        self.assertEqual(issue, 1)
        self.assertEqual(label, "phase:keter")

    @patch("trigger_workflow.github.discovery.run_gh_json")
    def test_resolve_oldest_phased_issue_fails_if_none(self, run_json_mock) -> None:
        run_json_mock.return_value = [
            {"number": 3, "createdAt": "2023-01-03", "labels": [{"name": "other"}]},
        ]
        
        with self.assertRaises(SystemExit):
            resolve_oldest_phased_issue("owner/repo")

    @patch("trigger_workflow.github.discovery.run_gh_json")
    def test_resolve_oldest_phased_issue_fails_if_multiple_phase_labels(self, run_json_mock) -> None:
        run_json_mock.return_value = [
            {"number": 1, "createdAt": "2023-01-01", "labels": [{"name": "phase:keter"}, {"name": "phase:chokhmah"}]},
        ]
        
        with self.assertRaises(SystemExit) as exc:
            resolve_oldest_phased_issue("owner/repo")
        self.assertIn("has multiple phase labels", str(exc.exception))


if __name__ == "__main__":
    unittest.main()

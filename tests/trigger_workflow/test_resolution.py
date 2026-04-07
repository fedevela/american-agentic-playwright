"""Tests for workflow phase resolution."""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from trigger_workflow.context_resolver.resolution import resolve_phase_signal


class ResolutionTests(unittest.TestCase):
    """Test resolution logic."""

    @patch("trigger_workflow.context_resolver.resolution.detect_local_repo_name")
    def test_resolve_phase_signal_fails_without_repo(self, detect_mock) -> None:
        detect_mock.return_value = ""
        with self.assertRaises(SystemExit) as exc:
            resolve_phase_signal(issue=1, label="phase:keter")
        self.assertIn("Repository name could not be detected", str(exc.exception))

    @patch("trigger_workflow.context_resolver.resolution.resolve_oldest_phased_issue")
    @patch("trigger_workflow.context_resolver.resolution.fetch_issue_data")
    @patch("trigger_workflow.context_resolver.resolution.read_microagent_persona_for_label")
    @patch("trigger_workflow.context_resolver.resolution.ensure_phase_labels")
    def test_resolve_phase_signal_discovers_oldest_issue(
        self, ensure_mock, read_persona_mock, fetch_mock, oldest_mock
    ) -> None:
        oldest_mock.return_value = (10, "phase:keter")
        fetch_mock.return_value = {"title": "Issue", "labels": [{"name": "phase:keter"}], "comments": []}
        read_persona_mock.return_value = "persona prompt"
        
        signal = resolve_phase_signal(repo="owner/repo", manual=False)
        self.assertEqual(signal.issue, 10)
        self.assertEqual(signal.label, "phase:keter")

    @patch("trigger_workflow.context_resolver.resolution.resolve_issue_by_label")
    @patch("trigger_workflow.context_resolver.resolution.fetch_issue_data")
    @patch("trigger_workflow.context_resolver.resolution.read_microagent_persona_for_label")
    @patch("trigger_workflow.context_resolver.resolution.ensure_phase_labels")
    def test_resolve_phase_signal_discovers_issue_by_label(
        self, ensure_mock, read_persona_mock, fetch_mock, by_label_mock
    ) -> None:
        by_label_mock.return_value = 20
        fetch_mock.return_value = {"title": "Issue", "labels": [{"name": "phase:chokhmah"}], "comments": []}
        read_persona_mock.return_value = "persona prompt"
        
        signal = resolve_phase_signal(label="phase:chokhmah", repo="owner/repo", manual=False)
        self.assertEqual(signal.issue, 20)
        self.assertEqual(signal.label, "phase:chokhmah")

    @patch("trigger_workflow.context_resolver.resolution.issue_phase_labels")
    @patch("trigger_workflow.context_resolver.resolution.fetch_issue_data")
    @patch("trigger_workflow.context_resolver.resolution.read_microagent_persona_for_label")
    @patch("trigger_workflow.context_resolver.resolution.ensure_phase_labels")
    def test_resolve_phase_signal_resolves_label_from_issue(
        self, ensure_mock, read_persona_mock, fetch_mock, phase_labels_mock
    ) -> None:
        fetch_mock.return_value = {"title": "Issue", "labels": [{"name": "phase:binah"}], "comments": []}
        phase_labels_mock.return_value = ["phase:binah"]
        read_persona_mock.return_value = "persona prompt"
        
        signal = resolve_phase_signal(issue=30, repo="owner/repo", manual=False)
        self.assertEqual(signal.issue, 30)
        self.assertEqual(signal.label, "phase:binah")

    @patch("trigger_workflow.context_resolver.resolution.issue_phase_labels")
    @patch("trigger_workflow.context_resolver.resolution.fetch_issue_data")
    @patch("trigger_workflow.context_resolver.resolution.ensure_phase_labels")
    def test_resolve_phase_signal_fails_when_no_labels_on_issue(
        self, ensure_mock, fetch_mock, phase_labels_mock
    ) -> None:
        fetch_mock.return_value = {"title": "Issue", "labels": [], "comments": []}
        phase_labels_mock.return_value = []
        
        with self.assertRaises(SystemExit):
            resolve_phase_signal(issue=40, repo="owner/repo", manual=False)

    @patch("trigger_workflow.context_resolver.resolution.issue_phase_labels")
    @patch("trigger_workflow.context_resolver.resolution.fetch_issue_data")
    @patch("trigger_workflow.context_resolver.resolution.ensure_phase_labels")
    def test_resolve_phase_signal_fails_when_multiple_labels_on_issue(
        self, ensure_mock, fetch_mock, phase_labels_mock
    ) -> None:
        fetch_mock.return_value = {"title": "Issue", "labels": [{"name": "phase:1"}, {"name": "phase:2"}], "comments": []}
        phase_labels_mock.return_value = ["phase:1", "phase:2"]
        
        with self.assertRaises(SystemExit):
            resolve_phase_signal(issue=50, repo="owner/repo", manual=False)

    @patch("trigger_workflow.context_resolver.resolution.fetch_issue_data")
    @patch("trigger_workflow.context_resolver.resolution.ensure_phase_labels")
    def test_resolve_phase_signal_fails_with_unknown_label(
        self, ensure_mock, fetch_mock
    ) -> None:
        fetch_mock.return_value = {"title": "Issue", "labels": [{"name": "phase:unknown"}], "comments": []}
        
        with self.assertRaises(SystemExit) as exc:
            resolve_phase_signal(issue=60, label="phase:unknown", repo="owner/repo", manual=False)
        self.assertIn("Unknown label 'phase:unknown'", str(exc.exception))

    @patch("trigger_workflow.context_resolver.resolution.issue_has_label")
    @patch("trigger_workflow.context_resolver.resolution.fetch_issue_data")
    @patch("trigger_workflow.context_resolver.resolution.read_microagent_persona_for_label")
    @patch("trigger_workflow.context_resolver.resolution.ensure_phase_labels")
    def test_resolve_phase_signal_manual_mode_skips_label_sync(
        self, ensure_mock, read_persona_mock, fetch_mock, has_label_mock
    ) -> None:
        has_label_mock.return_value = True
        fetch_mock.return_value = {"title": "Issue", "labels": [], "comments": []}
        read_persona_mock.return_value = "prompt"
        
        resolve_phase_signal(issue=70, label="phase:keter", repo="owner/repo", manual=True)
        ensure_mock.assert_not_called()

    @patch("trigger_workflow.context_resolver.resolution.issue_has_label")
    @patch("trigger_workflow.context_resolver.resolution.fetch_issue_data")
    @patch("trigger_workflow.context_resolver.resolution.read_microagent_persona_for_label")
    @patch("trigger_workflow.context_resolver.resolution.ensure_phase_labels")
    def test_resolve_phase_signal_manual_mode_ignores_missing_label(
        self, ensure_mock, read_persona_mock, fetch_mock, has_label_mock
    ) -> None:
        has_label_mock.return_value = False
        fetch_mock.return_value = {"title": "Issue", "labels": [], "comments": []}
        read_persona_mock.return_value = "prompt"
        
        # Should not raise
        resolve_phase_signal(issue=80, label="phase:keter", repo="owner/repo", manual=True)

    @patch("trigger_workflow.context_resolver.resolution.issue_has_label")
    @patch("trigger_workflow.context_resolver.resolution.fetch_issue_data")
    @patch("trigger_workflow.context_resolver.resolution.ensure_phase_labels")
    def test_resolve_phase_signal_auto_mode_fails_if_issue_missing_label(
        self, ensure_mock, fetch_mock, has_label_mock
    ) -> None:
        has_label_mock.return_value = False
        fetch_mock.return_value = {"title": "Issue", "labels": [], "comments": []}
        
        with self.assertRaises(SystemExit):
            resolve_phase_signal(issue=90, label="phase:keter", repo="owner/repo", manual=False)

    @patch("trigger_workflow.context_resolver.resolution.issue_has_label")
    @patch("trigger_workflow.context_resolver.resolution.fetch_issue_data")
    @patch("trigger_workflow.context_resolver.resolution.read_microagent_persona_for_label")
    @patch("trigger_workflow.context_resolver.resolution.ensure_phase_labels")
    def test_resolve_phase_signal_final_phase_has_no_next(
        self, ensure_mock, read_persona_mock, fetch_mock, has_label_mock
    ) -> None:
        has_label_mock.return_value = True
        fetch_mock.return_value = {"title": "Issue", "labels": [{"name": "phase:malkhut"}], "comments": []}
        read_persona_mock.return_value = "prompt"
        
        signal = resolve_phase_signal(issue=100, label="phase:malkhut", repo="owner/repo", manual=False)
        self.assertEqual(signal.phase, "9")

if __name__ == "__main__":
    unittest.main()

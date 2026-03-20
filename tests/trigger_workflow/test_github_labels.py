"""Tests for github label operations."""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

from trigger_workflow.config import PHASE_LABEL_METADATA
from trigger_workflow.github.labels import (
    fetch_repo_labels,
    ensure_phase_labels,
    advance_issue_label,
    clear_issue_labels_except,
    edit_issue_labels,
)


class GitHubLabelsTests(unittest.TestCase):
    """Test GitHub label operations."""

    @patch("trigger_workflow.github.labels.run_gh_json")
    def test_fetch_repo_labels_returns_dict_list(self, run_json_mock) -> None:
        run_json_mock.return_value = [{"name": "phase:1"}, "not a dict", {"name": "phase:2"}]
        
        result = fetch_repo_labels("owner/repo")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "phase:1")

    @patch("trigger_workflow.github.labels.fetch_repo_labels")
    @patch("trigger_workflow.github.labels.run_gh_strict")
    def test_ensure_phase_labels_creates_missing_and_updates_outdated(
        self, run_gh_mock, fetch_labels_mock
    ) -> None:
        # We need at least one to create, one to update, and one to skip.
        # Let's mock the existing labels.
        # Suppose PHASE_LABEL_METADATA has 'phase:keter', 'phase:chokhmah', 'phase:binah'
        keys = list(PHASE_LABEL_METADATA.keys())
        if len(keys) < 3:
            self.skipTest("Not enough canonical labels to test")
            
        label_to_skip = keys[0]
        label_to_update = keys[1]
        label_to_create = keys[2] # and all others
        
        existing_labels = [
            {
                "name": label_to_skip, 
                "description": PHASE_LABEL_METADATA[label_to_skip]["description"],
                "color": PHASE_LABEL_METADATA[label_to_skip]["color"]
            },
            {
                "name": label_to_update, 
                "description": "Old description",
                "color": "000000"
            }
            # label_to_create is missing
        ]
        
        fetch_labels_mock.return_value = existing_labels
        
        ensure_phase_labels("owner/repo")
        
        # Check run_gh_strict was called to create and update
        create_calls = [call for call in run_gh_mock.call_args_list if "create" in call.args[0]]
        update_calls = [call for call in run_gh_mock.call_args_list if "edit" in call.args[0]]
        
        self.assertGreaterEqual(len(create_calls), 1)
        self.assertEqual(len(update_calls), 1)

    @patch("trigger_workflow.github.labels.run_gh_strict")
    def test_edit_issue_labels_skips_if_empty(self, run_gh_mock) -> None:
        edit_issue_labels("owner/repo", 1)
        run_gh_mock.assert_not_called()

    @patch("trigger_workflow.github.labels.edit_issue_labels")
    def test_advance_issue_label_skips_final_phase(self, edit_mock) -> None:
        # phase:malkhut is usually the final phase
        advance_issue_label("owner/repo", 1, "phase:malkhut")
        edit_mock.assert_not_called()

    @patch("trigger_workflow.github.labels.edit_issue_labels")
    def test_clear_issue_labels_except_removes_unkept(self, edit_mock) -> None:
        clear_issue_labels_except("owner/repo", 1, ["a", "b", "c"], keep=["b"])
        edit_mock.assert_called_once_with("owner/repo", 1, remove=["a", "c"])

    @patch("trigger_workflow.github.labels.edit_issue_labels")
    def test_clear_issue_labels_except_skips_if_nothing_to_remove(self, edit_mock) -> None:
        clear_issue_labels_except("owner/repo", 1, ["b"], keep=["b"])
        edit_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()

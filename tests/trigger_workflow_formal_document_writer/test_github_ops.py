"""GitHub operation tests for Tiferet child-issue creation and linking.

These tests focus on the integration logic around ordered child issue creation,
parent/sub-issue attachment, and dependency wiring. They exist because the
workflow can appear to succeed locally while GitHub rejects or drops a link.
"""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from trigger_workflow_formal_document_writer.config import TIFERET_AUTO_ISSUE_PREFIX
from trigger_workflow_formal_document_writer.github_ops import (
    add_blocked_by_dependency,
    add_sub_issue_relationship,
    create_child_issues,
    edit_issue_labels,
    normalize_tiferet_child_title,
    parse_repo,
    remove_issue_label,
    tag_issue_needs_human,
    advance_issue_label,
    verify_parent_sub_issue_ids,
)


class GitHubOpsTests(unittest.TestCase):
    """Exercise GitHub-side orchestration behavior at the command boundary.

    The assertions here are primarily about avoiding operational regressions:
    wrong title normalization, wrong API field types, missed dependency edges,
    or false-positive success when GitHub did not attach the created child
    issues to the parent.
    """

    def test_normalize_tiferet_child_title_adds_prefix_once(self) -> None:
        self.assertEqual(
            normalize_tiferet_child_title("Implement Something"),
            f"{TIFERET_AUTO_ISSUE_PREFIX}Implement Something",
        )
        self.assertEqual(
            normalize_tiferet_child_title(f"{TIFERET_AUTO_ISSUE_PREFIX}Implement Something"),
            f"{TIFERET_AUTO_ISSUE_PREFIX}Implement Something",
        )

    @patch("trigger_workflow_formal_document_writer.github_ops.fetch_parent_sub_issue_ids", return_value={1001, 1002, 1003})
    @patch("trigger_workflow_formal_document_writer.github_ops.add_blocked_by_dependency")
    @patch("trigger_workflow_formal_document_writer.github_ops.add_sub_issue_relationship")
    @patch("trigger_workflow_formal_document_writer.github_ops.create_issue_via_api")
    def test_create_child_issues_creates_in_order_and_links_predecessors(
        self,
        create_issue_via_api_mock,
        add_sub_issue_relationship_mock,
        add_blocked_by_dependency_mock,
        fetch_parent_sub_issue_ids_mock,
    ) -> None:
        # The ordered side effect mirrors sequential issue creation so we can
        # assert both parent attachment and blocked-by chaining deterministically.
        create_issue_via_api_mock.side_effect = [
            {"number": 101, "id": 1001, "html_url": "https://example.test/101"},
            {"number": 102, "id": 1002, "html_url": "https://example.test/102"},
            {"number": 103, "id": 1003, "html_url": "https://example.test/103"},
        ]

        created = create_child_issues(
            "owner/repo",
            77,
            [
                {"title": "First", "body": "Body one"},
                {"title": "Second", "body": "Body two"},
                {"title": "Third", "body": "Body three"},
            ],
        )

        self.assertEqual([item["number"] for item in created], [101, 102, 103])
        self.assertEqual(create_issue_via_api_mock.call_count, 3)
        self.assertEqual(
            create_issue_via_api_mock.call_args_list[0].args[1],
            f"{TIFERET_AUTO_ISSUE_PREFIX}First",
        )
        first_body = create_issue_via_api_mock.call_args_list[0].args[2]
        self.assertIn("Automatically created by Phase 4/Tiferet from parent issue #77.", first_body)
        self.assertIn("Parent issue: #77", first_body)
        self.assertEqual(created[0]["title"], f"{TIFERET_AUTO_ISSUE_PREFIX}First")
        self.assertEqual(
            create_issue_via_api_mock.call_args_list[0].kwargs["labels"],
            ["phase:keter"],
        )

        add_sub_issue_relationship_mock.assert_any_call("owner/repo", 77, 1001)
        add_sub_issue_relationship_mock.assert_any_call("owner/repo", 77, 1002)
        add_sub_issue_relationship_mock.assert_any_call("owner/repo", 77, 1003)
        self.assertEqual(add_sub_issue_relationship_mock.call_count, 3)

        add_blocked_by_dependency_mock.assert_any_call("owner/repo", 102, 1001)
        add_blocked_by_dependency_mock.assert_any_call("owner/repo", 103, 1002)
        self.assertEqual(add_blocked_by_dependency_mock.call_count, 2)
        fetch_parent_sub_issue_ids_mock.assert_called_once_with("owner/repo", 77)

    @patch("trigger_workflow_formal_document_writer.github_ops.time.sleep")
    @patch("trigger_workflow_formal_document_writer.github_ops.fetch_parent_sub_issue_ids")
    def test_verify_parent_sub_issue_ids_retries_until_links_appear(
        self,
        fetch_parent_sub_issue_ids_mock,
        sleep_mock,
    ) -> None:
        # GitHub can lag before the sub-issue relationship becomes visible.
        # This simulates eventual consistency and ensures the verifier retries
        # before declaring the attachment missing.
        fetch_parent_sub_issue_ids_mock.side_effect = [
            set(),
            {1001},
            {1001, 1002},
        ]

        missing = verify_parent_sub_issue_ids(
            "owner/repo",
            77,
            [1001, 1002],
            attempts=3,
            delay_seconds=0.01,
        )

        self.assertEqual(missing, [])
        self.assertEqual(fetch_parent_sub_issue_ids_mock.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 2)

    @patch("trigger_workflow_formal_document_writer.github_ops.time.sleep")
    @patch("trigger_workflow_formal_document_writer.github_ops.fetch_parent_sub_issue_ids", return_value=set())
    def test_verify_parent_sub_issue_ids_returns_missing_after_retry_budget_exhausted(
        self,
        fetch_parent_sub_issue_ids_mock,
        sleep_mock,
    ) -> None:
        missing = verify_parent_sub_issue_ids(
            "owner/repo",
            77,
            [1001, 1002],
            attempts=3,
            delay_seconds=0.01,
        )

        self.assertEqual(missing, [1001, 1002])
        self.assertEqual(fetch_parent_sub_issue_ids_mock.call_count, 3)
        self.assertEqual(sleep_mock.call_count, 2)

    def test_parse_repo_rejects_invalid_identifier(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            parse_repo("owner")

        self.assertIn("Expected 'owner/repo'", str(exc.exception))

    @patch("trigger_workflow_formal_document_writer.github_ops.run_gh")
    def test_add_sub_issue_relationship_uses_typed_field_submission(self, run_gh_mock) -> None:
        run_gh_mock.return_value = subprocess.CompletedProcess(args=["gh"], returncode=0, stdout="", stderr="")

        add_sub_issue_relationship("owner/repo", 77, 1001)

        self.assertEqual(
            run_gh_mock.call_args.args[0],
            [
                "api",
                "repos/owner/repo/issues/77/sub_issues",
                "--method",
                "POST",
                "-F",
                "sub_issue_id=1001",
            ],
        )

    @patch("trigger_workflow_formal_document_writer.github_ops.run_gh")
    def test_add_blocked_by_dependency_uses_typed_field_submission(self, run_gh_mock) -> None:
        run_gh_mock.return_value = subprocess.CompletedProcess(args=["gh"], returncode=0, stdout="", stderr="")

        add_blocked_by_dependency("owner/repo", 102, 1001)

        self.assertEqual(
            run_gh_mock.call_args.args[0],
            [
                "api",
                "repos/owner/repo/issues/102/dependencies/blocked_by",
                "--method",
                "POST",
                "-F",
                "issue_id=1001",
            ],
        )

    @patch("trigger_workflow_formal_document_writer.github_ops.run_gh")
    def test_edit_issue_labels_builds_combined_add_remove_command(self, run_gh_mock) -> None:
        run_gh_mock.return_value = subprocess.CompletedProcess(args=["gh"], returncode=0, stdout="", stderr="")

        edit_issue_labels("owner/repo", 77, add=["phase:netzach"], remove=["phase:tiferet"])

        self.assertEqual(
            run_gh_mock.call_args.args[0],
            [
                "issue",
                "edit",
                "77",
                "--repo",
                "owner/repo",
                "--remove-label",
                "phase:tiferet",
                "--add-label",
                "phase:netzach",
            ],
        )

    @patch("trigger_workflow_formal_document_writer.github_ops.edit_issue_labels")
    def test_advance_issue_label_uses_shared_label_editor(self, edit_issue_labels_mock) -> None:
        advance_issue_label("owner/repo", 77, "phase:tiferet")

        edit_issue_labels_mock.assert_called_once_with(
            "owner/repo",
            77,
            add=["phase:netzach"],
            remove=["phase:tiferet"],
        )

    @patch("trigger_workflow_formal_document_writer.github_ops.edit_issue_labels")
    def test_remove_issue_label_uses_shared_label_editor(self, edit_issue_labels_mock) -> None:
        remove_issue_label("owner/repo", 77, "phase:tiferet")
        edit_issue_labels_mock.assert_called_once_with("owner/repo", 77, remove=["phase:tiferet"])

    @patch("trigger_workflow_formal_document_writer.github_ops.edit_issue_labels")
    def test_tag_issue_needs_human_uses_shared_label_editor(self, edit_issue_labels_mock) -> None:
        tag_issue_needs_human("owner/repo", 77)
        edit_issue_labels_mock.assert_called_once_with("owner/repo", 77, add=["phase:needsHuman"])

    @patch("trigger_workflow_formal_document_writer.github_ops.fetch_parent_sub_issue_ids", return_value=set())
    @patch("trigger_workflow_formal_document_writer.github_ops.add_blocked_by_dependency")
    @patch("trigger_workflow_formal_document_writer.github_ops.add_sub_issue_relationship")
    @patch("trigger_workflow_formal_document_writer.github_ops.create_issue_via_api")
    def test_create_child_issues_errors_when_parent_sub_issue_attachment_is_missing(
        self,
        create_issue_via_api_mock,
        add_sub_issue_relationship_mock,
        add_blocked_by_dependency_mock,
        fetch_parent_sub_issue_ids_mock,
    ) -> None:
        # A created child issue without a confirmed parent attachment is not a
        # success case for this workflow, even if the create call itself worked.
        del add_sub_issue_relationship_mock
        del add_blocked_by_dependency_mock
        del fetch_parent_sub_issue_ids_mock
        create_issue_via_api_mock.return_value = {
            "number": 101,
            "id": 1001,
            "html_url": "https://example.test/101",
        }

        with self.assertRaises(SystemExit) as exc:
            create_child_issues(
                "owner/repo",
                77,
                [{"title": "First", "body": "Body one"}],
            )

        self.assertIn("Missing sub-issue links: #101", str(exc.exception))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from trigger_workflow import prompts
from trigger_workflow.github_ops import create_child_issues
from trigger_workflow.prompts import (
    build_phase_input_context,
    determine_phase_from_label,
    read_microagent_for_label,
)
from trigger_workflow.router import trigger_agent


class PhaseMappingTests(unittest.TestCase):
    def test_determine_phase_from_label_uses_canonical_string_ids(self) -> None:
        self.assertEqual(determine_phase_from_label("phase:keter"), "1")
        self.assertEqual(determine_phase_from_label("phase:chokhmah"), "2a")
        self.assertEqual(determine_phase_from_label("phase:binah"), "2b")
        self.assertEqual(determine_phase_from_label("phase:chesed"), "2c")
        self.assertEqual(determine_phase_from_label("phase:gevurah"), "3")
        self.assertEqual(determine_phase_from_label("phase:tiferet"), "4")
        self.assertEqual(determine_phase_from_label("phase:malkhut"), "9")


class PromptCompositionTests(unittest.TestCase):
    def test_read_microagent_for_label_composes_base_persona_phase_persona_and_microagent(self) -> None:
        content = read_microagent_for_label("phase:binah", "2b")
        self.assertIsNotNone(content)
        assert content is not None
        self.assertIn("The user is your partner.", content)
        self.assertIn("expanded through Binah", content)
        self.assertIn("functional embodiment of Daneel-through-Binah", content)

    def test_build_phase_input_context_uses_keter_only_for_phase_2_variants(self) -> None:
        issue_data = {
            "title": "Example",
            "body": "Original issue body should not be used",
            "comments": [
                {
                    "body": "\n".join(
                        [
                            "<!-- phase:1:start label=phase:keter name=Keter -->",
                            "### Phase 1: Keter",
                            "",
                            "Clarified requirement from Keter.",
                            "",
                            "<!-- phase:1:end label=phase:keter name=Keter -->",
                        ]
                    )
                }
            ],
        }
        context = build_phase_input_context("phase:binah", 12, "owner/repo", "2b", issue_data)
        self.assertIn("Clarified requirement from Keter.", context)
        self.assertNotIn("Original issue body should not be used", context)


class ChildIssueCreationTests(unittest.TestCase):
    @patch("trigger_workflow.github_ops.add_blocked_by_dependency")
    @patch("trigger_workflow.github_ops.add_sub_issue_relationship")
    @patch("trigger_workflow.github_ops.create_issue_via_api")
    def test_create_child_issues_creates_in_order_and_links_predecessors(
        self,
        create_issue_via_api_mock,
        add_sub_issue_relationship_mock,
        add_blocked_by_dependency_mock,
    ) -> None:
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
        first_body = create_issue_via_api_mock.call_args_list[0].args[2]
        self.assertIn("Automatically created by Phase 4/Tiferet from parent issue #77.", first_body)
        self.assertIn("Parent issue: #77", first_body)

        add_sub_issue_relationship_mock.assert_any_call("owner/repo", 77, 1001)
        add_sub_issue_relationship_mock.assert_any_call("owner/repo", 77, 1002)
        add_sub_issue_relationship_mock.assert_any_call("owner/repo", 77, 1003)
        self.assertEqual(add_sub_issue_relationship_mock.call_count, 3)

        add_blocked_by_dependency_mock.assert_any_call("owner/repo", 102, 1001)
        add_blocked_by_dependency_mock.assert_any_call("owner/repo", 103, 1002)
        self.assertEqual(add_blocked_by_dependency_mock.call_count, 2)


class RouterExecutionTests(unittest.TestCase):
    @patch("trigger_workflow.router._execute_agent_phase")
    @patch("trigger_workflow.router._execute_specification_phase")
    @patch("trigger_workflow.router._execute_discussion_phase")
    @patch("trigger_workflow.router.fetch_issue_data")
    @patch("trigger_workflow.router.read_microagent_for_label")
    @patch("trigger_workflow.router.ensure_phase_labels")
    def test_trigger_agent_routes_chesed_to_discussion_phase(
        self,
        ensure_phase_labels_mock,
        read_microagent_for_label_mock,
        fetch_issue_data_mock,
        execute_discussion_mock,
        execute_specification_mock,
        execute_agent_mock,
    ) -> None:
        del ensure_phase_labels_mock
        read_microagent_for_label_mock.return_value = "prompt"
        fetch_issue_data_mock.return_value = {
            "title": "Issue",
            "labels": [{"name": "phase:chesed"}],
            "comments": [],
        }

        trigger_agent(label="phase:chesed", issue=55, repo="owner/repo")

        execute_discussion_mock.assert_called_once()
        execute_specification_mock.assert_not_called()
        execute_agent_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""Tests for prompt extraction logic."""

from __future__ import annotations

import unittest

from trigger_workflow.prompts_engine.extraction import (
    extract_phase_1_comment,
    build_issue_runtime_context,
    strip_microagent_persona_persona,
    build_phase_prompt_input_context,
)


class ExtractionTests(unittest.TestCase):
    """Test extraction of context from issue data."""

    def test_extract_phase_1_comment_success_with_header(self) -> None:
        issue_data = {"comments": [{"body": "<!-- phase:1:start -->\n### Phase 1:\nBlank line\nExtracted content\n<!-- phase:1:end -->"}]}
        result = extract_phase_1_comment(issue_data)
        self.assertEqual(result, "Extracted content")

    def test_build_phase_prompt_input_context_keter_derived_success(self) -> None:
        issue_data = {
            "title": "Title", 
            "comments": [{"body": "<!-- phase:1:start -->\n### Phase 1:\n\nExtracted content\n<!-- phase:1:end -->"}]
        }
        context = build_phase_prompt_input_context("label", 1, "repo", "2A", issue_data)
        self.assertIn("Extracted content", context)

    def test_build_phase_prompt_input_context_keter_derived_fails_without_comment(self) -> None:
        issue_data = {"title": "Title", "comments": []}
        with self.assertRaises(SystemExit):
            build_phase_prompt_input_context("label", 1, "repo", "2A", issue_data)

    def test_extract_phase_1_comment_skips_non_dict_comments(self) -> None:
        issue_data = {"comments": ["not a dict", 123]}
        self.assertIsNone(extract_phase_1_comment(issue_data))

    def test_extract_phase_1_comment_skips_empty_body(self) -> None:
        issue_data = {"comments": [{"body": ""}, {"body": None}]}
        self.assertIsNone(extract_phase_1_comment(issue_data))

    def test_extract_phase_1_comment_falls_back_when_missing_header(self) -> None:
        issue_data = {"comments": [{"body": "<!-- phase:1:start -->\nNo header here\n<!-- phase:1:end -->"}]}
        result = extract_phase_1_comment(issue_data)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIn("No header here", result)

    def test_extract_phase_1_comment_skips_when_end_marker_before_start(self) -> None:
        issue_data = {"comments": [{"body": "<!-- phase:1:end --><!-- phase:1:start -->"}]}
        self.assertIsNone(extract_phase_1_comment(issue_data))

    def test_build_issue_runtime_context_skips_non_dict_comments(self) -> None:
        issue_data = {"title": "Issue", "body": "Body", "comments": ["not a dict", {"body": "valid"}]}
        context = build_issue_runtime_context("label", 1, "repo", "3", issue_data, include_comments=True)
        self.assertIn("valid", context)
        self.assertNotIn("not a dict", context)

    def test_build_issue_runtime_context_skips_empty_comments(self) -> None:
        issue_data = {"title": "Issue", "body": "Body", "comments": [{"body": "  "}, {"body": None}, {"body": "valid"}]}
        context = build_issue_runtime_context("label", 1, "repo", "3", issue_data, include_comments=True)
        self.assertIn("valid", context)

    def test_strip_microagent_persona_persona_removes_eof(self) -> None:
        self.assertEqual(strip_microagent_persona_persona("content\nEOF"), "content")
        self.assertEqual(strip_microagent_persona_persona("contentEOF  "), "content")
        self.assertEqual(strip_microagent_persona_persona("content"), "content")


if __name__ == "__main__":
    unittest.main()

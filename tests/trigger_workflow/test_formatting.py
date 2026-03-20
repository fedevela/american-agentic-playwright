"""Tests for formatting utilities."""

from __future__ import annotations

import unittest

from trigger_workflow.prompts_engine.formatting import (
    phase_display_name,
    format_phase_comment,
    build_phase_four_summary,
)


class FormattingTests(unittest.TestCase):
    """Test output formatting rules."""

    def test_phase_display_name_capitalizes_labels_for_phase_2(self) -> None:
        self.assertEqual(phase_display_name("2A", "phase:chokhmah"), "Chokhmah")
        self.assertEqual(phase_display_name("2B", "phase:binah"), "Binah")
        self.assertEqual(phase_display_name("2C", "phase:chesed"), "Chesed")

    def test_phase_display_name_uses_map_for_known_phases(self) -> None:
        self.assertEqual(phase_display_name("1", "phase:keter"), "Keter")
        self.assertEqual(phase_display_name("7", "phase:yesod-orchestration"), "Yesod-Orchestration")
        self.assertEqual(phase_display_name("8", "phase:yesod-embodiment"), "Yesod-Embodiment")

    def test_phase_display_name_falls_back_to_capitalized_label_if_not_in_map(self) -> None:
        self.assertEqual(phase_display_name("99", "phase:unknown"), "Unknown")
        self.assertEqual(phase_display_name("99", "phase:weird-label"), "Weird-label")

    def test_format_phase_comment_wraps_body_with_html_comments_and_headers(self) -> None:
        body = "  This is the body.  "
        formatted = format_phase_comment("1", "phase:keter", body)

        self.assertIn("<!-- phase:1:start label=phase:keter name=Keter -->", formatted)
        self.assertIn("### Phase 1: Keter", formatted)
        self.assertIn("This is the body.", formatted)
        self.assertIn("<!-- phase:1:end label=phase:keter name=Keter -->", formatted)
        self.assertTrue(formatted.startswith("<!--"))
        self.assertTrue(formatted.endswith("-->"))

    def test_build_phase_four_summary_lists_issues_with_urls(self) -> None:
        created = [
            {"title": "Issue 1", "url": "https://github.com/a/b/issues/1"},
            {"title": "Issue 2", "url": "https://github.com/a/b/issues/2"},
        ]
        summary = build_phase_four_summary(created)
        
        self.assertIn("Spawned 2 auto-created child issues", summary)
        self.assertIn("- Issue 1: https://github.com/a/b/issues/1", summary)
        self.assertIn("- Issue 2: https://github.com/a/b/issues/2", summary)

if __name__ == "__main__":
    unittest.main()

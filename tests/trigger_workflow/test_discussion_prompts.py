"""Tests for discussion phase prompts."""

from __future__ import annotations

import unittest

from trigger_workflow.prompts_engine.discussion import (
    build_comment_phase_prompt,
    build_phase_2_story_requirements,
)


class DiscussionPromptTests(unittest.TestCase):
    """Test discussion phase prompt building and logic."""

    def test_build_comment_phase_prompt_includes_phase_2_requirements(self) -> None:
        """Verify phase 2A, 2B, 2C get the proper story requirements."""
        phases = ["2A", "2B", "2C"]
        issue_data = {
            "title": "Example", 
            "body": "Body", 
            "comments": [
                {"body": "<!-- phase:1:start label=phase:keter name=Keter -->\nPhase 1 comment body\n<!-- phase:1:end label=phase:keter name=Keter -->"}
            ]
        }
        
        for phase in phases:
            prompt = build_comment_phase_prompt(
                f"phase:label_{phase}",
                1,
                "owner/repo",
                "Persona details",
                phase,
                issue_data,
            )
            
            # Check for a specific phase 2 requirement line
            self.assertIn("Emit semaphored user stories only", prompt)
            self.assertIn("Format every line as `[COLOR] Given ..., when ..., then ...`.", prompt)
            
            # Check for a shared requirement line
            self.assertIn("Return only the GitHub comment body for this phase", prompt)
            self.assertIn("Keep the content appropriate for a single GitHub issue comment", prompt)
            
    def test_build_comment_phase_prompt_skips_phase_specific_requirements_for_unknown_phase(self) -> None:
        """Verify fallback behavior for unknown phases does not include phase 1 or 2 requirements."""
        issue_data = {"title": "Example", "body": "Body", "comments": []}
        
        prompt = build_comment_phase_prompt(
            "phase:unknown",
            1,
            "owner/repo",
            "Persona details",
            "99",
            issue_data,
        )
        
        # Check shared requirements still exist
        self.assertIn("Return only the GitHub comment body for this phase", prompt)
        
        # Check phase 1 requirements do NOT exist
        self.assertNotIn("Produce a comprehensive clarification comment", prompt)
        
        # Check phase 2 requirements do NOT exist
        self.assertNotIn("Emit semaphored user stories only", prompt)

    def test_build_comment_phase_prompt_includes_phase_1_requirements(self) -> None:
        """Verify phase 1 gets the comprehensive clarification requirements."""
        issue_data = {"title": "Example", "body": "Body", "comments": []}
        prompt = build_comment_phase_prompt(
            "phase:keter",
            1,
            "owner/repo",
            "Persona details",
            "1",
            issue_data,
        )
        self.assertIn("Produce a comprehensive clarification comment", prompt)
        self.assertIn("Include these exact section headings: `Clarified Requirement`", prompt)
        self.assertIn("Phase 2 Handoff", prompt)

if __name__ == "__main__":
    unittest.main()

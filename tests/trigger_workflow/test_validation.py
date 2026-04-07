"""Validation tests for the Tiferet payload contract.

These tests cover the rules that govern the structure of the phase-4/Tiferet
child-issue payload.
"""

from __future__ import annotations

import unittest

from trigger_workflow.config import TIFERET_AUTO_ISSUE_PREFIX
from trigger_workflow.validation import (
    validate_tiferet_specification_payload_structure,
)


class PhaseFourPayloadValidationTests(unittest.TestCase):
    """Verify payload shape for the phase-4/Tiferet JSON payload."""

    def test_validate_phase_four_payload_accepts_valid_structure(self) -> None:
        payload = {
            "comment": "Decomposition rationale.",
            "sub_issues": [
                {
                    "title": f"{TIFERET_AUTO_ISSUE_PREFIX}Example",
                    "body": "\n".join(
                        [
                            "Requirement IDs: CH-001, CH-003",
                            "",
                            "Canonical Requirements:",
                            "- CH-001: [RED] When x, then y",
                            "- CH-003: [RED] When a, then b",
                            "",
                            "Given x, when y, then z.",
                        ]
                    ),
                }
            ],
        }

        validate_tiferet_specification_payload_structure(payload)

    def test_validate_phase_four_payload_rejects_missing_requirement_ids_line(self) -> None:
        payload = {
            "comment": "Decomposition rationale.",
            "sub_issues": [
                {
                    "title": f"{TIFERET_AUTO_ISSUE_PREFIX}Example",
                    "body": "Given x, when y, then z.",
                }
            ],
        }

        with self.assertRaises(SystemExit) as exc:
            validate_tiferet_specification_payload_structure(payload)

        self.assertIn("must begin with a `Requirement IDs:` line", str(exc.exception))

    def test_validate_tiferet_specification_payload_rejects_non_dict(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            validate_tiferet_specification_payload_structure([])  # type: ignore
        self.assertIn("must be a JSON object", str(exc.exception))

    def test_validate_tiferet_specification_payload_rejects_missing_comment(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            validate_tiferet_specification_payload_structure({"comment": " "})
        self.assertIn("must include a non-empty `comment`", str(exc.exception))

    def test_validate_tiferet_specification_payload_rejects_missing_sub_issues(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            validate_tiferet_specification_payload_structure({"comment": "Valid"})
        self.assertIn("must include at least one `sub_issues` entry", str(exc.exception))
        
    def test_validate_tiferet_specification_payload_rejects_empty_sub_issues(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            validate_tiferet_specification_payload_structure({"comment": "Valid", "sub_issues": []})
        self.assertIn("must include at least one `sub_issues` entry", str(exc.exception))

    def test_validate_tiferet_specification_payload_rejects_invalid_sub_issue_type(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            validate_tiferet_specification_payload_structure({"comment": "Valid", "sub_issues": ["not a dict"]})
        self.assertIn("must be an object", str(exc.exception))
        
    def test_validate_tiferet_specification_payload_rejects_sub_issue_missing_title(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            validate_tiferet_specification_payload_structure({
                "comment": "Valid",
                "sub_issues": [{"title": "", "body": "Requirement IDs: X\nBody"}]
            })
        self.assertIn("must include a non-empty `title`", str(exc.exception))

    def test_validate_tiferet_specification_payload_rejects_sub_issue_missing_body(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            validate_tiferet_specification_payload_structure({
                "comment": "Valid",
                "sub_issues": [{"title": "Title", "body": "   "}]
            })
        self.assertIn("must include a non-empty `body`", str(exc.exception))
        
    def test_validate_tiferet_specification_payload_rejects_sub_issue_no_guids_in_requirement_ids(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            validate_tiferet_specification_payload_structure({
                "comment": "Valid",
                "sub_issues": [{"title": "Title", "body": "Requirement IDs: none\nBody"}]
            })
        self.assertIn("must list at least one Gevurah GUID in `Requirement IDs:`", str(exc.exception))


if __name__ == "__main__":
    unittest.main()

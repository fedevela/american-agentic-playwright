"""Validation tests for the Tiferet payload contract.

These tests cover the rules that govern the structure of the phase-4/Tiferet
child-issue payload.
"""

from __future__ import annotations

import unittest

from trigger_workflow_formal_document_writer.config import TIFERET_AUTO_ISSUE_PREFIX
from trigger_workflow_formal_document_writer.validation import (
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


if __name__ == "__main__":
    unittest.main()

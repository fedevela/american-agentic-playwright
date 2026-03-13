"""Validation tests for the strict Tiferet traceability contract.

These tests cover the rules that keep Gevurah canonical requirements intact as
Tiferet decomposes them into child issues. The emphasis is on preserving exact
requirement lines and failing hard when traceability is incomplete.
"""

from __future__ import annotations

import unittest

from trigger_workflow.config import TIFERET_AUTO_ISSUE_PREFIX
from trigger_workflow.validation import (
    extract_gevurah_canonical_requirements,
    validate_phase_four_payload,
    validate_phase_four_payload_against_gevurah,
)


class PhaseFourPayloadValidationTests(unittest.TestCase):
    """Verify payload shape and verbatim requirement preservation.

    The cases in this suite separate two concerns:
    structural validation of the phase-4 JSON payload, and semantic validation
    that child issues copy the Gevurah canonical requirements exactly for the
    requirement IDs they claim to cover.
    """

    def test_validate_phase_four_payload_accepts_requirement_id_traceability(self) -> None:
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

        validate_phase_four_payload(payload)

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
            validate_phase_four_payload(payload)

        self.assertIn("must begin with a `Requirement IDs:` line", str(exc.exception))

    def test_extract_gevurah_canonical_requirements_reads_phase_three_comment(self) -> None:
        # This fixture models the machine-marked Gevurah phase comment that
        # validation must mine for canonical requirement lines.
        issue_data = {
            "comments": [
                {
                    "body": "\n".join(
                        [
                            "<!-- phase:3:start label=phase:gevurah name=Gevurah -->",
                            "### Phase 3: Gevurah",
                            "",
                            "## Canonical Requirements",
                            "",
                            "- CH-001: [RED] When user selects the option, then the scene initializes",
                            "- CH-003: [RED] When a dot crosses the boundary, then it wraps",
                            "",
                            "## Synthesis Decisions",
                            "",
                            "Decision text.",
                            "",
                            "<!-- phase:3:end label=phase:gevurah name=Gevurah -->",
                        ]
                    )
                }
            ]
        }

        canonical = extract_gevurah_canonical_requirements(issue_data)

        self.assertEqual(
            canonical["CH-001"],
            "- CH-001: [RED] When user selects the option, then the scene initializes",
        )

    def test_validate_phase_four_payload_against_gevurah_accepts_verbatim_clones(self) -> None:
        # The child issue body intentionally uses a different later heading
        # ("Behavior Scenarios") to show that only the Canonical Requirements
        # block is rigid; surrounding structure may vary.
        issue_data = {
            "comments": [
                {
                    "body": "\n".join(
                        [
                            "<!-- phase:3:start label=phase:gevurah name=Gevurah -->",
                            "### Phase 3: Gevurah",
                            "",
                            "## Canonical Requirements",
                            "",
                            "- CH-001: [RED] When user selects the option, then the scene initializes",
                            "- CH-003: [RED] When a dot crosses the boundary, then it wraps",
                            "",
                            "## Synthesis Decisions",
                            "",
                            "Decision text.",
                        ]
                    )
                }
            ]
        }
        payload = {
            "comment": "Decomposition rationale.",
            "sub_issues": [
                {
                    "title": f"{TIFERET_AUTO_ISSUE_PREFIX}Example",
                    "body": "\n".join(
                        [
                            "Requirement IDs: CH-001, CH-003",
                            "",
                            "## Canonical Requirements",
                            "- CH-001: [RED] When user selects the option, then the scene initializes",
                            "- CH-003: [RED] When a dot crosses the boundary, then it wraps",
                            "",
                            "## Behavior Scenarios",
                            "Given x, when y, then z.",
                        ]
                    ),
                }
            ],
        }

        validate_phase_four_payload_against_gevurah(payload, issue_data)

    def test_validate_phase_four_payload_against_gevurah_rejects_paraphrase(self) -> None:
        issue_data = {
            "comments": [
                {
                    "body": "\n".join(
                        [
                            "<!-- phase:3:start label=phase:gevurah name=Gevurah -->",
                            "### Phase 3: Gevurah",
                            "",
                            "## Canonical Requirements",
                            "",
                            "- CH-001: [RED] When user selects the option, then the scene initializes",
                            "",
                            "## Synthesis Decisions",
                            "",
                            "Decision text.",
                        ]
                    )
                }
            ]
        }
        payload = {
            "comment": "Decomposition rationale.",
            "sub_issues": [
                {
                    "title": f"{TIFERET_AUTO_ISSUE_PREFIX}Example",
                    "body": "\n".join(
                        [
                            "Requirement IDs: CH-001",
                            "",
                            "Canonical Requirements:",
                            "- CH-001: [RED] Initialize the scene when selected",
                            "",
                            "Given x, when y, then z.",
                        ]
                    ),
                }
            ],
        }

        with self.assertRaises(SystemExit) as exc:
            validate_phase_four_payload_against_gevurah(payload, issue_data)

        self.assertIn("copy the full Gevurah requirement line", str(exc.exception))

    def test_validate_phase_four_payload_against_gevurah_rejects_missing_canonical_requirements_section(self) -> None:
        issue_data = {
            "comments": [
                {
                    "body": "\n".join(
                        [
                            "<!-- phase:3:start label=phase:gevurah name=Gevurah -->",
                            "### Phase 3: Gevurah",
                            "",
                            "## Canonical Requirements",
                            "",
                            "- CH-001: [RED] When user selects the option, then the scene initializes",
                            "",
                            "## Synthesis Decisions",
                            "",
                            "Decision text.",
                        ]
                    )
                }
            ]
        }
        payload = {
            "comment": "Decomposition rationale.",
            "sub_issues": [
                {
                    "title": f"{TIFERET_AUTO_ISSUE_PREFIX}Example",
                    "body": "\n".join(
                        [
                            "Requirement IDs: CH-001",
                            "",
                            "## Gherkin Scenarios",
                            "Given x, when y, then z.",
                        ]
                    ),
                }
            ],
        }

        with self.assertRaises(SystemExit) as exc:
            validate_phase_four_payload_against_gevurah(payload, issue_data)

        self.assertIn("Canonical Requirements", str(exc.exception))

    def test_validate_phase_four_payload_against_gevurah_accepts_reorganized_grouping_when_lines_survive(self) -> None:
        # Regrouping is legal as long as every referenced canonical line is
        # copied verbatim into the child issue that claims it.
        issue_data = {
            "comments": [
                {
                    "body": "\n".join(
                        [
                            "<!-- phase:3:start label=phase:gevurah name=Gevurah -->",
                            "### Phase 3: Gevurah",
                            "",
                            "## Canonical Requirements",
                            "",
                            "- CH-001: [RED] When user selects the option, then the scene initializes",
                            "- CH-002: [RED] When seed changes, then motion is reproducible",
                            "- CH-003: [RED] When a dot crosses the boundary, then it wraps",
                            "- CH-004: [RED] When physics updates, then friction slows the dot",
                            "",
                            "## Synthesis Decisions",
                            "",
                            "Decision text.",
                        ]
                    )
                }
            ]
        }
        payload = {
            "comment": "Decomposition rationale.",
            "sub_issues": [
                {
                    "title": f"{TIFERET_AUTO_ISSUE_PREFIX}Grouped A",
                    "body": "\n".join(
                        [
                            "Requirement IDs: CH-003, CH-001",
                            "",
                            "## Canonical Requirements",
                            "- CH-003: [RED] When a dot crosses the boundary, then it wraps",
                            "- CH-001: [RED] When user selects the option, then the scene initializes",
                            "",
                            "## Gherkin Scenarios",
                            "Given x, when y, then z.",
                        ]
                    ),
                },
                {
                    "title": f"{TIFERET_AUTO_ISSUE_PREFIX}Grouped B",
                    "body": "\n".join(
                        [
                            "Requirement IDs: CH-004, CH-002",
                            "",
                            "## Canonical Requirements",
                            "- CH-004: [RED] When physics updates, then friction slows the dot",
                            "- CH-002: [RED] When seed changes, then motion is reproducible",
                            "",
                            "## Gherkin Scenarios",
                            "Given a, when b, then c.",
                        ]
                    ),
                },
            ],
        }

        validate_phase_four_payload_against_gevurah(payload, issue_data)

    def test_validate_phase_four_payload_against_gevurah_rejects_reorganized_grouping_that_drops_a_line(self) -> None:
        # This catches the subtle failure mode where a child issue lists a
        # requirement ID but omits the full canonical line from its preserved
        # traceability block.
        issue_data = {
            "comments": [
                {
                    "body": "\n".join(
                        [
                            "<!-- phase:3:start label=phase:gevurah name=Gevurah -->",
                            "### Phase 3: Gevurah",
                            "",
                            "## Canonical Requirements",
                            "",
                            "- CH-001: [RED] When user selects the option, then the scene initializes",
                            "- CH-002: [RED] When seed changes, then motion is reproducible",
                            "",
                            "## Synthesis Decisions",
                            "",
                            "Decision text.",
                        ]
                    )
                }
            ]
        }
        payload = {
            "comment": "Decomposition rationale.",
            "sub_issues": [
                {
                    "title": f"{TIFERET_AUTO_ISSUE_PREFIX}Grouped A",
                    "body": "\n".join(
                        [
                            "Requirement IDs: CH-001, CH-002",
                            "",
                            "## Canonical Requirements",
                            "- CH-001: [RED] When user selects the option, then the scene initializes",
                            "",
                            "## Gherkin Scenarios",
                            "Given x, when y, then z.",
                        ]
                    ),
                }
            ],
        }

        with self.assertRaises(SystemExit) as exc:
            validate_phase_four_payload_against_gevurah(payload, issue_data)

        self.assertIn("CH-002", str(exc.exception))


if __name__ == "__main__":
    unittest.main()

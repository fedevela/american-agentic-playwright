"""Compatibility boundary for normalized dramatic Tiferet results."""
from copy import deepcopy
import unittest

from trigger_workflow_creative_writer.validation import (
    validate_result,
    validate_tiferet_specification_payload_structure,
)
from tests.trigger_workflow_creative_writer.test_dramaturgy import CYCLE, base, established


class PhaseFourPayloadValidationTests(unittest.TestCase):
    def normalized_result(self):
        accepted = established()
        payload = base('4')
        payload['assignments'] = [
            {'element_id': element['id'], 'outline': element['outline']}
            for element in accepted['3']['elements']
        ]
        return validate_result(payload, phase='4', cycle_id=CYCLE,
                               scope='season', accepted=accepted)

    def test_accepts_current_cycle_normalized_structure(self):
        validate_tiferet_specification_payload_structure(self.normalized_result())

    def test_rejects_legacy_prose_decomposition_even_with_requirement_ids(self):
        payload = {'comment': 'Decomposition rationale.', 'sub_issues': [
            {'title': '[SMALL] A scene',
             'body': 'Requirement IDs: CH-001\nCanonical Requirements:\nCH-001: A choice.'}
        ]}
        with self.assertRaisesRegex(SystemExit, 're-established through Keter'):
            validate_tiferet_specification_payload_structure(payload)

    def test_rejects_normalized_ready_scene_with_missing_beat_coverage(self):
        payload = deepcopy(self.normalized_result())
        payload['elements'][0]['beats'] = []
        with self.assertRaisesRegex(SystemExit, 'ordered nonempty beats'):
            validate_tiferet_specification_payload_structure(payload)

    def test_rejects_unknown_source_in_normalized_ready_scene(self):
        payload = deepcopy(self.normalized_result())
        payload['elements'][0]['source_refs'] = ['unknown-anchor']
        with self.assertRaisesRegex(SystemExit, 'unknown source references'):
            validate_tiferet_specification_payload_structure(payload)


if __name__ == '__main__':
    unittest.main()

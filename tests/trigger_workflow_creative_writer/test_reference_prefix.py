from copy import deepcopy
import unittest

from trigger_workflow_creative_writer import cycles, validation
from tests.trigger_workflow_creative_writer.test_dramaturgy import established, base


class ReferencePrefixTests(unittest.TestCase):
    def keter(self):
        payload = deepcopy(established()['1'])
        payload.pop('kind')
        payload.pop('version')
        payload['reference_prefix'] = {'code': 'LRRH', 'meaning': 'Little Red Riding Hood'}
        return payload

    def check(self, payload):
        return validation.validate_result(payload, phase='1', cycle_id='cycle-one', scope='season', accepted={})

    def test_new_complete_keter_requires_meaningful_safe_prefix(self):
        for prefix in (None, {}, {'code': 'LRRH', 'meaning': ''}, {'code': '<bad>', 'meaning': 'Story'}, {'code': 'A1', 'meaning': 'Story'}):
            with self.subTest(prefix=prefix):
                payload = self.keter()
                payload['reference_prefix'] = prefix
                with self.assertRaisesRegex(SystemExit, 'reference prefix'):
                    self.check(payload)

    def test_legacy_normalized_result_remains_readable_and_valid(self):
        legacy = deepcopy(established()['1'])
        legacy.pop('reference_prefix', None)
        self.assertEqual(self.check(legacy), legacy)
        body = cycles.render_result(legacy)
        self.assertNotIn('cycle-one', cycles.RECORD.sub('', body))
        self.assertEqual(cycles.decode_records(body), [legacy])

    def test_renderer_uses_chosen_prefix_preserving_hidden_ids(self):
        result = self.check(self.keter())
        body = cycles.render_result(result)
        public = cycles.RECORD.sub('', body)
        self.assertIn('Reference prefix: LRRH — Little Red Riding Hood', public)
        self.assertIn('#### LRRH-K1', public)
        self.assertNotIn('Source anchors:', public)
        self.assertNotIn('cycle-one', public)
        self.assertNotIn('Cycle:', public)
        self.assertEqual(cycles.decode_records(body), [result])
        self.assertEqual(result['anchors'][0]['id'], 'cycle-one:1:a1')

    def test_later_phases_inherit_keter_prefix_and_cannot_override(self):
        accepted = established()
        accepted['1'] = self.check(self.keter())
        payload = base('2A')
        payload.update(reference_prefix={'code': 'OTHER', 'meaning': 'Other'}, artifacts=[{'scope':'scene','content':'Door', 'source_refs':['cycle-one:1:a1']}])
        result = validation.validate_result(payload, phase='2A', cycle_id='cycle-one', scope='season', accepted=accepted)
        self.assertEqual(result['reference_prefix'], accepted['1']['reference_prefix'])
        self.assertIn('Source anchors: LRRH-K1', cycles.render_result(result))

    def test_ancestry_distinguishes_same_phase_from_different_explorations(self):
        accepted = established()
        accepted['1'] = self.check(self.keter())
        payload = base('4')
        payload['assignments'] = [{'element_id': 'cycle-one:e1', 'outline': 'She chooses.'}]
        result = validation.validate_result(payload, phase='4', cycle_id='cycle-one', scope='season', accepted=accepted)
        older = [{'id': 'older-cycle:1:a1', 'content': 'First idea', 'source_refs': []}]
        child = cycles.child_assignments(result, parent_issue=1, accepted=accepted, inherited={'ancestry':older, 'anchors':[]})[0]
        public = cycles.RECORD.sub('', child['body'])
        self.assertIn('LRRH-H1-K1', public)
        self.assertIn('LRRH-K1', public)
        self.assertNotIn('older-cycle', public)
        self.assertNotIn('cycle-one', public)
        self.assertEqual(cycles.decode_records(child['body'])[0]['ancestry'][0]['id'], 'older-cycle:1:a1')

    def test_cycle_start_keeps_identity_pending_without_github_comment(self):
        from unittest.mock import patch
        from trigger_workflow_creative_writer import core
        from tests.trigger_workflow_creative_writer.test_cycles import CycleRoutingTests
        request = CycleRoutingTests().request('1')
        with patch.object(core, 'post_issue_comment') as post:
            record = core._ensure_cycle(request)
        post.assert_not_called()
        self.assertEqual(cycles.current_cycle(request.issue_data), record)

    def test_embedded_internal_references_are_rendered_without_losing_prose(self):
        result = self.check(self.keter())
        result['narrative'] = 'Develop cycle-one:1:a1 in cycle-one; preserve the door.'
        body = cycles.render_result(result)
        self.assertIn('Develop LRRH-K1 in LRRH exploration; preserve the door.', body)
        self.assertEqual(cycles.decode_records(body), [result])

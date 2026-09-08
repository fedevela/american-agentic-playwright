"""Readable beat identities survive validation, publication, and legacy ancestry."""
from copy import deepcopy
import unittest

from trigger_workflow_creative_writer import cycles, validation


def material(identifier, parents=()):
    return {'pivotal_beats': [{'id': identifier, 'content': 'Red refuses and the Wolf withdraws its help.',
                             'source_beat_ids': list(parents)}]}


class ReadableBeatTests(unittest.TestCase):
    def test_malformed_beats_fail_as_contract_errors(self):
        for beats in (None, 3, [], [None], [{'id': []}]):
            with self.subTest(beats=beats), self.assertRaises(SystemExit):
                validation.validate_pivotal_identities([{'pivotal_beats': beats}], [],
                                                      cycle_id='current', phase='1')

    def test_new_readable_ids_and_retained_ids_survive_publication(self):
        items = [material('BEAT-K1-1-1')]
        validation.validate_pivotal_identities(items, [], cycle_id='current', phase='1')
        validation.validate_pivotal_identities(deepcopy(items), items, cycle_id='child', phase='1')
        result = {'kind': 'result', 'cycle_id': 'current', 'phase': '1', 'outcome': 'complete',
                  'anchors': [{'id': 'current:1:a1', **items[0]}]}
        published = cycles.render_result(result)
        self.assertIn('Item BEAT-K1-1-1', published)
        self.assertNotIn('BEAT-H', published)
        self.assertEqual(cycles.decode_records('### Phase 1: Keter\n\n' + published)[0]
                         ['anchors'][0]['pivotal_beats'][0]['id'], 'BEAT-K1-1-1')

    def test_failed_tick_readable_references_preserve_legacy_ancestry(self):
        old = 'BEAT-4d6a1d8707fe-1-1'
        sources = [material(old)]
        items = [material('BEAT-K1-1-1'), material('BEAT-CH1-2A-1', ['BEAT-K1-1-1'])]
        validation.validate_pivotal_identities(items, sources, cycle_id='4d6a1d8707fe', phase='2A')
        self.assertEqual(items[0]['pivotal_beats'][0]['source_beat_ids'], [old])
        self.assertEqual(items[1]['pivotal_beats'][0]['source_beat_ids'], [old, 'BEAT-K1-1-1'])
        self.assertEqual(sources, [material(old)])
        validation.validate_pivotal_identities(deepcopy(items), sources, cycle_id='4d6a1d8707fe', phase='2A')
        validation.validate_pivotal_identities(deepcopy(items), items, cycle_id='next', phase='1')

    def test_one_result_cannot_publish_both_names_for_the_same_legacy_beat(self):
        old = 'BEAT-4d6a1d8707fe-1-1'
        with self.assertRaisesRegex(SystemExit, 'both'):
            validation.validate_pivotal_identities([material(old), material('BEAT-K1-1-1')],
                                                  [material(old)], cycle_id='current', phase='2A')

    def test_readable_predecessor_without_retained_artifact_resolves_to_legacy(self):
        old = 'BEAT-4d6a1d8707fe-1-1'
        items = [material('BEAT-CH1-2A-1', ['BEAT-K1-1-1'])]
        validation.validate_pivotal_identities(items, [material(old)], cycle_id='current', phase='2A')
        self.assertEqual(items[0]['pivotal_beats'][0]['source_beat_ids'], [old])

    def test_ambiguous_legacy_alias_is_rejected(self):
        sources = [material('BEAT-first-1-1'), material('BEAT-second-1-1')]
        with self.assertRaisesRegex(SystemExit, 'ambiguous'):
            validation.validate_pivotal_identities([material('BEAT-K1-1-1')], sources,
                                                  cycle_id='current', phase='2A')

    def test_new_id_cannot_reuse_ancestor_or_wrong_phase(self):
        sources = [material('BEAT-CH1-2A-1', ['BEAT-K1-1-1'])]
        for identifier in ('BEAT-K1-1-1', 'BEAT-B1-2A-1', 'BEAT-K0-1-1', 'BEAT-K1-1-0'):
            with self.subTest(identifier=identifier), self.assertRaises(SystemExit):
                validation.validate_pivotal_identities([material(identifier, ['BEAT-CH1-2A-1'])],
                                                      sources, cycle_id='next', phase='1')

    def test_later_cycle_cannot_reuse_a_transitive_ancestor_name(self):
        keter = [material('BEAT-K1-1-1')]
        exploration = [material('BEAT-CH1-2A-1', ['BEAT-K1-1-1'])]
        validation.validate_pivotal_identities(exploration, keter, cycle_id='first', phase='2A')
        synthesis = [material('BEAT-G1-3-1', ['BEAT-CH1-2A-1'])]
        validation.validate_pivotal_identities(synthesis, exploration, cycle_id='first', phase='3')
        with self.assertRaisesRegex(SystemExit, 'ancestor'):
            validation.validate_pivotal_identities([material('BEAT-K1-1-1', ['BEAT-G1-3-1'])],
                                                  synthesis, cycle_id='second', phase='1')

    def test_legacy_ids_remain_accepted(self):
        items = [material('BEAT-current-1-1')]
        validation.validate_pivotal_identities(items, [], cycle_id='current', phase='1')
        validation.validate_pivotal_identities(deepcopy(items), items, cycle_id='next', phase='2A')

    def test_conflicting_definitions_and_missing_coverage_still_fail(self):
        first = material('BEAT-K1-1-1')
        different = deepcopy(first)
        different['pivotal_beats'][0]['content'] = 'Red accepts and the Wolf follows.'
        with self.assertRaisesRegex(SystemExit, 'conflicting'):
            validation.validate_pivotal_identities([first, different], [], cycle_id='current', phase='1')
        with self.assertRaisesRegex(SystemExit, 'coverage'):
            validation.validate_pivotal_identities([material('BEAT-CH1-2A-1')], [first],
                                                  cycle_id='current', phase='2A')

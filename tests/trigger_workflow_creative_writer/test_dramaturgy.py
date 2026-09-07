from copy import deepcopy
import unittest

from trigger_workflow_creative_writer import validation


CYCLE = 'cycle-one'


def ready_element():
    return {'title': 'The locked door', 'scope': 'scene', 'readiness': 'ready',
            'source_refs': ['cycle-one:3:a1'], 'content': 'She must choose who enters.',
            'outline': 'She bars the door, then lets her enemy in.',
            'development_question': '', 'return_reason': '',
            'placement': {'episode': 'Script/Season_01/Episode_01', 'act': '1', 'scene_id': 'door'},
            'beats': [{'content': 'She bars the door.', 'source_refs': ['cycle-one:3:a1']} ]}


def base(phase):
    return {'outcome': 'complete', 'narrative': 'The door becomes a choice.',
            'cycle_id': CYCLE, 'scope': 'season', 'questions': [], 'canon_refs': [],
            **({'reference_prefix': {'code': 'DOOR', 'meaning': 'The locked door'}} if phase == '1' else {})}


def established():
    keter = base('1')
    keter.update(axes={k: 'A dramatic tension.' for k in ('pursuit','opposition','pressure','change','dramatic_question')},
                 anchors=[{'content': 'The choice of loyalty', 'source_refs': []}])
    keter = validation.validate_result(keter, phase='1', cycle_id=CYCLE, scope='season', accepted={})
    accepted = {'1': keter}
    for phase in ('2A', '2B', '2C'):
        result = base(phase)
        result['artifacts'] = [{'scope':'scene','content': 'Door possibility ' + phase,
                                'source_refs': ['cycle-one:1:a1']}]
        accepted[phase] = validation.validate_result(result, phase=phase, cycle_id=CYCLE, scope='season', accepted=accepted)
    result = base('3')
    result.update(anchors=[{'content':'Loyalty at the door', 'source_refs': [f'cycle-one:{p}:a1' for p in ('2A','2B','2C')]}],
                  elements=[ready_element()])
    accepted['3'] = validation.validate_result(result, phase='3', cycle_id=CYCLE, scope='season', accepted=accepted)
    return accepted


class DramaturgyContractTests(unittest.TestCase):
    def test_mixed_assignments_keep_ready_scene_and_recursive_episode(self):
        self.assertTrue(hasattr(validation, 'validate_result'), 'Structured result validation is required')
        accepted = established()
        larger = deepcopy(ready_element())
        larger.update(title='The unanswered exile', scope='episode', readiness='develop', beats=[], placement=None,
                      outline='', development_question='Why does she return?', return_reason='Motive remains unresolved.')
        synthesis = deepcopy(accepted['3'])
        synthesis['elements'].append(larger)
        accepted['3'] = validation.validate_result(synthesis, phase='3', cycle_id=CYCLE, scope='season', accepted=accepted)
        payload = base('4')
        payload['assignments'] = [{'element_id': e['id'], 'outline': e['outline']} for e in accepted['3']['elements']]
        result = validation.validate_result(payload, phase='4', cycle_id=CYCLE, scope='season', accepted=accepted)
        self.assertEqual([(e['scope'],e['readiness']) for e in result['elements']], [('scene','ready'),('episode','develop')])

    def test_missing_beat_coverage_blocks_ready_scene(self):
        self.assertTrue(hasattr(validation, 'validate_result'))
        accepted = established()
        result = deepcopy(accepted['3'])
        result['elements'][0]['beats'][0]['source_refs'] = []
        with self.assertRaisesRegex(SystemExit, 'source|coverage'):
            validation.validate_result(result, phase='3', cycle_id=CYCLE, scope='season', accepted=accepted)

    def test_generated_seasons_and_beats_are_rejected(self):
        self.assertTrue(hasattr(validation, 'validate_result'))
        accepted = established()
        for scope in ('season','beat'):
            result = base('2A')
            result['artifacts'] = [{'scope':scope,'content':'A possibility','source_refs':['cycle-one:1:a1']}]
            with self.assertRaisesRegex(SystemExit, 'scope'):
                validation.validate_result(result, phase='2A', cycle_id=CYCLE, scope='season', accepted=accepted)

    def test_unfinished_scene_can_return_at_same_scope(self):
        self.assertTrue(hasattr(validation, 'validate_result'))
        accepted = established()
        result = deepcopy(accepted['3'])
        result['elements'][0].update(readiness='develop', beats=[], placement=None, outline='',
                                     development_question='What makes her open the door?', return_reason='Action not earned.')
        checked = validation.validate_result(result, phase='3', cycle_id=CYCLE, scope='season', accepted=accepted)
        self.assertEqual(checked['elements'][0]['scope'], 'scene')
        self.assertEqual(checked['elements'][0]['readiness'], 'develop')

    def test_tiferet_cannot_drop_or_rewrite_organization(self):
        self.assertTrue(hasattr(validation, 'validate_result'))
        accepted = established()
        for assignments in ([], [{'element_id':'invented','outline':'New story'}]):
            payload = base('4')
            payload['assignments'] = assignments
            with self.assertRaises(SystemExit):
                validation.validate_result(payload, phase='4', cycle_id=CYCLE, scope='season', accepted=accepted)

    def test_question_is_not_accepted_completion(self):
        self.assertTrue(hasattr(validation, 'validate_result'))
        payload = base('3')
        payload.update(outcome='question', questions=['Should she forgive him?'])
        checked = validation.validate_result(payload, phase='3', cycle_id=CYCLE, scope='season', accepted={})
        self.assertEqual(checked['outcome'], 'question')
        payload['outcome'] = 'complete'
        with self.assertRaisesRegex(SystemExit, 'question'):
            validation.validate_result(payload, phase='3', cycle_id=CYCLE, scope='season', accepted={})

    def test_malformed_status_and_development_material_fail_as_contract_errors(self):
        accepted=established()
        payload=base('3');payload['outcome']={}
        with self.assertRaises(SystemExit):
            validation.validate_result(payload,phase='3',cycle_id=CYCLE,scope='season',accepted=accepted)
        payload=deepcopy(accepted['3'])
        payload['elements'][0].update(readiness='develop',development_question='Why?',return_reason='Unresolved',beats='not beats')
        with self.assertRaises(SystemExit):
            validation.validate_result(payload,phase='3',cycle_id=CYCLE,scope='season',accepted=accepted)

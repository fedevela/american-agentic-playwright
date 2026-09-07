from copy import deepcopy
import unittest
from trigger_workflow_creative_writer import cycles, core, validation
from tests.trigger_workflow_creative_writer.test_dramaturgy import established, base


class IssueTraceabilityTests(unittest.TestCase):
    def issue(self):
        return {'number':1, '_repo':'owner/story', 'title':'Story', 'body':'Intent',
                'labels':[{'name':'size:season'}], 'comments':[]}

    def test_new_exploration_carries_actual_issue_identity_and_size(self):
        record=cycles.new_cycle(self.issue())
        self.assertEqual(record.get('issue_ref'),{'repo':'owner/story','number':1,'scope':'season'})

    def test_same_scope_cycle_cannot_be_copied_to_another_issue_or_repo(self):
        issue=self.issue()
        record=cycles.new_cycle(issue)
        issue['comments']=[{'body':cycles.encode_record(record)}]
        for field, value in [('number',99),('_repo','other/story')]:
            changed=deepcopy(issue); changed[field]=value
            with self.subTest(field=field), self.assertRaisesRegex(SystemExit,'own|issue|repository'):
                cycles.current_cycle(changed)

    def test_level_two_keeps_issue_scope_distinct_from_each_artifact_scope(self):
        issue=self.issue(); accepted=established()
        cycle={'kind':'cycle','version':1,'cycle_id':'cycle-one','scope':'season',
               'issue_ref':{'repo':'owner/story','number':1,'scope':'season'}}
        for result in accepted.values():
            result['issue_ref']=cycle['issue_ref']
        issue['comments']=[{'body':cycles.encode_record(cycle)}]+[{'body':cycles.encode_record(r)} for r in accepted.values()]
        for phase in ('2A','2B','2C'):
            context=cycles.prompt_context(issue,phase)
            self.assertEqual(context.get('issue_ref'),cycle['issue_ref'])
            self.assertEqual(context['scope'],'season')
            self.assertEqual(accepted[phase]['artifacts'][0]['scope'],'scene')
            self.assertNotIn('explorations',context)

    def test_result_from_another_issue_is_rejected_inside_current_cycle(self):
        issue=self.issue(); accepted=established()
        cycle={'kind':'cycle','version':1,'cycle_id':'cycle-one','scope':'season',
               'issue_ref':{'repo':'owner/story','number':1,'scope':'season'}}
        accepted['1']['issue_ref']={**cycle['issue_ref'],'number':2}
        issue['comments']=[{'body':cycles.encode_record(cycle)},{'body':cycles.encode_record(accepted['1'])}]
        with self.assertRaisesRegex(SystemExit,'own|issue'):
            cycles.accepted_results(issue)

    def test_child_parent_ref_and_size_survive_recursive_keter(self):
        accepted=established()
        source={'repo':'owner/story','number':1,'scope':'season'}
        for result in accepted.values():
            result['issue_ref']=source
        accepted['3']['elements'][0].update(readiness='develop',development_question='Why?',return_reason='Not earned')
        payload=base('4'); payload['assignments']=[{'element_id':'cycle-one:e1','outline':accepted['3']['elements'][0]['outline']}]
        result=validation.validate_result(payload,phase='4',cycle_id='cycle-one',scope='season',accepted=accepted)
        result['issue_ref']=source
        child=cycles.child_assignments(result,parent_issue=1,accepted=accepted)[0]
        issue={'number':2,'_repo':'owner/story','body':child['body'],'labels':[{'name':'size:scene'}],'comments':[]}
        context=cycles.prompt_context(issue,'1')
        self.assertEqual(context.get('issue_ref'),{'repo':'owner/story','number':2,'scope':'scene'})
        self.assertEqual(context['inherited'].get('parent_ref'),source)
        self.assertEqual(context['inherited']['element']['scope'],'scene')
        self.assertIn('Why?',str(context))

    def test_parent_number_cannot_be_substituted_when_creating_children(self):
        accepted=established(); payload=base('4')
        payload['assignments']=[{'element_id':'cycle-one:e1','outline':'Her choice.'}]
        result=validation.validate_result(payload,phase='4',cycle_id='cycle-one',scope='season',accepted=accepted)
        result['issue_ref']={'repo':'owner/story','number':1,'scope':'season'}
        with self.assertRaisesRegex(SystemExit,'parent|issue'):
            cycles.child_assignments(result,parent_issue=99,accepted=accepted)

    def test_development_assignment_revalidates_sources_and_child_size(self):
        accepted=established()
        accepted['3']['elements'][0].update(readiness='develop',development_question='Why?',return_reason='Unresolved')
        payload=base('4'); payload['assignments']=[{'element_id':'cycle-one:e1','outline':accepted['3']['elements'][0]['outline']}]
        result=validation.validate_result(payload,phase='4',cycle_id='cycle-one',scope='season',accepted=accepted)
        child=cycles.child_assignments(result,parent_issue=1,accepted=accepted)[0]
        assignment=cycles.decode_records(child['body'])[0]
        for change in ('scope','anchor','accepted'):
            issue={'number':2,'_repo':'owner/story','labels':[{'name':'size:scene'}],'comments':[]}
            altered=deepcopy(assignment)
            if change=='scope': issue['labels']=[{'name':'size:episode'}]
            if change=='anchor': altered['anchors'][0]['id']='invented'
            if change=='accepted': altered.pop('accepted')
            issue['body']=cycles.encode_record(altered)
            with self.subTest(change=change), self.assertRaisesRegex(SystemExit,'scope|size|source|accepted|Keter'):
                cycles.prompt_context(issue,'1')

    def test_legacy_results_gain_runtime_ownership_without_changing_source_ids(self):
        issue=self.issue(); accepted=established()
        issue['comments']=[{'body':cycles.encode_record({'kind':'cycle','version':1,'cycle_id':'cycle-one','scope':'season'})}]+[{'body':cycles.encode_record(r)} for r in accepted.values()]
        result=cycles.accepted_results(issue)
        self.assertEqual(result['1'].get('issue_ref'),{'repo':'owner/story','number':1,'scope':'season'})
        self.assertEqual(result['1']['anchors'][0]['id'],'cycle-one:1:a1')
        self.assertNotIn('issue_ref',cycles.decode_records(issue['comments'][1]['body'])[0])

    def test_assignment_cannot_drop_its_ancestry(self):
        accepted=established(); payload=base('4')
        payload['assignments']=[{'element_id':'cycle-one:e1','outline':'Her choice.'}]
        result=validation.validate_result(payload,phase='4',cycle_id='cycle-one',scope='season',accepted=accepted)
        child=cycles.child_assignments(result,parent_issue=1,accepted=accepted)[0]
        assignment=cycles.decode_records(child['body'])[0]
        assignment['ancestry']=[]
        with self.assertRaisesRegex(SystemExit,'ancestry'):
            cycles.ready_assignment({'body':cycles.encode_record(assignment),'labels':[{'name':'size:scene'}]})

    def test_mixed_level_two_scopes_reach_gevurah_without_reclassifying_issue(self):
        accepted = {'1': established()['1']}
        for phase in ('2A','2B','2C'):
            payload=base(phase)
            payload['artifacts']=[{'scope':scope,'content':f'{scope} material from {phase}',
                                   'source_refs':['cycle-one:1:a1']} for scope in ('episode','act','scene')]
            accepted[phase]=validation.validate_result(payload,phase=phase,cycle_id='cycle-one',scope='season',accepted=accepted)
        issue=self.issue()
        issue['comments']=[{'body':cycles.encode_record({'kind':'cycle','version':1,'cycle_id':'cycle-one','scope':'season'})}]+[{'body':cycles.encode_record(r)} for r in accepted.values()]
        context=cycles.prompt_context(issue,'3')
        self.assertEqual(context['issue_ref'],{'repo':'owner/story','number':1,'scope':'season'})
        for phase in ('2A','2B','2C'):
            material=context['explorations'][phase]
            self.assertEqual(material['scope'],'season')
            self.assertEqual([a['scope'] for a in material['artifacts']],['episode','act','scene'])
            self.assertEqual([a['id'] for a in material['artifacts']],
                             [f'cycle-one:{phase}:a1',f'cycle-one:{phase}:a2',f'cycle-one:{phase}:a3'])

    def test_foreign_question_cannot_pause_current_issue(self):
        issue=self.issue(); question=base('3')
        question.update(kind='result',version=1,phase='3',outcome='question',questions=['Choose?'],
                        issue_ref={'repo':'owner/story','number':99,'scope':'season'})
        issue['comments']=[{'body':cycles.encode_record({'kind':'cycle','version':1,'cycle_id':'cycle-one','scope':'season'})}, {'body':cycles.encode_record(question)}]
        with self.assertRaisesRegex(SystemExit,'issue|own'):
            cycles.waiting_for_partner(issue,'3')

    def test_grandparent_ancestry_cannot_be_dropped(self):
        import json
        older=established()
        inherited=older['3']['anchors']
        accepted={}
        for phase, old_result in older.items():
            payload=json.loads(json.dumps(old_result).replace('cycle-one','cycle-two'))
            payload['scope']='scene'
            if phase=='1': payload['anchors'][0]['source_refs']=['cycle-one:3:a1']
            accepted[phase]=validation.validate_result(payload,phase=phase,cycle_id='cycle-two',scope='scene',accepted=accepted,inherited=inherited)
        payload=base('4');payload.update(cycle_id='cycle-two',scope='scene',assignments=[{'element_id':'cycle-two:e1','outline':'Her choice.'}])
        result=validation.validate_result(payload,phase='4',cycle_id='cycle-two',scope='scene',accepted=accepted)
        ancestry=[a for r in older.values() for a in r.get('anchors',[])+r.get('artifacts',[])]
        child=cycles.child_assignments(result,parent_issue=2,accepted=accepted,inherited={'anchors':inherited,'ancestry':ancestry})[0]
        assignment=cycles.decode_records(child['body'])[0]
        assignment['ancestry']=[a for a in assignment['ancestry'] if not a['id'].startswith('cycle-one:') or a['id']=='cycle-one:3:a1']
        with self.assertRaisesRegex(SystemExit,'ancestry'):
            cycles.validate_assignment(assignment)

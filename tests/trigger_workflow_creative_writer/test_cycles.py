import unittest
from trigger_workflow_creative_writer import validation
from tests.trigger_workflow_creative_writer.test_dramaturgy import established, base


class CycleTests(unittest.TestCase):
    def cycles(self):
        from trigger_workflow_creative_writer import cycles
        return cycles

    def issue(self):
        c = self.cycles()
        return {'title':'Season','body':'Human intention', 'labels':[{'name':'size:season'}],
                'comments':[{'body':c.encode_record({'kind':'cycle','version':1,'cycle_id':'cycle-one','scope':'season'})}]
                + [{'body':c.encode_record(r)} for r in established().values()]}

    def test_new_cycle_excludes_old_explorations(self):
        c = self.cycles()
        issue = self.issue()
        issue['comments'].append({'body':c.encode_record({'kind':'cycle','version':1,'cycle_id':'cycle-two','scope':'season'})})
        with self.assertRaisesRegex(SystemExit, 'Keter'):
            c.prompt_context(issue,'2A')
        result = base('1')
        result.update(cycle_id='cycle-two', axes={a:'Fresh tension' for a in validation.AXES}, anchors=[{'content':'New brief','source_refs':[]}])
        result = validation.validate_result(result,phase='1',cycle_id='cycle-two',scope='season',accepted={})
        issue['comments'].append({'body':c.encode_record(result)})
        context = str(c.prompt_context(issue,'2B'))
        self.assertIn('New brief', context)
        self.assertNotIn('Door possibility', context)
        self.assertNotIn('Human intention', context)

    def test_question_waits_for_human_reply_after_it(self):
        c = self.cycles()
        issue = self.issue()
        question = base('3')
        question.update(kind='result',version=1,phase='3',outcome='question',questions=['Forgive him?'])
        issue['comments'].append({'body':c.encode_record(question)})
        self.assertTrue(c.waiting_for_partner(issue,'3'))
        issue['comments'].append({'body':'Bot thinks yes', 'author':{'login':'robot[bot]'}})
        self.assertTrue(c.waiting_for_partner(issue,'3'))
        issue['comments'].append({'body':'Let her refuse.', 'author':{'login':'partner'}})
        self.assertFalse(c.waiting_for_partner(issue,'3'))
        self.assertIn('Let her refuse.', str(c.prompt_context(issue,'3')))

    def test_legacy_scene_cannot_enter_phase_five(self):
        c = self.cycles()
        with self.assertRaisesRegex(SystemExit, 'Keter'):
            c.ready_assignment({'body':'[SMALL] Requirement IDs: ABC-001', 'labels':[{'name':'size:scene'}]})

    def test_recursive_assignment_preserves_prior_work_and_ancestry(self):
        c = self.cycles()
        accepted = established()
        payload = base('4')
        payload['assignments'] = [{'element_id':'cycle-one:e1','outline':'She chooses her enemy.'}]
        result = validation.validate_result(payload,phase='4',cycle_id='cycle-one',scope='season',accepted=accepted)
        children = c.child_assignments(result, parent_issue=1, accepted=accepted)
        self.assertEqual(children[0]['scope'],'scene')
        issue = {'body':children[0]['body'],'labels':[{'name':'size:scene'}]}
        assignment = c.ready_assignment(issue)
        self.assertEqual(assignment['element']['placement']['episode'],'Script/Season_01/Episode_01')
        self.assertIn('cycle-one:1:a1', str(assignment['ancestry']))


class CycleRoutingTests(unittest.TestCase):
    def request(self, phase='1'):
        from trigger_workflow_creative_writer.models import PhaseExecutionRequest
        from trigger_workflow_creative_writer import cycles
        from tests.trigger_workflow_creative_writer.test_dramaturgy import established
        labels = {'1':'keter','3':'gevurah','4':'tiferet','5':'netzach'}
        data = {'title':'Story','body':'The choice','labels':[{'name':'size:season'},{'name':'unrelated'}], 'comments':[]}
        if phase != '1':
            data['comments'] = [{'body':cycles.encode_record({'kind':'cycle','version':1,'cycle_id':'cycle-one','scope':'season'})}]
            data['comments'] += [{'body':cycles.encode_record(r)} for p,r in established().items() if p != phase]
        return PhaseExecutionRequest(label='phase:'+labels[phase],issue=1,repo='owner/repo',microagent_content='Write',phase=phase,issue_data=data)

    def test_question_does_not_advance_and_explicit_reply_resumes(self):
        from unittest.mock import patch
        from trigger_workflow_creative_writer import core, cycles
        request = self.request('3')
        question = base('3')
        question.update(outcome='question',questions=['Forgive?'])
        published=[]; labels=[]
        def post(repo, issue, body):
            published.append(body)
            request.issue_data['comments'].append({'body':body})
        with patch.object(core,'run_json_phase',return_value=question) as runner, patch.object(core,'post_issue_comment',side_effect=post), patch.object(core,'advance_issue_label',side_effect=lambda *args: labels.append(args)), patch.object(core,'edit_issue_labels',create=True):
            core.execute_comment_phase_handoff(request)
            self.assertEqual(labels,[])
            self.assertTrue(cycles.waiting_for_partner(request.issue_data,'3'))
            core.execute_comment_phase_handoff(request)
            self.assertEqual(runner.call_count,1)
            request.issue_data['comments'].append({'body':'She refuses.', 'author':{'login':'partner'}})
            runner.return_value = established()['3']
            core.execute_comment_phase_handoff(request)
            self.assertEqual(len(labels),1)
            self.assertIn('She refuses.',runner.call_args.args[0])

    def test_tiferet_preserves_parent_size_and_unrelated_labels(self):
        from unittest.mock import patch
        from trigger_workflow_creative_writer import core
        request = self.request('4')
        payload = base('4')
        payload['assignments'] = [{'element_id':'cycle-one:e1','outline':'Her choice unfolds.'}]
        with patch.object(core,'run_json_phase',return_value=payload), patch.object(core,'post_issue_comment'), patch.object(core,'create_child_issues',return_value=[{'number':2,'id':22,'title':'Door','url':'url'}]) as create, patch.object(core,'create_issue_branches_for_child_issues'), patch.object(core,'remove_issue_label') as remove, patch.object(core,'reconcile_parent_completion'), patch.object(core,'clear_issue_labels_except') as clear, patch.object(core,'edit_issue_labels',create=True):
            core.execute_tiferet_specification_phase(request)
            self.assertEqual(create.call_args.args[2][0]['scope'],'scene')
            remove.assert_called_once_with('owner/repo',1,'phase:tiferet')
            clear.assert_not_called()

    def test_manually_labeled_legacy_issue_cannot_run_phase_five(self):
        from unittest.mock import patch
        from trigger_workflow_creative_writer import core
        request = self.request('5')
        with patch.object(core,'run_implementation_phase') as run:
            with self.assertRaisesRegex(SystemExit,'Keter'):
                core.execute_implementation_phase_task(request)
            run.assert_not_called()

    def test_final_scene_delivery_closes_hierarchy_and_retry_skips_execution(self):
        from unittest.mock import patch
        from trigger_workflow_creative_writer import core, cycles
        from trigger_workflow_creative_writer.models import PhaseExecutionRequest
        data={'title':'Scene','body':'Body','comments':[],'labels':[{'name':'size:scene'}]}
        request=PhaseExecutionRequest('phase:hod-refactoring',2,'owner/repo','Write','10',data)
        def post(repo, issue, body):
            data['comments'].append({'body':body})
        with patch.object(core,'run_implementation_phase') as run, patch.object(core,'finalize_delivery',return_value='Delivered') as deliver, patch.object(core,'post_issue_comment',side_effect=post), patch.object(core,'complete_scene_and_roll_up',create=True) as close:
            core.execute_implementation_phase_task(request)
            core.execute_implementation_phase_task(request)
            self.assertEqual(run.call_count,1)
            self.assertEqual(deliver.call_count,1)
            self.assertEqual(close.call_count,2)


class ContextIntegrityTests(unittest.TestCase):
    def test_level_two_canon_does_not_depend_on_sibling_artifacts(self):
        accepted = established()
        accepted['2A']['canon_refs'] = ['bible/theme.md']
        payload = base('2B')
        payload['artifacts']=[{'scope':'act','content':'An independent possibility','source_refs':['cycle-one:1:a1']}]
        result=validation.validate_result(payload,phase='2B',cycle_id='cycle-one',scope='season',accepted=accepted)
        self.assertEqual(result['canon_refs'],[])

    def test_new_cycle_preview_ignores_existing_cycle(self):
        from trigger_workflow_creative_writer import cycles
        issue={'labels':[{'name':'size:season'}], 'comments':[{'body':cycles.encode_record({'kind':'cycle','version':1,'cycle_id':'old-cycle','scope':'season'})}],
               '_preview_cycle':{'kind':'cycle','version':1,'cycle_id':'fresh-cycle','scope':'season'}}
        self.assertEqual(cycles.current_cycle(issue)['cycle_id'],'fresh-cycle')

    def test_development_cycle_keeps_anchor_ancestry(self):
        from trigger_workflow_creative_writer import cycles
        issue={'labels':[{'name':'size:season'}], 'comments':[]}
        prior=established()
        record=cycles.new_cycle(issue,development={'prior_work':prior,'development_question':'Why?', 'return_reason':'Not earned'})
        issue['comments']=[{'body':cycles.encode_record(record)}]
        result=base('1')
        result.update(cycle_id=record['cycle_id'],axes={a:'Fresh tension' for a in validation.AXES},anchors=[{'content':'Developed loyalty','source_refs':['cycle-one:3:a1']}],kind='result',version=1,phase='1')
        issue['comments'].append({'body':cycles.encode_record(result)})
        self.assertEqual(cycles.accepted_results(issue)['1']['anchors'][0]['source_refs'],['cycle-one:3:a1'])

    def test_develop_label_failure_reconciles_without_running_old_phase(self):
        from unittest.mock import patch
        from trigger_workflow_creative_writer import core, cycles
        request=CycleRoutingTests().request('3')
        pending=base('3'); pending.update(outcome='question',questions=['Which way?'],kind='result',version=1,phase='3')
        request.issue_data['comments'] += [{'body':cycles.encode_record(pending)},{'body':'Explore her motive.', 'author':{'login':'partner'}}]
        request.issue_data['labels'].append({'name':'phase:askQuestion'})
        result=base('3'); result.update(outcome='develop',development_question='Why return?',return_reason='Motive unresolved')
        def edit(*args, **kwargs):
            if kwargs.get('add') == ['phase:keter']:
                raise SystemExit('GitHub unavailable')
        with patch.object(core,'run_json_phase',return_value=result) as run, patch.object(core,'post_issue_comment'), patch.object(core,'edit_issue_labels',side_effect=edit) as labels:
            with self.assertRaises(SystemExit):
                core.execute_comment_phase_handoff(request)
            labels.side_effect=None
            core.execute_comment_phase_handoff(request)
            self.assertEqual(run.call_count,1)
            self.assertIn('phase:keter',labels.call_args.kwargs['add'])
            self.assertIn('phase:askQuestion',labels.call_args.kwargs['remove'])

    def test_ready_assignment_rejects_pending_source_synthesis(self):
        from trigger_workflow_creative_writer import cycles
        prior=established()
        payload=base('4'); payload['assignments']=[{'element_id':'cycle-one:e1','outline':'She opens the door.'}]
        result=validation.validate_result(payload,phase='4',cycle_id='cycle-one',scope='season',accepted=prior)
        child=cycles.child_assignments(result,parent_issue=1,accepted=prior)[0]
        assignment=cycles.decode_records(child['body'])[0]
        assignment['accepted']['4'].update(outcome='question',questions=['Approve?'])
        with self.assertRaisesRegex(SystemExit,'complete|accepted'):
            cycles.ready_assignment({'labels':[{'name':'size:scene'}],'body':cycles.encode_record(assignment)})

    def test_develop_comment_failure_leaves_no_partial_cycle(self):
        from unittest.mock import patch
        from trigger_workflow_creative_writer import core
        request=CycleRoutingTests().request('3')
        result=base('3');result.update(outcome='develop',development_question='Why?',return_reason='Motive unresolved')
        with patch.object(core,'run_json_phase',return_value=result) as run, patch.object(core,'post_issue_comment',side_effect=SystemExit('post failed')) as post, patch.object(core,'edit_issue_labels'):
            with self.assertRaises(SystemExit):
                core.execute_comment_phase_handoff(request)
            post.side_effect=None
            core.execute_comment_phase_handoff(request)
            self.assertEqual(run.call_count,2)

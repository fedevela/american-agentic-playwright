import unittest
from copy import deepcopy
from unittest.mock import patch
from trigger_workflow_creative_writer import core, cycles
from tests.trigger_workflow_creative_writer.test_cycles import CycleRoutingTests
from tests.trigger_workflow_creative_writer.test_dramaturgy import base, established


class FinalCommentOnlyTests(unittest.TestCase):
    def test_keter_posts_only_final_brief_with_hidden_exploration_identity(self):
        request=CycleRoutingTests().request('1')
        def run(*args, **kwargs):
            result=deepcopy(established()['1'])
            result['cycle_id']=cycles.current_cycle(request.issue_data)['cycle_id']
            return result
        with patch.object(core,'post_issue_comment') as post, patch.object(core,'run_json_phase',side_effect=run), patch.object(core,'advance_issue_label'), patch.object(core,'edit_issue_labels'):
            core.execute_comment_phase_handoff(request)
        self.assertEqual(post.call_count,1)
        body=post.call_args.args[2]
        self.assertNotIn('Exploration started',body)
        records=cycles.decode_records(body)
        self.assertEqual([r['kind'] for r in records],['cycle','result'])
        self.assertEqual(records[0]['cycle_id'],records[1]['cycle_id'])
        self.assertEqual(cycles.current_result(request.issue_data,'1')['outcome'],'complete')

    def test_development_publishes_one_result_with_next_exploration_hidden(self):
        request=CycleRoutingTests().request('3')
        result=base('3'); result.update(outcome='develop',development_question='Why return?',return_reason='Motive unresolved')
        with patch.object(core,'post_issue_comment') as post, patch.object(core,'run_json_phase',return_value=result), patch.object(core,'edit_issue_labels'):
            core.execute_comment_phase_handoff(request)
        self.assertEqual(post.call_count,1)
        body=post.call_args.args[2]
        self.assertIn('Why return?',body)
        self.assertNotIn('exploration started',body.lower())
        records=cycles.decode_records(body)
        self.assertEqual([r['kind'] for r in records],['result','cycle'])
        self.assertEqual(cycles.current_cycle(request.issue_data)['development']['development_question'],'Why return?')

    def test_preparation_alone_does_not_publish_a_comment(self):
        request=CycleRoutingTests().request('1')
        with patch.object(core,'post_issue_comment') as post:
            record=core._ensure_cycle(request)
        post.assert_not_called()
        self.assertEqual(cycles.current_cycle(request.issue_data),record)

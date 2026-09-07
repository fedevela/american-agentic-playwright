import json
import subprocess
from types import SimpleNamespace

import pytest

from trigger_workflow_creative_writer import runner_utils, github_ops


def issue(number, scope, parent=None):
    return {'number': number, 'id': number * 10, 'title': f'Title {number}',
            'labels': [{'name': f'size:{scope}'}], 'comments': [],
            'body': '' if parent is None else f'Parent issue: #{parent}\n<!-- creative-child:{parent}:child -->'}


def tree(monkeypatch):
    monkeypatch.setattr(runner_utils, 'resolve_target_repo_config', lambda repo: SimpleNamespace(issue_branch_prefix='issue/', main_branch='main'))
    items = {1: issue(1, 'season'), 2: issue(2, 'episode', 1), 3: issue(3, 'scene', 2)}
    for child, parent in [(2, 1), (3, 2)]:
        record = {'parent': parent, 'number': child, 'id': child * 10, 'key': f'{parent}:child'}
        items[parent]['comments'] = [{'body': '<!-- creative-child-record:' + json.dumps(record) + ' -->'}]
    monkeypatch.setattr(github_ops, 'fetch_issue_data', lambda repo, number: items[number])
    monkeypatch.setattr(github_ops, '_fetch_parent_issue', lambda repo, number: None if number == 1 else {**items[number - 1], 'repository_url': f'https://api.github.com/repos/{repo}'})
    return items


def test_all_phases_use_validated_season_root(monkeypatch):
    tree(monkeypatch)
    monkeypatch.setattr(runner_utils, 'resolve_target_repo_config', lambda repo: SimpleNamespace(issue_branch_prefix='issue/', main_branch='main'))
    for phase in ['1', '4', '7', '9', '10']:
        assert runner_utils.resolve_phase_execution_branch('o/r', phase, 3) == 'issue/1'


def test_conflicting_parent_marker_fails(monkeypatch):
    items = tree(monkeypatch)
    items[3]['body'] = 'Parent issue: #99\n<!-- creative-child:2:child -->'
    with pytest.raises(SystemExit, match='parent|ownership'):
        runner_utils.resolve_phase_execution_branch('o/r', '9', 3)


def test_missing_root_fails(monkeypatch):
    items = tree(monkeypatch)
    items[1]['labels'] = [{'name': 'size:episode'}]
    with pytest.raises(SystemExit, match='season|parent'):
        runner_utils.resolve_phase_execution_branch('o/r', '1', 3)


def test_dirty_switch_never_resets_or_cleans(tmp_path):
    def git(*args):
        return subprocess.run(['git', *args], cwd=tmp_path, text=True, capture_output=True, check=True).stdout
    git('init', '-b', 'main')
    git('config', 'user.email', 'test@example.com')
    git('config', 'user.name', 'Test')
    (tmp_path / 'work').write_text('base')
    git('add', '.')
    git('commit', '-m', 'base')
    git('checkout', '-b', 'issue/1')
    (tmp_path / 'work').write_text('season')
    git('commit', '-am', 'season')
    git('checkout', 'main')
    (tmp_path / 'work').write_text('precious dirty work')
    with pytest.raises(SystemExit):
        runner_utils.ensure_git_branch(tmp_path, 'issue/1', base_branch='main')
    assert (tmp_path / 'work').read_text() == 'precious dirty work'
    assert git('branch', '--show-current').strip() == 'main'


def test_tiferet_creates_no_child_branches(monkeypatch):
    from trigger_workflow_creative_writer.openhands_runner import create_issue_branches_for_child_issues
    monkeypatch.setattr(runner_utils, 'resolve_target_repo_config', lambda repo: pytest.fail('Child delivery must not prepare or create branches'))
    create_issue_branches_for_child_issues('o/r', 2, [3, 4])


def test_checkout_lock_excludes_and_releases(tmp_path):
    from trigger_workflow_creative_writer.season_branches import checkout_lock
    with checkout_lock(tmp_path / 'checkout'):
        with pytest.raises(SystemExit, match='already in use'):
            with checkout_lock(tmp_path / 'checkout'):
                pytest.fail('Concurrent checkout entry')
    with checkout_lock(tmp_path / 'checkout'):
        pass


def test_cycle_and_cross_repository_fail(monkeypatch):
    from trigger_workflow_creative_writer.season_branches import resolve_season_root
    items = tree(monkeypatch)
    monkeypatch.setattr(github_ops, '_fetch_parent_issue', lambda repo, number: items[number])
    items[3]['body'] = 'Parent issue: #3\n<!-- creative-child:3:child -->'
    items[3]['comments'] = [{'body': '<!-- creative-child-record:' + json.dumps({'parent': 3, 'number': 3, 'id': 30, 'key': '3:child'}) + ' -->'}]
    with pytest.raises(SystemExit, match='cycle'):
        resolve_season_root('o/r', 3)
    items[3]['repository_url'] = 'https://api.github.com/repos/other/repo'
    with pytest.raises(SystemExit, match='Cross-repository'):
        resolve_season_root('o/r', 3)


def git_repo(tmp_path):
    def git(*args):
        return subprocess.run(['git', *args], cwd=tmp_path, text=True, capture_output=True, check=True).stdout
    git('init', '-b', 'main')
    git('config', 'user.email', 'test@example.com')
    git('config', 'user.name', 'Test')
    (tmp_path / 'work').write_text('base')
    git('add', '.')
    git('commit', '-m', 'base')
    git('remote', 'add', 'origin', str(tmp_path))
    return git


def test_season_branch_created_once_and_legacy_work_preserved(tmp_path):
    git = git_repo(tmp_path)
    runner_utils.prepare_season_branch(tmp_path, 'issue/1', 'main', (3, 2, 1), 'issue/')
    assert git('branch', '--show-current').strip() == 'issue/1'
    git('checkout', '-b', 'issue/3')
    (tmp_path / 'legacy').write_text('valuable')
    git('add', '.')
    git('commit', '-m', 'legacy')
    legacy_sha = git('rev-parse', 'issue/3')
    with pytest.raises(SystemExit, match='Legacy child work'):
        runner_utils.prepare_season_branch(tmp_path, 'issue/1', 'main', (3, 2, 1), 'issue/')
    assert git('rev-parse', 'issue/3') == legacy_sha
    assert (tmp_path / 'legacy').read_text() == 'valuable'


def test_root_resolution_binds_verified_metadata(monkeypatch):
    from trigger_workflow_creative_writer.season_branches import resolve_season_root
    items = tree(monkeypatch)
    resolve_season_root('o/r', 3, items[3])
    assert items[3]['_season_ref'] == {'repo': 'o/r', 'number': 1, 'scope': 'season'}


def test_cycle_and_assignment_persist_same_season():
    from trigger_workflow_creative_writer import cycles, validation
    from tests.trigger_workflow_creative_writer.test_dramaturgy import established, base
    reference = {'repo': 'o/r', 'number': 1, 'scope': 'season'}
    data = issue(3, 'scene')
    data['_season_ref'] = reference
    assert cycles.new_cycle(data)['season_ref'] == reference
    accepted = established()
    payload = base('4')
    payload['assignments'] = [{'element_id': 'cycle-one:e1', 'outline': 'She chooses her enemy.'}]
    result = validation.validate_result(payload, phase='4', cycle_id='cycle-one', scope='season', accepted=accepted)
    result['season_ref'] = reference
    child = cycles.child_assignments(result, parent_issue=1, accepted=accepted)[0]
    assignment = cycles.decode_records(child['body'])[0]
    assert assignment['season_ref'] == reference


def test_existing_pr_requires_unique_main_base_and_root_title():
    validate = getattr(runner_utils, 'validate_season_pr', None)
    assert validate is not None
    valid = {'url': 'https://example/pr/1', 'title': 'Season #1: Title', 'baseRefName': 'main'}
    assert validate([valid], 'main', 'Season #1: Title') == valid['url']
    for records in [[valid, valid], [{**valid, 'baseRefName': 'issue/2'}], [{**valid, 'title': 'Legacy title'}]]:
        with pytest.raises(SystemExit, match='reconcil'):
            validate(records, 'main', 'Season #1: Title')


def test_initial_preparation_refuses_dirty_work(tmp_path):
    git_repo(tmp_path)
    (tmp_path / 'work').write_text('unfinished')
    check = getattr(runner_utils, 'prepare_initial_season_work', None)
    assert check is not None
    with pytest.raises(SystemExit, match='dirty'):
        check(tmp_path, 'main')
    assert (tmp_path / 'work').read_text() == 'unfinished'


def test_root_execution_detects_unintegrated_descendant_branch(tmp_path, monkeypatch):
    from trigger_workflow_creative_writer.season_branches import SeasonRoot
    git = git_repo(tmp_path)
    git('checkout', '-b', 'issue/3')
    (tmp_path / 'legacy').write_text('descendant work')
    git('add', '.')
    git('commit', '-m', 'legacy')
    git('checkout', 'main')
    monkeypatch.setattr(runner_utils, 'resolve_season_root', lambda *a, **k: SeasonRoot(1, 'Season', (3, 1)))
    with pytest.raises(SystemExit, match='Legacy child work'):
        runner_utils.prepare_season_branch(tmp_path, 'issue/1', 'main', (1,), 'issue/', repo='o/r')
    assert git('branch', '--show-current').strip() == 'main'


def test_core_holds_checkout_lock_through_execution_and_releases_on_failure(tmp_path, monkeypatch):
    from trigger_workflow_creative_writer import core
    from trigger_workflow_creative_writer.season_branches import checkout_lock
    request = SimpleNamespace(repo='o/r', issue=1, phase='1', issue_data={})
    monkeypatch.setattr(core, 'resolve_phase_execution_request', lambda **kwargs: request)
    monkeypatch.setattr(runner_utils, 'managed_repo_path', lambda repo: tmp_path / 'checkout')
    monkeypatch.setattr(runner_utils, 'prepare_phase_execution_context', lambda *args, **kwargs: SimpleNamespace(local_path=tmp_path / 'checkout'))
    monkeypatch.setattr(runner_utils, 'prepare_initial_season_work', lambda *args, **kwargs: None)
    monkeypatch.setattr(runner_utils, 'resolve_target_repo_config', lambda repo: SimpleNamespace(main_branch='main'))
    def execute(request):
        with pytest.raises(SystemExit, match='already in use'):
            with checkout_lock(tmp_path / 'checkout'):
                pytest.fail('Lock released before delivery')
        raise RuntimeError('agent failure')
    monkeypatch.setattr(core, '_execute_prepared_phase', execute)
    with pytest.raises(RuntimeError, match='agent failure'):
        core.run_labeled_issue_phase_with_mode(repo='o/r', issue=1)
    with checkout_lock(tmp_path / 'checkout'):
        pass


def test_incompatible_pr_fails_before_staging_commit_or_push(tmp_path, monkeypatch):
    from trigger_workflow_creative_writer.season_branches import SeasonRoot
    monkeypatch.setattr(runner_utils, 'prepare_phase_execution_context', lambda *a, **k: SimpleNamespace(local_path=tmp_path, branch='issue/1'))
    monkeypatch.setattr(runner_utils, 'resolve_season_root', lambda *a, **k: SeasonRoot(1, 'Season', (3, 1)))
    monkeypatch.setattr(runner_utils, 'resolve_target_repo_config', lambda repo: SimpleNamespace(main_branch='main', issue_branch_prefix='issue/'))
    calls = []
    def run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:3] == ['gh', 'pr', 'list']:
            return subprocess.CompletedProcess(cmd, 0, json.dumps([{'url': 'url', 'title': 'Legacy', 'baseRefName': 'issue/2'}]), '')
        if cmd[:2] == ['git', 'status']:
            return subprocess.CompletedProcess(cmd, 0, ' M script.md\n', '')
        return subprocess.CompletedProcess(cmd, 1, '', 'must not mutate')
    monkeypatch.setattr(runner_utils.subprocess, 'run', run)
    with pytest.raises(SystemExit, match='reconcile'):
        runner_utils.finalize_phase_delivery(repo='o/r', issue=3, phase='9', issue_title='Scene')
    assert not any(cmd[:2] in [['git', 'add'], ['git', 'commit'], ['git', 'push']] for cmd in calls)


def test_recovery_rejects_unrelated_dirty_work(tmp_path):
    git_repo(tmp_path)
    (tmp_path / 'notes').write_text('unrelated notes')
    with pytest.raises(SystemExit, match='dirty|reconcil'):
        runner_utils.prepare_initial_season_work(tmp_path, 'main', recovery=True)
    assert (tmp_path / 'notes').read_text() == 'unrelated notes'


def test_recovery_allows_only_verified_script_modification(tmp_path):
    git = git_repo(tmp_path)
    (tmp_path / 'work').write_text('rendered script')
    runner_utils.prepare_initial_season_work(tmp_path, 'main', recovery=True, recovery_paths={'work'})
    git('add', 'work')
    runner_utils.prepare_initial_season_work(tmp_path, 'main', recovery=True, recovery_paths={'work'})
    (tmp_path / 'notes').write_text('unrelated notes')
    git('add', 'notes')
    with pytest.raises(SystemExit, match='dirty|reconcil'):
        runner_utils.prepare_initial_season_work(tmp_path, 'main', recovery=True, recovery_paths={'work'})

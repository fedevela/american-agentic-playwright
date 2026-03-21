import re

with open('tests/trigger_workflow/test_git_client.py', 'r') as f:
    content = f.read()

# 1. Update test_ensure_git_branch_creates_from_local_base
content = content.replace('self.assertIn("main", run_mock.call_args_list[0].args[1])', 'self.assertIn("feature-base", run_mock.call_args_list[0].args[1])')

# 2. Update test_ensure_git_branch_creates_from_origin_base_fallback
content = content.replace('self.assertIn("origin/main", run_mock.call_args_list[2].args[1])', 'self.assertIn("origin/feature-base", run_mock.call_args_list[2].args[1])')

# 3. Update test_ensure_git_branch_fails_if_feature_missing_both_local_and_origin
content = content.replace('self.assertEqual(run_mock.call_count, 6) # 3 for main, 3 for master', 'self.assertEqual(run_mock.call_count, 3)')

# 4. Remove test_ensure_git_branch_creates_from_master_fallback
import ast
# We can just delete the lines by regex
content = re.sub(r'    @patch\("trigger_workflow\.git_client\.current_branch", return_value="other"\)\n    @patch\("trigger_workflow\.git_client\.branch_exists", return_value=False\)\n    @patch\("trigger_workflow\.git_client\.git_run"\)\n    def test_ensure_git_branch_creates_from_master_fallback.*?self\.assertIn\("push", run_mock\.call_args_list\[4\]\.args\[1\]\)\n', '', content, flags=re.DOTALL)

# 5. Fix test_ensure_git_branch_fails_if_base_missing
old_missing = """    @patch("trigger_workflow.git_client.current_branch", return_value="other")
    @patch("trigger_workflow.git_client.branch_exists", return_value=False)
    def test_ensure_git_branch_fails_if_base_missing(self, exists_mock, curr_mock) -> None:
        with self.assertRaises(SystemExit) as exc:
            ensure_git_branch(Path("/mock"), "main", base_branch="feature-base")
        self.assertIn("does not exist locally", str(exc.exception))"""

new_missing = """    @patch("trigger_workflow.git_client.current_branch", return_value="other")
    @patch("trigger_workflow.git_client.branch_exists", return_value=False)
    @patch("trigger_workflow.git_client.git_run")
    def test_ensure_git_branch_fails_if_base_missing(self, run_mock, exists_mock, curr_mock) -> None:
        res = MagicMock()
        res.returncode = 1
        run_mock.return_value = res
        with self.assertRaises(SystemExit) as exc:
            ensure_git_branch(Path("/mock"), "feature", base_branch="feature")
        self.assertIn("does not exist locally", str(exc.exception))"""
content = content.replace(old_missing, new_missing)

with open('tests/trigger_workflow/test_git_client.py', 'w') as f:
    f.write(content)

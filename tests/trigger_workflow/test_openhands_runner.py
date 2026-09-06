"""OpenHands runner tests for config parsing, checkout resolution, and session policy.

The runner is where workflow policy becomes process execution. These tests pin
the branch-selection rules, workspace/config validation, and conversation state
behavior that determine whether a phase starts fresh or resumes prior context.
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from trigger_workflow.openhands_runner import (
    OpenHandsTargetContext,
    action_observation_event_lines,
    create_issue_branches_for_child_issues,
    extract_message_events,
    finalize_phase_delivery,
    run_openhands_implementation_phase,
    load_session_state,
    resolve_openhands_model_connection,
    run_openhands,
)
from trigger_workflow.runner_utils import (
    RunnerTargetContext,
    ensure_git_branch,
    resolve_phase_execution_branch,
    prepare_phase_execution_context,
)


class OpenHandsRunnerTests(unittest.TestCase):
    """Verify runner behavior at the config, git, and subprocess boundaries.

    The suite is designed to catch regressions that would be expensive to debug
    in live runs: invalid local config files, missing target checkouts,
    incorrect branch verification, or violating the no-resume session policy.
    """

    @patch(
        "trigger_workflow.openhands_runner.openhands_env",
        return_value={"LLM_MODEL": "env-model", "LLM_BASE_URL": "https://llm.example"},
    )
    def test_resolve_openhands_model_connection_prefers_effective_env_values(self, openhands_env_mock) -> None:
        del openhands_env_mock
        model_name, connection = resolve_openhands_model_connection()

        self.assertEqual(model_name, "env-model")
        self.assertEqual(connection, "https://llm.example")

    def test_resolve_openhands_model_connection_errors_on_invalid_config_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            config_dir = workspace / ".openhands"
            config_dir.mkdir(parents=True, exist_ok=True)
            # Invalid local runtime state should fail clearly before any runner
            # process launches with ambiguous configuration.
            (config_dir / "config.json").write_text("{invalid json")

            with patch("trigger_workflow.openhands_runner.WORKSPACE", workspace):
                with self.assertRaises(SystemExit) as exc:
                    resolve_openhands_model_connection()

        self.assertIn("Invalid OpenHands config JSON", str(exc.exception))

    def test_load_session_state_errors_on_invalid_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            session_state_path = Path(temp_dir) / ".session-state.json"
            session_state_path.write_text("{invalid json")

            with patch("trigger_workflow.openhands_runner.SESSION_STATE_PATH", session_state_path):
                with self.assertRaises(SystemExit) as exc:
                    load_session_state()

        self.assertIn("Session state file is invalid JSON", str(exc.exception))

    def test_load_session_state_errors_on_non_mapping_payload(self) -> None:
        with TemporaryDirectory() as temp_dir:
            session_state_path = Path(temp_dir) / ".session-state.json"
            session_state_path.write_text('["conv-123"]')

            with patch("trigger_workflow.openhands_runner.SESSION_STATE_PATH", session_state_path):
                with self.assertRaises(SystemExit) as exc:
                    load_session_state()

        self.assertIn("must contain a JSON object", str(exc.exception))

    def test_extract_message_events_supports_marker_payloads_and_jsonl_lines(self) -> None:
        marker_payload = (
            "--JSON Event--\n"
            '{"kind":"MessageEvent","llm_message":{"role":"assistant","content":[{"text":"hi"}]}}\n'
        )
        jsonl_payload = '{"type":"action","action":"write","path":"app.py"}\n'
        events = extract_message_events(f"{marker_payload}{jsonl_payload}")

        self.assertTrue(any(event.get("kind") == "MessageEvent" for event in events))
        self.assertTrue(any(event.get("type") == "action" for event in events))

    def test_action_observation_event_lines_renders_jsonl_action_and_observation_events(self) -> None:
        output = "\n".join(
            [
                '{"type":"action","action":"write","path":"app.py"}',
                '{"type":"observation","content":"File created successfully"}',
            ]
        )

        lines = action_observation_event_lines(output)

        self.assertTrue(any("type=action" in line and "app.py" in line for line in lines))
        self.assertTrue(any("type=observation" in line and "File created successfully" in line for line in lines))

    def test_branch_name_for_phase_errors_for_unknown_repo_config(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            resolve_phase_execution_branch("owner/unknown", "5", 12)

        self.assertIn("No local target repository config exists", str(exc.exception))

    @patch("trigger_workflow.runner_utils.current_branch", return_value="main")
    @patch("trigger_workflow.runner_utils.branch_exists", return_value=False)
    def test_ensure_git_branch_errors_when_non_base_branch_is_missing(
        self,
        branch_exists_mock,
        current_branch_mock,
    ) -> None:
        del branch_exists_mock
        del current_branch_mock
        with self.assertRaises(SystemExit) as exc:
            ensure_git_branch(Path("/tmp/repo"), "issue/55", base_branch="main")

        self.assertIn("Phase 4/Tiferet must create child issue branches", str(exc.exception))

    @patch("trigger_workflow.runner_utils.git_run")
    @patch("trigger_workflow.runner_utils.ensure_git_branch")
    @patch("trigger_workflow.runner_utils.branch_exists")
    @patch("trigger_workflow.openhands_runner.prepare_target_repo_checkout")
    @patch("trigger_workflow.runner_utils.resolve_target_repo_config")
    def test_create_issue_branches_for_child_issues_creates_missing_and_skips_existing(
        self,
        resolve_target_repo_config_mock,
        prepare_target_repo_checkout_mock,
        branch_exists_mock,
        ensure_git_branch_mock,
        git_run_mock,
    ) -> None:
        local_path = Path("/tmp/managed-repo")
        config = type(
            "Config",
            (),
            {"main_branch": "main", "issue_branch_prefix": "issue/"},
        )()
        resolve_target_repo_config_mock.return_value = config
        prepare_target_repo_checkout_mock.return_value = (config, local_path)
        branch_exists_mock.side_effect = [False, False, True]
        git_run_mock.return_value = subprocess.CompletedProcess(args=["git"], returncode=0, stdout="", stderr="")

        create_issue_branches_for_child_issues("owner/repo", 100, [101, 102])

        self.assertEqual(git_run_mock.call_count, 3)
        git_run_mock.assert_any_call(
            local_path,
            ["switch", "-c", "issue/100", "main"],
            capture_output=True,
        )
        git_run_mock.assert_any_call(
            local_path,
            ["switch", "-c", "issue/101", "issue/100"],
            capture_output=True,
        )
        self.assertEqual(ensure_git_branch_mock.call_count, 2)

    @patch("trigger_workflow.runner_utils.git_run", return_value=subprocess.CompletedProcess(args=["git"], returncode=0, stdout="", stderr=""))
    @patch("trigger_workflow.runner_utils.log_info")
    @patch("trigger_workflow.runner_utils.ensure_managed_repo_checkout")
    @patch("trigger_workflow.runner_utils.current_branch", return_value="issue/21")
    @patch("trigger_workflow.runner_utils.ensure_git_branch")
    @patch("trigger_workflow.runner_utils.resolve_phase_execution_branch", return_value="issue/21")
    @patch("trigger_workflow.runner_utils.resolve_target_repo_config")
    def test_prepare_openhands_run_context_logs_loaded_repo_and_verified_branch(
        self,
        resolve_target_repo_config_mock,
        branch_name_for_phase_mock,
        ensure_git_branch_mock,
        current_branch_mock,
        ensure_managed_repo_checkout_mock,
        log_info_mock,
        git_run_mock,
    ) -> None:
        # The mocked config object is intentionally minimal: this test is about
        # path verification and branch logging, not dataclass identity.
        del branch_name_for_phase_mock
        del ensure_git_branch_mock
        del current_branch_mock
        local_path = Path("/tmp/particle-life-3d")
        managed_path = Path(__file__).resolve().parents[2] / ".openhands" / "repos" / "fedevela__particle-life-3d"
        resolve_target_repo_config_mock.return_value = type(
            "Config",
            (),
            {"local_path": local_path, "main_branch": "main", "issue_branch_prefix": "issue/"},
        )()
        ensure_managed_repo_checkout_mock.return_value = managed_path

        with patch.object(Path, "exists", autospec=True) as exists_mock:
            exists_mock.side_effect = lambda path_obj: str(path_obj) in {
                str(local_path),
                str(local_path / ".git"),
                str(managed_path),
                str(managed_path / ".git"),
            }
            context = prepare_phase_execution_context("fedevela/particle-life-3d", "5", 21)

        self.assertEqual(context.local_path, managed_path)
        self.assertEqual(context.branch, "issue/21")
        messages = [call.args[0] for call in log_info_mock.call_args_list]
        self.assertIn(f"Verified source repository path exists: {local_path}", messages)
        self.assertIn(f"Verified managed repository path exists: {managed_path}", messages)
        self.assertIn("Resolved target branch for phase 5: issue/21", messages)
        self.assertIn("Verified target repository branch loaded: issue/21", messages)

    @patch("trigger_workflow.runner_utils.ensure_managed_repo_checkout")
    @patch("trigger_workflow.runner_utils.resolve_target_repo_config")
    def test_prepare_openhands_run_context_errors_when_target_repo_path_missing(
        self,
        resolve_target_repo_config_mock,
        ensure_managed_repo_checkout_mock,
    ) -> None:
        del ensure_managed_repo_checkout_mock
        local_path = Path("/tmp/missing-particle-life-3d")
        resolve_target_repo_config_mock.return_value = type(
            "Config",
            (),
            {"local_path": local_path, "main_branch": "main", "issue_branch_prefix": "issue/"},
        )()

        with patch.object(Path, "exists", autospec=True, return_value=False):
            with self.assertRaises(SystemExit) as exc:
                prepare_phase_execution_context("fedevela/particle-life-3d", "5", 21)

        self.assertIn("Configured target repository path does not exist", str(exc.exception))

    @patch("trigger_workflow.runner_utils.ensure_managed_repo_checkout")
    @patch("trigger_workflow.runner_utils.resolve_target_repo_config")
    def test_prepare_openhands_run_context_errors_when_git_directory_missing(
        self,
        resolve_target_repo_config_mock,
        ensure_managed_repo_checkout_mock,
    ) -> None:
        del ensure_managed_repo_checkout_mock
        local_path = Path("/tmp/particle-life-3d")
        resolve_target_repo_config_mock.return_value = type(
            "Config",
            (),
            {"local_path": local_path, "main_branch": "main", "issue_branch_prefix": "issue/"},
        )()

        with patch.object(Path, "exists", autospec=True) as exists_mock:
            exists_mock.side_effect = lambda path_obj: str(path_obj) == str(local_path)
            with self.assertRaises(SystemExit) as exc:
                prepare_phase_execution_context("fedevela/particle-life-3d", "5", 21)

        self.assertIn("is not a git checkout", str(exc.exception))

    @patch("trigger_workflow.runner_utils.ensure_managed_repo_checkout")
    @patch("trigger_workflow.runner_utils.resolve_target_repo_config")
    def test_prepare_openhands_run_context_errors_when_managed_checkout_path_is_not_openhands_clone(
        self,
        resolve_target_repo_config_mock,
        ensure_managed_repo_checkout_mock,
    ) -> None:
        local_path = Path("/tmp/particle-life-3d")
        wrong_managed_path = Path("/tmp/not-openhands-managed-repo")
        resolve_target_repo_config_mock.return_value = type(
            "Config",
            (),
            {"local_path": local_path, "main_branch": "main", "issue_branch_prefix": "issue/"},
        )()
        ensure_managed_repo_checkout_mock.return_value = wrong_managed_path

        with patch.object(Path, "exists", autospec=True) as exists_mock:
            exists_mock.side_effect = lambda path_obj: str(path_obj) in {
                str(local_path),
                str(local_path / ".git"),
                str(wrong_managed_path),
                str(wrong_managed_path / ".git"),
            }
            with self.assertRaises(SystemExit) as exc:
                prepare_phase_execution_context("fedevela/particle-life-3d", "5", 21)

        self.assertIn("Managed checkout path mismatch", str(exc.exception))

    @patch("trigger_workflow.runner_utils.ensure_managed_repo_checkout")
    @patch("trigger_workflow.runner_utils.current_branch", side_effect=["main", "main"])
    @patch("trigger_workflow.runner_utils.ensure_git_branch")
    @patch("trigger_workflow.runner_utils.resolve_phase_execution_branch", return_value="issue/21")
    @patch("trigger_workflow.runner_utils.resolve_target_repo_config")
    def test_prepare_openhands_run_context_errors_when_branch_verification_fails(
        self,
        resolve_target_repo_config_mock,
        branch_name_for_phase_mock,
        ensure_git_branch_mock,
        current_branch_mock,
        ensure_managed_repo_checkout_mock,
    ) -> None:
        del branch_name_for_phase_mock
        del ensure_git_branch_mock
        del current_branch_mock
        local_path = Path("/tmp/particle-life-3d")
        managed_path = Path(__file__).resolve().parents[2] / ".openhands" / "repos" / "fedevela__particle-life-3d"
        resolve_target_repo_config_mock.return_value = type(
            "Config",
            (),
            {"local_path": local_path, "main_branch": "main", "issue_branch_prefix": "issue/"},
        )()
        ensure_managed_repo_checkout_mock.return_value = managed_path

        with patch.object(Path, "exists", autospec=True) as exists_mock:
            exists_mock.side_effect = lambda path_obj: str(path_obj) in {
                str(local_path),
                str(local_path / ".git"),
                str(managed_path),
                str(managed_path / ".git"),
            }
            with self.assertRaises(SystemExit) as exc:
                prepare_phase_execution_context("fedevela/particle-life-3d", "5", 21)

        self.assertIn("Target repository branch verification failed", str(exc.exception))

    @patch("trigger_workflow.openhands_runner.prepare_phase_execution_context")
    @patch("trigger_workflow.openhands_runner._run_openhands_command")
    def test_run_openhands_uses_target_repo_cwd(
        self,
        run_openhands_command_mock,
        prepare_openhands_run_context_mock,
    ) -> None:
        # Running in the target repo checkout is the key behavioral guarantee
        # here; the subprocess payload itself is otherwise unimportant.
        target_path = Path("/tmp/particle-life-3d")
        prepare_openhands_run_context_mock.return_value = OpenHandsTargetContext(
            local_path=target_path,
            branch="main",
        )
        run_openhands_command_mock.return_value = subprocess.CompletedProcess(
            args=["openhands"],
            returncode=0,
            stdout="Conversation ID: abc123\n",
            stderr="",
        )

        run_openhands("Test prompt", repo="fedevela/particle-life-3d", issue=21, phase="3")

        run_openhands_command_mock.assert_called_once()
        self.assertEqual(run_openhands_command_mock.call_args.kwargs["cwd"], target_path)

    @patch("trigger_workflow.runner_utils.prepare_phase_execution_context")
    @patch("trigger_workflow.runner_utils.subprocess.run")
    def test_finalize_phase_delivery_commits_pushes_and_returns_summary(
        self,
        subprocess_run_mock,
        prepare_phase_execution_context_mock,
    ) -> None:
        target_path = Path("/tmp/particle-life-3d")
        prepare_phase_execution_context_mock.return_value = RunnerTargetContext(
            local_path=target_path,
            branch="issue/21",
        )
        subprocess_run_mock.side_effect = [
            subprocess.CompletedProcess(args=["git", "fetch", "origin"], returncode=0, stdout="", stderr=""),
            subprocess.CompletedProcess(args=["git", "rev-parse", "--verify", "origin/main"], returncode=0, stdout="def456\n", stderr=""),
            subprocess.CompletedProcess(args=["git", "merge", "origin/main"], returncode=0, stdout="Already up to date.\n", stderr=""),
            subprocess.CompletedProcess(args=["git", "status"], returncode=0, stdout=" M src/app.ts\n", stderr=""),
            subprocess.CompletedProcess(args=["git", "add"], returncode=0, stdout="", stderr=""),
            subprocess.CompletedProcess(args=["git", "commit"], returncode=0, stdout="[issue/21 abc123] msg", stderr=""),
            subprocess.CompletedProcess(args=["git", "push"], returncode=0, stdout="", stderr=""),
            subprocess.CompletedProcess(args=["git", "rev-parse"], returncode=0, stdout="abc123full\n", stderr=""),
            subprocess.CompletedProcess(
                args=["git", "ls-remote"],
                returncode=0,
                stdout="abc123full\trefs/heads/issue/21\n",
                stderr="",
            ),
            subprocess.CompletedProcess(args=["gh", "pr", "list"], returncode=0, stdout="[]", stderr=""),
            subprocess.CompletedProcess(
                args=["gh", "pr", "create"],
                returncode=0,
                stdout="https://github.com/owner/repo/pull/21\n",
                stderr="",
            ),
            subprocess.CompletedProcess(args=["git", "rev-parse"], returncode=0, stdout="abc123\n", stderr=""),
            subprocess.CompletedProcess(args=["git", "show"], returncode=0, stdout="src/app.ts\n", stderr=""),
        ]

        summary = finalize_phase_delivery(
            repo="fedevela/particle-life-3d",
            issue=21,
            phase="5",
            issue_title="Example Delivery Title",
        )

        self.assertIn("Branch: `issue/21`", summary)
        self.assertIn("PR: https://github.com/owner/repo/pull/21", summary)
        self.assertIn("Commit: `abc123`", summary)
        self.assertIn("- `src/app.ts`", summary)
        self.assertEqual(subprocess_run_mock.call_count, 13)

    @patch("trigger_workflow.runner_utils.prepare_phase_execution_context")
    @patch("trigger_workflow.runner_utils.subprocess.run")
    def test_finalize_phase_delivery_strips_auto_tiferet_prefix_from_commit_message(
        self,
        subprocess_run_mock,
        prepare_phase_execution_context_mock,
    ) -> None:
        target_path = Path("/tmp/particle-life-3d")
        prepare_phase_execution_context_mock.return_value = RunnerTargetContext(
            local_path=target_path,
            branch="issue/21",
        )
        subprocess_run_mock.side_effect = [
            subprocess.CompletedProcess(args=["git", "fetch", "origin"], returncode=0, stdout="", stderr=""),
            subprocess.CompletedProcess(args=["git", "rev-parse", "--verify", "origin/main"], returncode=0, stdout="def456\n", stderr=""),
            subprocess.CompletedProcess(args=["git", "merge", "origin/main"], returncode=0, stdout="Already up to date.\n", stderr=""),
            subprocess.CompletedProcess(args=["git", "status"], returncode=0, stdout=" M src/app.ts\n", stderr=""),
            subprocess.CompletedProcess(args=["git", "add"], returncode=0, stdout="", stderr=""),
            subprocess.CompletedProcess(args=["git", "commit"], returncode=0, stdout="[issue/21 abc123] msg", stderr=""),
            subprocess.CompletedProcess(args=["git", "push"], returncode=0, stdout="", stderr=""),
            subprocess.CompletedProcess(args=["git", "rev-parse"], returncode=0, stdout="abc123full\n", stderr=""),
            subprocess.CompletedProcess(
                args=["git", "ls-remote"],
                returncode=0,
                stdout="abc123full\trefs/heads/issue/21\n",
                stderr="",
            ),
            subprocess.CompletedProcess(args=["gh", "pr", "list"], returncode=0, stdout='[{"url":"https://github.com/owner/repo/pull/21"}]', stderr=""),
            subprocess.CompletedProcess(args=["git", "rev-parse"], returncode=0, stdout="abc123\n", stderr=""),
            subprocess.CompletedProcess(args=["git", "show"], returncode=0, stdout="src/app.ts\n", stderr=""),
        ]

        finalize_phase_delivery(
            repo="fedevela/particle-life-3d",
            issue=21,
            phase="6",
            issue_title="[AUTO/TIFERET] Example Child Issue",
        )

        commit_call = subprocess_run_mock.call_args_list[5]
        commit_cmd = commit_call.args[0]
        self.assertEqual(commit_cmd[0:3], ["git", "commit", "-m"])
        self.assertEqual(commit_cmd[3], "phase:6 issue #21: Example Child Issue")

    @patch("trigger_workflow.runner_utils.prepare_phase_execution_context")
    @patch("trigger_workflow.runner_utils.subprocess.run")
    def test_finalize_phase_delivery_fails_fast_when_push_rejected_non_fast_forward(
        self,
        subprocess_run_mock,
        prepare_phase_execution_context_mock,
    ) -> None:
        target_path = Path("/tmp/particle-life-3d")
        prepare_phase_execution_context_mock.return_value = RunnerTargetContext(
            local_path=target_path,
            branch="issue/21",
        )
        subprocess_run_mock.side_effect = [
            subprocess.CompletedProcess(args=["git", "fetch", "origin"], returncode=0, stdout="", stderr=""),
            subprocess.CompletedProcess(args=["git", "rev-parse", "--verify", "origin/main"], returncode=0, stdout="def456\n", stderr=""),
            subprocess.CompletedProcess(args=["git", "merge", "origin/main"], returncode=0, stdout="Already up to date.\n", stderr=""),
            subprocess.CompletedProcess(args=["git", "status"], returncode=0, stdout=" M src/app.ts\n", stderr=""),
            subprocess.CompletedProcess(args=["git", "add"], returncode=0, stdout="", stderr=""),
            subprocess.CompletedProcess(args=["git", "commit"], returncode=0, stdout="[issue/21 abc123] msg", stderr=""),
            subprocess.CompletedProcess(
                args=["git", "push"],
                returncode=1,
                stdout="",
                stderr="! [rejected] issue/21 -> issue/21 (fetch first)",
            ),
        ]

        with self.assertRaises(SystemExit) as exc:
            finalize_phase_delivery(
                repo="fedevela/particle-life-3d",
                issue=21,
                phase="7",
                issue_title="Example Delivery Title",
            )

        self.assertIn("Human intervention required", str(exc.exception))
        self.assertEqual(subprocess_run_mock.call_count, 7)

    @patch("trigger_workflow.runner_utils.prepare_phase_execution_context")
    @patch("trigger_workflow.runner_utils.subprocess.run")
    def test_finalize_phase_delivery_fails_when_no_git_changes_exist(
        self,
        subprocess_run_mock,
        prepare_phase_execution_context_mock,
    ) -> None:
        target_path = Path("/tmp/particle-life-3d")
        prepare_phase_execution_context_mock.return_value = RunnerTargetContext(
            local_path=target_path,
            branch="issue/21",
        )
        subprocess_run_mock.return_value = subprocess.CompletedProcess(
            args=["git", "status"], returncode=0, stdout="", stderr=""
        )

        with self.assertRaises(SystemExit) as exc:
            finalize_phase_delivery(repo="fedevela/particle-life-3d", issue=21, phase="5")

        self.assertIn("without repository changes", str(exc.exception))

    @patch("trigger_workflow.runner_utils.prepare_phase_execution_context")
    @patch("trigger_workflow.runner_utils.subprocess.run")
    def test_finalize_phase_delivery_fails_when_issue_title_missing_and_fallbacks_disabled(
        self,
        subprocess_run_mock,
        prepare_phase_execution_context_mock,
    ) -> None:
        target_path = Path("/tmp/particle-life-3d")
        prepare_phase_execution_context_mock.return_value = RunnerTargetContext(
            local_path=target_path,
            branch="issue/21",
        )
        subprocess_run_mock.side_effect = [
            subprocess.CompletedProcess(args=["git", "fetch", "origin"], returncode=0, stdout="", stderr=""),
            subprocess.CompletedProcess(args=["git", "rev-parse", "--verify", "origin/main"], returncode=0, stdout="def456\n", stderr=""),
            subprocess.CompletedProcess(args=["git", "merge", "origin/main"], returncode=0, stdout="Already up to date.\n", stderr=""),
            subprocess.CompletedProcess(args=["git", "status"], returncode=0, stdout=" M src/app.ts\n", stderr=""),
            subprocess.CompletedProcess(args=["git", "add"], returncode=0, stdout="", stderr=""),
        ]

        with self.assertRaises(SystemExit) as exc:
            finalize_phase_delivery(
                repo="fedevela/particle-life-3d",
                issue=21,
                phase="7",
                issue_title="   ",
            )

        self.assertIn("Fallback commit/PR titles are disabled by policy", str(exc.exception))

    @patch("trigger_workflow.openhands_runner.prepare_phase_execution_context")
    @patch("trigger_workflow.openhands_runner._run_openhands_command")
    def test_run_openhands_never_resumes_existing_conversation_for_same_repo_and_issue(
        self,
        run_openhands_command_mock,
        prepare_openhands_run_context_mock,
    ) -> None:
        # Policy is stateless execution: every run starts a fresh conversation.
        target_path = Path("/tmp/particle-life-3d")
        prepare_openhands_run_context_mock.return_value = OpenHandsTargetContext(
            local_path=target_path,
            branch="issue/21",
        )
        run_openhands_command_mock.return_value = subprocess.CompletedProcess(
            args=["openhands"],
            returncode=0,
            stdout="",
            stderr="",
        )

        run_openhands("Test prompt", repo="fedevela/particle-life-3d", issue=21, phase="5")

        command = run_openhands_command_mock.call_args.args[0]
        self.assertNotIn("--resume", command)

    @patch("trigger_workflow.openhands_runner.prepare_phase_execution_context")
    @patch("trigger_workflow.openhands_runner._run_openhands_command")
    def test_run_openhands_does_not_resume_when_phase_scope_is_set(
        self,
        run_openhands_command_mock,
        prepare_openhands_run_context_mock,
    ) -> None:
        # Phase-scoped runs are also stateless under the global no-resume policy.
        target_path = Path("/tmp/particle-life-3d")
        prepare_openhands_run_context_mock.return_value = OpenHandsTargetContext(
            local_path=target_path,
            branch="main",
        )
        run_openhands_command_mock.return_value = subprocess.CompletedProcess(
            args=["openhands"],
            returncode=0,
            stdout="",
            stderr="",
        )

        run_openhands(
            "Test prompt",
            repo="fedevela/particle-life-3d",
            issue=21,
            phase="2B",
            session_scope="phase-2B",
        )

        command = run_openhands_command_mock.call_args.args[0]
        self.assertNotIn("--resume", command)

    @patch("trigger_workflow.openhands_runner.save_session_state")
    @patch("trigger_workflow.openhands_runner.prepare_phase_execution_context")
    @patch("trigger_workflow.openhands_runner._run_openhands_command")
    def test_run_openhands_does_not_persist_conversation_id_under_repo_issue_key(
        self,
        run_openhands_command_mock,
        prepare_openhands_run_context_mock,
        save_session_state_mock,
    ) -> None:
        target_path = Path("/tmp/particle-life-3d")
        prepare_openhands_run_context_mock.return_value = OpenHandsTargetContext(
            local_path=target_path,
            branch="main",
        )
        run_openhands_command_mock.return_value = subprocess.CompletedProcess(
            args=["openhands"],
            returncode=0,
            stdout="Conversation ID: conv-999\n",
            stderr="",
        )

        run_openhands("Test prompt", repo="fedevela/particle-life-3d", issue=21, phase="3")

        save_session_state_mock.assert_not_called()

    @patch("trigger_workflow.openhands_runner.save_session_state")
    @patch("trigger_workflow.openhands_runner.prepare_phase_execution_context")
    @patch("trigger_workflow.openhands_runner._run_openhands_command")
    def test_run_openhands_does_not_persist_conversation_id_under_phase_scoped_key(
        self,
        run_openhands_command_mock,
        prepare_openhands_run_context_mock,
        save_session_state_mock,
    ) -> None:
        target_path = Path("/tmp/particle-life-3d")
        prepare_openhands_run_context_mock.return_value = OpenHandsTargetContext(
            local_path=target_path,
            branch="main",
        )
        run_openhands_command_mock.return_value = subprocess.CompletedProcess(
            args=["openhands"],
            returncode=0,
            stdout="Conversation ID: conv-phase\n",
            stderr="",
        )

        run_openhands(
            "Test prompt",
            repo="fedevela/particle-life-3d",
            issue=21,
            phase="2B",
            session_scope="phase-2B",
        )

        save_session_state_mock.assert_not_called()

    @patch("trigger_workflow.openhands_runner.run_phase_tests")
    @patch("trigger_workflow.openhands_runner.run_openhands")
    def test_run_openhands_implementation_phase_validates_for_phase_6(
        self,
        run_openhands_mock,
        run_phase_tests_mock,
    ) -> None:
        run_openhands_mock.return_value = subprocess.CompletedProcess(
            args=["openhands"],
            returncode=0,
            stdout="ok",
            stderr="",
        )
        run_phase_tests_mock.return_value = subprocess.CompletedProcess(
            args=["npm", "run", "tests:e2e"],
            returncode=0,
            stdout="tests ok",
            stderr="",
        )
        run_phase_tests_mock.return_value = subprocess.CompletedProcess(
            args=["npm", "run", "test"],
            returncode=0,
            stdout="tests ok",
            stderr="",
        )

        run_openhands_implementation_phase(
            "Initial task",
            repo="fedevela/particle-life-3d",
            issue=21,
            phase="6",
        )

        run_openhands_mock.assert_called_once()
        run_phase_tests_mock.assert_called_once()

    @patch("trigger_workflow.openhands_runner.run_phase_tests")
    @patch("trigger_workflow.openhands_runner.run_openhands")
    def test_run_openhands_implementation_phase_stops_when_tests_pass(
        self,
        run_openhands_mock,
        run_phase_tests_mock,
    ) -> None:
        run_openhands_mock.return_value = subprocess.CompletedProcess(
            args=["openhands"],
            returncode=0,
            stdout="ok",
            stderr="",
        )
        run_phase_tests_mock.return_value = subprocess.CompletedProcess(
            args=["npm", "run", "test"],
            returncode=0,
            stdout="tests ok",
            stderr="",
        )

        run_openhands_implementation_phase(
            "Initial task",
            repo="fedevela/particle-life-3d",
            issue=21,
            phase="8",
        )

        run_openhands_mock.assert_called_once()
        run_phase_tests_mock.assert_called_once()

    @patch("trigger_workflow.openhands_runner.run_phase_tests")
    @patch("trigger_workflow.openhands_runner.run_openhands")
    def test_run_openhands_implementation_phase_retries_with_scoped_feedback_when_validation_fails_then_passes(
        self,
        run_openhands_mock,
        run_phase_tests_mock,
    ) -> None:
        run_openhands_mock.side_effect = [
            subprocess.CompletedProcess(args=["openhands"], returncode=0, stdout="first", stderr=""),
            subprocess.CompletedProcess(args=["openhands"], returncode=0, stdout="second", stderr=""),
        ]
        run_phase_tests_mock.side_effect = [
            subprocess.CompletedProcess(
                args=["npm", "run", "test"],
                returncode=1,
                stdout="FAIL: expected 1 got 0",
                stderr="stacktrace",
            ),
            subprocess.CompletedProcess(args=["npm", "run", "test"], returncode=0, stdout="ok", stderr=""),
        ]

        run_openhands_implementation_phase(
            "Initial task",
            repo="fedevela/particle-life-3d",
            issue=21,
            phase="8",
        )

        self.assertEqual(run_openhands_mock.call_count, 2)
        self.assertEqual(run_phase_tests_mock.call_count, 2)
        retry_task = run_openhands_mock.call_args_list[1].args[0]
        self.assertIn("retry attempt 1 of 3", retry_task)
        self.assertIn("Do not expand scope beyond fixing these validation failures.", retry_task)
        self.assertIn("FAIL: expected 1 got 0", retry_task)

    @patch("trigger_workflow.openhands_runner.run_phase_tests")
    @patch("trigger_workflow.openhands_runner.run_openhands")
    def test_run_openhands_implementation_phase_fails_after_three_retries(
        self,
        run_openhands_mock,
        run_phase_tests_mock,
    ) -> None:
        run_openhands_mock.side_effect = [
            subprocess.CompletedProcess(args=["openhands"], returncode=0, stdout="run1", stderr=""),
            subprocess.CompletedProcess(args=["openhands"], returncode=0, stdout="run2", stderr=""),
            subprocess.CompletedProcess(args=["openhands"], returncode=0, stdout="run3", stderr=""),
            subprocess.CompletedProcess(args=["openhands"], returncode=0, stdout="run4", stderr=""),
        ]
        run_phase_tests_mock.side_effect = [
            subprocess.CompletedProcess(args=["npm", "run", "test"], returncode=1, stdout="fail-1", stderr=""),
            subprocess.CompletedProcess(args=["npm", "run", "test"], returncode=1, stdout="fail-2", stderr=""),
            subprocess.CompletedProcess(args=["npm", "run", "test"], returncode=1, stdout="fail-3", stderr=""),
            subprocess.CompletedProcess(args=["npm", "run", "test"], returncode=1, stdout="fail-4", stderr=""),
        ]

        with self.assertRaises(SystemExit) as exc:
            run_openhands_implementation_phase(
                "Initial task",
                repo="fedevela/particle-life-3d",
                issue=21,
                phase="8",
            )

        self.assertIn("Validation command contract failed", str(exc.exception))
        self.assertEqual(run_openhands_mock.call_count, 4)
        self.assertEqual(run_phase_tests_mock.call_count, 4)

    @patch("trigger_workflow.openhands_runner.run_phase_tests")
    @patch("trigger_workflow.openhands_runner.run_openhands")
    def test_run_openhands_implementation_phase_validates_for_phase_5(
        self,
        run_openhands_mock,
        run_phase_tests_mock,
    ) -> None:
        run_openhands_mock.return_value = subprocess.CompletedProcess(
            args=["openhands"],
            returncode=0,
            stdout="ok",
            stderr="",
        )
        run_phase_tests_mock.return_value = subprocess.CompletedProcess(
            args=["npm", "run", "tests:e2e"],
            returncode=0,
            stdout="tests ok",
            stderr="",
        )

        run_openhands_implementation_phase(
            "Initial task",
            repo="fedevela/particle-life-3d",
            issue=21,
            phase="5",
        )

        run_openhands_mock.assert_called_once()
        run_phase_tests_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()

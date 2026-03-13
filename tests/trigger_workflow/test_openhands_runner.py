"""OpenHands runner tests for config parsing, checkout resolution, and session reuse.

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
    resolve_phase_execution_branch,
    load_session_state,
    prepare_phase_execution_context,
    resolve_openhands_model_connection,
    run_openhands,
)


class OpenHandsRunnerTests(unittest.TestCase):
    """Verify runner behavior at the config, git, and subprocess boundaries.

    The suite is designed to catch regressions that would be expensive to debug
    in live runs: invalid local config files, missing target checkouts,
    incorrect branch verification, or resuming the wrong OpenHands conversation.
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

    def test_branch_name_for_phase_errors_for_unknown_repo_config(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            resolve_phase_execution_branch("owner/unknown", "5", 12)

        self.assertIn("No local target repository config exists", str(exc.exception))

    @patch("trigger_workflow.openhands_runner.log_info")
    @patch("trigger_workflow.openhands_runner.current_branch", return_value="issue/21")
    @patch("trigger_workflow.openhands_runner.ensure_git_branch")
    @patch("trigger_workflow.openhands_runner.resolve_phase_execution_branch", return_value="issue/21")
    @patch("trigger_workflow.openhands_runner.resolve_target_repo_config")
    def test_prepare_openhands_run_context_logs_loaded_repo_and_verified_branch(
        self,
        resolve_target_repo_config_mock,
        branch_name_for_phase_mock,
        ensure_git_branch_mock,
        current_branch_mock,
        log_info_mock,
    ) -> None:
        # The mocked config object is intentionally minimal: this test is about
        # path verification and branch logging, not dataclass identity.
        del branch_name_for_phase_mock
        del ensure_git_branch_mock
        del current_branch_mock
        local_path = Path("/tmp/particle-life-3d")
        resolve_target_repo_config_mock.return_value = type(
            "Config",
            (),
            {"local_path": local_path, "main_branch": "main", "issue_branch_prefix": "issue/"},
        )()

        with patch.object(Path, "exists", autospec=True) as exists_mock:
            exists_mock.side_effect = lambda path_obj: str(path_obj) in {
                str(local_path),
                str(local_path / ".git"),
            }
            context = prepare_phase_execution_context("fedevela/particle-life-3d", "5", 21)

        self.assertEqual(context.local_path, local_path)
        self.assertEqual(context.branch, "issue/21")
        messages = [call.args[0] for call in log_info_mock.call_args_list]
        self.assertIn(f"Verified target repository path exists: {local_path}", messages)
        self.assertIn("Resolved target branch for phase 5: issue/21", messages)
        self.assertIn("Verified target repository branch loaded: issue/21", messages)

    @patch("trigger_workflow.openhands_runner.resolve_target_repo_config")
    def test_prepare_openhands_run_context_errors_when_target_repo_path_missing(
        self,
        resolve_target_repo_config_mock,
    ) -> None:
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

    @patch("trigger_workflow.openhands_runner.resolve_target_repo_config")
    def test_prepare_openhands_run_context_errors_when_git_directory_missing(
        self,
        resolve_target_repo_config_mock,
    ) -> None:
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

    @patch("trigger_workflow.openhands_runner.current_branch", side_effect=["main", "main"])
    @patch("trigger_workflow.openhands_runner.ensure_git_branch")
    @patch("trigger_workflow.openhands_runner.resolve_phase_execution_branch", return_value="issue/21")
    @patch("trigger_workflow.openhands_runner.resolve_target_repo_config")
    def test_prepare_openhands_run_context_errors_when_branch_verification_fails(
        self,
        resolve_target_repo_config_mock,
        branch_name_for_phase_mock,
        ensure_git_branch_mock,
        current_branch_mock,
    ) -> None:
        del branch_name_for_phase_mock
        del ensure_git_branch_mock
        del current_branch_mock
        local_path = Path("/tmp/particle-life-3d")
        resolve_target_repo_config_mock.return_value = type(
            "Config",
            (),
            {"local_path": local_path, "main_branch": "main", "issue_branch_prefix": "issue/"},
        )()

        with patch.object(Path, "exists", autospec=True) as exists_mock:
            exists_mock.side_effect = lambda path_obj: str(path_obj) in {
                str(local_path),
                str(local_path / ".git"),
            }
            with self.assertRaises(SystemExit) as exc:
                prepare_phase_execution_context("fedevela/particle-life-3d", "5", 21)

        self.assertIn("branch verification failed", str(exc.exception))

    @patch("trigger_workflow.openhands_runner.extract_conversation_id", return_value="")
    @patch("trigger_workflow.openhands_runner.prepare_phase_execution_context")
    @patch("trigger_workflow.openhands_runner.subprocess.run")
    def test_run_openhands_uses_target_repo_cwd(
        self,
        subprocess_run_mock,
        prepare_openhands_run_context_mock,
        extract_conversation_id_mock,
    ) -> None:
        # Running in the target repo checkout is the key behavioral guarantee
        # here; the subprocess payload itself is otherwise unimportant.
        del extract_conversation_id_mock
        target_path = Path("/tmp/particle-life-3d")
        prepare_openhands_run_context_mock.return_value = OpenHandsTargetContext(
            local_path=target_path,
            branch="main",
        )
        subprocess_run_mock.return_value = subprocess.CompletedProcess(
            args=["openhands"],
            returncode=0,
            stdout="Conversation ID: abc123\n",
            stderr="",
        )

        run_openhands("Test prompt", repo="fedevela/particle-life-3d", issue=21, phase="3")

        subprocess_run_mock.assert_called_once()
        self.assertEqual(subprocess_run_mock.call_args.kwargs["cwd"], target_path)

    @patch("trigger_workflow.openhands_runner.extract_conversation_id", return_value="")
    @patch(
        "trigger_workflow.openhands_runner.load_session_state",
        return_value={"fedevela/particle-life-3d#21": "conv-123"},
    )
    @patch("trigger_workflow.openhands_runner.prepare_phase_execution_context")
    @patch("trigger_workflow.openhands_runner.subprocess.run")
    def test_run_openhands_resumes_existing_conversation_for_same_repo_and_issue(
        self,
        subprocess_run_mock,
        prepare_openhands_run_context_mock,
        load_session_state_mock,
        extract_conversation_id_mock,
    ) -> None:
        # Shared implementation phases should reuse the persisted per-issue
        # conversation unless an explicit phase scope isolates the run.
        del load_session_state_mock
        del extract_conversation_id_mock
        target_path = Path("/tmp/particle-life-3d")
        prepare_openhands_run_context_mock.return_value = OpenHandsTargetContext(
            local_path=target_path,
            branch="issue/21",
        )
        subprocess_run_mock.return_value = subprocess.CompletedProcess(
            args=["openhands"],
            returncode=0,
            stdout="",
            stderr="",
        )

        run_openhands("Test prompt", repo="fedevela/particle-life-3d", issue=21, phase="5")

        command = subprocess_run_mock.call_args.args[0]
        self.assertIn("--resume", command)
        self.assertIn("conv-123", command)

    @patch("trigger_workflow.openhands_runner.extract_conversation_id", return_value="")
    @patch(
        "trigger_workflow.openhands_runner.load_session_state",
        return_value={"fedevela/particle-life-3d#21": "shared-conv"},
    )
    @patch("trigger_workflow.openhands_runner.prepare_phase_execution_context")
    @patch("trigger_workflow.openhands_runner.subprocess.run")
    def test_run_openhands_does_not_resume_shared_issue_session_when_phase_scope_is_set(
        self,
        subprocess_run_mock,
        prepare_openhands_run_context_mock,
        load_session_state_mock,
        extract_conversation_id_mock,
    ) -> None:
        # Strictly isolated phases should ignore the shared issue conversation
        # even if one already exists in session state.
        del load_session_state_mock
        del extract_conversation_id_mock
        target_path = Path("/tmp/particle-life-3d")
        prepare_openhands_run_context_mock.return_value = OpenHandsTargetContext(
            local_path=target_path,
            branch="main",
        )
        subprocess_run_mock.return_value = subprocess.CompletedProcess(
            args=["openhands"],
            returncode=0,
            stdout="",
            stderr="",
        )

        run_openhands(
            "Test prompt",
            repo="fedevela/particle-life-3d",
            issue=21,
            phase="2b",
            session_scope="phase-2b",
        )

        command = subprocess_run_mock.call_args.args[0]
        self.assertNotIn("--resume", command)

    @patch("trigger_workflow.openhands_runner.save_session_state")
    @patch("trigger_workflow.openhands_runner.prepare_phase_execution_context")
    @patch("trigger_workflow.openhands_runner.subprocess.run")
    def test_run_openhands_persists_new_conversation_id_under_repo_issue_key(
        self,
        subprocess_run_mock,
        prepare_openhands_run_context_mock,
        save_session_state_mock,
    ) -> None:
        target_path = Path("/tmp/particle-life-3d")
        prepare_openhands_run_context_mock.return_value = OpenHandsTargetContext(
            local_path=target_path,
            branch="main",
        )
        subprocess_run_mock.return_value = subprocess.CompletedProcess(
            args=["openhands"],
            returncode=0,
            stdout="Conversation ID: conv-999\n",
            stderr="",
        )

        run_openhands("Test prompt", repo="fedevela/particle-life-3d", issue=21, phase="3")

        save_session_state_mock.assert_called_once()
        saved_state = save_session_state_mock.call_args.args[0]
        self.assertEqual(saved_state["fedevela/particle-life-3d#21"], "conv-999")

    @patch("trigger_workflow.openhands_runner.save_session_state")
    @patch("trigger_workflow.openhands_runner.prepare_phase_execution_context")
    @patch("trigger_workflow.openhands_runner.subprocess.run")
    def test_run_openhands_persists_new_conversation_id_under_phase_scoped_key(
        self,
        subprocess_run_mock,
        prepare_openhands_run_context_mock,
        save_session_state_mock,
    ) -> None:
        target_path = Path("/tmp/particle-life-3d")
        prepare_openhands_run_context_mock.return_value = OpenHandsTargetContext(
            local_path=target_path,
            branch="main",
        )
        subprocess_run_mock.return_value = subprocess.CompletedProcess(
            args=["openhands"],
            returncode=0,
            stdout="Conversation ID: conv-phase\n",
            stderr="",
        )

        run_openhands(
            "Test prompt",
            repo="fedevela/particle-life-3d",
            issue=21,
            phase="2b",
            session_scope="phase-2b",
        )

        save_session_state_mock.assert_called_once()
        saved_state = save_session_state_mock.call_args.args[0]
        self.assertEqual(saved_state["fedevela/particle-life-3d#21:phase-2b"], "conv-phase")


if __name__ == "__main__":
    unittest.main()

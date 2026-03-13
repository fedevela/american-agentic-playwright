from __future__ import annotations

import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch

from trigger_workflow.github_ops import create_child_issues
from trigger_workflow.openhands_runner import (
    OpenHandsRunContext,
    branch_name_for_phase,
    prepare_openhands_run_context,
    run_openhands,
)
from trigger_workflow.prompts import (
    build_phase_input_context,
    build_phase_2_story_requirements,
    determine_phase_from_label,
    read_legacy_microagent,
    read_microagent_for_label,
)
from trigger_workflow.router import trigger_agent


class PhaseMappingTests(unittest.TestCase):
    def test_determine_phase_from_label_uses_canonical_string_ids(self) -> None:
        self.assertEqual(determine_phase_from_label("phase:keter"), "1")
        self.assertEqual(determine_phase_from_label("phase:chokhmah"), "2a")
        self.assertEqual(determine_phase_from_label("phase:binah"), "2b")
        self.assertEqual(determine_phase_from_label("phase:chesed"), "2c")
        self.assertEqual(determine_phase_from_label("phase:gevurah"), "3")
        self.assertEqual(determine_phase_from_label("phase:tiferet"), "4")
        self.assertEqual(determine_phase_from_label("phase:malkhut"), "9")

    def test_branch_name_for_phase_uses_main_before_implementation_and_issue_branch_after(self) -> None:
        self.assertEqual(branch_name_for_phase("fedevela/particle-life-3d", "2b", 12), "main")
        self.assertEqual(branch_name_for_phase("fedevela/particle-life-3d", "4", 12), "main")
        self.assertEqual(branch_name_for_phase("fedevela/particle-life-3d", "5", 12), "issue/12")
        self.assertEqual(branch_name_for_phase("fedevela/particle-life-3d", "9", 12), "issue/12")


class PromptCompositionTests(unittest.TestCase):
    def test_phase_2_story_requirements_enforce_e2e_observable_outcomes(self) -> None:
        requirements = build_phase_2_story_requirements()
        joined = "\n".join(requirements)
        self.assertIn("observable, automatable, and verifiable through end-to-end tests", joined)
        self.assertIn("Write `then` clauses in measurable terms", joined)
        self.assertIn("Do not rely on subjective human judgments", joined)

    def test_read_microagent_for_label_composes_base_persona_phase_persona_and_microagent(self) -> None:
        content = read_microagent_for_label("phase:binah", "2b")
        self.assertIsNotNone(content)
        assert content is not None
        self.assertIn("The user is your partner.", content)
        self.assertIn("expanded through Binah", content)
        self.assertIn("functional embodiment of Daneel-through-Binah", content)

    def test_build_phase_input_context_uses_keter_only_for_phase_2_variants(self) -> None:
        issue_data = {
            "title": "Example",
            "body": "Original issue body should not be used",
            "comments": [
                {
                    "body": "\n".join(
                        [
                            "<!-- phase:1:start label=phase:keter name=Keter -->",
                            "### Phase 1: Keter",
                            "",
                            "Clarified requirement from Keter.",
                            "",
                            "<!-- phase:1:end label=phase:keter name=Keter -->",
                        ]
                    )
                }
            ],
        }
        context = build_phase_input_context("phase:binah", 12, "owner/repo", "2b", issue_data)
        self.assertIn("Clarified requirement from Keter.", context)
        self.assertNotIn("Original issue body should not be used", context)

    def test_build_phase_input_context_errors_when_phase_2_lacks_keter_comment(self) -> None:
        issue_data = {
            "title": "Example",
            "body": "Original body",
            "comments": [],
        }

        with self.assertRaises(SystemExit) as exc:
            build_phase_input_context("phase:binah", 12, "owner/repo", "2b", issue_data)

        self.assertIn("Phase 2B requires a Phase 1 clarification comment", str(exc.exception))

    @patch("trigger_workflow.prompts.BASE_PERSONA_FILE", "missing-daneel.md")
    def test_read_microagent_for_label_errors_when_base_persona_missing(self) -> None:
        content = read_microagent_for_label("phase:binah", "2b")
        self.assertIsNone(content)

    @patch.dict("trigger_workflow.prompts.PERSONA_FILE_MAP", {"2b": "missing-phase-persona.md"}, clear=False)
    def test_read_microagent_for_label_errors_when_phase_persona_missing(self) -> None:
        content = read_microagent_for_label("phase:binah", "2b")
        self.assertIsNone(content)

    @patch.dict("trigger_workflow.prompts.LEGACY_MICROAGENT_FILE_MAP", {"2b": "missing-functional-agent.md"}, clear=False)
    def test_read_legacy_microagent_errors_when_mapped_file_missing(self) -> None:
        content = read_legacy_microagent("phase:binah", "2b")
        self.assertIsNone(content)


class ChildIssueCreationTests(unittest.TestCase):
    @patch("trigger_workflow.github_ops.add_blocked_by_dependency")
    @patch("trigger_workflow.github_ops.add_sub_issue_relationship")
    @patch("trigger_workflow.github_ops.create_issue_via_api")
    def test_create_child_issues_creates_in_order_and_links_predecessors(
        self,
        create_issue_via_api_mock,
        add_sub_issue_relationship_mock,
        add_blocked_by_dependency_mock,
    ) -> None:
        create_issue_via_api_mock.side_effect = [
            {"number": 101, "id": 1001, "html_url": "https://example.test/101"},
            {"number": 102, "id": 1002, "html_url": "https://example.test/102"},
            {"number": 103, "id": 1003, "html_url": "https://example.test/103"},
        ]

        created = create_child_issues(
            "owner/repo",
            77,
            [
                {"title": "First", "body": "Body one"},
                {"title": "Second", "body": "Body two"},
                {"title": "Third", "body": "Body three"},
            ],
        )

        self.assertEqual([item["number"] for item in created], [101, 102, 103])
        self.assertEqual(create_issue_via_api_mock.call_count, 3)
        first_body = create_issue_via_api_mock.call_args_list[0].args[2]
        self.assertIn("Automatically created by Phase 4/Tiferet from parent issue #77.", first_body)
        self.assertIn("Parent issue: #77", first_body)

        add_sub_issue_relationship_mock.assert_any_call("owner/repo", 77, 1001)
        add_sub_issue_relationship_mock.assert_any_call("owner/repo", 77, 1002)
        add_sub_issue_relationship_mock.assert_any_call("owner/repo", 77, 1003)
        self.assertEqual(add_sub_issue_relationship_mock.call_count, 3)

        add_blocked_by_dependency_mock.assert_any_call("owner/repo", 102, 1001)
        add_blocked_by_dependency_mock.assert_any_call("owner/repo", 103, 1002)
        self.assertEqual(add_blocked_by_dependency_mock.call_count, 2)


class RouterExecutionTests(unittest.TestCase):
    @patch("trigger_workflow.router._execute_agent_phase")
    @patch("trigger_workflow.router._execute_specification_phase")
    @patch("trigger_workflow.router._execute_discussion_phase")
    @patch("trigger_workflow.router.fetch_issue_data")
    @patch("trigger_workflow.router.read_microagent_for_label")
    @patch("trigger_workflow.router.ensure_phase_labels")
    def test_trigger_agent_routes_chesed_to_discussion_phase(
        self,
        ensure_phase_labels_mock,
        read_microagent_for_label_mock,
        fetch_issue_data_mock,
        execute_discussion_mock,
        execute_specification_mock,
        execute_agent_mock,
    ) -> None:
        del ensure_phase_labels_mock
        read_microagent_for_label_mock.return_value = "prompt"
        fetch_issue_data_mock.return_value = {
            "title": "Issue",
            "labels": [{"name": "phase:chesed"}],
            "comments": [],
        }

        trigger_agent(label="phase:chesed", issue=55, repo="owner/repo")

        execute_discussion_mock.assert_called_once()
        execute_specification_mock.assert_not_called()
        execute_agent_mock.assert_not_called()

    @patch("trigger_workflow.router.log_error")
    @patch("trigger_workflow.router.fetch_issue_data")
    @patch("trigger_workflow.router.read_microagent_for_label")
    @patch("trigger_workflow.router.ensure_phase_labels")
    def test_trigger_agent_errors_when_issue_lacks_requested_label(
        self,
        ensure_phase_labels_mock,
        read_microagent_for_label_mock,
        fetch_issue_data_mock,
        log_error_mock,
    ) -> None:
        del ensure_phase_labels_mock
        read_microagent_for_label_mock.return_value = "prompt"
        fetch_issue_data_mock.return_value = {
            "title": "Issue",
            "labels": [{"name": "phase:binah"}],
            "comments": [],
        }

        with self.assertRaises(SystemExit) as exc:
            trigger_agent(label="phase:chesed", issue=55, repo="owner/repo")

        self.assertEqual(exc.exception.code, 1)
        log_error_mock.assert_called_once()
        self.assertIn("is not labeled 'phase:chesed'", log_error_mock.call_args.args[0])


class OpenHandsRunnerTests(unittest.TestCase):
    def test_branch_name_for_phase_errors_for_unknown_repo_config(self) -> None:
        with self.assertRaises(SystemExit) as exc:
            branch_name_for_phase("owner/unknown", "5", 12)

        self.assertIn("No local target repository config exists", str(exc.exception))

    @patch("trigger_workflow.openhands_runner.log_info")
    @patch("trigger_workflow.openhands_runner.current_branch", return_value="issue/21")
    @patch("trigger_workflow.openhands_runner.ensure_git_branch")
    @patch("trigger_workflow.openhands_runner.branch_name_for_phase", return_value="issue/21")
    @patch("trigger_workflow.openhands_runner.resolve_target_repo_config")
    def test_prepare_openhands_run_context_logs_loaded_repo_and_verified_branch(
        self,
        resolve_target_repo_config_mock,
        branch_name_for_phase_mock,
        ensure_git_branch_mock,
        current_branch_mock,
        log_info_mock,
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
            context = prepare_openhands_run_context("fedevela/particle-life-3d", "5", 21)

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
                prepare_openhands_run_context("fedevela/particle-life-3d", "5", 21)

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
                prepare_openhands_run_context("fedevela/particle-life-3d", "5", 21)

        self.assertIn("is not a git checkout", str(exc.exception))

    @patch("trigger_workflow.openhands_runner.current_branch", side_effect=["main", "main"])
    @patch("trigger_workflow.openhands_runner.ensure_git_branch")
    @patch("trigger_workflow.openhands_runner.branch_name_for_phase", return_value="issue/21")
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
                prepare_openhands_run_context("fedevela/particle-life-3d", "5", 21)

        self.assertIn("branch verification failed", str(exc.exception))

    @patch("trigger_workflow.openhands_runner.extract_conversation_id", return_value="")
    @patch("trigger_workflow.openhands_runner.prepare_openhands_run_context")
    @patch("trigger_workflow.openhands_runner.subprocess.run")
    def test_run_openhands_uses_target_repo_cwd(
        self,
        subprocess_run_mock,
        prepare_openhands_run_context_mock,
        extract_conversation_id_mock,
    ) -> None:
        del extract_conversation_id_mock
        target_path = Path("/tmp/particle-life-3d")
        prepare_openhands_run_context_mock.return_value = OpenHandsRunContext(
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
    @patch("trigger_workflow.openhands_runner.load_session_state", return_value={"fedevela/particle-life-3d#21": "conv-123"})
    @patch("trigger_workflow.openhands_runner.prepare_openhands_run_context")
    @patch("trigger_workflow.openhands_runner.subprocess.run")
    def test_run_openhands_resumes_existing_conversation_for_same_repo_and_issue(
        self,
        subprocess_run_mock,
        prepare_openhands_run_context_mock,
        load_session_state_mock,
        extract_conversation_id_mock,
    ) -> None:
        del load_session_state_mock
        del extract_conversation_id_mock
        target_path = Path("/tmp/particle-life-3d")
        prepare_openhands_run_context_mock.return_value = OpenHandsRunContext(
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

    @patch("trigger_workflow.openhands_runner.save_session_state")
    @patch("trigger_workflow.openhands_runner.prepare_openhands_run_context")
    @patch("trigger_workflow.openhands_runner.subprocess.run")
    def test_run_openhands_persists_new_conversation_id_under_repo_issue_key(
        self,
        subprocess_run_mock,
        prepare_openhands_run_context_mock,
        save_session_state_mock,
    ) -> None:
        target_path = Path("/tmp/particle-life-3d")
        prepare_openhands_run_context_mock.return_value = OpenHandsRunContext(
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


if __name__ == "__main__":
    unittest.main()

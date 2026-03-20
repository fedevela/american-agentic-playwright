"""Tests for the CLI entry point."""

from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock
import sys

from trigger_workflow.cli import run_trigger_cli


class CliTests(unittest.TestCase):
    """Test CLI parsing and execution flow."""

    @patch("argparse.ArgumentParser.parse_args")
    @patch("trigger_workflow.cli.route_labeled_signal_with_mode")
    def test_run_trigger_cli_routes_signal(self, route_mock, parse_mock) -> None:
        args_mock = MagicMock()
        args_mock.label = "phase:keter"
        args_mock.phase = None
        args_mock.issue = 123
        args_mock.repo = "owner/repo"
        args_mock.manual = False
        args_mock.prompt_only = False
        parse_mock.return_value = args_mock
        
        run_trigger_cli()
        
        route_mock.assert_called_once_with("phase:keter", 123, "owner/repo", manual=False)

    @patch("argparse.ArgumentParser.parse_args")
    @patch("trigger_workflow.cli.route_labeled_signal_with_mode")
    def test_run_trigger_cli_resolves_phase_to_label(self, route_mock, parse_mock) -> None:
        args_mock = MagicMock()
        args_mock.label = None
        args_mock.phase = "1"
        args_mock.issue = 123
        args_mock.repo = "owner/repo"
        args_mock.manual = False
        args_mock.prompt_only = False
        parse_mock.return_value = args_mock
        
        run_trigger_cli()
        
        route_mock.assert_called_once_with("phase:keter", 123, "owner/repo", manual=False)

    @patch("argparse.ArgumentParser.parse_args")
    def test_run_trigger_cli_fails_on_conflicting_label_and_phase(self, parse_mock) -> None:
        args_mock = MagicMock()
        args_mock.label = "phase:chokhmah"
        args_mock.phase = "1"
        args_mock.issue = 123
        args_mock.repo = "owner/repo"
        args_mock.manual = False
        args_mock.prompt_only = False
        parse_mock.return_value = args_mock
        
        with self.assertRaises(SystemExit) as exc:
            run_trigger_cli()
        self.assertIn("Conflicting inputs", str(exc.exception))

    @patch("argparse.ArgumentParser.parse_args")
    @patch("trigger_workflow.cli.resolve_phase_signal")
    @patch("trigger_workflow.cli.build_phase_execution_prompt")
    @patch("trigger_workflow.cli.render_prompt_only_output")
    @patch("sys.stdout")
    @patch("sys.stderr")
    def test_run_trigger_cli_prompt_only_mode(
        self, stderr_mock, stdout_mock, render_mock, build_mock, resolve_mock, parse_mock
    ) -> None:
        args_mock = MagicMock()
        args_mock.label = "phase:keter"
        args_mock.phase = None
        args_mock.issue = 123
        args_mock.repo = "owner/repo"
        args_mock.manual = False
        args_mock.prompt_only = True
        parse_mock.return_value = args_mock
        
        signal_mock = MagicMock()
        signal_mock.phase = "1"
        resolve_mock.return_value = signal_mock
        build_mock.return_value = ("PROMPT", "SCOPE")
        render_mock.return_value = "RENDERED PROMPT"
        
        run_trigger_cli()
        
        resolve_mock.assert_called_once_with(
            label="phase:keter", issue=123, repo="owner/repo", manual=True, include_base_persona=True
        )
        build_mock.assert_called_once()
        render_mock.assert_called_once_with(signal_mock, "PROMPT")

    @patch("argparse.ArgumentParser.parse_args")
    @patch("trigger_workflow.cli.resolve_phase_signal")
    @patch("sys.stderr")
    def test_run_trigger_cli_prompt_only_mode_preserves_logs_on_error(
        self, stderr_mock, resolve_mock, parse_mock
    ) -> None:
        args_mock = MagicMock()
        args_mock.label = "phase:keter"
        args_mock.phase = None
        args_mock.issue = 123
        args_mock.repo = "owner/repo"
        args_mock.manual = False
        args_mock.prompt_only = True
        parse_mock.return_value = args_mock
        
        resolve_mock.side_effect = SystemExit("Resolution failed")
        
        with self.assertRaises(SystemExit):
            run_trigger_cli()
            
        # Error should be printed to stderr
        self.assertTrue(stderr_mock.write.called)


if __name__ == "__main__":
    unittest.main()

"""Availability checks must run before subprocesses or GitHub mutations."""
import subprocess
import sys
from unittest.mock import patch

import pytest

from trigger_workflow_creative_writer import config, core, execution


@pytest.mark.parametrize("provider", ["gemini", "openhands", "unknown"])
@pytest.mark.parametrize("phase", ["1", "2A", "2B", "2C", "3", "4", "5", "6", "7", "8", "9", "10"])
def test_disabled_provider_rejected_before_resolution(provider, phase):
    with patch.object(config, "RUNNER_TYPE", provider), patch.object(core, "ensure_phase_labels", side_effect=AssertionError("GitHub mutation")):
        with pytest.raises(SystemExit, match="disabled.*unimplemented"):
            core.run_labeled_issue_phase_with_mode(core.label_for_phase_id(phase), 42, "owner/story")


@pytest.mark.parametrize("provider", ["gemini", "openhands"])
@pytest.mark.parametrize("entry", ["run_comment_phase", "run_json_phase", "run_implementation_phase", "finalize_delivery"])
def test_direct_dispatch_rejects_disabled_providers(provider, entry):
    with patch.object(config, "RUNNER_TYPE", provider):
        kwargs = dict(repo="owner/story", issue=42, phase="7", issue_data={})
        with pytest.raises(SystemExit, match="Use --runner codex"):
            if entry == "finalize_delivery":
                getattr(execution, entry)(issue_title="Story", **kwargs)
            else:
                getattr(execution, entry)("prompt", session_scope="", **kwargs)


@pytest.mark.parametrize("provider", ["gemini", "openhands"])
def test_cli_disabled_even_for_preview(provider):
    result = subprocess.run([sys.executable, "trigger.py", "--mode", "creative-writer",
                             "--runner", provider, "--phase", "9", "--issue", "42", "--manual"],
                            text=True, capture_output=True)
    assert result.returncode != 0
    assert "disabled" in result.stderr and "unimplemented" in result.stderr
    assert "Synchronizing" not in result.stdout


def test_manual_malkhut_describes_sessions_and_writing_gates_without_launch(capsys):
    from trigger_workflow_creative_writer.models import PhaseExecutionRequest
    request = PhaseExecutionRequest("phase:malkhut", 42, "owner/story", "Director", "9", {"title": "Story", "body": "", "comments": []})
    core.preview_phase_execution_plan(request)
    output = capsys.readouterr().out
    assert "native" in output and "performance" in output
    assert "typecheck -> build" not in output


def test_native_session_policy_describes_fresh_prep_and_separate_performance_sessions():
    assert "fresh" in core.describe_phase_conversation_policy("7", "")
    assert "director" in core.describe_phase_conversation_policy("9", "")
    assert "OpenHands" not in core.describe_phase_conversation_policy("9", "")

from typing import Any

from . import config
from .gemini_runner import (
    finalize_phase_delivery as gemini_finalize_delivery,
    run_gemini_comment_phase,
    run_gemini_implementation_phase,
    run_gemini_json_phase,
)
from .openhands_runner import (
    finalize_phase_delivery as openhands_finalize_delivery,
    run_openhands_comment_phase,
    run_openhands_implementation_phase,
    run_openhands_json_phase,
)


def run_comment_phase(prompt: str, repo: str, issue: int, phase: str, session_scope: str, issue_data: dict[str, Any] | None = None) -> str:
    if config.RUNNER_TYPE == "gemini":
        return run_gemini_comment_phase(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope, issue_data=issue_data)
    return run_openhands_comment_phase(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope, issue_data=issue_data)


def run_json_phase(prompt: str, repo: str, issue: int, phase: str, session_scope: str, issue_data: dict[str, Any] | None = None) -> dict[str, Any]:
    if config.RUNNER_TYPE == "gemini":
        return run_gemini_json_phase(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope, issue_data=issue_data)
    return run_openhands_json_phase(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope, issue_data=issue_data)


def run_implementation_phase(prompt: str, repo: str, issue: int, phase: str, session_scope: str, issue_data: dict[str, Any] | None = None) -> None:
    if config.RUNNER_TYPE == "gemini":
        run_gemini_implementation_phase(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope, issue_data=issue_data)
    else:
        run_openhands_implementation_phase(prompt, repo=repo, issue=issue, phase=phase, session_scope=session_scope, issue_data=issue_data)


def finalize_delivery(repo: str, issue: int, phase: str, issue_title: str, issue_data: dict[str, Any] | None = None) -> str:
    if config.RUNNER_TYPE == "gemini":
        return gemini_finalize_delivery(repo=repo, issue=issue, phase=phase, issue_title=issue_title, issue_data=issue_data)
    return openhands_finalize_delivery(repo=repo, issue=issue, phase=phase, issue_title=issue_title, issue_data=issue_data)

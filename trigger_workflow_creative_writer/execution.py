"""Explicit Codex-only creative-writing dispatch; SDLC is independent."""
from . import config, codex_runner


def run_comment_phase(prompt, **kwargs):
    config.require_enabled_provider()
    return codex_runner.run_codex_comment_phase(prompt, **kwargs)


def run_json_phase(prompt, **kwargs):
    config.require_enabled_provider()
    return codex_runner.run_codex_json_phase(prompt, **kwargs)


def run_implementation_phase(prompt, **kwargs):
    config.require_enabled_provider()
    return codex_runner.run_codex_implementation_phase(prompt, **kwargs)


def finalize_delivery(**kwargs):
    config.require_enabled_provider()
    return codex_runner.finalize_phase_delivery(**kwargs)

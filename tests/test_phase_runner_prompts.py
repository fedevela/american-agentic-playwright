import importlib.util
import json
import sys
from pathlib import Path


def _load_phase_runner_module():
    path = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "phase_runner.py"
    spec = importlib.util.spec_from_file_location("phase_runner_prompts", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


phase_runner = _load_phase_runner_module()


def test_generate_prompt_payload_for_every_phase(monkeypatch) -> None:
    ctx = phase_runner.Context(
        repo="acme/repo",
        issue_number=7,
        owner="run-7",
        run_url="https://github.com/acme/repo/actions/runs/7",
    )
    monkeypatch.setattr(phase_runner, "_get_issue", lambda _: {"title": "T", "body": "B"})
    monkeypatch.setattr(phase_runner, "read_artifact", lambda *_: "artifact-content")

    payloads = [
        phase_runner.generate_prompt_payload(ctx, "queen"),
        phase_runner.generate_prompt_payload(ctx, "triad-persona", persona="advocate"),
        phase_runner.generate_prompt_payload(ctx, "triad-aggregate"),
        phase_runner.generate_prompt_payload(ctx, "arbiter"),
        phase_runner.generate_prompt_payload(ctx, "contract"),
        phase_runner.generate_prompt_payload(ctx, "spec"),
        phase_runner.generate_prompt_payload(ctx, "pseudo"),
        phase_runner.generate_prompt_payload(ctx, "arch"),
        phase_runner.generate_prompt_payload(ctx, "refine"),
        phase_runner.generate_prompt_payload(ctx, "completion"),
    ]

    artifact_names = [payload.artifact_name for payload in payloads]
    assert artifact_names == [
        "queen:structured",
        "triad:advocate",
        "triad:personas",
        "arbiter:stories",
        "contract:bdd",
        "spec:mapping",
        "pseudo:flows",
        "arch:plan",
        "refine:traceability",
        "completion:pr",
    ]
    assert all("openhands-swarm:artifact" in payload.prompt for payload in payloads)


def test_emit_prompt_prints_json_payload(monkeypatch, capsys) -> None:
    ctx = phase_runner.Context(
        repo="acme/repo",
        issue_number=8,
        owner="run-8",
        run_url="https://github.com/acme/repo/actions/runs/8",
    )
    payload = phase_runner.PromptPayload(
        phase="phase:queen",
        artifact_name="queen:structured",
        prompt="Prompt text",
    )
    monkeypatch.setattr(phase_runner, "generate_prompt_payload", lambda *_args, **_kwargs: payload)

    code = phase_runner.emit_prompt(ctx, "queen")
    captured = capsys.readouterr().out.strip()

    assert code == 0
    data = json.loads(captured)
    assert data["phase"] == "phase:queen"
    assert data["artifact_name"] == "queen:structured"
    assert data["prompt"] == "Prompt text"

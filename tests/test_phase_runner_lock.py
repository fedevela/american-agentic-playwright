import importlib.util
import sys
from pathlib import Path


def _load_phase_runner_module():
    path = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "phase_runner.py"
    spec = importlib.util.spec_from_file_location("phase_runner", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


phase_runner = _load_phase_runner_module()


def test_acquire_lock_takes_over_existing_owner_and_refreshes_lock_comment(monkeypatch) -> None:
    ctx = phase_runner.Context(
        repo="acme/repo",
        issue_number=42,
        owner="run-2",
        run_url="https://github.com/acme/repo/actions/runs/2",
    )
    existing_comment = {
        "id": 10,
        "body": (
            "<!-- openhands-swarm:lock -->\n"
            "## Lock\n"
            "- Owner: `run-1`\n"
            "- Run: https://github.com/acme/repo/actions/runs/1\n"
            "- State: held"
        ),
    }
    api_calls = []
    labels_added = []

    def fake_gh_api_json(method: str, endpoint: str, fields=None):
        api_calls.append((method, endpoint, fields))
        if method == "GET" and endpoint == "repos/acme/repo/issues/42/comments?per_page=100":
            return [existing_comment]
        if method == "PATCH" and endpoint == "repos/acme/repo/issues/comments/10":
            existing_comment["body"] = fields["body"]
            return {}
        raise AssertionError(f"Unexpected gh api call: {method} {endpoint}")

    def fake_add_labels(_, labels):
        labels_added.append(labels)

    monkeypatch.setattr(phase_runner, "_gh_api_json", fake_gh_api_json)
    monkeypatch.setattr(phase_runner, "add_labels", fake_add_labels)

    assert phase_runner.acquire_lock(ctx) is True

    assert labels_added == [["lock"]]
    assert "- Owner: `run-2`" in existing_comment["body"]
    assert "- State: held" in existing_comment["body"]
    assert any(call[0] == "PATCH" for call in api_calls)


def test_release_lock_releases_only_for_current_owner(monkeypatch) -> None:
    ctx = phase_runner.Context(
        repo="acme/repo",
        issue_number=42,
        owner="run-2",
        run_url="https://github.com/acme/repo/actions/runs/2",
    )
    removed_labels = []
    upserts = []

    monkeypatch.setattr(phase_runner, "_parse_lock_owner", lambda _: "run-2")
    monkeypatch.setattr(phase_runner, "remove_label", lambda _, label: removed_labels.append(label))
    monkeypatch.setattr(
        phase_runner,
        "_upsert_comment",
        lambda _, marker, body: upserts.append((marker, body)),
    )

    phase_runner.release_lock(ctx)

    assert removed_labels == ["lock"]
    assert upserts
    assert upserts[0][0] == "<!-- openhands-swarm:lock -->"
    assert "- State: released" in upserts[0][1]
    assert "- Owner: `run-2`" in upserts[0][1]


def test_release_lock_non_owner_keeps_lock_and_comment_unchanged(monkeypatch) -> None:
    ctx = phase_runner.Context(
        repo="acme/repo",
        issue_number=42,
        owner="run-2",
        run_url="https://github.com/acme/repo/actions/runs/2",
    )
    removed_labels = []
    upserts = []

    monkeypatch.setattr(phase_runner, "_parse_lock_owner", lambda _: "run-1")
    monkeypatch.setattr(phase_runner, "remove_label", lambda _, label: removed_labels.append(label))
    monkeypatch.setattr(
        phase_runner,
        "_upsert_comment",
        lambda _, marker, body: upserts.append((marker, body)),
    )

    phase_runner.release_lock(ctx)

    assert removed_labels == []
    assert upserts == []

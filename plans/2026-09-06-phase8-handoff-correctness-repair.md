# Phase 8 Handoff Correctness Repair

**Status:** Implemented and independently reviewed in the current working directory; no commits or live model calls.

**Goal:** Close reproducible handoff-validation gaps before phase 9 starts native sessions, and restore portable offline verification.

**Architecture:** Keep the existing phase 7 brief → phase 8 preserved materials → phase 9 roundtable architecture. Tighten its existing Python gates rather than introduce another orchestration layer.

**Tech Stack:** Python, pathlib, JSON, pytest.

**Spec:** The two September 6 director-roundtable and native-session plans; phase 8 must preserve the source skeleton and each dramatic moment must include its participants.

## Global constraints

- Preserve existing uncommitted work. Work here, as requested, without a worktree.
- Do not change SDLC runtime, enable other creative providers, or call paid/live models.
- Independent review and failing regression tests precede completion claims.
- Phase 8 remains an LLM-produced handoff with deterministic validation, not a prose-generation stage.

## Task 1 — Reproduce and repair handoff gates

Files: `trigger_workflow_creative_writer/scene_materials.py`, `tests/trigger_workflow_creative_writer/test_scene_materials.py`.

- [x] Add regressions showing that added skeleton whitespace is rejected, including when both phase-8 copies match one another.
- [x] Add regressions for non-integer JSON schema versions (`true`, `1.0`) and issue identifiers.
- [x] Add a two-moment brief regression: a character named in moment 1 cannot be supplied only in moment 2. Exercise both quotation styles in tag attributes.
- [x] Run `.venv/bin/python -m pytest tests/trigger_workflow_creative_writer/test_scene_materials.py -q` and confirm the new cases fail for the intended reasons.
- [x] Implement exact text comparison, strict integer checks, and moment-local participant validation. Preserve object-valued ACTION focus and the existing canonical marker spelling.

Implementation rules:

```python
if type(data["version"]) is not int or data["version"] != 1:
    raise ValueError("Unsupported performance_context version")
if skeleton != original:
    raise ValueError("Preserved skeleton differs from phase 6 source")
```

For each marker-delimited skeleton segment, extract `character` attributes and known-character ACTION `focus` attributes; compare that set with the corresponding brief moment's `characters`. Accept single and double quotes. Keep global participant validation for tags before the first marker.

- [x] Re-run the focused suite to green.

## Task 2 — Repair portable checkout fixtures

Files: both `tests/trigger_workflow/test_openhands_runner.py` and `tests/trigger_workflow_creative_writer/test_openhands_runner.py`.

- [x] Reproduce the four existing managed-checkout failures.
- [x] Replace the hardcoded developer-machine checkout prefix with the test repository's actual root; retain the independently specified managed suffix and branch assertions.

```python
managed_path = Path(__file__).resolve().parents[2] / ".openhands" / "repos" / "fedevela__particle-life-3d"
```

- [x] Run both runner test modules. Do not modify their production implementations.

## Task 3 — Correctness review and verification

- [x] Independently review the repaired handoff gates and their phase-9 consumption; fix confirmed important findings with regressions.
- [x] Run `.venv/bin/python -m pytest tests/ -q --tb=short`.
- [x] Run `.venv/bin/python -m compileall -q trigger_workflow_creative_writer` and whitespace checks scoped to repaired files.
- [x] Record results below. Native Codex acceptance remains explicitly unverified unless separately enabled by the partner.

## Results

- RED: seven new handoff cases failed because invalid inputs were accepted; four existing checkout tests failed on their hardcoded macOS path.
- GREEN: 78 focused handoff and runner tests passed.
- Correcting the paths exposed unstubbed Git fetch/merge in two success-path fixtures; those external operations are now stubbed. SDLC runtime is unchanged.
- Full offline suite: **334 passed, 1 skipped** (33.16 seconds).
- Independent reviewer: no critical or important findings; separately ran 75 scene-materials and roundtable tests successfully.
- Compilation and repaired-file whitespace checks passed.
- Preservation is exact decoded text, including surrounding whitespace; line-ending byte normalization is not a new byte-for-byte guarantee.
- Native Codex acceptance remains opt-in and unverified. No provider/session architecture redesign was required.
- Superpowers systematic debugging, test-first fixes, and independent review guided this pass. Optional additional tag-parser coverage can follow without blocking these repairs.

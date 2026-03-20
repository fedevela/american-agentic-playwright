from __future__ import annotations

from .orchestration import (
    route_labeled_signal,
    route_labeled_signal_with_mode,
)

# For backward compatibility
run_labeled_issue_phase = route_labeled_signal
run_labeled_issue_phase_with_mode = route_labeled_signal_with_mode

# For backward compatibility in tests and other modules
from .context import (
    SfiratPhaseSignal,
    resolve_phase_signal,
    conversation_scope_for_phase,
)
PhaseExecutionRequest = SfiratPhaseSignal
resolve_phase_execution_request = resolve_phase_signal

from .cli import label_for_phase_id
from .preview import render_prompt_only_output
from .execution import (
    execute_comment_phase_handoff,
    embody_implementation_contract,
    execute_phase_with_needs_human_tagging,
    manifest_specification_decomposition,
    run_comment_phase,
    run_json_phase,
    run_implementation_phase,
    formalize_delivery_handoff,
    build_phase_execution_prompt,
)
execute_implementation_phase_task = embody_implementation_contract
execute_tiferet_specification_phase = manifest_specification_decomposition
finalize_delivery = formalize_delivery_handoff

from .github_ops import (
    advance_issue_label,
    post_issue_comment,
    remove_issue_label,
    create_child_issues,
    fetch_issue_data,
    ensure_phase_labels,
    tag_issue_needs_human,
)
from .prompts import (
    read_microagent_for_label,
    build_phase_four_summary,
)
from .validation import validate_tiferet_specification_payload_structure
from .runner_utils import create_issue_branches_for_child_issues
from .preview import preview_phase_execution_plan

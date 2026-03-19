import sys
from pathlib import Path
from typing import List

from .logging_utils import log_error, log_info

REQUIRED_ARTIFACTS = [
    "Beca para el fortalecimiento de procesos.md",
    "condiciones.md",
    "table-of-contents.md"
]

def validate_required_artifacts(workspace_path: Path) -> None:
    """Validate that all required formal document artifacts exist in the workspace."""
    log_info(f"Validating required artifacts in workspace: {workspace_path}")
    
    missing_artifacts: List[str] = []
    
    for artifact in REQUIRED_ARTIFACTS:
        artifact_path = workspace_path / artifact
        if not artifact_path.exists():
            missing_artifacts.append(artifact)
                        
    if missing_artifacts:
        log_error("Artifact Validation Gate Failed! The following required artifacts are missing from the repository:")
        for artifact in missing_artifacts:
            log_error(f"  - {artifact}")
        log_error("These files form the binding constraints of the scholarship application and must be provided.")
        raise SystemExit(1)
        
    log_info("✓ All required formal document artifacts are present.")

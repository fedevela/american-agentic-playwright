import sys
from pathlib import Path
from typing import List

from .logging_utils import log_error, log_info

REQUIRED_ARTIFACTS = [
    "agents.md",
    "agents_artifacts/dramatic_arcs.md",
    "agents_artifacts/world_rules.md",
    "agents_artifacts/theme.md",
    "agents_artifacts/relationships.drawio",
]

REQUIRED_CHARACTER_ARTIFACTS = [
    "appearance.md",
    "personality.md",
    "interiorvoice.md",
    "motivations_and_fears.md",
    "secrets.md",
    "lexicon.md",
]

def validate_required_artifacts(workspace_path: Path) -> None:
    """Validate that all required creative writer artifacts exist in the workspace."""
    log_info(f"Validating required artifacts in workspace: {workspace_path}")
    
    missing_artifacts: List[str] = []
    
    # Check top-level and agents_artifacts/ files
    for artifact in REQUIRED_ARTIFACTS:
        artifact_path = workspace_path / artifact
        if not artifact_path.exists():
            missing_artifacts.append(artifact)
            
    # Check character artifacts
    characters_dir = workspace_path / "agents_artifacts" / "characters"
    if not characters_dir.exists() or not characters_dir.is_dir():
        missing_artifacts.append("agents_artifacts/characters/ (directory missing)")
    else:
        # Check that at least one character exists
        character_dirs = [d for d in characters_dir.iterdir() if d.is_dir()]
        if not character_dirs:
            missing_artifacts.append("agents_artifacts/characters/ (no character directories found)")
        else:
            # Check that each character has all required artifacts
            for char_dir in character_dirs:
                for char_artifact in REQUIRED_CHARACTER_ARTIFACTS:
                    artifact_path = char_dir / char_artifact
                    if not artifact_path.exists():
                        missing_artifacts.append(f"agents_artifacts/characters/{char_dir.name}/{char_artifact}")
                        
    if missing_artifacts:
        log_error("Artifact Validation Gate Failed! The following required artifacts are missing from the repository:")
        for artifact in missing_artifacts:
            log_error(f"  - {artifact}")
        log_error("These files form the binding constraints of the story and must be provided.")
        raise SystemExit(1)
        
    log_info("✓ All required creative writing artifacts are present.")

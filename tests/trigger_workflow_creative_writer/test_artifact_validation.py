import pytest
from pathlib import Path

from trigger_workflow_creative_writer.artifact_validation import (
    validate_required_artifacts,
    REQUIRED_ARTIFACTS,
    REQUIRED_CHARACTER_ARTIFACTS,
)

class TestArtifactValidation:
    @pytest.mark.parametrize("missing", ["wants.md", "fears.md"])
    def test_combined_legacy_sheet_cannot_replace_split_artifacts(self, tmp_path, missing):
        for artifact in REQUIRED_ARTIFACTS:
            path = tmp_path / artifact
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        character = tmp_path / "agents_artifacts/characters/test_char"
        character.mkdir(parents=True)
        for name in ("appearance.md", "personality.md", "interiorvoice.md", "wants.md",
                     "fears.md", "secrets.md", "lexicon.md", "motivations_and_fears.md"):
            if name != missing:
                (character / name).touch()
        with pytest.raises(SystemExit):
            validate_required_artifacts(tmp_path)

    def test_validation_passes_when_all_artifacts_exist(self, tmp_path: Path):
        # Setup valid structure
        for artifact in REQUIRED_ARTIFACTS:
            file_path = tmp_path / artifact
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.touch()
        
        char_dir = tmp_path / "agents_artifacts" / "characters" / "test_char"
        char_dir.mkdir(parents=True, exist_ok=True)
        for char_artifact in REQUIRED_CHARACTER_ARTIFACTS:
            (char_dir / char_artifact).touch()

        # Should not raise an exception
        validate_required_artifacts(tmp_path)

    def test_validation_fails_when_top_level_artifact_missing(self, tmp_path: Path):
        # Setup valid structure EXCEPT agents.md
        for artifact in REQUIRED_ARTIFACTS:
            if artifact == "agents.md":
                continue
            file_path = tmp_path / artifact
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.touch()
        
        char_dir = tmp_path / "agents_artifacts" / "characters" / "test_char"
        char_dir.mkdir(parents=True, exist_ok=True)
        for char_artifact in REQUIRED_CHARACTER_ARTIFACTS:
            (char_dir / char_artifact).touch()

        with pytest.raises(SystemExit):
            validate_required_artifacts(tmp_path)

    def test_validation_fails_when_characters_directory_missing(self, tmp_path: Path):
        for artifact in REQUIRED_ARTIFACTS:
            file_path = tmp_path / artifact
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.touch()
        
        # We explicitly DO NOT create agents_artifacts/characters/
        
        with pytest.raises(SystemExit):
            validate_required_artifacts(tmp_path)

    def test_validation_fails_when_no_characters_exist(self, tmp_path: Path):
        for artifact in REQUIRED_ARTIFACTS:
            file_path = tmp_path / artifact
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.touch()
        
        # Create characters dir but leave it empty
        char_dir = tmp_path / "agents_artifacts" / "characters"
        char_dir.mkdir(parents=True, exist_ok=True)

        with pytest.raises(SystemExit):
            validate_required_artifacts(tmp_path)

    def test_validation_fails_when_character_artifact_missing(self, tmp_path: Path):
        for artifact in REQUIRED_ARTIFACTS:
            file_path = tmp_path / artifact
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.touch()
        
        char_dir = tmp_path / "agents_artifacts" / "characters" / "test_char"
        char_dir.mkdir(parents=True, exist_ok=True)
        for char_artifact in REQUIRED_CHARACTER_ARTIFACTS:
            if char_artifact == "appearance.md":
                continue
            (char_dir / char_artifact).touch()

        with pytest.raises(SystemExit):
            validate_required_artifacts(tmp_path)

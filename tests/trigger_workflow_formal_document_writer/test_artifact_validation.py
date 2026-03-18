import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from trigger_workflow_formal_document_writer.artifact_validation import (
    REQUIRED_ARTIFACTS,
    validate_required_artifacts,
)

class ArtifactValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.workspace_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_file(self, rel_path: str) -> None:
        full_path = self.workspace_path / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text("dummy content")

    @patch("trigger_workflow_formal_document_writer.artifact_validation.log_info")
    def test_validation_passes_when_all_artifacts_exist(self, mock_log_info) -> None:
        for artifact in REQUIRED_ARTIFACTS:
            self._create_file(artifact)
            
        try:
            validate_required_artifacts(self.workspace_path)
        except SystemExit:
            self.fail("validate_required_artifacts raised SystemExit unexpectedly!")

    @patch("trigger_workflow_formal_document_writer.artifact_validation.log_error")
    @patch("trigger_workflow_formal_document_writer.artifact_validation.log_info")
    def test_validation_fails_when_artifact_missing(self, mock_log_info, mock_log_error) -> None:
        # Create all but the first required artifact
        for artifact in REQUIRED_ARTIFACTS[1:]:
            self._create_file(artifact)

        with self.assertRaises(SystemExit) as context:
            validate_required_artifacts(self.workspace_path)

        self.assertEqual(context.exception.code, 1)
        mock_log_error.assert_any_call(f"  - {REQUIRED_ARTIFACTS[0]}")

"""Offline tests for the Vosk model installer."""
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_vosk_model import install_model, model_is_ready


class VoskInstallerTests(unittest.TestCase):
    @staticmethod
    def _model(root: Path) -> None:
        for name in ("am", "conf", "graph", "ivector"):
            directory = root / name
            directory.mkdir(parents=True)
            (directory / "placeholder").write_text("test", encoding="utf-8")

    def test_model_readiness_requires_expected_directories(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            self.assertFalse(model_is_ready(root))
            self._model(root)
            self.assertTrue(model_is_ready(root))

    def test_install_extracts_single_wrapped_model(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "source" / "vosk-model-small-cn-test"
            source.mkdir(parents=True)
            self._model(source)
            archive = root / "fixture.zip"
            with zipfile.ZipFile(archive, "w") as package:
                for path in source.rglob("*"):
                    if path.is_file():
                        package.write(path, path.relative_to(root / "source"))
            target = root / "installed"

            def copy_fixture(_url, destination):
                destination.write_bytes(archive.read_bytes())

            with patch("prepare_vosk_model._download", side_effect=copy_fixture):
                self.assertEqual(install_model("https://example.invalid/model.zip", target), target.resolve())
            self.assertTrue(model_is_ready(target))

    def test_existing_complete_model_does_not_download(self):
        with tempfile.TemporaryDirectory() as temp_name:
            target = Path(temp_name) / "model"
            target.mkdir()
            self._model(target)
            with patch("prepare_vosk_model._download") as download:
                install_model(target=target)
            download.assert_not_called()


if __name__ == "__main__":
    unittest.main()

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ff_tkinter_app.settings import load_settings


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / "config.toml"

    def test_relative_paths_are_based_on_config_location(self):
        self.config.write_text('[api]\nbase_url="http://100.101.102.103:8000/"\n[files]\nsample_video="data/test.mov"\n', encoding="utf-8")
        settings = load_settings(self.config)
        self.assertEqual(settings.base_url, "http://100.101.102.103:8000")
        self.assertEqual(settings.sample_video, self.config.parent / "data" / "test.mov")

    def test_invalid_urls_indices_and_timeouts_are_rejected(self):
        for text in ['[api]\nbase_url="ftp://host"', '[api]\nbase_url="http://host/path"',
                     '[api]\nbase_url="http://host?pipeline=other"', '[camera]\nindex=-1',
                     '[api]\nresponse_timeout_seconds=0', '[api]\nconnect_timeout_seconds=inf']:
            with self.subTest(config=text):
                self.config.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_settings(self.config)

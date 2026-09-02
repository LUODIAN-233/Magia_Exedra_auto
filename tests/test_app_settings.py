import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.core import app_settings


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / 'src' / 'workers' / 'registry.py'
_registry_spec = importlib.util.spec_from_file_location('_worker_registry_test', REGISTRY_PATH)
_registry = importlib.util.module_from_spec(_registry_spec)
_registry_spec.loader.exec_module(_registry)
ParamSpec = _registry.ParamSpec


class WorkerSettingsTests(unittest.TestCase):
    def test_worker_params_are_saved_per_mode_without_overwriting_other_settings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / 'settings.json'
            with patch.object(app_settings, 'SETTINGS_PATH', str(settings_path)):
                self.assertTrue(app_settings.save_log_level('DEBUG'))
                self.assertTrue(app_settings.save_worker_params(
                    'link_raid', {
                        'level_choices': [12, 6],
                        'skip_nine_rooms': False,
                    },
                ))
                self.assertTrue(app_settings.save_worker_params(
                    'crystalis', {'lp_recover_times': 8},
                ))

                self.assertEqual(app_settings.load_log_level(), 'DEBUG')
                self.assertEqual(app_settings.load_worker_params('link_raid'), {
                    'level_choices': [12, 6],
                    'skip_nine_rooms': False,
                })
                self.assertEqual(
                    app_settings.load_worker_params('crystalis'),
                    {'lp_recover_times': 8},
                )

    def test_param_specs_normalize_stale_or_invalid_values(self):
        levels = ParamSpec(
            'level_choices', '等级', kind='ordered_multi_choice',
            choices=[4, 6, 7], default=[6],
        )
        flag = ParamSpec('skip', '跳过', kind='bool', default=True)
        count = ParamSpec('count', '次数', kind='int', min=0, max=8, default=3)

        self.assertEqual(levels.normalize([7, 7, 99, 4]), [7, 4])
        self.assertEqual(levels.normalize([]), [6])
        self.assertTrue(flag.normalize('false'))
        self.assertEqual(count.normalize(True), 3)

    def test_rejects_non_json_worker_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / 'settings.json'
            with patch.object(app_settings, 'SETTINGS_PATH', str(settings_path)):
                self.assertFalse(app_settings.save_worker_params(
                    'link_raid', {'invalid': object()},
                ))
                self.assertFalse(settings_path.exists())

    def test_notification_settings_normalize_and_persist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / 'settings.json'
            with patch.object(app_settings, 'SETTINGS_PATH', str(settings_path)):
                self.assertTrue(app_settings.save_notification_settings({
                    'enabled': True,
                    'send_key': 'SCT_local_only_key',
                    'channels': [8, 9, 18, 8, 999],
                    'events': {'timeout': False},
                }))
                loaded = app_settings.load_notification_settings()

        self.assertTrue(loaded['enabled'])
        self.assertEqual(loaded['send_key'], 'SCT_local_only_key')
        self.assertEqual(loaded['channels'], [8, 9])
        self.assertFalse(loaded['events']['timeout'])
        self.assertTrue(loaded['events']['worker_auto_ended'])
        self.assertTrue(loaded['events']['lp_exhausted'])


if __name__ == '__main__':
    unittest.main()

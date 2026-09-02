import contextlib
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from src.core import input_activity
from src.core.automation_position import capture_client_position, resolve_client_position
from src.core.input_activity import UserActivityGuard
from src.core.log_fold import ConsecutiveLogFolder
from src.packs import language_switcher


ROOT = Path(__file__).resolve().parents[1]


def _load_module(name, path, modules):
    with patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class AutomationPositionTests(unittest.TestCase):
    def test_window_move_rebases_client_position(self):
        record = capture_client_position((150, 260), (100, 200, 800, 600))
        self.assertEqual(record, (50, 60, 800, 600))
        self.assertEqual(resolve_client_position(record, (300, 400, 800, 600)), (350, 460))

    def test_client_resize_invalidates_position(self):
        record = capture_client_position((150, 260), (100, 200, 800, 600))
        self.assertIsNone(resolve_client_position(record, (100, 200, 1024, 768)))


class UserActivityTests(unittest.TestCase):
    def test_mouse_button_activity_is_detected(self):
        user32 = types.SimpleNamespace(
            GetAsyncKeyState=lambda key: 0x8000 if key == 2 else 0,
        )
        with patch.object(input_activity.ctypes, 'windll',
                          types.SimpleNamespace(user32=user32)):
            self.assertEqual(UserActivityGuard._mouse_active(), '鼠标右键')

    def test_recent_key_bit_does_not_trigger_activity(self):
        user32 = types.SimpleNamespace(GetAsyncKeyState=lambda _key: 0x0001)
        with patch.object(input_activity.ctypes, 'windll',
                          types.SimpleNamespace(user32=user32)):
            self.assertIsNone(UserActivityGuard._keyboard_active())
            self.assertIsNone(UserActivityGuard._mouse_active())

    def test_keyboard_activity_reports_key_name_and_code(self):
        user32 = types.SimpleNamespace(
            GetAsyncKeyState=lambda key: 0x8000 if key == ord('A') else 0,
        )
        with patch.object(input_activity.ctypes, 'windll',
                          types.SimpleNamespace(user32=user32)):
            self.assertEqual(
                UserActivityGuard._keyboard_active(),
                '键盘按键 A（VK 0x41）',
            )

    def test_mouse_path_is_accumulated(self):
        guard = UserActivityGuard(mouse_threshold=10)
        guard._last_position = (0, 0)
        self.assertFalse(guard._observe_mouse_movement((4, 0)))
        self.assertFalse(guard._observe_mouse_movement((8, 0)))
        self.assertIn('累计移动 12px', guard._observe_mouse_movement((12, 0)))

    def test_automation_movement_is_ignored(self):
        guard = UserActivityGuard(mouse_threshold=1)
        guard._last_position = (0, 0)
        guard._automation_depth = 1
        self.assertFalse(guard._observe_mouse_movement((100, 100)))


class LogFoldingTests(unittest.TestCase):
    def test_only_consecutive_identical_lines_are_folded(self):
        folder = ConsecutiveLogFolder()
        replace, first = folder.render('10:00:00', 'INFO', '运行', '等待战斗结束')
        self.assertFalse(replace)
        self.assertNotIn('连续重复', first)

        replace, second = folder.render('10:00:01', 'INFO', '运行', '等待战斗结束')
        self.assertTrue(replace)
        self.assertIn('连续重复 2 次', second)

        replace, _third = folder.render('10:00:02', 'INFO', '运行', '发现 retry')
        self.assertFalse(replace)
        replace, _fourth = folder.render('10:00:03', 'INFO', '运行', '等待战斗结束')
        self.assertFalse(replace)


class ClickConfirmationTests(unittest.TestCase):
    def test_every_sample_compares_full_group_and_reuses_expected_pack(self):
        paths_seen = []
        selections_seen = []
        points = iter(((100, 100), (101, 100), (102, 100)))

        behavior = types.ModuleType('src.click.click_behavior')

        def best_template_match(paths, search_region=None):
            paths_seen.append(tuple(str(path) for path in paths))
            return next(points), 0.95, str(paths[0])

        behavior.best_template_match = best_template_match
        behavior.get_client_size = lambda _title: (1280, 720)
        behavior.click_auto = lambda point, _callback: 2
        behavior._record_automation_position = lambda _callback, _position: None

        confidence = types.ModuleType('src.click.template_confidence')

        def threshold_for(_path, selection=None):
            selections_seen.append(selection)
            return 0.8

        confidence.threshold_for = threshold_for

        click_package = types.ModuleType('src.click')
        click_package.__path__ = []
        click_package.click_behavior = behavior
        click_package.template_confidence = confidence
        packs = types.ModuleType('src.packs')
        packs.language_switcher = types.SimpleNamespace(
            current_selection=lambda: self.fail('不应重新扫描当前模板 pack')
        )
        packs.image_scaler = types.SimpleNamespace(SOURCE_RES='2560x1440', scale_factor=lambda _res: 1)
        pyautogui = types.ModuleType('pyautogui')

        module = _load_module(
            'src.click._click_action_test',
            ROOT / 'src' / 'click' / 'click_action.py',
            {
                'src.click': click_package,
                'src.click.click_behavior': behavior,
                'src.click.template_confidence': confidence,
                'src.packs': packs,
                'pyautogui': pyautogui,
            },
        )

        class Worker:
            expected_pack = ('EN', '2560x1440')

            def __init__(self):
                self.logs = []
                self.waits = []

            def _running(self):
                return True

            def _wait(self, seconds):
                self.waits.append(seconds)
                return False

            def _wait_for_user_idle(self):
                return True

            def _automation_input(self):
                return contextlib.nullcontext()

            def _emit_log(self, message, level):
                self.logs.append((message, level))

        worker = Worker()
        with tempfile.TemporaryDirectory() as temp_dir:
            picture = Path(temp_dir) / 'item'
            Path(f'{picture}_1.png').write_bytes(b'1')
            Path(f'{picture}_2.png').write_bytes(b'2')
            self.assertEqual(module.click_item_with_result(worker, str(picture), 'item'), 2)

        self.assertEqual(len(paths_seen), 3)
        self.assertTrue(all(len(paths) == 2 for paths in paths_seen))
        self.assertTrue(selections_seen)
        self.assertTrue(all(selection == ('EN', '2560x1440') for selection in selections_seen))
        self.assertEqual(len(worker.logs), 1)
        self.assertIn('已点击模板 item', worker.logs[0][0])
        self.assertIn('置信度 0.9500，阈值 0.8000', worker.logs[0][0])
        self.assertEqual(worker.logs[0][1], 'INFO')
        self.assertEqual(worker.waits, [0.3, 0.3, 0.2])


class CrystalisFlowTests(unittest.TestCase):
    def test_retry_is_checked_after_result_disappears(self):
        find_results = iter((1, 1, 2))
        calls = {'find': 0, 'click': 0}

        class ClickAction:
            @staticmethod
            def find_item_with_result(_worker, _picture, _name):
                calls['find'] += 1
                return next(find_results)

            @staticmethod
            def click_item_with_result(_worker, _picture, _name, search_region=None):
                calls['click'] += 1
                return 2 if calls['click'] == 1 else 1

        click_package = types.ModuleType('src.click')
        click_package.click_action = ClickAction
        workers_package = types.ModuleType('src.workers')
        workers_package.__path__ = []
        base = types.ModuleType('src.workers.base')
        base.BaseWorker = object
        base.BATTLE_TIMEOUT = 1
        registry = types.ModuleType('src.workers.registry')
        registry.register = lambda *_args, **_kwargs: lambda cls: cls
        registry.ParamSpec = lambda *_args, **_kwargs: object()

        module = _load_module(
            'src.workers._crystalis_test',
            ROOT / 'src' / 'workers' / 'crystalis.py',
            {
                'src.click': click_package,
                'src.workers': workers_package,
                'src.workers.base': base,
                'src.workers.registry': registry,
            },
        )

        class Signal:
            def emit(self, _message):
                pass

        class Worker:
            signal = Signal()
            finished = False

            def _running(self):
                return not self.finished

            def _wait(self, _seconds):
                return False

            def _finish(self):
                self.finished = True

            def _emit_log(self, _message, _level):
                pass

        worker = Worker()
        module.CrystalisWorker.wait_win(worker)
        self.assertFalse(worker.finished)
        self.assertEqual(calls, {'find': 3, 'click': 1})


class RepositoryValidationTests(unittest.TestCase):
    def test_registered_workers_have_complete_source_templates(self):
        workers_package = types.ModuleType('src.workers')
        workers_package.__path__ = []
        click_package = types.ModuleType('src.click')
        click_package.click_action = types.SimpleNamespace()
        base = types.ModuleType('src.workers.base')
        base.BaseWorker = object
        base.BATTLE_TIMEOUT = 1800
        base.RETRY_TIMEOUT = 60
        base.retry_until = lambda *_args, **_kwargs: 1

        modules = {
            'src.workers': workers_package,
            'src.workers.base': base,
            'src.click': click_package,
        }
        with patch.dict(sys.modules, modules):
            registry = _load_module(
                'src.workers.registry', ROOT / 'src' / 'workers' / 'registry.py', modules,
            )
            sys.modules['src.workers.registry'] = registry
            link_raid = _load_module(
                'src.workers.link_raid', ROOT / 'src' / 'workers' / 'link_raid.py',
                {**modules, 'src.workers.registry': registry},
            )
            crystalis = _load_module(
                'src.workers.crystalis', ROOT / 'src' / 'workers' / 'crystalis.py',
                {**modules, 'src.workers.registry': registry},
            )
            self.assertIsNotNone(link_raid.LinkRaidWorker)
            self.assertIsNotNone(crystalis.CrystalisWorker)
            metas = registry.get_registry()

        self.assertEqual([meta.name for meta in metas], ['link_raid', 'crystalis'])
        confidence = _load_module(
            '_template_confidence_test',
            ROOT / 'src' / 'click' / 'template_confidence.py',
            {},
        )
        for lang in ('EN', 'JP'):
            valid, errors = confidence.validate_pack(lang, '2560x1440')
            self.assertTrue(valid, f'{lang}/thresholds: {errors}')
            for meta in metas:
                values = {spec.key: spec.default for spec in meta.params}
                groups = [path.format(**values) for path in meta.required_templates]
                valid, errors = language_switcher.validate_template_groups(
                    lang, '2560x1440', groups,
                )
                self.assertTrue(valid, f'{lang}/{meta.name}: {errors}')


if __name__ == '__main__':
    unittest.main()

import json
import os
import threading
import types
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, call, patch

import cv2
import numpy as np

from main import mywindow
from src.click import click_action, click_behavior
from src.core.input_activity import UserActivityGuard
from src.packs import image_scaler
from src.workers import base as worker_base, link_raid


class ClientCoordinateTests(unittest.TestCase):
    def test_coordinate_actions_use_client_origin(self):
        callback = None
        with patch.object(click_behavior, 'find_win', return_value=(10, 20, 1000, 800)), \
                patch.object(click_behavior, 'get_client_region',
                             return_value=(30, 50, 900, 700)), \
                patch.object(click_behavior, '_record_automation_position') as record, \
                patch.object(click_action.pyautogui, 'moveTo') as move_to, \
                patch.object(click_action.pyautogui, 'click') as click, \
                patch.object(click_action.pyautogui, 'dragTo') as drag_to, \
                patch.object(click_action.time, 'sleep'):
            self.assertEqual(click_action.click_position(100, 200, callback), 2)
            self.assertEqual(click_action.move_a_to_b(5, 6, 200, 300, callback), 2)

        self.assertEqual(move_to.call_args_list, [call(130, 250), call(35, 56)])
        click.assert_called_once_with(130, 250, button='left')
        drag_to.assert_called_once_with(230, 350, duration=0.5, button='left')
        self.assertEqual(record.call_args_list, [
            call(callback, (130, 250)),
            call(callback, (230, 350)),
        ])


class FixedPositionTemplateActionTests(unittest.TestCase):
    class Worker:
        expected_pack = ('EN', '2560x1440')

        def __init__(self):
            self.logs = []
            self.waits = []

        @staticmethod
        def _running():
            return True

        def _wait(self, seconds):
            self.waits.append(seconds)
            return False

        @staticmethod
        def _wait_for_user_idle():
            return True

        @staticmethod
        def _automation_input():
            return patch.object(click_action, '_unused_test_marker', create=True)

        def _emit_log(self, message, level):
            self.logs.append((message, level))

    def test_text_variants_trigger_one_fixed_position_click(self):
        worker = self.Worker()
        with TemporaryDirectory(dir=Path.cwd() / 'tests') as temp_dir:
            picture = Path(temp_dir) / 'tap_to_countinue'
            templates = [Path(f'{picture}_{index}.png') for index in range(1, 5)]
            for template in templates:
                template.write_bytes(b'png')
            detected = ((100, 100), 0.95, str(templates[1]))
            with patch.object(click_behavior, 'best_template_match',
                              return_value=detected) as match, \
                    patch.object(click_action.template_confidence, 'threshold_for',
                                 return_value=0.8), \
                    patch.object(click_action, 'click_position_scaled',
                                 return_value=2) as fixed_click:
                result = click_action.click_fixed_position_for_item_with_result(
                    worker, str(picture), 'tap_to_countinue', 1280, 1367,
                    foreground_variants=(1, 2),
                )

        self.assertEqual(result, 2)
        self.assertEqual(match.call_count, 3)
        for call_args in match.call_args_list:
            self.assertEqual(call_args.args[0], templates[:2])
            self.assertTrue(call_args.kwargs['foreground'])
        self.assertEqual(fixed_click.call_count, 1)
        self.assertEqual(fixed_click.call_args.args[:2], (1280, 1367))
        self.assertEqual(worker.waits, [0.3, 0.3, 0.2])
        self.assertIn('已点击安全位置 (1280, 1367)', worker.logs[0][0])

    def test_click_until_does_not_repeat_fixed_click_while_waiting_for_next_step(self):
        class Signal:
            @staticmethod
            def emit(_message):
                pass

        class Worker:
            signal = Signal()

            @staticmethod
            def _running():
                return True

            @staticmethod
            def _wait(_seconds):
                return False

            @staticmethod
            def _emit_log(_message, _level):
                raise AssertionError('不应超时')

            @staticmethod
            def _finish():
                raise AssertionError('不应停止')

        next_step = ('./aim/back', 'back')
        with patch.object(worker_base.click_action,
                          'click_fixed_position_for_item_with_result',
                          return_value=2) as fixed_click, \
                patch.object(worker_base.click_action, 'find_first_item_with_result',
                             side_effect=(None, next_step)), \
                patch.object(worker_base.click_action, 'click_item_with_result') as click:
            result = worker_base.BaseWorker._click_until(
                Worker(), './aim/tap_to_countinue', 'tap_to_countinue', timeout=1,
                next_steps=(next_step,), fixed_click_2k=(1280, 1367),
                foreground_variants=(1, 2),
            )

        self.assertEqual(result, 2)
        fixed_click.assert_called_once()
        click.assert_not_called()


class ForegroundTemplateMatchTests(unittest.TestCase):
    def test_text_mask_ignores_changed_background(self):
        template = np.zeros((48, 180, 3), dtype=np.uint8)
        cv2.putText(template, 'continue', (4, 37), cv2.FONT_HERSHEY_SIMPLEX,
                    1.0, (220, 220, 220), 2, cv2.LINE_AA)
        rng = np.random.default_rng(7)
        screen = rng.integers(15, 55, (120, 320, 3), dtype=np.uint8)
        x, y = 70, 35
        foreground = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY) > 80
        region = screen[y:y + template.shape[0], x:x + template.shape[1]]
        region[foreground] = template[foreground]
        blurred = cv2.GaussianBlur(template, (3, 3), 0)

        with patch.object(click_behavior, '_capture_game_window',
                          return_value=(screen, (0, 0))), \
                patch.object(click_behavior, '_load_template',
                             return_value=(template, blurred)):
            full = click_behavior.best_template_match(('text.png',))
            masked = click_behavior.best_template_match(('text.png',), foreground=True)

        self.assertEqual(masked[0], (x + template.shape[1] // 2,
                                     y + template.shape[0] // 2))
        self.assertGreater(masked[1], full[1])
        self.assertGreater(masked[1], 0.8)


class RecoveryClickSafetyTests(unittest.TestCase):
    def test_next_step_is_rechecked_after_observation_before_recovery_click(self):
        messages = []

        class Signal:
            @staticmethod
            def emit(message):
                messages.append(message)

        class Worker:
            signal = Signal()

            @staticmethod
            def _running():
                return True

            @staticmethod
            def _wait(_seconds):
                return False

            @staticmethod
            def _emit_log(_message, _level):
                raise AssertionError('不应超时')

            @staticmethod
            def _finish():
                raise AssertionError('不应停止')

        next_step = ('./aim/tap_to_countinue', 'tap_to_countinue')
        worker = Worker()
        with patch.object(worker_base.time, 'monotonic',
                          side_effect=(100, 100, 100, 100, 106)), \
                patch.object(worker_base.click_action, 'click_item_with_result',
                             return_value=2), \
                patch.object(worker_base.click_action.click_behavior,
                             'screen_changes_significantly', return_value=False), \
                patch.object(worker_base.click_action, 'find_first_item_with_result',
                             return_value=next_step) as find_next, \
                patch.object(worker_base.click_action.click_behavior,
                             'click_last_automation_position') as recovery_click:
            result = worker_base.BaseWorker._click_until(
                worker, './aim/ended', 'ended', timeout=60,
                next_steps=(next_step,),
            )

        self.assertEqual(result, 2)
        find_next.assert_called_once_with(worker, (next_step,))
        recovery_click.assert_not_called()
        self.assertTrue(any('恢复点击前已检测到下一步tap_to_countinue' in message
                            for message in messages))


class PausedInputTests(unittest.TestCase):
    def test_slow_movement_accumulates_while_paused(self):
        guard = UserActivityGuard()
        guard._paused = True
        guard._last_position = (0, 0)
        guard._mouse_travel = 0

        self.assertIsNone(guard._observe_mouse_movement((1, 0)))
        self.assertIsNone(guard._observe_mouse_movement((2, 0)))
        self.assertIn('累计移动 3px', guard._observe_mouse_movement((3, 0)))

class ParticipantDetectionTests(unittest.TestCase):
    def test_capture_failure_returns_unknown(self):
        with patch.object(click_behavior, '_capture_game_window', return_value=(None, None)):
            self.assertIsNone(click_behavior.participant_count_crowded_near((100, 100)))

    @staticmethod
    def _level_digit_mask(level):
        path = (Path(__file__).resolve().parents[1] / 'language' / 'EN' /
                'EN_2560x1440' / 'quests' / 'link_raid' / 'backup_requests' /
                'lv' / f'lv{level}' / f'lv{level}_1.png')
        image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        mask = (cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) > 145).astype(np.uint8)
        count, labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
        components = [index for index in range(1, count)
                      if stats[index, cv2.CC_STAT_AREA] >= 100]
        digit = max(components, key=lambda index: stats[index, cv2.CC_STAT_LEFT])
        left = stats[digit, cv2.CC_STAT_LEFT]
        top = stats[digit, cv2.CC_STAT_TOP]
        width = stats[digit, cv2.CC_STAT_WIDTH]
        height = stats[digit, cv2.CC_STAT_HEIGHT]
        return labels[top:top + height, left:left + width] == digit

    def test_nine_is_crowded_but_other_loop_digits_are_allowed(self):
        nine = self._level_digit_mask(9)
        self.assertTrue(click_behavior._digit_has_upper_loop(nine))
        allowed = [self._level_digit_mask(level) for level in (4, 6, 7, 8)]
        self.assertTrue(all(
            not click_behavior._digit_has_upper_loop(digit) for digit in allowed
        ))

        for digit, expected in [(nine, True), *((digit, False) for digit in allowed)]:
            mask = np.zeros((60, 180), dtype=bool)
            height, width = digit.shape
            mask[10:10 + height, 5:5 + width] = digit
            self.assertIs(
                click_behavior._participant_count_is_crowded(mask, 2560),
                expected,
            )
        full_mask = np.zeros((60, 180), dtype=bool)
        height, width = nine.shape
        full_mask[10:10 + height, 5:5 + width] = nine
        full_mask[10:10 + height, 140:140 + width] = nine
        self.assertTrue(
            click_behavior._participant_count_is_crowded(full_mask, 2560)
        )

    def test_unknown_candidate_is_skipped(self):
        first = (6, 6, (100, 100), 0.95, 0.95, 'lv6-a.png', 'lv6-a.png')
        second = (6, 6, (200, 200), 0.94, 0.94, 'lv6-b.png', 'lv6-b.png')
        with patch.object(click_behavior, 'best_competing_template_matches',
                          return_value=[first, second]), \
                patch.object(click_action, '_competing_match_accepted', return_value=True), \
                patch.object(click_behavior, 'participant_count_crowded_near',
                             side_effect=[None, False]):
            detected = click_action._best_accepted_competing_detection(
                6, {}, ('EN', '2560x1440'), skip_crowded=True, name='lv6',
            )
        self.assertEqual(detected, second)


class CompetingMatchCacheTests(unittest.TestCase):
    def test_template_groups_share_one_capture(self):
        screen = np.zeros((40, 40, 3), dtype=np.uint8)
        template = np.zeros((5, 5, 3), dtype=np.uint8)
        with patch.object(click_behavior, '_capture_game_window',
                          return_value=(screen, (0, 0))) as capture, \
                patch.object(click_behavior, '_load_template',
                             return_value=(template, template)):
            results = click_behavior.best_template_matches(
                (('first.png',), ('second.png',)),
            )

        self.assertEqual(len(results), 2)
        capture.assert_called_once_with()

    def test_template_preprocessing_is_cached_until_file_changes(self):
        with TemporaryDirectory(dir=Path.cwd() / 'tests') as temp_dir:
            path = Path(temp_dir) / 'template.png'
            relative = path.relative_to(Path.cwd())
            first = np.zeros((10, 10, 3), dtype=np.uint8)
            second = np.full((10, 10, 3), 255, dtype=np.uint8)
            path.write_bytes(cv2.imencode('.png', first)[1].tobytes())
            click_behavior._load_template_cached.cache_clear()
            with patch.object(click_behavior.cv2, 'imread', wraps=cv2.imread) as imread:
                loaded_first, _blurred = click_behavior._load_template(relative)
                click_behavior._load_template(relative)
                stat = path.stat()
                path.write_bytes(cv2.imencode('.png', second)[1].tobytes())
                os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
                loaded_second, _blurred = click_behavior._load_template(relative)

            self.assertEqual(imread.call_count, 2)
            self.assertLess(float(loaded_first.mean()), float(loaded_second.mean()))
            click_behavior._load_template_cached.cache_clear()

    def test_full_match_map_is_computed_once_per_template(self):
        rng = np.random.default_rng(42)
        selected_template = rng.integers(0, 256, (20, 20, 3), dtype=np.uint8)
        other_template = rng.integers(0, 256, (20, 20, 3), dtype=np.uint8)
        screen = rng.integers(0, 256, (80, 80, 3), dtype=np.uint8)
        screen[5:25, 5:25] = selected_template
        screen[45:65, 45:65] = selected_template
        original_match = cv2.matchTemplate
        full_map_calls = []

        def tracked_match(image, template, method):
            if image.shape[:2] == screen.shape[:2]:
                full_map_calls.append(template.shape)
            return original_match(image, template, method)

        templates = {'lv6.png': selected_template, 'lv7.png': other_template}
        with patch.object(click_behavior, '_capture_game_window',
                          return_value=(screen, (0, 0))), \
                patch.object(click_behavior.cv2, 'imread',
                             side_effect=lambda path: templates[str(path)]), \
                patch.object(click_behavior.cv2, 'matchTemplate', side_effect=tracked_match):
            matches = click_behavior.best_competing_template_matches(
                6, {6: ['lv6.png'], 7: ['lv7.png']}, max_candidates=2,
            )

        self.assertEqual(len(matches), 2)
        self.assertEqual(len(full_map_calls), 2)


class BatchStateDetectionTests(unittest.TestCase):
    def test_multiple_next_steps_use_one_shared_frame(self):
        entries = (('first', 'first'), ('second', 'second'))
        detections = [
            ((10, 10), 0.70, 'first_1.png'),
            ((20, 20), 0.95, 'second_1.png'),
        ]

        class Worker:
            expected_pack = ('EN', '2560x1440')

            @staticmethod
            def _running():
                return True

            @staticmethod
            def _wait_for_user_idle():
                return True

        with patch.object(click_action, '_template_files',
                          side_effect=lambda picture: [f'{picture}_1.png']), \
                patch.object(click_behavior, 'best_template_matches',
                             return_value=detections) as match_groups, \
                patch.object(click_action.template_confidence, 'threshold_for',
                             return_value=0.8):
            found = click_action.find_first_item_with_result(Worker(), entries)

        self.assertEqual(found, entries[1])
        match_groups.assert_called_once()

    def test_next_step_can_use_only_text_foreground_variants(self):
        entry = (
            'tap_to_countinue',
            'tap_to_countinue',
            {'foreground_variants': (1, 2)},
        )

        class Worker:
            expected_pack = ('JP', '2560x1440')

            @staticmethod
            def _running():
                return True

            @staticmethod
            def _wait_for_user_idle():
                return True

        files = [f'tap_to_countinue_{index}.png' for index in range(1, 5)]
        detection = ((1280, 1367), 0.95, files[1])
        with patch.object(click_action, '_template_files', return_value=files), \
                patch.object(click_behavior, 'best_template_matches',
                             return_value=[detection]) as match_groups, \
                patch.object(click_action.template_confidence, 'threshold_for',
                             return_value=0.8):
            found = click_action.find_first_item_with_result(Worker(), (entry,))

        self.assertEqual(found, entry[:2])
        self.assertEqual(match_groups.call_args.args[0], [files[:2]])
        self.assertEqual(match_groups.call_args.kwargs['foreground_groups'], [True])


class LinkRaidRecoveryTests(unittest.TestCase):
    class Signal:
        def __init__(self):
            self.messages = []

        def emit(self, message):
            self.messages.append(message)

    def test_room_full_popup_is_dismissed_and_rematched(self):
        clicked = []

        class Worker:
            signal = LinkRaidRecoveryTests.Signal()
            LP_full_add = 1
            LP_full = 1
            already_end = 1

            @staticmethod
            def _running():
                return True

            @staticmethod
            def _wait(_seconds):
                return False

            @staticmethod
            def prepare_matching_battle():
                return True

            @staticmethod
            def _finish():
                raise AssertionError('不应停止任务')

            @staticmethod
            def _click_until(picture, name, *args, **kwargs):
                clicked.append((picture, name, kwargs.get('next_steps')))
                return 2

        def find_item(_worker, picture, _name):
            if picture.endswith('no_lp'):
                return 1
            self.fail(f'未预期的模板查询: {picture}')

        worker = Worker()
        full_entry = (
            './aim/quests/link_raid/backup_requests/join/full/battle_full',
            'battle_full',
        )
        with patch.object(link_raid.click_action, 'find_first_item_with_result',
                          side_effect=(full_entry, None)), \
                patch.object(link_raid.click_action, 'find_item_with_result',
                             side_effect=find_item):
            link_raid.LinkRaidWorker.join_battle(worker)

        self.assertEqual(clicked[1][0],
                         './aim/quests/link_raid/backup_requests/join/full/ok')
        self.assertEqual(clicked[2][0], './aim/quests/link_raid/backup_requests/join')
        self.assertEqual(clicked[-1][0], './aim/quests/link_raid/backup_requests/join/play')
        self.assertTrue(any(
            step[0].endswith('battle_full') for step in clicked[0][2]
        ))

    def test_scrolled_likes_still_respect_nine_click_limit(self):
        state = {'calls': 0, 'successes': 0}

        def click_item(*_args, **_kwargs):
            state['calls'] += 1
            if state['calls'] % 2:
                return 1
            state['successes'] += 1
            return 2

        class Worker:
            signal = LinkRaidRecoveryTests.Signal()

            @staticmethod
            def _running():
                return state['successes'] < 12

            @staticmethod
            def _wait(_seconds):
                return False

            @staticmethod
            def _emit_log(_message, _level):
                pass

            @staticmethod
            def _finish():
                pass

        with patch.object(link_raid, 'retry_until', return_value=2), \
                patch.object(link_raid.click_action, 'click_item_with_result',
                             side_effect=click_item), \
                patch.object(link_raid.click_action, 'move_a_to_b_scaled', return_value=2):
            link_raid.LinkRaidWorker.like_battle_result(Worker())

        self.assertEqual(state['successes'], 9)


class ScalerManifestTests(unittest.TestCase):
    def test_failed_regeneration_preserves_old_manifest_record(self):
        with TemporaryDirectory() as temp_dir:
            language_dir = Path(temp_dir) / 'language'
            source_dir = language_dir / 'EN' / 'EN_2560x1440'
            target_dir = language_dir / 'EN' / 'EN_1280x720'
            source_dir.mkdir(parents=True)
            target_dir.mkdir(parents=True)
            (source_dir / 'item.png').write_bytes(b'new source')
            (target_dir / 'item.png').write_bytes(b'old target')
            old_record = {
                'source': 'old-source-hash',
                'target': image_scaler._file_hash(target_dir / 'item.png'),
                'recipe': 'old-recipe',
            }
            (target_dir / image_scaler.MANIFEST_NAME).write_text(
                json.dumps({'item.png': old_record}), encoding='utf-8',
            )

            with patch.object(image_scaler, 'LANGUAGE_DIR', str(language_dir)), \
                    patch.object(image_scaler, '_run_magick',
                                 side_effect=RuntimeError('conversion failed')):
                generated, _skipped, notes = image_scaler.scale_pack(
                    'EN', tool_fingerprint='test-tool',
                )

            manifest, status = image_scaler._load_manifest(str(target_dir))
            self.assertEqual(generated, 0)
            self.assertEqual(status, 'ok')
            self.assertEqual(manifest['item.png'], old_record)
            self.assertTrue(any('conversion failed' in note for note in notes))


class UpdateCancellationTests(unittest.TestCase):
    def test_new_check_clears_latched_cancellation(self):
        cancel = threading.Event()
        cancel.set()
        holder = types.SimpleNamespace(
            _update_state='idle',
            _closing=False,
            _update_cancel=cancel,
            _update_job_id=None,
            _update_manual=False,
            _update_check_thread=None,
            betaCheckBox=types.SimpleNamespace(isChecked=lambda: False),
            _refresh_control_state=lambda: None,
            _append_log=lambda *_args, **_kwargs: None,
        )
        fake_thread = types.SimpleNamespace(start=lambda: None)
        with patch('main.threading.Thread', return_value=fake_thread):
            mywindow._check_update_async(holder)

        self.assertFalse(cancel.is_set())
        self.assertEqual(holder._update_state, 'checking')


class WindowFocusEfficiencyTests(unittest.TestCase):
    @staticmethod
    def _window(active):
        return types.SimpleNamespace(
            isMinimized=False,
            isActive=active,
            left=10,
            top=20,
            width=1280,
            height=720,
            restore=Mock(),
            activate=Mock(),
        )

    def test_active_window_has_no_activation_delay(self):
        window = self._window(True)
        with patch.object(click_behavior.pwc, 'getWindowsWithTitle',
                          return_value=[window]), \
                patch.object(click_behavior.time, 'sleep') as sleep:
            self.assertEqual(
                click_behavior.find_win('MadokaExedra'),
                (10, 20, 1280, 720),
            )
        window.activate.assert_not_called()
        sleep.assert_not_called()

    def test_inactive_window_is_activated_before_capture(self):
        window = self._window(False)
        with patch.object(click_behavior.pwc, 'getWindowsWithTitle',
                          return_value=[window]), \
                patch.object(click_behavior.time, 'sleep') as sleep:
            click_behavior.find_win('MadokaExedra')
        window.activate.assert_called_once_with()
        sleep.assert_called_once_with(0.2)


if __name__ == '__main__':
    unittest.main()

import json
import os
import threading
import types
import unittest
from pathlib import Path
from contextlib import nullcontext
from tempfile import TemporaryDirectory
from unittest.mock import ANY, Mock, call, patch

import cv2
import numpy as np

from main import SettingsDialog, mywindow
from src.click import click_action, click_behavior
from src.core.input_activity import UserActivityGuard
from src.packs import image_scaler
from src.workers import base as worker_base, link_raid


class WorkerTerminationNotificationTests(unittest.TestCase):
    @staticmethod
    def _run(action):
        worker = worker_base.BaseWorker()
        events = []
        worker.majorEvent.connect(
            lambda event_key, reason, params: events.append(
                (event_key, reason, params)
            )
        )
        with patch.object(worker_base, 'template_write_lock',
                          return_value=nullcontext()), \
                patch.object(worker._activity_guard, 'stop'):
            worker._run_safely(lambda: action(worker))
        return events

    def test_automatic_return_emits_auto_end_event(self):
        events = self._run(lambda _worker: None)

        self.assertEqual([event[0] for event in events], ['worker_auto_ended'])
        self.assertIn('自动结束', events[0][1])

    def test_manual_stop_does_not_emit_auto_end_event(self):
        events = self._run(lambda worker: worker.stop())

        self.assertEqual(events, [])

    def test_existing_major_event_suppresses_auto_end_event(self):
        events = self._run(
            lambda worker: worker._emit_major_event('timeout', '等待超时。')
        )

        self.assertEqual([event[0] for event in events], ['timeout'])

    def test_restart_clears_manual_stop_and_major_event_tracking(self):
        worker = worker_base.BaseWorker()
        worker.stop()
        worker._major_event_emitted = True

        with patch.object(worker._activity_guard, 'start'), \
                patch.object(worker_base.QThread, 'start'):
            self.assertTrue(worker.start())

        self.assertFalse(worker._manual_stop_event.is_set())
        self.assertFalse(worker._major_event_emitted)
        worker.stop()


class NotificationChannelSelectionTests(unittest.TestCase):
    class CheckBox:
        def __init__(self, checked):
            self.checked = checked

        def isChecked(self):
            return self.checked

        def setChecked(self, checked):
            self.checked = checked

        def blockSignals(self, _blocked):
            pass

    def test_third_channel_is_reverted_with_feedback(self):
        first = self.CheckBox(True)
        second = self.CheckBox(True)
        third = self.CheckBox(True)
        status = types.SimpleNamespace(text='', setText=lambda text: setattr(status, 'text', text))
        emitted = []
        dialog = types.SimpleNamespace(
            channelChecks={9: first, 8: second, 18: third},
            notificationStatusLabel=status,
            _emit_notification_settings=lambda: emitted.append(True),
        )

        SettingsDialog._channel_toggled(dialog, third, True)

        self.assertTrue(first.isChecked())
        self.assertTrue(second.isChecked())
        self.assertFalse(third.isChecked())
        self.assertEqual(status.text, '最多选择 2 个推送通道。')
        self.assertEqual(emitted, [True])


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
            self.assertEqual(click_action.move_position(50, 60, callback), 2)

        self.assertEqual(move_to.call_args_list, [
            call(130, 250), call(35, 56), call(80, 110),
        ])
        click.assert_called_once_with(130, 250, button='left')
        drag_to.assert_called_once_with(230, 350, duration=0.5, button='left')
        self.assertEqual(record.call_args_list, [
            call(callback, (130, 250)),
            call(callback, (230, 350)),
            call(callback, (80, 110)),
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

    def test_click_until_allows_second_confirmed_fixed_click(self):
        next_step = ('./aim/back', 'back')

        class Worker:
            signal = types.SimpleNamespace(emit=lambda _message: None)
            _running = staticmethod(lambda: True)
            _wait = staticmethod(lambda _seconds: False)
            _emit_log = staticmethod(
                lambda _message, _level: (_ for _ in ()).throw(
                    AssertionError('不应超时')
                )
            )
            _finish = staticmethod(
                lambda: (_ for _ in ()).throw(AssertionError('不应停止'))
            )

        with patch.object(worker_base.click_action,
                          'click_fixed_position_for_item_with_result',
                          return_value=2) as fixed_click, \
                patch.object(worker_base.click_action, 'find_first_item_with_result',
                             side_effect=(None, next_step)):
            result = worker_base.BaseWorker._click_until(
                Worker(), './aim/tap_to_countinue', 'tap_to_countinue', timeout=1,
                next_steps=(next_step,), fixed_click_2k=(1280, 1367),
                foreground_variants=(1, 2), fixed_click_limit=2,
            )

        self.assertEqual(result, 2)
        self.assertEqual(fixed_click.call_count, 2)


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
        # 游戏文字会淡入淡出；保留一半透明度，原始亮度匹配会跌破阈值。
        region[foreground] = (
            region[foreground].astype(float) * 0.5
            + template[foreground].astype(float) * 0.5
        ).astype(np.uint8)
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

    def test_text_outline_rejects_plain_bright_area(self):
        template = np.zeros((48, 180, 3), dtype=np.uint8)
        cv2.putText(template, 'continue', (4, 37), cv2.FONT_HERSHEY_SIMPLEX,
                    1.0, (220, 220, 220), 2, cv2.LINE_AA)
        mask = click_behavior._foreground_mask(template)
        support = click_behavior._foreground_support(mask)
        bright_screen = np.full((120, 320), 255, dtype=np.uint8)

        _location, _size, score = click_behavior._match_one(
            click_behavior._foreground_outline(bright_screen),
            click_behavior._foreground_outline(mask),
            support,
        )

        self.assertLess(score, 0.8)

    def test_text_outline_tolerates_supported_resolution_rasterization(self):
        source_root = Path(__file__).resolve().parents[1] / 'language'
        for language in ('EN', 'JP'):
            template_dir = (
                source_root / language / f'{language}_2560x1440' / 'quests' /
                'link_raid' / 'backup_requests' / 'battle'
            )
            for index in (1, 2):
                source = cv2.imdecode(
                    np.fromfile(
                        template_dir / f'tap_to_countinue_{index}.png',
                        dtype=np.uint8,
                    ),
                    cv2.IMREAD_COLOR,
                )
                for scale, client_height in (
                        (0.5, 720), (0.75, 1080), (1.0, 1440), (1.5, 2160)):
                    size = (round(source.shape[1] * scale),
                            round(source.shape[0] * scale))
                    # Triangle 派生模板与原生游戏字体可能采用不同采样方式。
                    template = cv2.resize(
                        source, size, interpolation=cv2.INTER_LINEAR,
                    )
                    native = cv2.resize(
                        source, size, interpolation=cv2.INTER_NEAREST,
                    )
                    mask = click_behavior._foreground_mask(template)
                    support = click_behavior._foreground_support(mask)
                    gray = cv2.cvtColor(native, cv2.COLOR_BGR2GRAY)
                    block_size = max(15, round(client_height * 31 / 1440))
                    if block_size % 2 == 0:
                        block_size += 1
                    native_binary = cv2.adaptiveThreshold(
                        gray, 255,
                        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                        cv2.THRESH_BINARY,
                        block_size, 0,
                    )
                    outline = click_behavior._foreground_outline(mask)

                    _location, _size, score = click_behavior._match_one(
                        click_behavior._foreground_outline(native_binary),
                        outline,
                        support,
                    )
                    bright = np.full(mask.shape, 255, dtype=np.uint8)
                    _location, _size, bright_score = click_behavior._match_one(
                        click_behavior._foreground_outline(bright),
                        outline,
                        support,
                    )

                    label = (
                        f'{language} tap_to_countinue_{index}.png '
                        f'{client_height}p'
                    )
                    self.assertGreater(score, 0.8, f'{label}: {score:.4f}')
                    self.assertLess(
                        bright_score, 0.8, f'{label} 亮区: {bright_score:.4f}',
                    )

    def test_committed_jp_text_templates_tolerate_low_opacity(self):
        template_dir = (
            Path(__file__).resolve().parents[1] / 'language' / 'JP' /
            'JP_2560x1440' / 'quests' / 'link_raid' / 'backup_requests' /
            'battle'
        )
        for index in (1, 2):
            path = template_dir / f'tap_to_countinue_{index}.png'
            template = cv2.imdecode(
                np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR,
            )
            mask = click_behavior._foreground_mask(template)
            support = click_behavior._foreground_support(mask)
            foreground = mask > 0
            height, width = template.shape[:2]
            screen = np.random.default_rng(index).integers(
                10, 80, (1440, 1440, 3), dtype=np.uint8,
            )
            x, y = 500, 1200
            region = screen[y:y + height, x:x + width]
            region[foreground] = (
                region[foreground].astype(float) * 0.6
                + template[foreground].astype(float) * 0.4
            ).astype(np.uint8)

            location, _size, score = click_behavior._match_one(
                click_behavior._foreground_outline(
                    click_behavior._foreground_binary(screen),
                ),
                click_behavior._foreground_outline(mask),
                support,
            )

            self.assertEqual(location, (x, y), path.name)
            self.assertGreater(score, 0.8, path.name)


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

    def test_fixed_action_rejects_next_step_before_first_confirmed_click(self):
        messages = []

        class Worker:
            signal = types.SimpleNamespace(emit=messages.append)
            _running = staticmethod(lambda: True)
            _wait = staticmethod(lambda _seconds: False)
            _emit_log = staticmethod(
                lambda _message, _level: (_ for _ in ()).throw(
                    AssertionError('不应超时')
                )
            )
            _finish = staticmethod(
                lambda: (_ for _ in ()).throw(AssertionError('不应停止'))
            )

        next_step = ('./aim/back', 'back')
        worker = Worker()
        with patch.object(worker_base.time, 'monotonic', side_effect=(
                100, 100, 106, 106, 106, 106, 106, 106, 106, 106)), \
                patch.object(
                    worker_base.click_action,
                    'click_fixed_position_for_item_with_result',
                    side_effect=(1, 2),
                ) as fixed_click, \
                patch.object(
                    worker_base.click_action.click_behavior,
                    'screen_changes_significantly',
                    return_value=False,
                ), \
                patch.object(
                    worker_base.click_action,
                    'find_first_item_with_result',
                    return_value=next_step,
                ) as find_next:
            result = worker_base.BaseWorker._click_until(
                worker,
                './aim/tap_to_countinue',
                'tap_to_countinue',
                timeout=60,
                next_steps=(next_step,),
                fixed_click_2k=(1280, 1367),
                foreground_variants=(1, 2),
                fixed_click_limit=2,
            )

        self.assertEqual(result, 2)
        self.assertEqual(fixed_click.call_count, 2)
        find_next.assert_called_once_with(worker, (next_step,))
        self.assertFalse(any('恢复点击前已检测到下一步back' in message
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
            self.assertIsNone(click_behavior.participant_count_near((100, 100)))

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
                click_behavior._participant_count_value(mask, 2560),
                9 if expected else 8,
            )
        full_mask = np.zeros((60, 180), dtype=bool)
        height, width = nine.shape
        full_mask[10:10 + height, 5:5 + width] = nine
        full_mask[10:10 + height, 140:140 + width] = nine
        self.assertEqual(click_behavior._participant_count_value(full_mask, 2560), 10)

    def test_unknown_candidate_is_allowed(self):
        first = (6, 6, (100, 100), 0.95, 0.95, 'lv6-a.png', 'lv6-a.png')
        second = (6, 6, (200, 200), 0.94, 0.94, 'lv6-b.png', 'lv6-b.png')
        with patch.object(click_behavior, 'best_competing_template_matches',
                          return_value=[first, second]), \
                patch.object(click_action, '_competing_match_accepted', return_value=True), \
                patch.object(click_behavior, 'participant_count_near',
                             side_effect=[None, 8]):
            detected = click_action._best_accepted_competing_detection(
                6, {}, ('EN', '2560x1440'),
                skip_participant_counts=(9, 10), name='lv6',
            )
        self.assertEqual(detected, first)

    def test_nine_and_ten_can_be_skipped_independently(self):
        matches = [
            (6, 6, (100, 100), 0.96, 0.96, 'nine.png', 'nine.png'),
            (6, 6, (200, 200), 0.95, 0.95, 'ten.png', 'ten.png'),
            (6, 6, (300, 300), 0.94, 0.94, 'open.png', 'open.png'),
        ]
        with patch.object(click_behavior, 'best_competing_template_matches',
                          return_value=matches), \
                patch.object(click_action, '_competing_match_accepted', return_value=True), \
                patch.object(click_behavior, 'participant_count_near',
                             side_effect=(9, 10, 8)):
            detected = click_action._best_accepted_competing_detection(
                6, {}, ('EN', '2560x1440'),
                skip_participant_counts=(9,), name='lv6',
            )
        self.assertEqual(detected, matches[1])

    def test_priority_order_selects_first_eligible_level(self):
        matches = [
            (12, 12, (100, 100), 0.95, 0.95, 'lv12.png', 'lv12.png'),
            (6, 6, (200, 200), 0.99, 0.99, 'lv6.png', 'lv6.png'),
        ]
        with patch.object(click_behavior, 'best_competing_template_matches',
                          return_value=matches), \
                patch.object(click_action, '_competing_match_accepted', return_value=True), \
                patch.object(click_behavior, 'participant_count_near', return_value=8):
            detected = click_action._best_accepted_competing_detection(
                [12, 6], {}, ('EN', '2560x1440'), name='LV12 > LV6',
            )
        self.assertEqual(detected, matches[0])

    def test_no_accepted_candidate_does_not_query_none_threshold(self):
        with patch.object(click_behavior, 'best_competing_template_matches',
                          return_value=[]), \
                patch.object(click_action, '_template_files',
                             return_value=[Path('lv4_1.png')]), \
                patch.object(click_action.template_confidence, 'threshold_for',
                             side_effect=AssertionError('不应查询空模板路径')):
            found = click_action.find_competing_item_with_result(
                types.SimpleNamespace(
                    expected_pack=('JP', '2560x1440'),
                    _running=lambda: True,
                    _wait_for_user_idle=lambda: True,
                ),
                4, {4: 'lv4'}, 'lv4', skip_participant_counts=(9, 10),
            )

        self.assertEqual(found, 1)


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

    def test_cross_level_candidate_cannot_bypass_priority(self):
        screen = np.zeros((60, 80, 3), dtype=np.uint8)
        prepared = [
            (12, 'lv12.png', np.zeros((8, 8, 3), dtype=np.uint8),
             np.zeros((3, 3), dtype=np.float32), (8, 8)),
            (6, 'lv6.png', np.zeros((8, 8, 3), dtype=np.uint8),
             np.zeros((3, 3), dtype=np.float32), (8, 8)),
        ]

        def classify(_screen, _origin, source_level, _prepared, *_args):
            if source_level == 12:
                return 6, 6, (10, 10), 0.96, 0.96, 'lv6.png', 'lv6.png'
            return 6, 6, (20, 20), 0.95, 0.95, 'lv6.png', 'lv6.png'

        with patch.object(click_behavior, '_capture_game_window',
                          return_value=(screen, (0, 0))), \
                patch.object(click_behavior, '_prepare_competing_templates',
                             return_value=prepared), \
                patch.object(click_behavior, '_match_result_candidates',
                             return_value=[((1, 1), (8, 8), 0.95)]), \
                patch.object(click_behavior, '_competing_match_at_location',
                             side_effect=classify):
            matches = click_behavior.best_competing_template_matches(
                [12, 6], {12: (), 6: ()},
            )

        self.assertEqual([match[0] for match in matches], [6])
        self.assertEqual(matches[0][2], (20, 20))


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


class ContextualTemplateActionTests(unittest.TestCase):
    class Worker:
        expected_pack = ('EN', '2560x1440')

        def __init__(self):
            self.logs = []

        @staticmethod
        def _running():
            return True

        @staticmethod
        def _wait_for_user_idle():
            return True

        @staticmethod
        def _wait(_seconds):
            return False

        def _emit_log(self, message, level):
            self.logs.append((message, level))

    def test_click_requires_context_and_target_in_all_three_frames(self):
        context_files = ['already_end_1.png']
        target_files = ['ok_1.png']
        frames = (
            (((500, 300), 0.96, context_files[0]),
             ((500, 500), 0.95, target_files[0])),
            (((501, 300), 0.96, context_files[0]),
             ((501, 500), 0.95, target_files[0])),
            (((502, 300), 0.96, context_files[0]),
             ((502, 500), 0.95, target_files[0])),
        )
        worker = self.Worker()
        with patch.object(
                click_action, '_template_files',
                side_effect=(context_files, target_files),
        ), patch.object(
                click_behavior, 'best_template_matches', side_effect=frames,
        ) as match_groups, patch.object(
                click_behavior, 'get_client_size', return_value=(2560, 1440),
        ), patch.object(
                click_behavior, 'click_auto', return_value=2,
        ) as click_auto, patch.object(
                click_action.template_confidence, 'threshold_for', return_value=0.8,
        ):
            result = click_action.click_contextual_item_with_result(
                worker,
                'already_end',
                'already_end',
                'ok',
                'ok',
                search_region=(0.2, 0.2, 0.8, 0.85),
            )

        self.assertEqual(result, 2)
        self.assertEqual(match_groups.call_count, 3)
        self.assertTrue(all(
            call.kwargs['search_region'] == (0.2, 0.2, 0.8, 0.85)
            for call in match_groups.call_args_list
        ))
        click_auto.assert_called_once_with((501, 500), worker._running)

    def test_context_disappearing_prevents_clicking_another_ok(self):
        context_files = ['already_end_1.png']
        target_files = ['ok_1.png']
        frames = (
            (((500, 300), 0.96, context_files[0]),
             ((500, 500), 0.95, target_files[0])),
            ((None, 0.0, None),
             ((500, 500), 0.95, target_files[0])),
        )
        worker = self.Worker()
        with patch.object(
                click_action, '_template_files',
                side_effect=(context_files, target_files),
        ), patch.object(
                click_behavior, 'best_template_matches', side_effect=frames,
        ), patch.object(
                click_behavior, 'get_client_size', return_value=(2560, 1440),
        ), patch.object(
                click_behavior, 'click_auto', return_value=2,
        ) as click_auto, patch.object(
                click_action.template_confidence, 'threshold_for', return_value=0.8,
        ):
            result = click_action.click_contextual_item_with_result(
                worker,
                'already_end',
                'already_end',
                'ok',
                'ok',
                search_region=(0.2, 0.2, 0.8, 0.85),
            )

        self.assertEqual(result, 1)
        click_auto.assert_not_called()


class RefreshInputTimingTests(unittest.TestCase):
    def test_template_click_records_actual_click_timestamp(self):
        class Worker:
            _last_automation_click_at = None
            _next_automation_input_at = 0.0

            def _running(self):
                return True

        worker = Worker()
        with patch.object(click_behavior.pyautogui, 'moveTo'), \
                patch.object(click_behavior.pyautogui, 'click'), \
                patch.object(click_behavior, '_record_automation_position'), \
                patch.object(click_behavior.time, 'sleep'), \
                patch.object(click_behavior.time, 'monotonic', return_value=123.25):
            result = click_behavior.click_auto((100, 200), worker._running)

        self.assertEqual(result, 2)
        self.assertEqual(worker._last_automation_click_at, 123.25)

    def test_refresh_interval_includes_processing_before_next_input(self):
        waits = []

        class Worker:
            _next_automation_input_at = 104.5

            def _running(self):
                return True

            def _wait(self, seconds):
                waits.append(seconds)
                return False

        worker = Worker()
        with patch.object(click_behavior.time, 'monotonic',
                          side_effect=(102.0, 104.5)):
            ready = click_behavior.wait_for_automation_input_deadline(
                worker._running,
            )

        self.assertTrue(ready)
        self.assertEqual(waits, [2.5])
        self.assertEqual(worker._next_automation_input_at, 0.0)

    def test_refresh_deadline_uses_actual_mouse_click_timestamp(self):
        class Worker:
            signal = types.SimpleNamespace(emit=lambda _message: None)
            _last_automation_click_at = 90.0
            _next_automation_input_at = 0.0

            def _click_until(self, _picture, _name):
                self._last_automation_click_at = 100.0
                return 2

        worker = Worker()
        result = link_raid.LinkRaidWorker._refresh_battle_list(worker)

        self.assertEqual(result, 2)
        self.assertEqual(
            worker._next_automation_input_at,
            100.0 + link_raid.REFRESH_MIN_CLICK_INTERVAL,
        )


class LinkRaidLevelSearchTests(unittest.TestCase):
    class Signal:
        @staticmethod
        def emit(_message):
            pass

    def test_scan_passes_priority_and_independent_participant_rules(self):
        class Worker:
            signal = LinkRaidLevelSearchTests.Signal()
            level_choices = [12, 6]
            skip_nine_rooms = False
            skip_ten_rooms = True
            _running = staticmethod(lambda: True)

        worker = Worker()
        with patch.object(
                link_raid.click_action, 'find_competing_item_with_result',
                return_value=1,
        ) as find_competing, patch.object(
                link_raid.click_action, 'find_item_with_result', return_value=2,
        ):
            result = link_raid.LinkRaidWorker._scan_lv(worker)

        self.assertEqual(result, 1)
        args, kwargs = find_competing.call_args
        self.assertEqual(args[1], [12, 6])
        self.assertEqual(args[3], 'LV12 > LV6')
        self.assertEqual(kwargs['skip_participant_counts'], (10,))

    def test_rescans_before_one_scroll_then_scans_final_time(self):
        events = []
        outcomes = iter((0, 2))

        class Worker:
            signal = LinkRaidLevelSearchTests.Signal()
            level_choices = [6]

            @staticmethod
            def _running():
                return True

            @staticmethod
            def _scan_lv():
                events.append('scan')
                return next(outcomes)

            @staticmethod
            def _wait(seconds):
                events.append(('wait', seconds))
                return False

        def move_once(*_args, **_kwargs):
            events.append('scroll')
            return 2

        with patch.object(
                link_raid.click_action, 'move_a_to_b_scaled',
                side_effect=move_once,
        ) as move:
            result = link_raid.LinkRaidWorker._find_lv_by_scroll(Worker())

        self.assertEqual(result, 2)
        self.assertEqual(events, [
            'scan', 'scroll', ('wait', link_raid.SCROLL_SETTLE_DELAY), 'scan',
        ])
        move.assert_called_once()

    def test_successful_rescan_avoids_scroll(self):
        class Worker:
            signal = LinkRaidLevelSearchTests.Signal()
            level_choices = [6]
            _running = staticmethod(lambda: True)
            _scan_lv = staticmethod(lambda: 2)
            _wait = staticmethod(lambda _seconds: False)

        with patch.object(
                link_raid.click_action, 'move_a_to_b_scaled',
        ) as move:
            result = link_raid.LinkRaidWorker._find_lv_by_scroll(Worker())

        self.assertEqual(result, 2)
        move.assert_not_called()


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
                patch.object(
                    link_raid.click_action, 'click_contextual_item_with_result',
                    return_value=2,
                ) as contextual_click, \
                patch.object(link_raid.click_action, 'find_item_with_result',
                             side_effect=find_item):
            link_raid.LinkRaidWorker.join_battle(worker)

        contextual_click.assert_called_once_with(
            worker,
            './aim/quests/link_raid/backup_requests/join/full/battle_full',
            'battle_full',
            './aim/quests/link_raid/backup_requests/join/full/ok',
            'ok',
            search_region=link_raid.JOIN_DIALOG_SEARCH_REGION,
        )
        self.assertEqual(clicked[1][0], './aim/quests/link_raid/backup_requests/join')
        self.assertEqual(clicked[-1][0], './aim/quests/link_raid/backup_requests/join/play')
        self.assertTrue(any(
            step[0].endswith('battle_full') for step in clicked[0][2]
        ))

    def test_delayed_already_end_is_recovered_while_waiting_for_battle_result(self):
        events = []
        already_end = (
            './aim/quests/link_raid/backup_requests/join/full/already_end',
            'already_end',
        )
        tap = (
            './aim/quests/link_raid/backup_requests/battle/tap_to_countinue',
            'tap_to_countinue',
        )
        back = (
            './aim/quests/link_raid/backup_requests/battle/back',
            'back',
        )

        class Worker:
            signal = LinkRaidRecoveryTests.Signal()
            _wait_battle_outcome = link_raid.LinkRaidWorker._wait_battle_outcome
            _recover_already_ended_battle = \
                link_raid.LinkRaidWorker._recover_already_ended_battle

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
                raise AssertionError('不应停止任务')

            @staticmethod
            def _click_until(picture, _name, *args, **kwargs):
                events.append(('click', picture))
                return 2

            @staticmethod
            def prepare_matching_battle():
                events.append(('prepare', None))
                return True

            @staticmethod
            def join_battle():
                events.append(('join', None))

        with patch.object(
                link_raid.click_action, 'find_first_item_with_result',
                side_effect=(None, already_end, tap, back),
        ), patch.object(
                link_raid.click_action, 'click_contextual_item_with_result',
                return_value=2,
        ) as contextual_click, patch.object(
                link_raid.click_action, 'click_fixed_position_for_item_with_result',
                return_value=2,
        ) as fixed_click:
            link_raid.LinkRaidWorker.battle_and_finish(Worker())

        self.assertEqual(events, [
            ('prepare', None),
            ('join', None),
            ('click', './aim/quests/link_raid/backup_requests/battle/back'),
        ])
        contextual_click.assert_called_once_with(
            ANY,
            already_end[0],
            already_end[1],
            './aim/quests/link_raid/backup_requests/join/ok',
            'ok',
            search_region=link_raid.JOIN_DIALOG_SEARCH_REGION,
        )
        fixed_click.assert_called_once()

    def test_single_frame_already_end_false_positive_never_clicks_ok(self):
        already_end = (
            './aim/quests/link_raid/backup_requests/join/full/already_end',
            'already_end',
        )
        tap = (
            './aim/quests/link_raid/backup_requests/battle/tap_to_countinue',
            'tap_to_countinue',
        )
        back = (
            './aim/quests/link_raid/backup_requests/battle/back',
            'back',
        )

        class Worker:
            signal = LinkRaidRecoveryTests.Signal()

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
                raise AssertionError('不应停止任务')

        with patch.object(
                link_raid.click_action, 'find_first_item_with_result',
                side_effect=(already_end, tap, back),
        ), patch.object(
                link_raid.click_action, 'click_contextual_item_with_result',
                return_value=1,
        ) as contextual_click, patch.object(
                link_raid.click_action, 'click_fixed_position_for_item_with_result',
                return_value=2,
        ) as fixed_click:
            result = link_raid.LinkRaidWorker._wait_battle_outcome(Worker())

        self.assertEqual(result, 'finished')
        contextual_click.assert_called_once()
        fixed_click.assert_called_once()

    def test_battle_result_checks_back_only_after_confirmed_tap_click(self):
        captured_states = []
        tap = (
            './aim/quests/link_raid/backup_requests/battle/tap_to_countinue',
            'tap_to_countinue',
        )
        back = (
            './aim/quests/link_raid/backup_requests/battle/back',
            'back',
        )

        class Worker:
            signal = LinkRaidRecoveryTests.Signal()

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
                raise AssertionError('不应停止任务')

        def find_state(_worker, states):
            captured_states.append(states)
            return tap if len(captured_states) == 1 else back

        with patch.object(
                link_raid.click_action, 'find_first_item_with_result',
                side_effect=find_state,
        ), patch.object(
                link_raid.click_action, 'click_fixed_position_for_item_with_result',
                return_value=2,
        ):
            result = link_raid.LinkRaidWorker._wait_battle_outcome(Worker())

        self.assertEqual(result, 'finished')
        self.assertFalse(any(state[1] == 'back' for state in captured_states[0]))
        self.assertTrue(any(state[1] == 'back' for state in captured_states[1]))

class ScalerManifestTests(unittest.TestCase):
    def test_retired_official_template_is_removed_without_manifest(self):
        with TemporaryDirectory() as temp_dir:
            language_dir = Path(temp_dir) / 'language'
            source_dir = language_dir / 'EN' / 'EN_2560x1440'
            target_dir = language_dir / 'EN' / 'EN_1920x1080'
            retired = Path('quests/link_raid/backup_requests/battle/love_1.png')
            source_retired = source_dir / retired
            target_retired = target_dir / retired
            custom_target = target_dir / 'custom.png'
            current_source = source_dir / 'current.png'
            for path in (source_retired, target_retired, custom_target, current_source):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(path.name.encode('ascii'))

            def generate(_source, target, _factor, _is_cancelled=None):
                path = Path(target)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'generated')

            with patch.object(image_scaler, 'LANGUAGE_DIR', str(language_dir)), \
                    patch.object(image_scaler, '_run_magick', side_effect=generate):
                generated, _skipped, notes = image_scaler.scale_pack(
                    'EN', tool_fingerprint='test-tool',
                )

            manifest, status = image_scaler._load_manifest(str(target_dir))
            self.assertEqual(generated, 1)
            self.assertFalse(source_retired.exists())
            self.assertFalse(target_retired.exists())
            self.assertTrue(current_source.exists())
            self.assertTrue(custom_target.exists())
            self.assertTrue((target_dir / 'current.png').exists())
            self.assertEqual(status, 'ok')
            self.assertNotIn(retired.as_posix(), manifest)
            self.assertTrue(any('清理退役模板 2 张' in note for note in notes))

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

    def test_startup_update_offer_runs_before_template_refresh(self):
        events = []
        holder = types.SimpleNamespace(
            _closing=False,
            _update_job_id='startup-job',
            _update_state='checking',
            _update_check_thread=object(),
            _update_cancel=Mock(),
            _startup_update_check_pending=True,
            _refresh_control_state=lambda: None,
            _append_log=lambda *_args, **_kwargs: None,
            _offer_update=lambda _result: events.append('offer'),
            _refresh_templates_at_startup=Mock(),
        )
        holder._continue_startup_after_update = types.MethodType(
            mywindow._continue_startup_after_update, holder,
        )

        with patch('main.QTimer.singleShot',
                   side_effect=lambda *_args: events.append('refresh')):
            mywindow._on_update_checked(holder, 'startup-job', {
                'has_update': True,
                'message': '发现新版本',
            })

        self.assertEqual(events, ['offer', 'refresh'])
        self.assertFalse(holder._startup_update_check_pending)

    def test_accepted_startup_update_keeps_template_refresh_waiting(self):
        refresh = Mock()
        holder = types.SimpleNamespace(
            _startup_update_check_pending=True,
            _closing=False,
            _update_state='downloading',
            _refresh_templates_at_startup=refresh,
        )

        with patch('main.QTimer.singleShot') as single_shot:
            mywindow._continue_startup_after_update(holder)

        single_shot.assert_not_called()
        self.assertTrue(holder._startup_update_check_pending)

    def test_failed_startup_update_resumes_template_refresh(self):
        events = []

        def reset_update_state(cleanup):
            events.append(('reset', cleanup))
            holder._update_state = 'idle'

        holder = types.SimpleNamespace(
            _closing=False,
            _update_job_id='startup-job',
            _update_state='downloading',
            _update_prepare_thread=object(),
            _startup_update_check_pending=True,
            _append_log=lambda *_args, **_kwargs: None,
            _reset_update_state=reset_update_state,
            _refresh_templates_at_startup=Mock(),
        )
        holder._continue_startup_after_update = types.MethodType(
            mywindow._continue_startup_after_update, holder,
        )

        with patch('main.QTimer.singleShot',
                   side_effect=lambda *_args: events.append(('refresh', None))):
            mywindow._on_update_failed(holder, 'startup-job', '下载失败')

        self.assertEqual(events, [('reset', False), ('refresh', None)])
        self.assertFalse(holder._startup_update_check_pending)


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

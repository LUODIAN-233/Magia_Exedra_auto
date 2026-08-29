import json
import logging
import unittest
from unittest.mock import Mock

from src.core.notification import (DEDUPE_SECONDS, RETRY_DELAYS,
                                   NotificationManager)


class ImmediateThread:
    def __init__(self, target, args, daemon):
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self):
        self.target(*self.args)


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return json.dumps(self.payload).encode('utf-8')


def enabled_settings(**overrides):
    settings = {
        'enabled': True,
        'send_key': 'SCT_test_key_123456',
        'channels': [9, 8, 18],
        'events': {
            'worker_auto_ended': True,
            'lp_exhausted': True,
            'timeout': True,
            'worker_exception': True,
            'update_failed': True,
            'update_recovery_blocked': True,
        },
    }
    settings.update(overrides)
    return settings


class NotificationManagerTests(unittest.TestCase):
    def test_request_uses_at_most_two_official_channel_values(self):
        captured = {}

        def opener(request, timeout):
            captured['url'] = request.full_url
            captured['timeout'] = timeout
            captured['payload'] = json.loads(request.data.decode('utf-8'))
            return Response({'code': 0})

        manager = NotificationManager(
            enabled_settings(), opener=opener,
            thread_factory=ImmediateThread,
        )
        self.assertTrue(manager.notify(
            'timeout', 'link_raid', '等待战斗超时。', {'等级': ['LV12', 'LV6']},
        ))

        self.assertEqual(captured['payload']['channel'], '9|8')
        self.assertIn('SCT_test_key_123456.send', captured['url'])
        self.assertNotIn('SCT_test_key_123456', captured['payload']['desp'])
        self.assertEqual(captured['timeout'], 15)

    def test_same_event_is_deduplicated_for_ten_minutes(self):
        now = [100.0]
        opener = Mock(return_value=Response({'code': 0}))
        manager = NotificationManager(
            enabled_settings(), opener=opener, clock=lambda: now[0],
            thread_factory=ImmediateThread,
        )

        self.assertTrue(manager.notify('timeout', 'link_raid', '同一原因'))
        self.assertFalse(manager.notify('timeout', 'link_raid', '同一原因'))
        now[0] += DEDUPE_SECONDS
        self.assertTrue(manager.notify('timeout', 'link_raid', '同一原因'))
        self.assertEqual(opener.call_count, 2)

    def test_failure_retries_three_times_with_increasing_delays(self):
        sleeps = []

        def opener(_request, timeout):
            self.assertEqual(timeout, 15)
            raise OSError('SCT_secret_must_not_escape')

        manager = NotificationManager(
            enabled_settings(), opener=opener, sleeper=sleeps.append,
            thread_factory=ImmediateThread,
        )
        with self.assertLogs('src.core.notification', logging.WARNING) as logs:
            self.assertTrue(manager.notify('update_failed', '应用更新', '下载失败'))

        self.assertEqual(sleeps, list(RETRY_DELAYS))
        self.assertNotIn('SCT_secret_must_not_escape', '\n'.join(logs.output))
        self.assertNotIn('SCT_test_key_123456', '\n'.join(logs.output))

    def test_test_notification_bypasses_master_switch_and_dedupe(self):
        opener = Mock(return_value=Response({'code': 0}))
        results = []
        manager = NotificationManager(
            enabled_settings(enabled=False), opener=opener,
            thread_factory=ImmediateThread,
        )

        self.assertTrue(manager.send_test(lambda ok, message: results.append((ok, message))))
        self.assertTrue(manager.send_test(lambda ok, message: results.append((ok, message))))
        self.assertEqual(opener.call_count, 2)
        self.assertTrue(all(result[0] for result in results))

    def test_disabled_or_unselected_event_does_not_start_request(self):
        settings = enabled_settings(enabled=False)
        opener = Mock(return_value=Response({'code': 0}))
        manager = NotificationManager(
            settings, opener=opener, thread_factory=ImmediateThread,
        )
        self.assertFalse(manager.notify('timeout', 'link_raid', '不会发送'))

        settings['enabled'] = True
        settings['events']['timeout'] = False
        manager.configure(settings)
        self.assertFalse(manager.notify('timeout', 'link_raid', '不会发送'))
        opener.assert_not_called()


if __name__ == '__main__':
    unittest.main()

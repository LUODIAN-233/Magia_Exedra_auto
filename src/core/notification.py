import copy
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from .app_settings import normalize_notification_settings


logger = logging.getLogger(__name__)

SERVERCHAN_API_ROOT = 'https://sctapi.ftqq.com'
SERVERCHAN_CHANNELS = (
    (9, '微信服务号'),
    (0, '微信测试号'),
    (66, '企业微信应用消息'),
    (1, '企业微信群机器人'),
    (2, '钉钉群机器人'),
    (3, '飞书群机器人'),
    (8, 'Bark iOS'),
    (18, 'PushDeer'),
    (98, '官方 Android 客户端'),
    (88, '自定义 Webhook'),
)
NOTIFICATION_EVENTS = (
    ('worker_auto_ended', '脚本自动结束'),
    ('lp_exhausted', '体力恢复次数耗尽'),
    ('timeout', '识图或战斗超时'),
    ('worker_exception', '挂机线程异常退出'),
    ('update_failed', '更新失败'),
    ('update_recovery_blocked', '更新恢复标记阻止挂机'),
)
EVENT_TITLES = dict(NOTIFICATION_EVENTS)
EVENT_TITLES['test'] = '测试通知'
SEND_KEY_PATTERN = re.compile(r'^SCT[A-Za-z0-9_-]{5,253}$')
DEDUPE_SECONDS = 10 * 60
RETRY_DELAYS = (2, 5, 10)
MAX_RESPONSE_BYTES = 64 * 1024


class NotificationSendError(Exception):
    pass


def valid_send_key(value):
    return isinstance(value, str) and SEND_KEY_PATTERN.fullmatch(value) is not None


def _safe_text(value, limit=240):
    text = str(value).replace('\r', ' ').replace('\n', ' ').strip()
    return text[:limit] if text else '未提供'


def _parameter_lines(params):
    if not isinstance(params, dict):
        return []
    lines = []
    for key, value in params.items():
        if not isinstance(key, str) or not key or len(lines) >= 12:
            continue
        if isinstance(value, (list, tuple)):
            value = ' > '.join(_safe_text(item, 32) for item in value[:20])
        elif not isinstance(value, (str, bool, int, float)) and value is not None:
            continue
        lines.append(f'- {_safe_text(key, 48)}: {_safe_text(value)}')
    return lines


def build_message(event_key, mode, reason, params=None, occurred_at=None):
    event_name = EVENT_TITLES.get(event_key, '重大事件')
    timestamp = occurred_at or datetime.now().astimezone()
    title = f'Magia Exedra：{event_name}'[:32]
    lines = [
        f'**事件**：{event_name}',
        f'**挂机模式**：{_safe_text(mode, 64)}',
        f'**发生时间**：{timestamp.strftime("%Y-%m-%d %H:%M:%S %z")}',
        f'**原因**：{_safe_text(reason, 500)}',
    ]
    param_lines = _parameter_lines(params)
    if param_lines:
        lines.extend(('', '**相关参数**：', *param_lines))
    return title, '\n\n'.join(lines[:4]) + ('\n' + '\n'.join(lines[4:]) if len(lines) > 4 else '')


class NotificationManager:
    def __init__(self, settings=None, opener=None, sleeper=None, clock=None,
                 thread_factory=None):
        self._lock = threading.Lock()
        self._settings = normalize_notification_settings(settings)
        self._last_events = {}
        self._opener = opener or urllib.request.urlopen
        self._sleeper = sleeper or time.sleep
        self._clock = clock or time.monotonic
        self._thread_factory = thread_factory or threading.Thread

    def configure(self, settings):
        with self._lock:
            self._settings = normalize_notification_settings(settings)

    def settings_snapshot(self):
        with self._lock:
            return copy.deepcopy(self._settings)

    def notify(self, event_key, mode, reason, params=None):
        now = self._clock()
        with self._lock:
            settings = copy.deepcopy(self._settings)
            if not settings['enabled'] or not settings['events'].get(event_key, False) \
                    or not valid_send_key(settings['send_key']) or not settings['channels']:
                return False
            dedupe_key = (event_key, _safe_text(mode, 64), _safe_text(reason, 240))
            previous = self._last_events.get(dedupe_key)
            if previous is not None and now - previous < DEDUPE_SECONDS:
                return False
            self._last_events[dedupe_key] = now
            expired = [key for key, sent_at in self._last_events.items()
                       if now - sent_at >= DEDUPE_SECONDS]
            for key in expired:
                self._last_events.pop(key, None)
        title, desp = build_message(event_key, mode, reason, params)
        self._start_thread(self._deliver, settings, title, desp, None)
        return True

    def send_test(self, callback=None):
        settings = self.settings_snapshot()
        if not valid_send_key(settings['send_key']) or not settings['channels']:
            if callback is not None:
                callback(False, '请先填写有效的 SendKey，并至少选择一个通道。')
            return False
        title = 'Magia Exedra：测试通知'
        _title, desp = build_message(
            'test', '应用设置', '这是由设置页面发出的测试通知。',
        )
        self._start_thread(self._deliver, settings, title, desp, callback)
        return True

    def _start_thread(self, target, *args):
        thread = self._thread_factory(target=target, args=args, daemon=True)
        thread.start()

    def _deliver(self, settings, title, desp, callback):
        attempts = 1 + len(RETRY_DELAYS)
        error_message = '发送失败。'
        for attempt in range(attempts):
            try:
                self._send_once(settings, title, desp)
                if callback is not None:
                    try:
                        callback(True, '测试通知发送成功。')
                    except Exception:
                        pass
                return
            except NotificationSendError as error:
                error_message = str(error)
                if attempt < len(RETRY_DELAYS):
                    self._sleeper(RETRY_DELAYS[attempt])
        logger.warning('Server酱通知在 %d 次尝试后仍失败：%s', attempts, error_message)
        if callback is not None:
            try:
                callback(False, f'测试通知发送失败：{error_message}')
            except Exception:
                pass

    def _send_once(self, settings, title, desp):
        send_key = settings['send_key']
        if not valid_send_key(send_key):
            raise NotificationSendError('SendKey 格式无效。')
        payload = json.dumps({
            'title': title[:32],
            'desp': desp,
            'channel': '|'.join(str(channel) for channel in settings['channels']),
        }, ensure_ascii=False).encode('utf-8')
        url = f'{SERVERCHAN_API_ROOT}/{urllib.parse.quote(send_key, safe="")}.send'
        request = urllib.request.Request(
            url,
            data=payload,
            headers={'Content-Type': 'application/json;charset=utf-8'},
            method='POST',
        )
        try:
            with self._opener(request, timeout=15) as response:
                raw = response.read(MAX_RESPONSE_BYTES)
        except (OSError, urllib.error.URLError, ValueError):
            raise NotificationSendError('网络请求失败。') from None
        try:
            result = json.loads(raw.decode('utf-8'))
        except (UnicodeError, ValueError):
            raise NotificationSendError('服务返回了无法解析的响应。') from None
        if not isinstance(result, dict) or result.get('code') != 0:
            raise NotificationSendError('服务拒绝了本次请求，请检查 SendKey、通道和额度。')

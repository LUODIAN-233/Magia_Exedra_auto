import json
import logging
import os
import sys
import tempfile


logger = logging.getLogger(__name__)

GUI_LOG_LEVELS = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
DEFAULT_LOG_RETENTION_DAYS = 7


def _base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


SETTINGS_PATH = os.path.join(_base_dir(), 'settings.json')


def _read_settings():
    try:
        with open(SETTINGS_PATH, 'r', encoding='utf-8') as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, TypeError) as error:
        logger.warning('读取应用设置失败，将使用默认值: %s', error)
        return {}


def _write_settings(data):
    temp_path = None
    try:
        directory = os.path.dirname(SETTINGS_PATH)
        os.makedirs(directory, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix='.settings.', suffix='.tmp', dir=directory)
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=True, indent=2, sort_keys=True)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, SETTINGS_PATH)
        return True
    except OSError as error:
        logger.warning('保存应用设置失败: %s', error)
        return False
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def load_log_level(default='INFO'):
    fallback = default if default in GUI_LOG_LEVELS else 'INFO'
    data = _read_settings()
    #兼容 2.4.0-beta.1 旧键名。
    level = data.get('log_level', data.get('gui_log_level'))
    return level if level in GUI_LOG_LEVELS else fallback


def save_log_level(level):
    if level not in GUI_LOG_LEVELS:
        return False
    data = _read_settings()
    data['log_level'] = level
    data.pop('gui_log_level', None)
    return _write_settings(data)


def load_log_retention_days(default=DEFAULT_LOG_RETENTION_DAYS):
    fallback = default if isinstance(default, int) and 1 <= default <= 365 else DEFAULT_LOG_RETENTION_DAYS
    days = _read_settings().get('log_retention_days')
    return days if isinstance(days, int) and 1 <= days <= 365 else fallback


def save_log_retention_days(days):
    if not isinstance(days, int) or not 1 <= days <= 365:
        return False
    data = _read_settings()
    data['log_retention_days'] = days
    return _write_settings(data)


def load_automation_mode(default=None):
    mode = _read_settings().get('automation_mode')
    return mode if isinstance(mode, str) and mode else default


def save_automation_mode(mode):
    if not isinstance(mode, str) or not mode or len(mode) > 64:
        return False
    data = _read_settings()
    data['automation_mode'] = mode
    return _write_settings(data)

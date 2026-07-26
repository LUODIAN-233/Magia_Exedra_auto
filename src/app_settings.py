import json
import logging
import os
import sys
import tempfile


logger = logging.getLogger(__name__)

GUI_LOG_LEVELS = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')


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


def load_gui_log_level(default='WARNING'):
    fallback = default if default in GUI_LOG_LEVELS else 'WARNING'
    level = _read_settings().get('gui_log_level')
    return level if level in GUI_LOG_LEVELS else fallback


def save_gui_log_level(level):
    if level not in GUI_LOG_LEVELS:
        return False
    data = _read_settings()
    data['gui_log_level'] = level
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

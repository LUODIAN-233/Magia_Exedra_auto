import logging
import math
import os
import threading
from pathlib import Path

from src.packs import language_switcher


logger = logging.getLogger(__name__)

CONFIG_PATH = Path(language_switcher.BASE_DIR) / 'resource' / 'template_confidence.txt'

_cache_lock = threading.RLock()
_CACHE_UNSET = object()
_cache_signature = _CACHE_UNSET
_cache_entries = {}
_cache_errors = []
_warned_lookups = set()


def _normalize_key(raw):
    key = raw.strip().replace('\\', '/')
    while key.startswith('./'):
        key = key[2:]
    parts = key.split('/')
    if not key or key.startswith('/') or ':' in key \
            or any(not part or part in ('.', '..') for part in parts) \
            or not key.lower().endswith('.png'):
        return None
    return '/'.join(parts).casefold()


def _signature():
    try:
        stat = CONFIG_PATH.stat()
        return stat.st_mtime_ns, stat.st_size
    except OSError:
        return None


def _load_config():
    global _cache_signature, _cache_entries, _cache_errors, _warned_lookups
    signature = _signature()
    with _cache_lock:
        if signature == _cache_signature:
            return _cache_entries, _cache_errors

        entries = {}
        errors = []
        try:
            lines = CONFIG_PATH.read_text(encoding='utf-8-sig').splitlines()
        except OSError as error:
            lines = []
            errors.append(f'无法读取置信度配置 {CONFIG_PATH}: {error}')

        for line_number, raw_line in enumerate(lines, 1):
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue
            key_text, separator, value_text = line.partition('=')
            key = _normalize_key(key_text)
            if not separator or key is None:
                errors.append(f'置信度配置第 {line_number} 行格式无效')
                continue
            try:
                value = float(value_text.strip())
            except ValueError:
                errors.append(f'置信度配置第 {line_number} 行不是数字')
                continue
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                errors.append(f'置信度配置第 {line_number} 行必须在 0.0-1.0 之间')
                continue
            if key in entries:
                errors.append(f'置信度配置第 {line_number} 行重复: {key_text.strip()}')
                continue
            entries[key] = value

        _cache_signature = signature
        _cache_entries = entries if not errors else {}
        _cache_errors = errors
        _warned_lookups = set()
        if errors:
            logger.error('置信度配置加载失败：%s', '；'.join(errors[:10]))
        else:
            logger.info('已加载 %d 项模板置信度配置', len(entries))
        return _cache_entries, _cache_errors


def _logical_path(template_path):
    normalized = str(template_path).replace('\\', '/')
    parts = [part for part in normalized.split('/') if part and part != '.']
    lowered = [part.casefold() for part in parts]
    if 'aim' in lowered:
        index = len(lowered) - 1 - lowered[::-1].index('aim')
        relative = parts[index + 1:]
    elif 'language' in lowered:
        index = len(lowered) - 1 - lowered[::-1].index('language')
        relative = parts[index + 3:]
    elif parts and parts[0].casefold() in ('crystalis', 'quests'):
        relative = parts
    else:
        return None
    key = _normalize_key('/'.join(relative))
    return key


def _candidate_keys(relative, selection):
    if selection and len(selection) >= 2:
        lang, resolution = selection[:2]
        if lang and resolution:
            yield f'{lang}/{resolution}/{relative}'.casefold()
        if lang:
            yield f'{lang}/{relative}'.casefold()
    yield relative.casefold()


def _lookup(entries, relative, selection):
    for key in _candidate_keys(relative, selection):
        if key in entries:
            return entries[key], key
    return None, None


def threshold_for(template_path, selection=None):
    """返回实际模板的独立阈值；配置不可用或缺项时返回 None。"""
    entries, errors = _load_config()
    if errors:
        return None
    relative = _logical_path(template_path)
    if relative is None:
        warning_key = ('invalid-path', str(template_path))
        message = f'无法映射模板置信度路径: {template_path}'
    else:
        active = selection if selection is not None else language_switcher.current_selection()
        threshold, _key = _lookup(entries, relative, active)
        if threshold is not None:
            return threshold
        warning_key = ('missing', active, relative)
        message = f'模板缺少独立置信度配置: {relative}'
    with _cache_lock:
        if warning_key not in _warned_lookups:
            _warned_lookups.add(warning_key)
            logger.error(message)
    return None


def validate_pack(lang, resolution):
    """确认当前模板包中的每张 PNG 都能解析到独立阈值。"""
    entries, errors = _load_config()
    if errors:
        return False, list(errors)
    root = Path(language_switcher.LANGUAGE_DIR) / lang / f'{lang}_{resolution}'
    if not root.is_dir():
        return False, [f'模板 pack 不存在: {lang}_{resolution}']
    missing = []
    png_count = 0
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [
            name for name in dirs
            if not language_switcher._is_link(os.path.join(current_root, name))
        ]
        for filename in files:
            if not filename.lower().endswith('.png'):
                continue
            path = Path(current_root) / filename
            if language_switcher._is_link(str(path)):
                continue
            png_count += 1
            relative = path.relative_to(root).as_posix().casefold()
            threshold, _key = _lookup(entries, relative, (lang, resolution))
            if threshold is None:
                missing.append(f'缺少置信度: {relative}')
    if png_count == 0:
        return False, [f'模板 pack 没有 PNG: {lang}_{resolution}']
    return not missing, missing


def reset_cache_for_tests():
    global _cache_signature, _cache_entries, _cache_errors, _warned_lookups
    with _cache_lock:
        _cache_signature = _CACHE_UNSET
        _cache_entries = {}
        _cache_errors = []
        _warned_lookups = set()

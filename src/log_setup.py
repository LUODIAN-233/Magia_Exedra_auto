#日志配置模块
#统一管理全项目的日志输出，替代散落在各模块的 print()。
#
#设计：
#- 控制台 handler：默认 WARNING 级别（仅警告/错误上屏，避免识图重试刷屏）；
#  可用环境变量 MAGIA_LOG_LEVEL=DEBUG/INFO/WARNING 覆盖，方便开发时排查。
#- 文件 handler：启动时读取 settings.json 中的日志等级，GUI 设置可在运行时同步调整。
#  日志目录不可写时退化为仅控制台，不阻塞启动。
#- 各业务模块用 logging.getLogger(__name__) 获取独立 logger，命名按模块自动分层。
#- worker 的 signal.emit 仍保留，那是面向 GUI 日志框的用户可见消息，不属于调试日志。
#
#只依赖标准库，不依赖 PySide6，import 早于 cv2/pyautogui 也安全。

import logging
import logging.handlers
import json
import os
import re
import sys
import time
from datetime import datetime


_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

_LOG_FILE_PATTERN = re.compile(r'^magia_\d{8}_\d{6}\.log(?:\.\d+)?$')


def _base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _log_dir():
    #日志目录：打包用 exe 同级 logs/，源码用仓库根 logs/（本文件位于 src/）
    return os.path.join(_base_dir(), "logs")


def _saved_file_level(default=logging.INFO):
    """启动早期读取持久化等级，避免业务模块先向文件写入 DEBUG。"""
    try:
        with open(os.path.join(_base_dir(), 'settings.json'), 'r', encoding='utf-8') as file:
            data = json.load(file)
        if not isinstance(data, dict):
            return default
        level = data.get('log_level', data.get('gui_log_level'))
        return _LEVELS.get(str(level).strip().upper(), default)
    except (FileNotFoundError, OSError, ValueError, TypeError):
        #此时 logging 尚未配置，不能在这里记录读取失败。
        return default


def _saved_retention_days(default=7):
    """启动早期读取日志保留天数；非法配置回退到 7 天。"""
    fallback = default if isinstance(default, int) and 1 <= default <= 365 else 7
    try:
        with open(os.path.join(_base_dir(), 'settings.json'), 'r', encoding='utf-8') as file:
            data = json.load(file)
        if not isinstance(data, dict):
            return fallback
        days = data.get('log_retention_days')
        return days if isinstance(days, int) and 1 <= days <= 365 else fallback
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return fallback


def _resolve_console_level(default):
    #环境变量 MAGIA_LOG_LEVEL 覆盖控制台级别，大小写不敏感；非法值回退默认
    raw = os.environ.get("MAGIA_LOG_LEVEL")
    if not raw:
        return default
    return _LEVELS.get(raw.strip().upper(), default)


def set_file_log_level(level):
    """调整本模块创建的滚动文件 handler；返回是否找到可用 handler。"""
    value = _LEVELS.get(level.strip().upper()) if isinstance(level, str) else None
    if value is None:
        return False
    changed = False
    for handler in logging.getLogger().handlers:
        if getattr(handler, '_magia_file_handler', False):
            handler.setLevel(value)
            changed = True
    return changed


def cleanup_old_logs(retention_days=7, now=None):
    """删除超过保留天数的 Magia 日志，保留当前进程正在使用的日志族。"""
    if not isinstance(retention_days, int) or not 1 <= retention_days <= 365:
        retention_days = 7
    cutoff = (time.time() if now is None else float(now)) - retention_days * 24 * 60 * 60
    active_bases = set()
    for handler in logging.getLogger().handlers:
        if getattr(handler, '_magia_file_handler', False):
            base_filename = getattr(handler, 'baseFilename', None)
            if base_filename:
                active_bases.add(os.path.basename(os.path.abspath(base_filename)))

    removed = []
    failed = []
    log_dir = _log_dir()
    try:
        entries = list(os.scandir(log_dir))
    except FileNotFoundError:
        return {'removed': removed, 'failed': failed, 'kept': sorted(active_bases)}
    except OSError as error:
        return {
            'removed': removed,
            'failed': [(log_dir, str(error))],
            'kept': sorted(active_bases),
        }

    for entry in entries:
        name = entry.name
        if not _LOG_FILE_PATTERN.fullmatch(name):
            continue
        if any(name == base or name.startswith(base + '.') for base in active_bases):
            continue
        try:
            if not entry.is_file(follow_symlinks=False):
                continue
            if entry.stat(follow_symlinks=False).st_mtime >= cutoff:
                continue
            os.remove(entry.path)
            removed.append(name)
        except OSError as error:
            failed.append((name, str(error)))
    return {'removed': removed, 'failed': failed, 'kept': sorted(active_bases)}


def configure_logging(console_level=logging.WARNING, file_level=None,
                      max_bytes=2 * 1024 * 1024, backup_count=3, enable_file=True):
    #在 main.py 启动早期调用一次。重复调用会先清除旧 handler，避免重复输出。
    #返回根 logger。控制台实际级别会被 MAGIA_LOG_LEVEL 环境变量覆盖。
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    #Pillow 解码 PNG 时会为每个数据块输出 DEBUG，容易淹没实际识图流程。
    logging.getLogger('PIL').setLevel(logging.WARNING)
    if file_level is None:
        file_level = _saved_file_level()
    for h in list(root.handlers):
        root.removeHandler(h)
        try:
            h.close()
        except Exception:
            #第三方 handler 的 close 不应阻塞应用日志初始化。
            pass
    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    console = None
    file_handler_ready = False
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setLevel(_resolve_console_level(console_level))
        console.setFormatter(fmt)
        root.addHandler(console)
    if enable_file:
        try:
            os.makedirs(_log_dir(), exist_ok=True)
            log_file = os.path.join(
                _log_dir(), f"magia_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            )
            file_h = logging.handlers.RotatingFileHandler(
                log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8",
            )
            file_h._magia_file_handler = True
            file_h.setLevel(file_level)
            file_h.setFormatter(fmt)
            root.addHandler(file_h)
            file_handler_ready = True
        except OSError:
            #日志目录不可写时退化为仅控制台，不阻塞启动
            if console is not None:
                console.setLevel(min(console.level, logging.INFO))
    if file_handler_ready:
        cleanup_result = cleanup_old_logs(_saved_retention_days())
        cleanup_logger = logging.getLogger(__name__)
        if cleanup_result['failed']:
            cleanup_logger.warning(
                '自动清理过时日志未完全完成：已删除 %s 个，失败 %s 个',
                len(cleanup_result['removed']), len(cleanup_result['failed']),
            )
        elif cleanup_result['removed']:
            cleanup_logger.info(
                '已自动清理 %s 个超过保留期限的日志', len(cleanup_result['removed']),
            )
    return root


if __name__ == "__main__":
    #单独运行时验证配置：分别打各级别一条，看控制台与文件是否生效
    configure_logging(console_level=logging.DEBUG, file_level=logging.DEBUG)
    logger = logging.getLogger("log_setup_test")
    logger.debug("调试消息")
    logger.info("信息消息")
    logger.warning("警告消息")
    logger.error("错误消息")
    print("日志目录:", _log_dir())

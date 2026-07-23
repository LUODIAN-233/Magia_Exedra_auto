#日志配置模块
#统一管理全项目的日志输出，替代散落在各模块的 print()。
#
#设计：
#- 控制台 handler：默认 WARNING 级别（仅警告/错误上屏，避免识图重试刷屏）；
#  可用环境变量 MAGIA_LOG_LEVEL=DEBUG/INFO/WARNING 覆盖，方便开发时排查。
#- 文件 handler：DEBUG 级别，滚动写入 exe/仓库根的 logs/ 目录，便于事后排查。
#  日志目录不可写时退化为仅控制台，不阻塞启动。
#- 各业务模块用 logging.getLogger(__name__) 获取独立 logger，命名按模块自动分层。
#- worker 的 signal.emit 仍保留，那是面向 GUI 日志框的用户可见消息，不属于调试日志。
#
#只依赖标准库，不依赖 PySide6，import 早于 cv2/pyautogui 也安全。

import logging
import logging.handlers
import os
import sys
from datetime import datetime


_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def _log_dir():
    #日志目录：打包用 exe 同级 logs/，源码用仓库根 logs/（本文件位于 src/）
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "logs")


def _resolve_console_level(default):
    #环境变量 MAGIA_LOG_LEVEL 覆盖控制台级别，大小写不敏感；非法值回退默认
    raw = os.environ.get("MAGIA_LOG_LEVEL")
    if not raw:
        return default
    return _LEVELS.get(raw.strip().upper(), default)


def configure_logging(console_level=logging.WARNING, file_level=logging.DEBUG,
                      max_bytes=2 * 1024 * 1024, backup_count=3, enable_file=True):
    #在 main.py 启动早期调用一次。重复调用会先清除旧 handler，避免重复输出。
    #返回根 logger。控制台实际级别会被 MAGIA_LOG_LEVEL 环境变量覆盖。
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for h in list(root.handlers):
        root.removeHandler(h)
    fmt = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
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
            file_h.setLevel(file_level)
            file_h.setFormatter(fmt)
            root.addHandler(file_h)
        except OSError:
            #日志目录不可写时退化为仅控制台，不阻塞启动
            console.setLevel(min(console.level, logging.INFO))
    return root


if __name__ == "__main__":
    #单独运行时验证配置：分别打各级别一条，看控制台与文件是否生效
    configure_logging(console_level=logging.DEBUG)
    logger = logging.getLogger("log_setup_test")
    logger.debug("调试消息")
    logger.info("信息消息")
    logger.warning("警告消息")
    logger.error("错误消息")
    print("日志目录:", _log_dir())

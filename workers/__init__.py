#挂机工作线程包
#把原来挤在 main.py 里的两个 QThread 工作线程拆出来：
#  base.py       公共基类（运行/停止状态、日志信号、点击重试与超时停止）
#  link_raid.py  Link Raid 挂机流程
#  crystalis.py  晶花挂机流程
#GUI（main.py）只负责构造工作线程、设置参数和启动/停止，不再包含任何挂机流程代码。

from .base import BaseWorker, retry_until, RETRY_TIMEOUT, BATTLE_TIMEOUT
from .link_raid import LinkRaidWorker
from .crystalis import CrystalisWorker

__all__ = [
    "BaseWorker",
    "retry_until",
    "RETRY_TIMEOUT",
    "BATTLE_TIMEOUT",
    "LinkRaidWorker",
    "CrystalisWorker",
]

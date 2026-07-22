#挂机工作线程包
#把原来挤在 main.py 里的两个 QThread 工作线程拆出来：
#  base.py       公共基类（运行/停止状态、日志信号、点击重试与超时停止）
#  registry.py   注册表：worker 用 @register 自描述参数，GUI 遍历 REGISTRY 自动生成控件
#  link_raid.py  Link Raid 挂机流程
#  crystalis.py  晶花挂机流程
#GUI（main.py）只负责遍历 REGISTRY 生成控件、收集参数、启动/停止，不再包含任何挂机流程代码。
#
#新增挂机模式：写一个 BaseWorker 子类文件，用 @register 声明参数，在这里 import 一行即可，
#main.py 的 GUI 会自动出现对应按钮和参数控件。

from .base import BaseWorker, retry_until, RETRY_TIMEOUT, BATTLE_TIMEOUT
from .registry import register, ParamSpec, WorkerMeta, REGISTRY, get_registry
#导入以下子模块是为了触发它们内部的 @register 装饰器，把模式登记进 REGISTRY
from .link_raid import LinkRaidWorker
from .crystalis import CrystalisWorker

__all__ = [
    "BaseWorker",
    "retry_until",
    "RETRY_TIMEOUT",
    "BATTLE_TIMEOUT",
    "register",
    "ParamSpec",
    "WorkerMeta",
    "REGISTRY",
    "get_registry",
    "LinkRaidWorker",
    "CrystalisWorker",
]

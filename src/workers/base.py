#挂机工作线程基类
#抽取 main.py 两个 QThread 的公共逻辑：运行/停止状态管理、日志信号、点击重试与超时停止。
#具体的挂机流程（link raid / 晶花）分别在 link_raid.py / crystalis.py 里实现，互不依赖。
#
#运行状态说明（取代原来的 guaji_1/guaji_2 全局标志）：
#  _active     由工作线程自己维护，True 表示正在正常运行；内部决定停止（超时/体力耗尽）时置 False。
#  _stop_event 由 GUI 的停止按钮置位；start() 时清空。
#  _running()  同时满足 _active 且 _stop_event 未置位才视为运行中，
#              语义和原来的 "guaji==1 且 stop_event 未置位" 一致。

import time
import threading
import traceback

from PySide6.QtCore import QThread, Signal

from src.click import click_action
from src.packs import language_switcher
from src.packs.file_lock import template_write_lock
from src.packs.file_lock import TemplateOperationCancelled
from src.input_activity import UserActivityGuard


#普通界面等待超时（秒），超时后安全停止
RETRY_TIMEOUT = 60
#战斗等待超时（秒），超时后安全停止
BATTLE_TIMEOUT = 1800


def retry_until(action, is_running, timeout=RETRY_TIMEOUT, wait=None):
    #在 timeout 内反复执行 action，返回 2 即成功；超时返回 1。
    #和原 main.py 里的同名函数完全一致，保留给子类使用。
    deadline = time.monotonic() + timeout
    while is_running() and time.monotonic() < deadline:
        result = action()
        if result == 2:
            return 2
        if wait is not None:
            if wait(min(0.5, max(0, deadline - time.monotonic()))):
                break
        else:
            time.sleep(0.5)
    return 1


class BaseWorker(QThread):
    #所有挂机工作线程的基类。子类只需实现 run()，流程中用 self._running() / self._wait() / self._click_until()。
    signal = Signal(str)

    def __init__(self):
        super().__init__()
        self._stop_event = threading.Event()
        self._active = False
        self.expected_pack = None
        self._last_automation_position = None
        self._activity_guard = UserActivityGuard(state_callback=self._activity_changed)

    def _activity_changed(self, paused):
        if paused:
            self.signal.emit('检测到用户键盘操作或大幅移动鼠标，挂机暂停；停止操作 5 秒后自动继续。')
        else:
            self.signal.emit('用户已停止操作 5 秒，挂机继续运行。')

    def _wait_for_user_idle(self):
        return self._activity_guard.wait_until_idle(self._stop_event.is_set)

    def _automation_input(self):
        return self._activity_guard.automation_input()

    def _running(self):
        #是否仍在运行：自身未主动停止且未被 GUI 要求停止
        return self._active and not self._stop_event.is_set()

    def _finish(self):
        #内部结束与 GUI 停止使用同一个事件，让所有等待都能立即退出。
        self._active = False
        self._stop_event.set()

    def stop(self):
        #GUI 调用：请求停止。置位事件并清掉 active 标志，让 _running() 立刻变 False。
        #对未启动或已结束的线程调用也是安全的。
        self._finish()

    def start(self, priority=QThread.InheritPriority):
        #每次启动前重置状态，保证同一个线程对象可反复启动
        #（对应原来 GUI 启动前 guaji=1、clear 事件 的两步操作）。
        if self.isRunning():
            self.signal.emit('挂机线程尚未结束，不能重新启动。')
            return False
        self._stop_event.clear()
        self._active = True
        self._last_automation_position = None
        self._activity_guard.start()
        super().start(priority)
        return True

    def _wait(self, seconds):
        #替代原来的 stop_event.wait(seconds)，返回 True 表示等待期间被停止打断。
        return self._stop_event.wait(seconds)

    def _run_safely(self, action):
        #QThread 的未捕获异常通常只会出现在控制台；同步报告到 GUI 便于排查。
        try:
            #整个挂机周期持有模板租约，阻止其它进程切换 aim 或重写派生模板。
            with template_write_lock(
                    language_switcher.BASE_DIR, timeout=2, is_cancelled=self._stop_event.is_set):
                if self.expected_pack and language_switcher.current_selection() != self.expected_pack:
                    self.signal.emit('激活模板已被其它程序改变，本次挂机已停止。')
                    return
                action()
        except TemplateOperationCancelled:
            pass
        except TimeoutError as e:
            self.signal.emit(f'{e}，本次挂机未启动。')
        except Exception:
            self.signal.emit('挂机线程异常退出：\n' + traceback.format_exc())
        finally:
            self._activity_guard.stop()
            self._finish()

    def _click_until(self, picture, name, timeout=RETRY_TIMEOUT, next_steps=()):
        #在 timeout 内反复尝试点击某组模板；超时则安全停止本线程并返回 1。
        #恢复点击可能已代替目标点击推进流程，因此恢复后先检查下一步，再重试当前步骤。
        #返回 2 表示点击成功，1 表示未点到（含超时停止）。
        deadline = time.monotonic() + timeout
        recovery_deadline = time.monotonic() + 5
        result = 1
        while self._running() and time.monotonic() < deadline:
            result = click_action.click_item_with_result(self, picture, name)
            if result == 2:
                break
            if time.monotonic() >= recovery_deadline:
                self.signal.emit(f'连续 5 秒未匹配到{name}，正在观察画面变化。')
                dynamic = click_action.click_behavior.screen_changes_significantly(self)
                if dynamic is True:
                    self.signal.emit('2 秒内超过 50% 的画面像素发生变化，疑似正在战斗，跳过恢复点击。')
                elif dynamic is False:
                    clicked = click_action.click_behavior.click_last_automation_position(self)
                    if clicked == 2:
                        self.signal.emit('画面较稳定，已在脚本上一次操作位置执行一次恢复点击。')
                        for next_picture, next_name in next_steps:
                            if click_action.find_item_with_result(self, next_picture, next_name) == 2:
                                self.signal.emit(f'恢复点击后已检测到下一步{next_name}，当前{name}步骤已完成。')
                                result = 2
                                break
                        if result != 2:
                            result = click_action.click_item_with_result(self, picture, name)
                            if result == 2:
                                self.signal.emit(f'恢复点击后仍检测到{name}，已冗余点击当前步骤。')
                        if result == 2:
                            break
                    else:
                        self.signal.emit('画面较稳定，但没有可安全使用的上一次操作位置，未执行恢复点击。')
                #当前周期无论点击、跳过或截图失败，都从现在开始等待下一个 5 秒周期。
                recovery_deadline = time.monotonic() + 5
            if self._wait(min(0.5, max(0, deadline - time.monotonic()))):
                break
        if result == 1 and self._running():
            self.signal.emit(f'等待{name}超过{timeout}秒，已安全停止。请检查起始界面、模板语言和分辨率。')
            self._finish()
        return result

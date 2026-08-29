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
from src.core.input_activity import UserActivityGuard


#普通界面等待超时（秒），超时后安全停止
RETRY_TIMEOUT = 60
#战斗等待超时（秒），超时后安全停止
BATTLE_TIMEOUT = 1800
POLL_INTERVAL = 0.2
BATTLE_POLL_INTERVAL = 0.5


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
    logSignal = Signal(str, str)
    majorEvent = Signal(str, str, object)

    def __init__(self):
        super().__init__()
        self._stop_event = threading.Event()
        self._manual_stop_event = threading.Event()
        self._active = False
        self._major_event_emitted = False
        self.expected_pack = None
        self._last_automation_position = None
        self._last_automation_click_at = None
        self._next_automation_input_at = 0.0
        self._notification_params = {}
        self._activity_guard = UserActivityGuard(state_callback=self._activity_changed)

    def _emit_log(self, message, level='INFO'):
        self.logSignal.emit(str(message), str(level).upper())

    def _emit_major_event(self, event_key, reason, params=None):
        self._major_event_emitted = True
        details = dict(self._notification_params)
        details.update(dict(params or {}))
        self.majorEvent.emit(str(event_key), str(reason), details)

    def _emit_auto_end_if_needed(self):
        if self._manual_stop_event.is_set() or self._major_event_emitted:
            return False
        self._emit_major_event(
            'worker_auto_ended',
            '挂机流程在未收到手动停止请求的情况下自动结束。',
        )
        return True

    def _activity_changed(self, paused, reason=None):
        if paused:
            detail = reason or '未能识别具体输入'
            self.signal.emit(
                f'检测到用户输入：{detail}，挂机暂停；停止操作 5 秒后自动继续。'
            )
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
        self._manual_stop_event.set()
        self._finish()

    def start(self, priority=QThread.InheritPriority):
        #每次启动前重置状态，保证同一个线程对象可反复启动
        #（对应原来 GUI 启动前 guaji=1、clear 事件 的两步操作）。
        if self.isRunning():
            self._emit_log('挂机线程尚未结束，不能重新启动。', 'WARNING')
            return False
        self._stop_event.clear()
        self._manual_stop_event.clear()
        self._active = True
        self._major_event_emitted = False
        self._last_automation_position = None
        self._last_automation_click_at = None
        self._next_automation_input_at = 0.0
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
                    self._emit_log('激活模板已被其它程序改变，本次挂机已停止。', 'ERROR')
                    return
                action()
        except TemplateOperationCancelled:
            pass
        except TimeoutError as e:
            self._emit_log(f'{e}，本次挂机未启动。', 'ERROR')
        except Exception as error:
            self._emit_major_event(
                'worker_exception',
                f'{type(error).__name__} 导致挂机线程异常退出：{error}',
            )
            self._emit_log('挂机线程异常退出：\n' + traceback.format_exc(), 'ERROR')
        finally:
            self._activity_guard.stop()
            self._emit_auto_end_if_needed()
            self._finish()

    def _click_until(self, picture, name, timeout=RETRY_TIMEOUT, next_steps=(),
                     fixed_click_2k=None, foreground_variants=None,
                     fixed_click_limit=1):
        #在 timeout 内反复尝试模板动作；fixed_click_2k 使用检测组确认页面后点击安全坐标。
        #声明下一步时，动作完成后必须确认下一步出现；固定坐标动作只在重新识别后有限重试。
        #返回 2 表示动作成功且已确认推进，1 表示未完成（含超时停止）。
        deadline = time.monotonic() + timeout
        recovery_deadline = time.monotonic() + 5
        poll_interval = BATTLE_POLL_INTERVAL if timeout >= BATTLE_TIMEOUT else POLL_INTERVAL
        result = 1
        waiting_for_next = False
        fixed_click_count = 0
        fixed_click_limit = max(1, int(fixed_click_limit))
        while self._running() and time.monotonic() < deadline:
            if waiting_for_next:
                next_step = click_action.find_first_item_with_result(self, next_steps)
                if next_step is not None:
                    _next_picture, next_name = next_step
                    self.signal.emit(f'已检测到下一步{next_name}，确认{name}页面已经推进。')
                    result = 2
                if result == 2:
                    break

            can_attempt_fixed = (
                fixed_click_2k is None
                or not waiting_for_next
                or fixed_click_count < fixed_click_limit
            )
            if can_attempt_fixed:
                if fixed_click_2k is not None:
                    result = click_action.click_fixed_position_for_item_with_result(
                        self, picture, name, *fixed_click_2k,
                        foreground_variants=foreground_variants,
                    )
                else:
                    result = click_action.click_item_with_result(self, picture, name)
                if result == 2:
                    if fixed_click_2k is not None:
                        fixed_click_count += 1
                    if not next_steps:
                        break
                    if fixed_click_2k is not None:
                        self.signal.emit(
                            f'{name}已识别并执行第{fixed_click_count}/'
                            f'{fixed_click_limit}次安全点击，正在等待下一步页面出现。'
                        )
                    elif waiting_for_next:
                        self.signal.emit(f'下一步尚未出现，仍检测到{name}，已冗余点击当前步骤。')
                    else:
                        self.signal.emit(f'{name}已点击，正在等待下一步页面出现。')
                    waiting_for_next = True
                    result = 1
                    recovery_deadline = time.monotonic() + 5
            if time.monotonic() >= recovery_deadline:
                if foreground_variants:
                    variants = '/'.join(f'_{index}' for index in foreground_variants)
                    self.signal.emit(
                        f'连续 5 秒未通过文字前景轮廓匹配到{name}'
                        f'（仅使用 {variants}），正在观察画面变化。'
                    )
                else:
                    self.signal.emit(f'连续 5 秒未匹配到{name}，正在观察画面变化。')
                dynamic = click_action.click_behavior.screen_changes_significantly(self)
                if dynamic is True:
                    self.signal.emit('2 秒内超过 50% 的画面像素发生变化，疑似正在战斗，跳过恢复点击。')
                elif dynamic is False:
                    # 画面观察本身需要 2 秒；下一步可能在此期间出现，恢复点击前必须复查。
                    # 固定坐标动作没有恢复点击，必须先真实识别并点击当前步骤，才接受下一步。
                    can_confirm_next = (
                        bool(next_steps)
                        and (fixed_click_2k is None or waiting_for_next)
                    )
                    next_step = click_action.find_first_item_with_result(
                        self, next_steps,
                    ) if can_confirm_next else None
                    if next_step is not None:
                        _next_picture, next_name = next_step
                        self.signal.emit(
                            f'恢复点击前已检测到下一步{next_name}，跳过原地点击。'
                        )
                        result = 2
                        break
                    if fixed_click_2k is not None:
                        self.signal.emit(
                            f'{name}属于固定安全坐标动作，未识别时不执行上一次位置恢复点击。'
                        )
                        recovery_deadline = time.monotonic() + 5
                        continue
                    clicked = click_action.click_behavior.click_last_automation_position(self)
                    if clicked == 2:
                        self.signal.emit('画面较稳定，已在脚本上一次操作位置执行一次恢复点击。')
                        waiting_for_next = bool(next_steps)
                        if not next_steps:
                            result = click_action.click_item_with_result(self, picture, name)
                            if result == 2:
                                self.signal.emit(f'恢复点击后仍检测到{name}，已冗余点击当前步骤。')
                                break
                    else:
                        self.signal.emit('画面较稳定，但没有可安全使用的上一次操作位置，未执行恢复点击。')
                #当前周期无论点击、跳过或截图失败，都从现在开始等待下一个 5 秒周期。
                recovery_deadline = time.monotonic() + 5
            if self._wait(min(poll_interval, max(0, deadline - time.monotonic()))):
                break
        if result == 1 and self._running():
            self._emit_major_event(
                'timeout',
                f'等待识别或推进 {name} 超时。',
                {'步骤': name, '超时秒数': timeout},
            )
            self._emit_log(
                f'等待{name}超过{timeout}秒，已安全停止。请检查起始界面、模板语言和分辨率。',
                'ERROR',
            )
            self._finish()
        return result

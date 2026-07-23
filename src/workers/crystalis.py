#晶花挂机工作线程
#从 main.py 的 WorkThread_2 迁移而来，流程逻辑完全不变：
#  play -> wait_win(找 result/retry) -> click_retry_or_recover_lp 循环。
#GUI 只负责构造本线程、设置参数（lp_recover_times）和启动/停止。
#
#原来对全局 guaji_2 / stop_event_2 的判断，统一替换为基类的 self._running() / self._wait()：
#  guaji_2 == 1            -> self._running()
#  guaji_2 = 2（内部停止） -> self._active = False
#  stop_event_2.wait(n)    -> self._wait(n)

import time
import logging

from src.click import click_action
from .base import BaseWorker, BATTLE_TIMEOUT
from .registry import register, ParamSpec

logger = logging.getLogger(__name__)


@register(
    'crystalis',
    '自动刷晶花，需要在play界面启动',
    params=[
        ParamSpec(
            'lp_recover_times',
            '刷晶花部分\n晶花挂机要喝体力药几次',
            kind='lp_recover',
            min=0,
            max=8,
            default=8,
        ),
    ],
    start_hint='需要在选择完成关卡和队伍的界面启动。也就是点一下play就进入战斗的界面',
    required_templates=['crystalis/play', 'crystalis/result', 'crystalis/retry', 'crystalis/ok'],
)
class CrystalisWorker(BaseWorker):
    def __init__(self, lp_recover_times=9):
        super().__init__()
        logger.debug('CrystalisWorker准备就绪')
        #喝体力药次数，存储的是“显示次数+1”，1 表示不喝药；GUI 启动前会重新赋值
        self.lp_recover_times = lp_recover_times

    def run(self):
        self._run_safely(self._run)

    def _run(self):
        if isinstance(self.lp_recover_times, bool) or not isinstance(self.lp_recover_times, int) \
                or not 1 <= self.lp_recover_times <= 9:
            self.signal.emit('喝体力药次数参数无效，本次挂机已停止。')
            return
        logger.info('执行CrystalisWorker,两秒钟后启动！')
        self.signal.emit(str('启动刷晶花挂机'))

        # 喝药次数副本（运行时递减），1 是不喝药，2 是 1 次，需要减一
        self.lp_recover = self.lp_recover_times

        # 提示框
        self.signal.emit(str('具体参数如下：'))
        self.signal.emit(str(f'喝体力药的次数：{self.lp_recover - 1}'))
        self.signal.emit(str('参数错误请暂停'))
        self.signal.emit(str(f'需要在选择完成关卡和队伍的界面启动。也就是点一下play就进入战斗的界面'))

        if self._wait(2):
            return
        if click_action.click_position_scaled(2000, 1000, self._running) != 2:
            self.signal.emit('无法安全执行初始坐标点击，本次挂机已停止。')
            return
        self.signal.emit(str('把游戏弄到前台，然后随便碰一下中间'))
        if self._wait(1):
            return

        self.click_play()
        # 执行部分
        while self._running():
            self.wait_win()
            if not self._running():
                break
            self.click_retry_or_recover_lp()

    # 函数部分
    # 点击 play 开始挂
    def click_play(self):
        result = 1

        # 在主界面点击 quests
        result = self._click_until('./aim/crystalis/play', 'play')
        if result == 2:
            self.signal.emit(str('play点击完成'))

    def wait_win(self):
        check_win = 1  # 这东西代表看到 retry，1 是没看到，2 是看到
        deadline = time.monotonic() + BATTLE_TIMEOUT
        while check_win == 1 and self._running() and time.monotonic() < deadline:
            # 战斗结束后，右上角会出现 result，点击整个右侧屏幕的任何地方几次就会让它出现 retry
            result = click_action.click_item_with_result(self, './aim/crystalis/result', 'result')
            if result == 2:
                self.signal.emit(str('result点击完成，点了之后会出现retry'))
            else:
                self.signal.emit(str('result没有找到，还在战斗状态'))

            if result == 2:
                check_win = click_action.find_item_with_result(self, f'./aim/crystalis/retry', 'retry')
                self.signal.emit(str(f'result被点击过一次，尝试寻找retry，具体的状态是{check_win}，1是没有找到，2是找到了'))
            if check_win == 1 and self._wait(0.5):
                return
        if check_win == 1 and self._running():
            self.signal.emit('等待晶花战斗结束超时，已安全停止。')
            self._finish()

    def click_retry_or_recover_lp(self):
        result = 1
        result = self._click_until('./aim/crystalis/retry', 'retry')
        if result == 2:
            self.signal.emit(str('retry点击完成'))

        if self._wait(2):  # 等待确保延迟
            return
        # 寻找是否存在体力耗尽
        if click_action.find_item_with_result(self, './aim/crystalis/ok', 'ok') == 2:
            self.lp_recover = self.lp_recover - 1
            self.signal.emit(str(f'体力用完了，剩余体力恢复次数还是{self.lp_recover}'))
            if self.lp_recover == 0:
                self._finish()
                return

            result = 1
            result = self._click_until('./aim/crystalis/ok', 'ok')
            if result == 2:
                self.signal.emit(str('ok点击完成，体力完成恢复'))
                self._wait(5)  # 防止瞬间出现的 retry 干扰
        else:
            self.signal.emit(str(f'当前还有体力，下一把战斗正常开始，体力剩余恢复次数是{self.lp_recover - 1}'))

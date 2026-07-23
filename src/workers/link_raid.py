#Link Raid 挂机工作线程
#从 main.py 的 WorkThread_1 迁移而来，流程逻辑完全不变：
#  主界面 -> backup_requests -> 刷新 -> 找等级 -> join -> 战斗 -> 点赞 -> back 循环。
#GUI 只负责构造本线程、设置参数（level_choice / lp_recover_times）和启动/停止。
#
#原来对全局 guaji_1 / stop_event_1 的判断，统一替换为基类的 self._running() / self._wait()：
#  guaji_1 == 1            -> self._running()
#  guaji_1 = 2（内部停止） -> self._active = False
#  stop_event_1.wait(n)    -> self._wait(n)

import time
import logging

from src.click import click_action
from .base import BaseWorker, BATTLE_TIMEOUT, retry_until
from .registry import register, ParamSpec

logger = logging.getLogger(__name__)


@register(
    'link_raid',
    'link raid挂机启动',
    params=[
        ParamSpec(
            'level_choice',
            'link raid挂机部分\n选择link raid要挂机的等级',
            kind='choice',
            choices=[6, 7, 8, 9, 10, 11, 12],
            default=6,
        ),
        ParamSpec(
            'lp_recover_times',
            'link raid挂机要喝体力药几次',
            kind='lp_recover',
            min=0,
            max=10,
            default=0,
        ),
    ],
    start_hint='需要在游戏主界面启动本挂机系统',
    required_templates=[
        'quests/link_raid',
        'quests/link_raid/backup_requests',
        'quests/link_raid/backup_requests/backup_requests',
        'quests/link_raid/backup_requests/refresh',
        'quests/link_raid/backup_requests/no_join',
        'quests/link_raid/backup_requests/joined_battles',
        'quests/link_raid/joined_battles/win',
        'quests/link_raid/joined_battles/ended',
        'quests/link_raid/backup_requests/join',
        'quests/link_raid/backup_requests/no_lp/no_lp',
        'quests/link_raid/backup_requests/no_lp/ok',
        'quests/link_raid/backup_requests/join/play',
        'quests/link_raid/backup_requests/join/ok',
        'quests/link_raid/backup_requests/join/full/already_end',
        'quests/link_raid/backup_requests/battle/tap_to_countinue',
        'quests/link_raid/backup_requests/battle/back',
        'quests/link_raid/backup_requests/lv/lv6/lv6',
        'quests/link_raid/backup_requests/lv/lv7/lv7',
        'quests/link_raid/backup_requests/lv/lv8/lv8',
        'quests/link_raid/backup_requests/lv/lv9/lv9',
        'quests/link_raid/backup_requests/lv/lv10/lv10',
        'quests/link_raid/backup_requests/lv/lv11/lv11',
        'quests/link_raid/backup_requests/lv/lv12/lv12',
    ],
)
class LinkRaidWorker(BaseWorker):
    def __init__(self, level=6, lp_recover_times=1):
        super().__init__()
        logger.debug('LinkRaidWorker准备就绪')
        #等级选择（lv6~lv12），GUI 启动前会重新赋值
        self.level_choice = level
        #喝体力药次数，存储的是“显示次数+1”，1 表示不喝药；GUI 启动前会重新赋值
        self.lp_recover_times = lp_recover_times

    def run(self):
        self._run_safely(self._run)

    def _run(self):
        if isinstance(self.level_choice, bool) or self.level_choice not in range(6, 13):
            self.signal.emit('Link Raid 等级参数无效，本次挂机已停止。')
            return
        if isinstance(self.lp_recover_times, bool) or not isinstance(self.lp_recover_times, int) \
                or not 1 <= self.lp_recover_times <= 11:
            self.signal.emit('喝体力药次数参数无效，本次挂机已停止。')
            return
        logger.info('执行LinkRaidWorker,两秒钟后启动！')
        self.signal.emit(str('启动link raid挂机'))

        # 体力是否够打下一把，1 是可以，2 是不行
        self.LP_full = 1
        # 体力药使用次数副本（运行时递减），1 是不用，2 是 1 次，最多 4 三次
        self.LP_full_add = self.lp_recover_times
        # 是否找到需要打的等级，参数为 2 是找到，1 不是，用的点击代码进行寻找
        self.level_choice_exist = 1
        # 点击 play 后因为打太多导致满了的情况，1 代表没满，2 代表满了
        self.join_full = 1
        # 找 win 至少运行成功一次，防止卡
        self.win_exist = 1
        # 点击 play 之后战斗已经结束，1 代表没结束，2 代表战斗已经结束
        self.already_end = 1
        # 清理打满状态，指的是清理里面还有没有 loss 或者 win 状态的标识，1 是清理干净了，2 还没清理干净
        self.join_fill_clean = 1

        self.signal.emit(str('具体挂机参数为：'))
        self.signal.emit(str(f'选择的等级是：{self.level_choice}'))
        self.signal.emit(str(f'喝体力药的次数是：{self.LP_full_add - 1}'))
        self.signal.emit(str('参数错误请及时暂停'))
        self.signal.emit(str('需要在游戏主界面启动本挂机系统'))

        if self._wait(2):
            return

        self.into_link_raid()

        while self._running():
            self.link_raid_to_backup_requests()
            if not self._running():
                break
            self.prepare_battle()  # 指的就是刷新一下
            if not self._running():
                break
            self.check_join_full()  # 判断右下角的 join 是不是黑色的，黑色的说明加入对局满了
            if not self._running():
                break
            # 这里指的是清理打完的局，需要注意的是，这个参数要在没有 win 之后改成 1，这样就跳出循环了
            self.win_exist = 1  # 这个东西找到一次 win 之后变成 2，否则一直等待
            while self._running() and self.join_full == 2:
                self.clean_full()
            if not self._running():
                break
            self.find_lv()
            if not self._running():
                break
            self.join_battle()
            if not self._running():
                break
            # 判断是否结束，重新点击后会直接再次加入战斗，函数都在里面写了，不需要重新运行上面的
            self.check_already_end()
            if not self._running():
                break
            self.battle_and_finish()

    # 函数
    # 从主界面到 link raid 界面
    def into_link_raid(self):
        result = 1

        if not self._running():
            return
        if click_action.click_position_scaled(2000, 1000, self._running) != 2:
            self.signal.emit('无法安全执行初始坐标点击，本次挂机已停止。')
            self._finish()
            return
        self.signal.emit(str('把游戏弄到前台，然后随便碰一下中间'))
        if self._wait(0.2):
            return
        if click_action.click_position_scaled(2400, 1200, self._running) != 2:
            self.signal.emit('无法安全执行 quests 坐标点击，本次挂机已停止。')
            self._finish()
            return
        self.signal.emit(str('quests点击完成，这一下使用的是位置点击，不是识图，如果没有点到说明其他问题发生了'))
        if self._wait(0.2):
            return

        # 在 quest 界面点击 link raid
        result = self._click_until('./aim/quests/link_raid', 'link_raid')
        if result == 2:
            self.signal.emit(str('link_raid点击完成'))
        result = 1

    def link_raid_to_backup_requests(self):
        result = 1

        # 进入到 boss 大脸的界面，在 link raid 界面点击 backup_requests
        result = self._click_until('./aim/quests/link_raid/backup_requests', 'backup_requests')
        if result == 2:
            self.signal.emit(str('第一层的backup_requests点击完成'))
        result = 1

        # 点击第二层 backup_requests，进入到加入界面
        result = self._click_until('./aim/quests/link_raid/backup_requests/backup_requests', 'backup_requests')
        if result == 2:
            self.signal.emit(str('第二层的backup_requests点击完成'))
        result = 1

    # 判断右下角的 join 是不是黑色的，黑色的代表打满了
    def check_join_full(self):
        self.join_full = click_action.find_item_with_result(self, './aim/quests/link_raid/backup_requests/no_join', 'no_join')
        if self.join_full == 1:
            self.signal.emit(str('战斗没有打满，正常运行'))
        else:
            self.signal.emit(str('战斗已经打满了，需要清理joined battles'))

        result = 1
        if self.join_full == 2:
            # 点击左边的 joined battle
            result = self._click_until('./aim/quests/link_raid/backup_requests/joined_battles', 'joined_battles')
            if result == 2:
                self.signal.emit(str('joined_battles点击完成'))
            result = 1

    def clean_full(self):
        result = 1
        find_one_win = 1

        wait_deadline = time.monotonic() + BATTLE_TIMEOUT
        while self._running() and self.win_exist == 1 and time.monotonic() < wait_deadline:
            self.signal.emit(str(f'进入joined battle，开始清空已经结束的战斗。需要保证第一次能够清除后才会回到寻找战斗界面'))
            for _ in range(3):
                if not self._running():
                    return
                click_action.move_a_to_b_scaled(1400, 1200, 1400, 400, self._running)
            self.signal.emit(
                str(f'完成下移，开始找结束的对局'))
            if self._wait(2):
                return
            find_one_win = click_action.find_item_with_result(self, './aim/quests/link_raid/joined_battles/win', 'win/lose')
            self.signal.emit(str(f'寻找win/loss的状态是{find_one_win}，1是没有了，2是还存在。此处没有找到会一直等待到找到为止，否则会无法继续'))
            if find_one_win == 2:
                self.win_exist = 2
            else:
                self.signal.emit(str(f'没有看到一场结束的战斗，等待5s后点击刷新，然后继续找'))
                if self._wait(5):
                    return
                result = 1

                # 点击刷新
                result = self._click_until('./aim/quests/link_raid/backup_requests/refresh', 'refresh')
                if result == 2:
                    self.signal.emit(str('refresh点击完成'))

        if self._running() and self.win_exist == 1:
            self.signal.emit('等待已结束战斗超时，已安全停止。')
            self._finish()
            return

        result = 1
        self.clean_fin = click_action.find_item_with_result(self, './aim/quests/link_raid/joined_battles/win', 'win/lose')
        self.signal.emit(str(f'win/loss的状态是{self.clean_fin}，1是没有了，2是还存在'))

        if self.clean_fin == 2:
            # 点击 win/lose
            result = self._click_until('./aim/quests/link_raid/joined_battles/win', 'win/lose')
            if result == 2:
                self.signal.emit(str('win/lose点击完成'))
            result = 1

            # 点击右下角的 ended
            result = self._click_until('./aim/quests/link_raid/joined_battles/ended', 'ended')
            if result == 2:
                self.signal.emit(str('ended点击完成'))
            result = 1

            # 点击结算界面的 tap_to_countinue
            result = self._click_until(
                './aim/quests/link_raid/backup_requests/battle/tap_to_countinue',
                'tap_to_countinue',
                BATTLE_TIMEOUT,
            )
            if result == 2:
                self.signal.emit(str('tap_to_countinue点击完成'))
            result = 1

            # 点击结算界面的 back，点完后回到前面
            result = self._click_until('./aim/quests/link_raid/backup_requests/battle/back', 'back')
            if result == 2:
                self.signal.emit(str('back点击完成'))
            result = 1

            # 返回后点击左侧 joined battle，这个没有意义，主要是防止延迟导致出问题，如果 joined battle 能点击，说明加载好了
            result = self._click_until('./aim/quests/link_raid/backup_requests/joined_battles', 'joined_battles')
            if result == 2:
                self.signal.emit(str('joined_battles点击完成，这一个点击主要为了防止延迟'))
            result = 1

            self.clean_fin = click_action.find_item_with_result(self, './aim/quests/link_raid/joined_battles/win', 'win/lose')
            self.signal.emit(str(f'win/loss的状态是{self.clean_fin}，1是没有了，2是还存在'))

        else:
            self.join_full = 1  # 用于跳出外部的 while

            # 点击第二层 backup_requests，回到选战斗界面
            result = self._click_until('./aim/quests/link_raid/backup_requests/backup_requests', 'backup_requests')
            if result == 2:
                self.signal.emit(str('第二层的backup_requests点击完成'))
            result = 1

            # 点击刷新
            result = self._click_until('./aim/quests/link_raid/backup_requests/refresh', 'refresh')
            if result == 2:
                self.signal.emit(str('refresh点击完成'))
            result = 1

    # 打架之前点击刷新
    def prepare_battle(self):
        result = 1

        # 点击刷新
        result = self._click_until('./aim/quests/link_raid/backup_requests/refresh', 'refresh')
        if result == 2:
            self.signal.emit(str('refresh点击完成'))
        result = 1

    # 寻找需要打架的等级，这个找不到也要继续，不能用 while 循环寻找
    def find_lv(self):
        # 往下拉 3 次用于寻找
        find_time = 4
        # 这个判断对应等级是否存在，1 是没找到，2 是找到了默认设置没找到，进入第一次循环
        self.level_choice_exist = 1

        while self._running() and find_time > 1 and self.level_choice_exist == 1:
            self.level_choice_exist = click_action.find_item_with_result(self,
                                                                         f'./aim/quests/link_raid/backup_requests/lv/lv{self.level_choice}/lv{self.level_choice}',
                                                                         f'lv{self.level_choice}')
            if self.level_choice_exist == 2:
                self.signal.emit(str(f'lv{self.level_choice}找到了，下一步是选择'))
            else:
                find_time = find_time - 1
                self.signal.emit(str(f'lv{self.level_choice}没有找到，往下拉动，还有的寻找次数为{find_time - 2}'))
                if not self._running():
                    return
                click_action.move_a_to_b_scaled(1400, 1200, 1400, 400, self._running)
                if self._wait(4):
                    return
                self.signal.emit(str(f'往下移动完成'))

        if self.level_choice_exist == 2:
            if self._running():  # 这里不可以用 while，只能运行一遍
                result = click_action.click_item_with_result(self,
                                                             f'./aim/quests/link_raid/backup_requests/lv/lv{self.level_choice}/lv{self.level_choice}',
                                                             f'lv{self.level_choice}')
                if result == 2:
                    self.signal.emit(str(f'lv{self.level_choice}点击完成'))
                else:
                    self.signal.emit(str(f'lv{self.level_choice}没有找到，不会重复运行，理论上这一条不应该发生，即便发生了也会继续运行'))
                result = 1

        # 这个判断对应等级是否存在，1 是没找到，2 是找到了

        if self.level_choice_exist == 1:
            self.signal.emit(str(f'lv{self.level_choice}没有找到，直接点击第一个'))
        else:
            self.signal.emit(str(f'lv{self.level_choice}找到了，下一步是选择'))

        result = 1
        # 当需要点击的等级存在，点击相应等级，只过一遍，不循环，这里不会卡

    # 加入战斗，需要点击 join 和 play 两个，接下来就会又各种情况判定，因为体力会满，战斗会结束
    def join_battle(self):
        result = 1

        # 点击 join 进入到选人的界面
        result = self._click_until('./aim/quests/link_raid/backup_requests/join', 'join')
        if result == 2:
            self.signal.emit(str('join点击完成'))
        result = 1

        # 判断体力是否耗尽，正常情况应该是 1，耗尽会变成 2
        if self._wait(0.2):
            return
        self.LP_full = click_action.find_item_with_result(self, f'./aim/quests/link_raid/backup_requests/no_lp/no_lp', 'no_lp')
        self.signal.emit(str(f'体力是否耗尽的状态是{self.LP_full}，1是体力还能继续打，2是不能打了，要开始判断是否喝药或者暂停'))

        # 如果体力耗尽，判断是否要结束或者喝药
        if self.LP_full == 2:
            self.LP_full_add = self.LP_full_add - 1
            self.signal.emit(str(f'剩余喝体力药的次数是{self.LP_full_add}，0就是不喝药了，结束挂机'))
            if self.LP_full_add == 0:  # 剩余喝药次数耗尽
                self._finish()
                return
            else:
                result = self._click_until('./aim/quests/link_raid/backup_requests/no_lp/ok', 'ok')
                if result == 2:
                    self.signal.emit(str('ok点击完成，完成喝药'))
                result = 1

        # 点击 play 理论上进入战斗，实际上不一定，可能体力回满一类的
        result = self._click_until('./aim/quests/link_raid/backup_requests/join/play', 'play')
        if result == 2:
            self.signal.emit(str('play点击完成'))
        result = 1

    # 判断当前战斗是否结束，结束了点一下刷新
    def check_already_end(self):
        # 防止延迟问题
        if self._wait(0.9):
            return

        # 确认战斗是否结束
        self.already_end = click_action.find_item_with_result(self, f'./aim/quests/link_raid/backup_requests/join/full/already_end', 'already_end')
        self.signal.emit(str(f'战斗是否已经结束的状态是{self.already_end}，1是没有结束，2是结束了'))

        # 如果战斗已经结束，点击 ok，然后点击刷新
        while self._running() and self.already_end == 2:
            result = 1
            # 点击 ok
            result = self._click_until('./aim/quests/link_raid/backup_requests/join/ok', 'ok')
            if result == 2:
                self.signal.emit(str('ok点击完成'))
            result = 1

            self.prepare_battle()
            if not self._running():
                return
            self.find_lv()
            if not self._running():
                return
            self.join_battle()
            if not self._running():
                return

            # 再次判断，只要脸够黑，就能连着结束
            self.already_end = click_action.find_item_with_result(self, f'./aim/quests/link_raid/backup_requests/join/full/already_end', 'already_end')
            self.signal.emit(str(f'战斗是否已经结束的状态是{self.already_end}，1是没有结束，2是结束了'))

    # 完成战斗，然后点 back。点击战斗结束会出来的 tap_to_countinue
    def battle_and_finish(self):
        result = 1

        # 点击结算界面的 tap_to_countinue
        result = self._click_until(
            './aim/quests/link_raid/backup_requests/battle/tap_to_countinue',
            'tap_to_countinue',
            BATTLE_TIMEOUT,
        )
        if result == 2:
            self.signal.emit(str('tap_to_countinue点击完成'))
        result = 1

        # 等待 2 秒，防止延迟，该死的服务器
        if self._wait(2):
            return

        # 等待 back 界面出现，然后开始点赞，这里通过找到最底下的 back 来判定是否可以点赞
        wait_back = retry_until(
            lambda: click_action.find_item_with_result(
                self, './aim/quests/link_raid/backup_requests/battle/back', 'back'
            ),
            self._running,
            wait=self._wait,
        )
        if wait_back == 2:
            self.signal.emit(str('back已经可以看到，可以开始点赞'))
        elif self._running():
            self.signal.emit('等待back超时，已安全停止。')
            self._finish()

        # 点赞系统。最多点 9 下，点到不能点为止
        love_time = 9
        while self._running() and love_time > 0:
            result = click_action.click_item_with_result(self, './aim/quests/link_raid/backup_requests/battle/love', 'love')
            if result == 2:
                self.signal.emit(str('love点击完成，点赞完成一次'))
                love_time = love_time - 1
            else:
                self.signal.emit(str('love没有找到，可能是次数耗尽或者要下拉'))
                if self._wait(0.5):
                    return
                if not self._running():
                    return
                click_action.move_a_to_b_scaled(1400, 1000, 1400, 600, self._running)
                result = click_action.click_item_with_result(self, './aim/quests/link_raid/backup_requests/battle/love',
                                                             'love')
                if result == 1:
                    love_time = 0
                    self.signal.emit(str('没有点赞了'))
        result = 1

        # 点击结算界面的 back，点完后回到 boss 打脸的界面
        result = self._click_until('./aim/quests/link_raid/backup_requests/battle/back', 'back')
        if result == 2:
            self.signal.emit(str('back点击完成，一场战斗结束了'))
        result = 1

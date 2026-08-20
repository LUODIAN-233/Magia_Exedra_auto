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

LEVEL_LIST_SEARCH_REGION = (0.20, 0.18, 0.70, 0.78)
JOIN_DIALOG_SEARCH_REGION = (0.20, 0.20, 0.80, 0.85)
SCROLL_SETTLE_DELAY = 1.0
TAP_TO_CONTINUE_POSITION_2K = (1280, 1367)
TAP_TO_CONTINUE_FOREGROUND_VARIANTS = (1, 2)
TAP_TO_CONTINUE_MAX_CLICKS = 2
LIKE_SCROLL_SETTLE_DELAY = 1.0
LIKE_RETRY_TIMEOUT = 3.0
LIKE_NEUTRAL_MOUSE_POSITION_2K = (1280, 120)
BATTLE_STATE_POLL_INTERVAL = 0.5
REFRESH_MIN_CLICK_INTERVAL = 4.5


@register(
    'link_raid',
    'link raid挂机启动',
    params=[
        ParamSpec(
            'level_choice',
            'link raid挂机部分\n选择link raid要挂机的等级',
            kind='choice',
            choices=[4, 6, 7, 8, 9, 10, 11, 12],
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
        'quests/link_raid/backup_requests/join/full/battle_full',
        'quests/link_raid/backup_requests/join/full/ok',
        'quests/link_raid/backup_requests/battle/tap_to_countinue',
        'quests/link_raid/backup_requests/battle/back',
        'quests/link_raid/backup_requests/lv/lv4/lv4',
        'quests/link_raid/backup_requests/lv/lv6/lv6',
        'quests/link_raid/backup_requests/lv/lv7/lv7',
        'quests/link_raid/backup_requests/lv/lv8/lv8',
        'quests/link_raid/backup_requests/lv/lv9/lv9',
        'quests/link_raid/backup_requests/lv/lv10/lv10',
        'quests/link_raid/backup_requests/lv/lv11/lv11',
        'quests/link_raid/backup_requests/lv/lv12/lv12',
        'quests/link_raid/backup_requests/lv/no_lv',
    ],
)
class LinkRaidWorker(BaseWorker):
    def __init__(self, level=6, lp_recover_times=1):
        super().__init__()
        logger.debug('LinkRaidWorker准备就绪')
        #等级选择（lv4、lv6~lv12），GUI 启动前会重新赋值
        self.level_choice = level
        #喝体力药次数，存储的是“显示次数+1”，1 表示不喝药；GUI 启动前会重新赋值
        self.lp_recover_times = lp_recover_times
        self._next_automation_input_at = 0.0

    def run(self):
        self._run_safely(self._run)

    def _run(self):
        if isinstance(self.level_choice, bool) or self.level_choice not in (4, 6, 7, 8, 9, 10, 11, 12):
            self._emit_log('Link Raid 等级参数无效，本次挂机已停止。', 'ERROR')
            return
        if isinstance(self.lp_recover_times, bool) or not isinstance(self.lp_recover_times, int) \
                or not 1 <= self.lp_recover_times <= 11:
            self._emit_log('喝体力药次数参数无效，本次挂机已停止。', 'ERROR')
            return
        logger.info('执行LinkRaidWorker,两秒钟后启动！')
        self.signal.emit(str('启动link raid挂机'))

        # 体力是否够打下一把，1 是可以，2 是不行
        self.LP_full = 1
        # 体力药使用次数副本（运行时递减），1 是不用，2 是 1 次，最多 4 三次
        self.LP_full_add = self.lp_recover_times
        # 点击 play 后因为打太多导致满了的情况，1 代表没满，2 代表满了
        self.join_full = 1
        # 找 win 至少运行成功一次，防止卡
        self.win_exist = 1
        # 点击 play 之后战斗已经结束，1 代表没结束，2 代表战斗已经结束
        self.already_end = 1
        self._next_automation_input_at = 0.0
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
            if not self.prepare_matching_battle():
                break
            self.join_battle()
            if not self._running():
                break
            # 同时等待迟到的 already_end 和正常结算，避免一次性检查漏掉延迟弹窗。
            self.battle_and_finish()

    # 函数
    # 从主界面到 link raid 界面
    def into_link_raid(self):
        result = 1

        if not self._running():
            return
        if click_action.click_position_scaled(2000, 1000, self._running) != 2:
            self._emit_log('无法安全执行初始坐标点击，本次挂机已停止。', 'ERROR')
            self._finish()
            return
        self.signal.emit(str('把游戏弄到前台，然后随便碰一下中间'))
        if self._wait(0.2):
            return
        if click_action.click_position_scaled(2400, 1200, self._running) != 2:
            self._emit_log('无法安全执行 quests 坐标点击，本次挂机已停止。', 'ERROR')
            self._finish()
            return
        self.signal.emit(str('quests点击完成，这一下使用的是位置点击，不是识图，如果没有点到说明其他问题发生了'))
        if self._wait(0.2):
            return

        # 在 quest 界面点击 link raid
        result = self._click_until(
            './aim/quests/link_raid', 'link_raid',
            next_steps=(('./aim/quests/link_raid/backup_requests', 'backup_requests'),),
        )
        if result == 2:
            self.signal.emit(str('link_raid点击完成'))
        result = 1

    def link_raid_to_backup_requests(self):
        result = 1

        # 进入到 boss 大脸的界面，在 link raid 界面点击 backup_requests
        result = self._click_until(
            './aim/quests/link_raid/backup_requests', 'backup_requests',
            next_steps=(('./aim/quests/link_raid/backup_requests/backup_requests', 'backup_requests'),),
        )
        if result == 2:
            self.signal.emit(str('第一层的backup_requests点击完成'))
        result = 1

        # 点击第二层 backup_requests，进入到加入界面
        result = self._click_until(
            './aim/quests/link_raid/backup_requests/backup_requests', 'backup_requests',
            next_steps=(('./aim/quests/link_raid/backup_requests/refresh', 'refresh'),),
        )
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
            result = self._click_until(
                './aim/quests/link_raid/backup_requests/joined_battles', 'joined_battles'
            )
            if result == 2:
                self.signal.emit(str('joined_battles点击完成'))
            result = 1

    def clean_full(self):
        result = 1
        find_one_win = 1

        wait_deadline = time.monotonic() + BATTLE_TIMEOUT
        while self._running() and self.win_exist == 1 and time.monotonic() < wait_deadline:
            self.signal.emit(str(f'进入joined battle，开始清空已经结束的战斗。需要保证第一次能够清除后才会回到寻找战斗界面'))
            for _ in range(6):
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

                result = self._refresh_battle_list()

        if self._running() and self.win_exist == 1:
            self._emit_log('等待已结束战斗超时，已安全停止。', 'ERROR')
            self._finish()
            return

        result = 1
        self.clean_fin = click_action.find_item_with_result(self, './aim/quests/link_raid/joined_battles/win', 'win/lose')
        self.signal.emit(str(f'win/loss的状态是{self.clean_fin}，1是没有了，2是还存在'))

        if self.clean_fin == 2:
            # 点击 win/lose
            result = self._click_until(
                './aim/quests/link_raid/joined_battles/win', 'win/lose',
                next_steps=(('./aim/quests/link_raid/joined_battles/ended', 'ended'),),
            )
            if result == 2:
                self.signal.emit(str('win/lose点击完成'))
            result = 1

            # 点击右下角的 ended
            result = self._click_until(
                './aim/quests/link_raid/joined_battles/ended', 'ended',
                next_steps=((
                    './aim/quests/link_raid/backup_requests/battle/tap_to_countinue',
                    'tap_to_countinue',
                    {'foreground_variants': TAP_TO_CONTINUE_FOREGROUND_VARIANTS},
                ),),
            )
            if result == 2:
                self.signal.emit(str('ended点击完成'))
            result = 1

            # 检测模板只用于确认结算页，点击固定的底部中央安全位置。
            result = self._click_until(
                './aim/quests/link_raid/backup_requests/battle/tap_to_countinue',
                'tap_to_countinue',
                BATTLE_TIMEOUT,
                next_steps=(('./aim/quests/link_raid/backup_requests/battle/back', 'back'),),
                fixed_click_2k=TAP_TO_CONTINUE_POSITION_2K,
                foreground_variants=TAP_TO_CONTINUE_FOREGROUND_VARIANTS,
                fixed_click_limit=TAP_TO_CONTINUE_MAX_CLICKS,
            )
            if result == 2:
                self.signal.emit(str('tap_to_countinue页面已推进'))
                self.like_battle_result()
            if not self._running():
                return
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

            result = self._refresh_battle_list()
            result = 1

    def _refresh_battle_list(self):
        """刷新列表，并以实际点击时刻限制下一次自动化输入。"""
        previous_click_at = getattr(self, '_last_automation_click_at', None)
        result = self._click_until('./aim/quests/link_raid/backup_requests/refresh', 'refresh')
        if result == 2:
            clicked_at = getattr(self, '_last_automation_click_at', None)
            if clicked_at is None or clicked_at == previous_click_at:
                # 测试替身或兼容旧输入实现时使用安全回退；正常路径取鼠标点击实时时间。
                clicked_at = time.monotonic()
            self._next_automation_input_at = clicked_at + REFRESH_MIN_CLICK_INTERVAL
            self.signal.emit(str('refresh点击完成'))
        return result

    # 打架之前点击刷新
    def prepare_battle(self):
        self._refresh_battle_list()

    def prepare_matching_battle(self):
        # 刷新前：先查一次目标等级
        r = self._scan_lv()
        while self._running():
            if r == 2:
                # 找到并点击目标等级后，检查并清理打满的已结束对局
                self.check_join_full()
                if not self._running():
                    return False
                if self.join_full == 2:
                    self.win_exist = 1
                    while self._running() and self.join_full == 2:
                        self.clean_full()
                    if not self._running():
                        return False
                    # 清理会离开选等级界面，需重新查找并点击目标等级
                    r = self._scan_lv()
                    continue
                return True
            if r == 0:
                # 既没找到目标等级也没发现 no_lv，下拉查找
                r = self._find_lv_by_scroll()
                continue
            # r == 1：发现 no_lv 或下拉耗尽，刷新救援列表后重查
            self.prepare_battle()
            if not self._running():
                return False
            r = self._scan_lv()
        return False

    def _scan_lv(self):
        level_pictures = {
            level: f'./aim/quests/link_raid/backup_requests/lv/lv{level}/lv{level}'
            for level in (4, 6, 7, 8, 9, 10, 11, 12)
        }
        found = click_action.find_competing_item_with_result(
            self, self.level_choice, level_pictures, f'lv{self.level_choice}',
            search_region=LEVEL_LIST_SEARCH_REGION,
            skip_crowded=True,
        )
        if found == 2:
            self.signal.emit(str(f'lv{self.level_choice}找到了，下一步是选择'))
            if not self._running():
                return 1
            result = click_action.click_competing_item_with_result(
                self, self.level_choice, level_pictures, f'lv{self.level_choice}',
                search_region=LEVEL_LIST_SEARCH_REGION,
                skip_crowded=True,
            )
            if result == 2:
                self.signal.emit(str(f'lv{self.level_choice}点击完成'))
                return 2
            self._emit_log(f'lv{self.level_choice}点击失败，将刷新列表', 'WARNING')
            return 1
        no_lv = click_action.find_item_with_result(
            self, './aim/quests/link_raid/backup_requests/lv/no_lv', 'no_lv'
        )
        if no_lv == 2:
            self.signal.emit(str(f'当前列表无 lv{self.level_choice}（no_lv），将刷新救援列表'))
            return 1
        self.signal.emit(str(f'未找到 lv{self.level_choice} 且未发现 no_lv，将下拉查找'))
        return 0

    # 下拉前先额外复扫一次；仍未找到时只下拉一次并进行最后扫描。
    # 返回：2=找到并点击，1=发现 no_lv 或单次下拉后仍未找到（需刷新）
    def _find_lv_by_scroll(self):
        r = self._scan_lv()
        if r != 0 or not self._running():
            return 1 if not self._running() else r
        self.signal.emit(str(f'复扫仍未找到 lv{self.level_choice} 或 no_lv，执行一次下拉'))
        moved = click_action.move_a_to_b_scaled(
            1400, 1200, 1400, 400, self._running,
        )
        if moved != 2 or self._wait(SCROLL_SETTLE_DELAY):
            return 1
        self.signal.emit(str(f'下拉完成，最后查找一次 lv{self.level_choice}'))
        r = self._scan_lv()
        if r != 0:
            return r
        self.signal.emit(str(f'单次下拉后仍未找到 lv{self.level_choice} 或 no_lv，将刷新救援列表'))
        return 1

    def join_battle(self):
        result = 1

        # 点击 join 后可能进入编队，也可能遇到体力不足、战斗结束或房间满员。
        join_next_steps = (
            ('./aim/quests/link_raid/backup_requests/no_lp/no_lp', 'no_lp'),
            ('./aim/quests/link_raid/backup_requests/join/play', 'play'),
            ('./aim/quests/link_raid/backup_requests/join/full/already_end', 'already_end'),
            ('./aim/quests/link_raid/backup_requests/join/full/battle_full', 'battle_full'),
        )
        result = self._click_until(
            './aim/quests/link_raid/backup_requests/join', 'join',
            next_steps=join_next_steps,
        )
        if result == 2:
            self.signal.emit(str('join点击完成'))
        result = 1

        # 已结束和满员都表示当前候选已失效：关闭弹窗后重新匹配，绝不加入其它等级。
        while self._running():
            if self._wait(0.2):
                return
            recovery = click_action.find_first_item_with_result(
                self,
                (
                    ('./aim/quests/link_raid/backup_requests/join/full/already_end',
                     'already_end'),
                    ('./aim/quests/link_raid/backup_requests/join/full/battle_full',
                     'battle_full'),
                ),
            )
            if recovery is None:
                self.already_end = 1
                break
            _picture, recovery_name = recovery
            self.already_end = 2 if recovery_name == 'already_end' else 1
            if recovery_name == 'battle_full':
                self.signal.emit(str('点击 join 后房间已满，点 ok 后重新匹配加入'))
                ok_picture = './aim/quests/link_raid/backup_requests/join/full/ok'
            else:
                self.signal.emit(str('点击 join 后战斗已结束，点 ok 后重新匹配加入'))
                ok_picture = './aim/quests/link_raid/backup_requests/join/ok'
            result = click_action.click_contextual_item_with_result(
                self,
                f'./aim/quests/link_raid/backup_requests/join/full/{recovery_name}',
                recovery_name,
                ok_picture,
                'ok',
                search_region=JOIN_DIALOG_SEARCH_REGION,
            )
            if result != 2:
                # 单帧误报或弹窗正在变化时不寻找通用 OK，重新确认完整弹窗。
                continue
            self.signal.emit(str('ok点击完成'))
            result = 1
            if not self.prepare_matching_battle():
                return
            result = self._click_until(
                './aim/quests/link_raid/backup_requests/join', 'join',
                next_steps=join_next_steps,
            )
            if result == 2:
                self.signal.emit(str('join点击完成'))
            result = 1

        if not self._running():
            return

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

    def _wait_battle_outcome(self):
        """持续等待迟到的已结束弹窗，或确认并推进正常结算页。"""
        deadline = time.monotonic() + BATTLE_TIMEOUT
        tap_click_count = 0
        already_end_step = (
            './aim/quests/link_raid/backup_requests/join/full/already_end',
            'already_end',
        )
        back_step = (
            './aim/quests/link_raid/backup_requests/battle/back',
            'back',
        )
        tap_step = (
            './aim/quests/link_raid/backup_requests/battle/tap_to_countinue',
            'tap_to_countinue',
            {'foreground_variants': TAP_TO_CONTINUE_FOREGROUND_VARIANTS},
        )
        while self._running() and time.monotonic() < deadline:
            # 第一次真实 Tap 点击前不检查 back；迟到的 already_end 始终优先。
            states = [already_end_step]
            if tap_click_count:
                states.append(back_step)
            if tap_click_count < TAP_TO_CONTINUE_MAX_CLICKS:
                states.append(tap_step)
            outcome = click_action.find_first_item_with_result(self, tuple(states))
            if outcome is not None:
                _picture, state_name = outcome
                if state_name == 'already_end':
                    result = click_action.click_contextual_item_with_result(
                        self,
                        already_end_step[0],
                        already_end_step[1],
                        './aim/quests/link_raid/backup_requests/join/ok',
                        'ok',
                        search_region=JOIN_DIALOG_SEARCH_REGION,
                    )
                    if result == 2:
                        self.signal.emit(
                            'play 后稳定确认延迟出现的 already_end，'
                            '已单次点击其弹窗 OK，准备重新匹配'
                        )
                        return 'already_end'
                    # 单帧误报不能阻塞真实结算；本轮忽略 already_end 后继续检查其它状态。
                    fallback_states = tuple(
                        state for state in states if state[1] != 'already_end'
                    )
                    outcome = click_action.find_first_item_with_result(
                        self, fallback_states,
                    ) if fallback_states else None
                    if outcome is None:
                        if self._wait(min(
                                BATTLE_STATE_POLL_INTERVAL,
                                max(0, deadline - time.monotonic()),
                        )):
                            return None
                        continue
                    _picture, state_name = outcome
                if state_name == 'back' and tap_click_count:
                    self.signal.emit('已检测到下一步back，确认tap_to_countinue页面已经推进。')
                    return 'finished'
                if state_name == 'tap_to_countinue' \
                        and tap_click_count < TAP_TO_CONTINUE_MAX_CLICKS:
                    result = click_action.click_fixed_position_for_item_with_result(
                        self,
                        './aim/quests/link_raid/backup_requests/battle/tap_to_countinue',
                        'tap_to_countinue',
                        *TAP_TO_CONTINUE_POSITION_2K,
                        foreground_variants=TAP_TO_CONTINUE_FOREGROUND_VARIANTS,
                    )
                    if result == 2:
                        tap_click_count += 1
                        self.signal.emit(
                            f'tap_to_countinue已识别并执行第{tap_click_count}/'
                            f'{TAP_TO_CONTINUE_MAX_CLICKS}次安全点击，正在等待下一步页面出现。'
                        )
                        continue
            if self._wait(min(
                    BATTLE_STATE_POLL_INTERVAL,
                    max(0, deadline - time.monotonic()),
            )):
                return None
        if self._running():
            self._emit_log(
                f'等待战斗结算或already_end超过{BATTLE_TIMEOUT}秒，已安全停止。'
                '请检查游戏网络、模板语言和分辨率。',
                'ERROR',
            )
            self._finish()
        return None

    def _recover_already_ended_battle(self):
        if not self._running():
            return False
        if not self.prepare_matching_battle():
            return False
        self.join_battle()
        return self._running()

    # 完成战斗，然后点 back。点击战斗结束会出来的 tap_to_countinue
    def battle_and_finish(self):
        while self._running():
            outcome = self._wait_battle_outcome()
            if outcome == 'already_end':
                if not self._recover_already_ended_battle():
                    return
                continue
            if outcome != 'finished':
                return
            self.signal.emit('tap_to_countinue页面已推进')
            self.like_battle_result()
            if not self._running():
                return
            break

        # 点击结算界面的 back，点完后回到 boss 打脸的界面
        result = self._click_until('./aim/quests/link_raid/backup_requests/battle/back', 'back')
        if result == 2:
            self.signal.emit(str('back点击完成，一场战斗结束了'))

    def like_battle_result(self):
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
            self._emit_log('等待back超时，已安全停止。', 'ERROR')
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
                moved = click_action.move_a_to_b_scaled(
                    1400, 1000, 1400, 600, self._running,
                )
                if moved != 2:
                    self._emit_log('点赞列表滑动失败，结束本页点赞。', 'WARNING')
                    break
                click_action.move_position_scaled(
                    *LIKE_NEUTRAL_MOUSE_POSITION_2K, self._running,
                )
                self.signal.emit('点赞列表滑动完成，等待页面稳定后继续识别')
                if self._wait(LIKE_SCROLL_SETTLE_DELAY):
                    return
                result = retry_until(
                    lambda: click_action.click_item_with_result(
                        self,
                        './aim/quests/link_raid/backup_requests/battle/love',
                        'love',
                    ),
                    self._running,
                    timeout=LIKE_RETRY_TIMEOUT,
                    wait=self._wait,
                )
                if result == 1:
                    love_time = 0
                    self.signal.emit(str('滑动后连续 3 秒未找到可点赞目标，本页点赞结束'))
                else:
                    love_time = love_time - 1
                    self.signal.emit(str('滑动后已找到 love，点赞完成一次'))

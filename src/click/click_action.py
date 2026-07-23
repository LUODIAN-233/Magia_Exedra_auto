import time
from pathlib import Path

import pyautogui

from . import click_behavior
from src.packs import language_switcher, image_scaler


def _wait(self, seconds):
    wait = getattr(self, '_wait', None)
    if wait is not None:
        return wait(seconds)
    time.sleep(seconds)
    return False


#尝试点击一次，查询组内所有图片，返回点击结果return
def click_item_with_result(self, picture, name):
    check = 1  # 这个是判断要不要继续循环
    click_time = 1  # 尝试点击一次这玩意+1
    click_file = ''


    click_file = (f'{picture}_{click_time}.png')
    file_exist = Path(click_file)

    while (check == 1 and file_exist.exists()):
        click_file = (f'{picture}_{click_time}.png')
        click_time = click_time + 1

        file_exist=Path(click_file)
        print(f'文件状态是{file_exist}\n')

        if file_exist.exists():
            can_click = getattr(self, '_running', None)
            if can_click is not None and not can_click():
                return 1
            check = click_behavior.routine(click_file, name, can_click)
            print(f'点击{click_file}，点击返回值是{check}，成功点击是2，不点击是1')
            if _wait(self, 0.4):
                return 1
        else:
            print('文件耗尽\n')

    if (check == 1):
        click_time = click_time - 1
        print(f'尝试了{click_time-1}次数，没有找到{name}，当前点击事件执行结束\n')
        return check

    if (check == 2):
        print(f'点击{name}事件完成，当前点击事件执行结束\n')
        if _wait(self, 0.5):
            return 1
        return check



#尝试寻找目标一次，查询组内所有图片，返回寻找结果return
def find_item_with_result(self, picture, name):
    check = 1  # 这个是判断要不要继续循环
    click_time = 1  # 尝试点击一次这玩意+1
    click_file = ''

    click_file = (f'{picture}_{click_time}.png')
    file_exist = Path(click_file)

    while (check == 1 and file_exist.exists()):
        click_file = (f'{picture}_{click_time}.png')
        click_time = click_time + 1

        file_exist = Path(click_file)
        print(f'文件状态是{file_exist}\n')
        if file_exist.exists():
            can_find = getattr(self, '_running', None)
            if can_find is not None and not can_find():
                return 1
            check = click_behavior.routine_only_find(click_file, name, can_find)
            print(f'寻找{click_file}，寻找返回值是{check}，成功寻找是2，没找到是1')
            if _wait(self, 0.4):
                return 1
        else:
            print('文件耗尽\n')

    if (check == 1):
        click_time = click_time - 1
        print(f'尝试了{click_time-1}次数，没有找到{name}，当前寻找事件执行结束\n')
        return check
    if (check == 2):
        print(f'寻找{name}事件完成，找到了，当前寻找事件执行结束\n')
        if _wait(self, 0.5):
            return 1
        return check

#用于点击特定位置，输入坐标，第一个为窗口左到右的偏移，第二个上到下，注意上到下会有一个窗体厚度，不同缩放倍率会不同！
def click_position(move_lelt, move_top, can_click=None):
    # 把游戏窗口弄出来
    window = click_behavior.find_win('MadokaExedra')
    if window is None:
        return 1
    left, top, width, height = window
    if not (0 <= move_lelt < width and 0 <= move_top < height):
        print(f'点击坐标超出游戏窗口: ({move_lelt}, {move_top})，窗口大小 {width}x{height}')
        return 1
    try:
        time.sleep(0.1)
        if can_click is not None and not can_click():
            return 1
        pyautogui.moveTo(left + move_lelt, top + move_top)
        time.sleep(0.1)
        if can_click is not None and not can_click():
            return 1
        pyautogui.click(left + move_lelt, top + move_top, button='left')
        time.sleep(0.1)
    except Exception as e:
        print(f'坐标点击失败: {e}')
        return 1
    return 2

def move_a_to_b(move_lelt_a, move_top_a, move_lelt_b, move_top_b, can_move=None):
    window = click_behavior.find_win('MadokaExedra')
    if window is None:
        return 1
    left, top, width, height = window
    points = ((move_lelt_a, move_top_a), (move_lelt_b, move_top_b))
    if any(not (0 <= x < width and 0 <= y < height) for x, y in points):
        print(f'拖拽坐标超出游戏窗口: {points}，窗口大小 {width}x{height}')
        return 1
    try:
        time.sleep(0.1)
        if can_move is not None and not can_move():
            return 1
        pyautogui.moveTo(left + move_lelt_a, top + move_top_a)
        time.sleep(0.1)
        if can_move is not None and not can_move():
            return 1
        pyautogui.dragTo(left + move_lelt_b, top + move_top_b, duration=2, button='left')
        time.sleep(0.1)
    except Exception as e:
        print(f'坐标拖拽失败: {e}')
        return 1
    return 2


#按当前激活分辨率缩放 2K 基准坐标（窗口相对）。
#读取 language_switcher.current_selection() 拿到当前 pack 的分辨率，
#再用 image_scaler.scale_factor() 算出相对 2K 源的倍数（2K 源自身=1.0）。
#这样 link_raid 开头那些硬编码坐标在 720p/1080p/2K/4K 下都能命中同一处 UI。
def _res_scale_factor():
    sel = language_switcher.current_selection()
    if not sel or not sel[1]:
        return None
    if sel[1] == image_scaler.SOURCE_RES:
        return 1.0
    f = image_scaler.scale_factor(sel[1])
    return f


def click_position_scaled(x_2k, y_2k, can_click=None):
    #把 2K 基准坐标按当前分辨率缩放后点击
    f = _res_scale_factor()
    if f is None:
        print('无法确认模板 pack 的坐标缩放倍率，拒绝位置点击')
        return 1
    return click_position(round(x_2k * f), round(y_2k * f), can_click)


def move_a_to_b_scaled(ax_2k, ay_2k, bx_2k, by_2k, can_move=None):
    #把 2K 基准起止坐标按当前分辨率缩放后拖拽
    f = _res_scale_factor()
    if f is None:
        print('无法确认模板 pack 的坐标缩放倍率，拒绝拖拽')
        return 1
    return move_a_to_b(
        round(ax_2k * f), round(ay_2k * f),
        round(bx_2k * f), round(by_2k * f),
        can_move,
    )


#识别游戏窗口客户区分辨率，并与当前激活模板 pack 的标称分辨率做容差比对。
#客户区是实际渲染区（不含标题栏/边框），比外框尺寸更贴合 pack 标称分辨率。
#容差：宽高各自允许 |detected - expected| <= max(40, round(expected * tolerance))，
#兼容标题栏/边框/DPI 缩放带来的小幅偏差，不要求严格相等。
def detect_window_resolution(tolerance=0.1):
    sel = language_switcher.current_selection()
    expected_res = sel[1] if sel else None
    expected = None
    if expected_res:
        try:
            w_s, h_s = expected_res.lower().split('x')
            expected = (int(w_s), int(h_s))
        except Exception:
            expected = None

    detected = click_behavior.get_client_size()

    result = {
        'detected': detected,
        'expected': expected,
        'expected_res': expected_res,
        'matched': False,
        'message': '',
    }

    if detected is None:
        result['message'] = '未能读取游戏窗口客户区尺寸（窗口可能未显示或已被关闭）'
        return result
    if expected is None:
        result['message'] = f'未激活模板 pack，无法比对分辨率。检测到窗口客户区: {detected[0]}x{detected[1]}'
        return result

    def _within(d, e):
        margin = max(40, round(e * tolerance))
        return abs(d - e) <= margin

    matched = _within(detected[0], expected[0]) and _within(detected[1], expected[1])
    result['matched'] = matched
    if matched:
        result['message'] = f'窗口分辨率匹配: 检测到 {detected[0]}x{detected[1]}，模板 pack {expected_res}'
    else:
        result['message'] = (f'窗口分辨率不匹配: 检测到 {detected[0]}x{detected[1]}，'
                             f'模板 pack 为 {expected_res}，请检查游戏窗口分辨率与所选模板是否一致')
    return result

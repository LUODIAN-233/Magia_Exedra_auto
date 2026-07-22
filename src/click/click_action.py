import time
from pathlib import Path

import pyautogui

from . import click_behavior
from src.packs import language_switcher, image_scaler


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
            time.sleep(0.4)
        else:
            print('文件耗尽\n')

    if (check == 1):
        click_time = click_time - 1
        print(f'尝试了{click_time-1}次数，没有找到{name}，当前点击事件执行结束\n')
        return check

    if (check == 2):
        print(f'点击{name}事件完成，当前点击事件执行结束\n')
        time.sleep(0.5)
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
            check = click_behavior.routine_only_find(click_file, name)
            print(f'寻找{click_file}，寻找返回值是{check}，成功寻找是2，没找到是1')
            time.sleep(0.4)
        else:
            print('文件耗尽\n')

    if (check == 1):
        click_time = click_time - 1
        print(f'尝试了{click_time-1}次数，没有找到{name}，当前寻找事件执行结束\n')
        return check
    if (check == 2):
        print(f'寻找{name}事件完成，找到了，当前寻找事件执行结束\n')
        time.sleep(0.5)
        return check

#用于点击特定位置，输入坐标，第一个为窗口左到右的偏移，第二个上到下，注意上到下会有一个窗体厚度，不同缩放倍率会不同！
def click_position(move_lelt,move_top):
    # 把游戏窗口弄出来
    window = click_behavior.find_win('MadokaExedra')
    if window is None:
        return 1
    left, top, _width, _height = window
    time.sleep(0.1)
    pyautogui.moveTo(left + move_lelt, top + move_top)
    time.sleep(0.1)
    pyautogui.click(left + move_lelt, top + move_top,button='left')
    time.sleep(0.1)
    return 2

def move_a_to_b(move_lelt_a,move_top_a,move_lelt_b,move_top_b):
    window = click_behavior.find_win('MadokaExedra')
    if window is None:
        return 1
    left, top, _width, _height = window
    time.sleep(0.1)
    pyautogui.moveTo(left + move_lelt_a, top + move_top_a)
    time.sleep(0.1)
    pyautogui.dragTo(left + move_lelt_b, top + move_top_b,duration=2,button='left')
    time.sleep(0.1)
    return 2


#按当前激活分辨率缩放 2K 基准坐标（窗口相对）。
#读取 language_switcher.current_selection() 拿到当前 pack 的分辨率，
#再用 image_scaler.scale_factor() 算出相对 2K 源的倍数（2K 源自身=1.0）。
#这样 link_raid 开头那些硬编码坐标在 720p/1080p/2K/4K 下都能命中同一处 UI。
def _res_scale_factor():
    sel = language_switcher.current_selection()
    if not sel or not sel[1]:
        return 1.0
    f = image_scaler.scale_factor(sel[1])
    return f if f else 1.0


def click_position_scaled(x_2k, y_2k):
    #把 2K 基准坐标按当前分辨率缩放后点击
    f = _res_scale_factor()
    return click_position(round(x_2k * f), round(y_2k * f))


def move_a_to_b_scaled(ax_2k, ay_2k, bx_2k, by_2k):
    #把 2K 基准起止坐标按当前分辨率缩放后拖拽
    f = _res_scale_factor()
    return move_a_to_b(round(ax_2k * f), round(ay_2k * f), round(bx_2k * f), round(by_2k * f))

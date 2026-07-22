import time
import math
import cv2
import numpy as np
import pyautogui

import pywinctl as pwc

def get_xy(img_model_path):
    """
    找到需要点击什么的坐标
    :param img_model_path:输入需要找的图片
    :return:坐标,匹配度（1是完全，0是不匹配）
    """
    window = find_win('MadokaExedra')
    if window is None:
        return None, 0.0

    left, top, width, height = window
    try:
        screenshot = pyautogui.screenshot(region=(left, top, width, height))
        img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
    except Exception as e:
        print(f"游戏窗口截图失败: {e}")
        return None, 0.0

    #要找的模板
    img_terminal = cv2.imread(img_model_path)
    if img_terminal is None:
        print(f"模板图片读取失败: {img_model_path}")
        return None, 0.0

    #读取模板宽度和高度
    height,width,ch= img_terminal.shape
    if height > img.shape[0] or width > img.shape[1]:
        print(f"模板尺寸大于游戏窗口: {img_model_path}")
        return None, 0.0

    #匹配，返回一个值
    result=cv2.matchTemplate(img,img_terminal, cv2.TM_SQDIFF_NORMED)

    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

    # 匹配率查看（TM_SQDIFF_NORMED越接近0越匹配,所以这里反一下）
    match_rate = math.sqrt(min_val)
    # match_rate = min_val
    print(f"匹配率: {1-match_rate:.4f}")

    #这个输出的是左上角坐标，是result的第3个值
    upper_left = cv2.minMaxLoc(result)[2]


    #算出右下角，这里要注意，你不能直接取出右下角，不然会发生不幸。截图需要准确
    lower_right = (upper_left[0]+ width, upper_left[1]+height)

    #计算中心
    avg = (
        left + int((upper_left[0] + lower_right[0]) / 2),
        top + int((upper_left[1] + lower_right[1]) / 2),
    )
    return avg,1-match_rate

def click_auto (var_avg):
    """
    接受要点的坐标然后点
    :param var_avg:坐标组
    :return:不
    """
    #这里采取的先移动后点击的策略，如果直接点击，游戏会判定无效
    pyautogui.moveTo(var_avg[0],var_avg[1])
    time.sleep(0.1) #等待一会
    pyautogui.click(var_avg[0],var_avg[1],button='left')

    print('当前点击事件执行')

    #点击完成等待0.5秒，防止奇怪的问题发生
    time.sleep(0.1)


def routine (img_model_path,name, can_click=None):
    """
    点击的事实上的使用函数
    :param img_model_path:图片
    :param name:这个没有实际作用，只是一个提示
    :return:输出2代表点了，输出1代表没点
    """
    avg,match_rate= get_xy(img_model_path)

    if avg is not None and match_rate>0.8:
        if can_click is not None and not can_click():
            print(f'任务已停止，不点击{name}')
            return int(1)
        print(f'点击{name}')
        click_auto(avg)
        return int(2)
    else:
        print(f'匹配率太低，不点击{name}')
        return int(1)


def routine_only_find (img_model_path,name):
    """
    点击的事实上的使用函数
    :param img_model_path:图片
    :param name:这个没有实际作用，只是一个提示
    :return:输出2代表点了，输出1代表没点
    """
    avg,match_rate= get_xy(img_model_path)

    if avg is not None and match_rate>0.8:
        print(f'存在{name}元素，不会点击')
        # click_auto(avg)
        return int(2)
    else:
        print(f'匹配率太低，不存在{name}元素，这个不会进行点击')
        return int(1)

def find_win(title):
    """
    点击的事实上的使用函数
    :param img_model_path:图片
    :param name:这个没有实际作用，只是一个提示
    :return:输出2代表点了，输出1代表没点
    """

    wins = pwc.getWindowsWithTitle(title)
    if not wins:
        print(f"找不到窗口: {title}\n")
        return None

    w = wins[0]
    if w.isMinimized:
        w.restore()
        print(f"正常找到\n")
    try:
        w.activate()  # 置前/聚焦
    except Exception as e:
        print(f"窗口聚焦失败: {e}")
        return None
    print(f"窗口已弹出\n")
    time.sleep(0.2)
    print(f"返回的两个数据是，left：{w.left}，top：{w.top}")
    if w.width <= 0 or w.height <= 0:
        print(f"游戏窗口尺寸无效: {w.width}x{w.height}")
        return None
    return w.left, w.top, w.width, w.height




#routine("./aim/2222.png",'bbb')

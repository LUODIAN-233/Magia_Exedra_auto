import time
import math
import logging
import cv2
import numpy as np
import pyautogui

import pywinctl as pwc

logger = logging.getLogger(__name__)


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
        logger.warning("游戏窗口截图失败: %s", e)
        return None, 0.0

    #要找的模板
    img_terminal = cv2.imread(img_model_path)
    if img_terminal is None:
        logger.warning("模板图片读取失败: %s", img_model_path)
        return None, 0.0

    #读取模板宽度和高度
    height,width,ch= img_terminal.shape
    if height > img.shape[0] or width > img.shape[1]:
        logger.warning("模板尺寸大于游戏窗口: %s", img_model_path)
        return None, 0.0

    #匹配，返回一个值
    try:
        result = cv2.matchTemplate(img, img_terminal, cv2.TM_SQDIFF_NORMED)
        min_val, _max_val, min_loc, _max_loc = cv2.minMaxLoc(result)
    except cv2.error as e:
        logger.warning("模板匹配失败: %s", e)
        return None, 0.0

    # 匹配率查看（TM_SQDIFF_NORMED越接近0越匹配,所以这里反一下）
    match_rate = math.sqrt(min_val)
    # match_rate = min_val
    logger.debug("匹配率: %.4f", 1-match_rate)

    #这个输出的是左上角坐标，是result的第3个值
    upper_left = min_loc


    #算出右下角，这里要注意，你不能直接取出右下角，不然会发生不幸。截图需要准确
    lower_right = (upper_left[0]+ width, upper_left[1]+height)

    #计算中心
    avg = (
        left + int((upper_left[0] + lower_right[0]) / 2),
        top + int((upper_left[1] + lower_right[1]) / 2),
    )
    return avg,1-match_rate

def click_auto(var_avg, can_click=None):
    """
    接受要点的坐标然后点
    :param var_avg:坐标组
    :return:不
    """
    #这里采取的先移动后点击的策略，如果直接点击，游戏会判定无效
    try:
        pyautogui.moveTo(var_avg[0], var_avg[1])
        time.sleep(0.1) #等待一会
        if can_click is not None and not can_click():
            logger.debug('任务已停止，取消点击')
            return 1
        pyautogui.click(var_avg[0], var_avg[1], button='left')
    except Exception as e:
        logger.warning('鼠标点击失败: %s', e)
        return 1

    logger.debug('当前点击事件执行')

    #点击完成等待0.5秒，防止奇怪的问题发生
    time.sleep(0.1)
    return 2


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
            logger.debug('任务已停止，不点击%s', name)
            return int(1)
        logger.debug('点击%s', name)
        return int(click_auto(avg, can_click))
    else:
        logger.debug('匹配率太低，不点击%s', name)
        return int(1)


def routine_only_find(img_model_path, name, can_find=None):
    """
    点击的事实上的使用函数
    :param img_model_path:图片
    :param name:这个没有实际作用，只是一个提示
    :return:输出2代表点了，输出1代表没点
    """
    if can_find is not None and not can_find():
        return int(1)
    avg,match_rate= get_xy(img_model_path)
    if can_find is not None and not can_find():
        return int(1)

    if avg is not None and match_rate>0.8:
        logger.debug('存在%s元素，不会点击', name)
        # click_auto(avg)
        return int(2)
    else:
        logger.debug('匹配率太低，不存在%s元素，这个不会进行点击', name)
        return int(1)

def get_client_size(title='MadokaExedra'):
    """
    返回游戏窗口客户区（实际渲染区域，不含标题栏/边框）的 (width, height)。
    客户区才是游戏真正的"画面分辨率"，比外框尺寸更贴合模板 pack 的标称分辨率。
    找不到窗口或读取失败返回 None。
    注意：本函数不激活/恢复窗口，调用方需保证窗口已正常显示（如先调用 find_win）。
    """
    try:
        wins = pwc.getWindowsWithTitle(title)
    except Exception as e:
        logger.warning("查找窗口失败: %s", e)
        return None
    if not wins:
        return None
    try:
        rect = wins[0].getClientFrame()
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 0 or height <= 0:
            return None
        return width, height
    except Exception as e:
        logger.warning("读取客户区失败: %s", e)
        return None


def find_win(title):
    """
    恢复并聚焦第一个标题匹配的窗口。
    成功返回 (left, top, width, height)，失败返回 None；不使用模板动作的 2/1 约定。
    """

    try:
        wins = pwc.getWindowsWithTitle(title)
    except Exception as e:
        logger.warning("查找窗口失败: %s", e)
        return None
    if not wins:
        logger.debug("找不到窗口: %s", title)
        return None

    try:
        w = wins[0]
        if w.isMinimized:
            w.restore()
            logger.debug("窗口从最小化恢复")
        w.activate()  # 置前/聚焦
    except Exception as e:
        logger.warning("读取或聚焦窗口失败: %s", e)
        return None
    logger.debug("窗口已弹出")
    time.sleep(0.2)
    try:
        left, top, width, height = w.left, w.top, w.width, w.height
    except Exception as e:
        logger.warning("读取窗口位置失败: %s", e)
        return None
    logger.debug("返回的两个数据是，left：%s，top：%s", left, top)
    if width <= 0 or height <= 0:
        logger.warning("游戏窗口尺寸无效: %sx%s", width, height)
        return None
    return left, top, width, height




#routine("./aim/2222.png",'bbb')

import time
import math
import logging
import os
from functools import lru_cache

import cv2
import numpy as np
import pyautogui

import pywinctl as pwc
from contextlib import nullcontext

from src.core.automation_position import capture_client_position, resolve_client_position

logger = logging.getLogger(__name__)


def _worker_from_callback(callback):
    return getattr(callback, '__self__', None)


def _wait_for_user(callback):
    worker = _worker_from_callback(callback)
    wait = getattr(worker, '_wait_for_user_idle', None)
    return wait is None or wait()


def _automation_input(callback):
    worker = _worker_from_callback(callback)
    guard = getattr(worker, '_automation_input', None)
    return guard() if guard is not None else nullcontext()


def _record_automation_position(callback, position):
    worker = _worker_from_callback(callback)
    if worker is not None:
        worker._last_automation_position = capture_client_position(
            position, get_client_region('MadokaExedra'),
        )


def _capture_region(region):
    try:
        screenshot = pyautogui.screenshot(region=region)
        image = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        return cv2.resize(image, (320, 180), interpolation=cv2.INTER_AREA)
    except Exception as e:
        logger.warning('游戏窗口截图失败: %s', e)
        return None


def frame_change_ratio(first, second, pixel_delta=25):
    if first is None or second is None or first.shape != second.shape:
        return None
    difference = cv2.absdiff(first, second)
    changed = np.max(difference, axis=2) >= pixel_delta
    return float(np.count_nonzero(changed)) / changed.size


def screen_changes_significantly(worker, duration=2, change_threshold=0.5):
    """只观察可见游戏客户区；返回 True/False，截图或取消失败返回 None。"""
    can_continue = getattr(worker, '_running', None)
    if can_continue is not None and not can_continue():
        return None
    if not _wait_for_user(can_continue):
        return None
    if find_win('MadokaExedra') is None:
        return None
    client_region = get_client_region('MadokaExedra')
    if client_region is None:
        return None

    first = _capture_region(client_region)
    if first is None:
        return None
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        wait_time = min(0.25, max(0, deadline - time.monotonic()))
        wait = getattr(worker, '_wait', None)
        if wait is not None and wait(wait_time):
            return None
        if can_continue is not None and not can_continue():
            return None
        current = _capture_region(client_region)
        ratio = frame_change_ratio(first, current)
        if ratio is None:
            return None
        if ratio > change_threshold:
            logger.debug('画面变化比例 %.2f，判定为动态画面', ratio)
            return True
    return False


def click_last_automation_position(worker):
    can_click = getattr(worker, '_running', None)
    if can_click is not None and not can_click():
        return 1
    if not _wait_for_user(can_click):
        return 1
    record = getattr(worker, '_last_automation_position', None)
    if record is None:
        logger.debug('没有上一次自动化位置，跳过恢复点击')
        return 1
    window = find_win('MadokaExedra')
    if window is None:
        return 1
    client_region = get_client_region('MadokaExedra')
    position = resolve_client_position(record, client_region)
    if position is None:
        logger.warning('游戏客户区尺寸已变化或旧位置无效，跳过恢复点击: %s', record)
        return 1
    return click_auto(position, can_click)


def _capture_game_window():
    window = find_win('MadokaExedra')
    if window is None:
        return None, None
    region = get_client_region('MadokaExedra')
    if region is None:
        return None, None
    left, top, width, height = region
    try:
        screenshot = pyautogui.screenshot(region=region)
        return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR), (left, top)
    except Exception as e:
        logger.warning('游戏客户区截图失败: %s', e)
        return None, None


def _crop_search_region(screen, origin, search_region):
    """按客户区归一化坐标裁剪搜索范围，并同步修正屏幕坐标原点。"""
    if search_region is None:
        return screen, origin
    try:
        left_ratio, top_ratio, right_ratio, bottom_ratio = map(float, search_region)
    except (TypeError, ValueError):
        logger.warning('模板搜索区域格式无效: %r', search_region)
        return None, None
    if not (0 <= left_ratio < right_ratio <= 1
            and 0 <= top_ratio < bottom_ratio <= 1):
        logger.warning('模板搜索区域超出客户区: %r', search_region)
        return None, None
    height, width = screen.shape[:2]
    left = round(width * left_ratio)
    top = round(height * top_ratio)
    right = round(width * right_ratio)
    bottom = round(height * bottom_ratio)
    if right <= left or bottom <= top:
        return None, None
    return screen[top:bottom, left:right], (origin[0] + left, origin[1] + top)


@lru_cache(maxsize=512)
def _load_template_cached(path, _resolved_path, signature):
    template = cv2.imread(path)
    if template is None:
        return None, None
    return template, cv2.GaussianBlur(template, (3, 3), 0)


def _load_template(path):
    path_text = str(path)
    try:
        stat = os.stat(path_text)
        signature = (stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_size)
        resolved = os.path.normcase(os.path.realpath(path_text))
    except OSError:
        template = cv2.imread(path_text)
        if template is None:
            return None, None
        return template, cv2.GaussianBlur(template, (3, 3), 0)
    return _load_template_cached(path_text, resolved, signature)


def _foreground_mask(template):
    """从深色背景上的亮色文字模板提取文字轮廓。"""
    gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
    _threshold, mask = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )
    return mask if np.any(mask) else None


def _foreground_binary(screen):
    """按局部亮度提取画面文字，避免淡入淡出改变绝对亮度。"""
    gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    short_side = min(gray.shape[:2])
    max_block = short_side if short_side % 2 else short_side - 1
    block_size = max(15, round(short_side * 31 / 1440))
    if block_size % 2 == 0:
        block_size += 1
    block_size = min(block_size, max_block)
    if block_size < 3:
        return None
    return cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size, 0,
    )


def _foreground_support(mask):
    """文字笔画使用满权重，周围一像素负空间使用四成权重。"""
    foreground = mask > 0
    nearby = cv2.dilate(mask, np.ones((3, 3), np.uint8)) > 0
    support = np.zeros(mask.shape, np.float32)
    support[nearby] = 0.4
    support[foreground] = 1.0
    return support


@lru_cache(maxsize=512)
def _load_foreground_mask_cached(path, resolved_path, signature):
    template, _match_template = _load_template_cached(path, resolved_path, signature)
    return None if template is None else _foreground_mask(template)


def _load_foreground_mask(path):
    path_text = str(path)
    try:
        stat = os.stat(path_text)
        signature = (stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_size)
        resolved = os.path.normcase(os.path.realpath(path_text))
    except OSError:
        template, _match_template = _load_template(path_text)
        return None if template is None else _foreground_mask(template)
    return _load_foreground_mask_cached(path_text, resolved, signature)


def _match_one(match_screen, match_template, mask=None):
    height, width = match_template.shape[:2]
    if height > match_screen.shape[0] or width > match_screen.shape[1]:
        return None
    try:
        if mask is None:
            result = cv2.matchTemplate(
                match_screen, match_template, cv2.TM_SQDIFF_NORMED,
            )
        else:
            result = cv2.matchTemplate(
                match_screen, match_template, cv2.TM_SQDIFF_NORMED, mask=mask,
            )
            # 带掩码的归一化结果在全黑区域可能产生 NaN/Inf，统一视为最差匹配。
            result = np.nan_to_num(result, nan=1.0, posinf=1.0, neginf=1.0)
        min_val, _max_val, min_loc, _max_loc = cv2.minMaxLoc(result)
    except cv2.error as e:
        logger.warning('模板匹配失败: %s', e)
        return None
    score = 1 - math.sqrt(max(0.0, min(1.0, min_val)))
    return min_loc, (width, height), score


def _match_result_candidates(result, size, limit=8):
    """从已计算的匹配图中提取互不重叠的候选点。"""
    width, height = size
    result = result.copy()
    candidates = []
    suppress_x = max(8, width // 2)
    suppress_y = max(8, height // 2)
    for _ in range(limit):
        min_val, _max_val, min_loc, _max_loc = cv2.minMaxLoc(result)
        if min_val >= 1.0:
            break
        score = 1 - math.sqrt(max(0.0, min(1.0, min_val)))
        candidates.append((min_loc, (width, height), score))
        x, y = min_loc
        left = max(0, x - suppress_x)
        top = max(0, y - suppress_y)
        right = min(result.shape[1], x + suppress_x + 1)
        bottom = min(result.shape[0], y + suppress_y + 1)
        result[top:bottom, left:right] = 1.0
    return candidates


def best_template_matches(template_groups, search_region=None, foreground_groups=None):
    """让多组模板共享一帧，按组返回各自最高分的匹配结果。"""
    groups = [tuple(paths) for paths in template_groups]
    foreground = ([False] * len(groups) if foreground_groups is None
                  else list(foreground_groups))
    if len(foreground) != len(groups):
        raise ValueError('foreground_groups 必须与 template_groups 等长')
    empty = [(None, 0.0, None) for _paths in groups]
    screen, origin = _capture_game_window()
    if screen is None:
        return empty
    screen, origin = _crop_search_region(screen, origin, search_region)
    if screen is None:
        return empty
    # 整组候选共享同一张截图和预处理结果，保证分数可比并避免重复处理全窗口。
    match_screen = None
    foreground_screen = None
    results = []
    for template_paths, use_foreground in zip(groups, foreground):
        best = None
        for path in template_paths:
            _template, match_template = _load_template(path)
            if match_template is None:
                logger.warning('模板图片读取失败: %s', path)
                continue
            mask = _load_foreground_mask(path) if use_foreground else None
            if use_foreground and mask is None:
                logger.warning('无法生成模板文字前景掩码: %s', path)
                continue
            if use_foreground:
                if foreground_screen is None:
                    foreground_screen = _foreground_binary(screen)
                if foreground_screen is None:
                    logger.warning('无法从游戏画面提取文字前景')
                    continue
                # 加权检查文字及其周边负空间，兼顾淡入淡出与纯亮色误报。
                support = _foreground_support(mask)
                matched = _match_one(foreground_screen, mask, support)
            else:
                if match_screen is None:
                    match_screen = cv2.GaussianBlur(screen, (3, 3), 0)
                matched = _match_one(match_screen, match_template)
            if matched is None:
                logger.warning('模板尺寸大于游戏窗口或无法匹配: %s', path)
                continue
            location, size, score = matched
            logger.debug('候选模板 %s 匹配率: %.4f', path, score)
            if best is None or score > best[0]:
                best = score, location, size, str(path)
        if best is None:
            results.append((None, 0.0, None))
            continue
        score, location, size, path = best
        avg = (
            origin[0] + location[0] + size[0] // 2,
            origin[1] + location[1] + size[1] // 2,
        )
        logger.debug('模板组最高匹配: %s，匹配率 %.4f', path, score)
        results.append((avg, score, path))
    return results


def best_template_match(template_paths, search_region=None, foreground=False):
    """在同一帧中比较整组模板，返回全局最高分的 (坐标, 分数, 路径)。"""
    return best_template_matches(
        (template_paths,), search_region, foreground_groups=(foreground,),
    )[0]


def _prepare_competing_templates(match_screen, template_groups):
    """读取模板并缓存整图匹配结果，同一帧内供所有候选位置复用。"""
    prepared = []
    for label, template_paths in template_groups.items():
        for path in template_paths:
            template, match_template = _load_template(path)
            if template is None:
                logger.warning('模板图片读取失败: %s', path)
                continue
            height, width = template.shape[:2]
            if height > match_screen.shape[0] or width > match_screen.shape[1]:
                continue
            try:
                result = cv2.matchTemplate(
                    match_screen, match_template, cv2.TM_SQDIFF_NORMED,
                )
            except cv2.error as e:
                logger.warning('模板匹配失败: %s', e)
                continue
            prepared.append((label, str(path), match_template, result, (width, height)))
    return prepared


def _competing_match_at_location(match_screen, origin, selected, prepared_templates,
                                 selected_location, selected_size, selected_score,
                                 selected_path, radius):
    best = selected_score, selected, selected_location, selected_size, selected_path
    text_best = None
    for label, path, match_template, result, size in prepared_templates:
        width, height = size
        x, y = selected_location
        left = max(0, x - radius)
        top = max(0, y - radius)
        right = min(result.shape[1], x + radius + 1)
        bottom = min(result.shape[0], y + radius + 1)
        local = result[top:bottom, left:right]
        if local.size == 0:
            continue
        min_val, _max_val, min_loc, _max_loc = cv2.minMaxLoc(local)
        score = 1 - math.sqrt(max(0.0, min(1.0, min_val)))
        location = (left + min_loc[0], top + min_loc[1])
        if score > best[0]:
            best = score, label, location, size, path

        margin_x = round(width * 0.55)
        right_margin = 5
        margin_y = max(3, round(height * 0.12))
        text_template = match_template[margin_y:height - margin_y,
                                       margin_x:width - right_margin]
        text_screen = match_screen[location[1] + margin_y:location[1] + height - margin_y,
                                   location[0] + margin_x:location[0] + width - right_margin]
        if text_template.size == 0 or text_screen.shape != text_template.shape:
            continue
        text_value = float(cv2.matchTemplate(
            text_screen, text_template, cv2.TM_SQDIFF_NORMED
        )[0, 0])
        text_score = 1 - math.sqrt(max(0.0, min(1.0, text_value)))
        if text_best is None or text_score > text_best[0]:
            text_best = text_score, label, path
    score, label, location, size, path = best
    if text_best is None:
        return label, None, None, score, 0.0, path, None
    text_score, text_label, text_path = text_best
    avg = (origin[0] + selected_location[0] + selected_size[0] // 2,
           origin[1] + selected_location[1] + selected_size[1] // 2)
    return label, text_label, avg, score, text_score, path, text_path


def best_competing_template_matches(selected, template_groups, radius=3, search_region=None,
                                    max_candidates=8):
    """返回多个等级候选点，供上层跳过拥挤的救援条目。"""
    screen, origin = _capture_game_window()
    if screen is None:
        return []
    screen, origin = _crop_search_region(screen, origin, search_region)
    if screen is None:
        return []
    match_screen = cv2.GaussianBlur(screen, (3, 3), 0)
    prepared_templates = _prepare_competing_templates(match_screen, template_groups)
    selected_candidates = []
    for label, path, _template, result, size in prepared_templates:
        if label != selected:
            continue
        for location, size, score in _match_result_candidates(result, size, max_candidates):
            center = (origin[0] + location[0] + size[0] // 2,
                      origin[1] + location[1] + size[1] // 2)
            if any(max(abs(center[0] - old[0]), abs(center[1] - old[1])) <= max(size)
                   for old, *_rest in selected_candidates):
                continue
            selected_candidates.append((center, score, location, size, str(path)))
    selected_candidates.sort(key=lambda item: item[1], reverse=True)

    matches = []
    for _center, score, location, size, path in selected_candidates[:max_candidates]:
        matches.append(_competing_match_at_location(
            match_screen, origin, selected, prepared_templates,
            location, size, score, path, radius,
        ))
    return matches


def _digit_has_upper_loop(digit_mask):
    """数字 9 有一个明显靠上的闭合环；用于和 4/6/8 等单数字区分。"""
    if digit_mask.size == 0:
        return False
    padded = np.pad(digit_mask.astype(np.uint8), 1)
    outside = (1 - padded).astype(np.uint8)
    flood_mask = np.zeros((outside.shape[0] + 2, outside.shape[1] + 2), np.uint8)
    cv2.floodFill(outside, flood_mask, (0, 0), 2)
    holes = (outside == 1).astype(np.uint8)
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(holes, 8)
    min_area = max(2, round(int(digit_mask.sum()) * 0.04))
    significant = [stats[index] for index in range(1, count)
                   if stats[index, cv2.CC_STAT_AREA] >= min_area]
    if len(significant) != 1:
        return False
    hole = significant[0]
    center_y = (hole[cv2.CC_STAT_TOP] + hole[cv2.CC_STAT_HEIGHT] / 2) / padded.shape[0]
    return bool(center_y < 0.43)


def _participant_count_is_crowded(mask, client_width):
    """从参加人数区域判断是否为 9/10 或 10/10；无法判断时返回 None。"""
    _ys, xs = np.where(mask)
    if xs.size == 0:
        return None
    text_width = int(xs.max() - xs.min() + 1)
    full_width = round(client_width * 0.044)
    if text_width >= full_width:
        return True

    count, labels, stats, _centroids = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), 8,
    )
    min_height = max(5, round(mask.shape[0] * 0.30))
    min_area = max(6, round(mask.size * 0.003))
    components = [index for index in range(1, count)
                  if stats[index, cv2.CC_STAT_HEIGHT] >= min_height
                  and stats[index, cv2.CC_STAT_AREA] >= min_area]
    if not components:
        return None
    numerator = min(components, key=lambda index: stats[index, cv2.CC_STAT_LEFT])
    left = stats[numerator, cv2.CC_STAT_LEFT]
    top = stats[numerator, cv2.CC_STAT_TOP]
    width = stats[numerator, cv2.CC_STAT_WIDTH]
    height = stats[numerator, cv2.CC_STAT_HEIGHT]
    digit_mask = labels[top:top + height, left:left + width] == numerator
    return _digit_has_upper_loop(digit_mask)


def participant_count_crowded_near(point):
    """识别拥挤状态：True=9/10或10/10，False=至多8/10，None=无法判断。"""
    if point is None:
        return None
    screen, origin = _capture_game_window()
    if screen is None:
        return None
    client = get_client_region('MadokaExedra')
    if client is None:
        return None
    _left, _top, width, height = client
    x = round(point[0] - origin[0])
    y = round(point[1] - origin[1])
    left = max(0, x - round(width * 0.005))
    right = min(screen.shape[1], x + round(width * 0.065))
    top = max(0, y + round(height * 0.080))
    bottom = min(screen.shape[0], y + round(height * 0.120))
    if right <= left or bottom <= top:
        return None
    crop = screen[top:bottom, left:right]
    try:
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    except cv2.error as e:
        logger.warning('参加人数区域解析失败: %s', e)
        return None
    mask = gray > 145
    crowded = _participant_count_is_crowded(mask, width)
    if crowded is None:
        logger.debug('参加人数区域无法可靠解析: %s', point)
        return None
    logger.debug('参加人数是否达到 9/10 或 10/10: %s，位置 %s', crowded, point)
    return crowded


def click_auto(var_avg, can_click=None):
    """
    接受要点的坐标然后点
    :param var_avg:坐标组
    :return:不
    """
    #这里采取的先移动后点击的策略，如果直接点击，游戏会判定无效
    try:
        if not _wait_for_user(can_click):
            return 1
        with _automation_input(can_click):
            pyautogui.moveTo(var_avg[0], var_avg[1])
            time.sleep(0.1) #等待一会
            if can_click is not None and not can_click():
                logger.debug('任务已停止，取消点击')
                return 1
            pyautogui.click(var_avg[0], var_avg[1], button='left')
            _record_automation_position(can_click, var_avg)
    except Exception as e:
        logger.warning('鼠标点击失败: %s', e)
        return 1

    logger.debug('当前点击事件执行')

    #点击完成等待0.5秒，防止奇怪的问题发生
    time.sleep(0.1)
    return 2
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


def get_client_region(title='MadokaExedra'):
    """返回客户区在屏幕上的 (left, top, width, height)，不含标题栏和边框。"""
    try:
        wins = pwc.getWindowsWithTitle(title)
    except Exception as e:
        logger.warning('查找窗口失败: %s', e)
        return None
    if not wins:
        return None
    try:
        rect = wins[0].getClientFrame()
        left, top = rect.left, rect.top
        width, height = rect.right - left, rect.bottom - top
        if width <= 0 or height <= 0:
            return None
        return left, top, width, height
    except Exception as e:
        logger.warning('读取客户区位置失败: %s', e)
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
        changed = False
        if w.isMinimized:
            w.restore()
            changed = True
            logger.debug("窗口从最小化恢复")
        if not getattr(w, 'isActive', False):
            w.activate()
            changed = True
            logger.debug("窗口已置前")
    except Exception as e:
        logger.warning("读取或聚焦窗口失败: %s", e)
        return None
    if changed:
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

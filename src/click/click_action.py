import time
import logging
import statistics
from pathlib import Path
from contextlib import nullcontext

import pyautogui

from . import click_behavior, template_confidence
from src.packs import language_switcher, image_scaler

logger = logging.getLogger(__name__)

CLICK_CONFIRM_SAMPLES = 3
CLICK_CONFIRM_INTERVAL = 0.3
CLICK_STABILITY_RATIO = 0.008
CLICK_STABILITY_MIN_RADIUS = 6
POST_CLICK_DELAY = 0.2
DRAG_DURATION = 0.5


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
    click_behavior._record_automation_position(callback, position)


def _emit_template_click(self, message):
    emit = getattr(self, '_emit_log', None)
    if emit is not None:
        emit(message, 'INFO')
    else:
        logger.info(message)


def _template_selection(self):
    selection = getattr(self, 'expected_pack', None)
    return selection if selection is not None else language_switcher.current_selection()


def _wait(self, seconds):
    wait = getattr(self, '_wait', None)
    if wait is not None:
        return wait(seconds)
    time.sleep(seconds)
    return False


def _template_match_accepted(detected, selection):
    if not detected or detected[0] is None or detected[2] is None:
        return False
    threshold = template_confidence.threshold_for(detected[2], selection)
    return threshold is not None and detected[1] > threshold


def _competing_match_accepted(detected, selected, selection):
    if not detected or len(detected) < 7:
        return False
    label, text_label, point, score, text_score, path, text_path = detected
    if path is None or text_path is None:
        return False
    full_threshold = template_confidence.threshold_for(path, selection)
    text_threshold = template_confidence.threshold_for(text_path, selection)
    return label == selected and text_label == selected and point is not None \
        and full_threshold is not None and text_threshold is not None \
        and score > full_threshold and text_score > text_threshold


def _template_files(picture):
    files = []
    index = 1
    while True:
        path = Path(f'{picture}_{index}.png')
        if not path.exists():
            return files
        files.append(path)
        index += 1


def _template_files_for_variants(picture, variants=None):
    files = _template_files(picture)
    if variants is None:
        return files
    selected = set(variants)
    return [path for index, path in enumerate(files, 1) if index in selected]


def _click_stability_radius():
    size = click_behavior.get_client_size('MadokaExedra')
    if size is None:
        return 12
    return max(CLICK_STABILITY_MIN_RADIUS, round(min(size) * CLICK_STABILITY_RATIO))


def _confirm_stable_detection(self, detect_once, accepted, position, name):
    """要求目标在 0.6 秒内三次采样都命中同一区域，确认期间不移动鼠标。"""
    can_continue = getattr(self, '_running', None)
    radius = _click_stability_radius()
    samples = []
    reference = None
    for index in range(CLICK_CONFIRM_SAMPLES):
        if can_continue is not None and not can_continue():
            return None
        if not _wait_for_user(can_continue):
            return None
        detected = detect_once()
        point = position(detected)
        if not accepted(detected) or point is None:
            logger.debug('%s稳定性确认失败：第%d/%d次采样未命中',
                         name, index + 1, CLICK_CONFIRM_SAMPLES)
            return None
        if reference is None:
            reference = point
        elif max(abs(point[0] - reference[0]), abs(point[1] - reference[1])) > radius:
            logger.debug('%s稳定性确认失败：第%d/%d次采样位置%s偏离首次%s超过%dpx',
                         name, index + 1, CLICK_CONFIRM_SAMPLES, point, reference, radius)
            return None
        samples.append((detected, point))
        if index + 1 < CLICK_CONFIRM_SAMPLES and _wait(self, CLICK_CONFIRM_INTERVAL):
            return None

    click_point = (
        round(statistics.median(sample[1][0] for sample in samples)),
        round(statistics.median(sample[1][1] for sample in samples)),
    )
    logger.debug('%s在%.1f秒内连续%d次采样稳定命中，位置半径%dpx，确认点击坐标%s',
                 name, CLICK_CONFIRM_INTERVAL * (CLICK_CONFIRM_SAMPLES - 1),
                 CLICK_CONFIRM_SAMPLES, radius, click_point)
    return samples[-1][0], click_point


def _confirm_stable_presence(self, detect_once, accepted, name):
    """连续三次确认页面特征存在；允许检测模板和位置在组内切换。"""
    can_continue = getattr(self, '_running', None)
    samples = []
    for index in range(CLICK_CONFIRM_SAMPLES):
        if can_continue is not None and not can_continue():
            return None
        if not _wait_for_user(can_continue):
            return None
        detected = detect_once()
        if not accepted(detected):
            logger.debug('%s页面确认失败：第%d/%d次采样未命中',
                         name, index + 1, CLICK_CONFIRM_SAMPLES)
            return None
        samples.append(detected)
        if index + 1 < CLICK_CONFIRM_SAMPLES and _wait(self, CLICK_CONFIRM_INTERVAL):
            return None
    logger.debug('%s在%.1f秒内连续%d次采样命中页面特征',
                 name, CLICK_CONFIRM_INTERVAL * (CLICK_CONFIRM_SAMPLES - 1),
                 CLICK_CONFIRM_SAMPLES)
    return samples[-1]


#尝试点击一次，查询组内所有图片，返回点击结果return
def click_item_with_result(self, picture, name, search_region=None):
    files = _template_files(picture)
    can_click = getattr(self, '_running', None)
    selection = _template_selection(self)
    if can_click is not None and not can_click():
        return 1
    if not files or not _wait_for_user(can_click):
        return 1
    confirmed = _confirm_stable_detection(
        self,
        lambda: click_behavior.best_template_match(files, search_region=search_region),
        lambda detected: _template_match_accepted(detected, selection),
        lambda detected: detected[0],
        name,
    )
    if confirmed is None:
        logger.debug('比较了%s个模板，%s未通过独立阈值与0.6秒三次稳定性确认',
                     len(files), name)
        return 1
    detected, click_point = confirmed
    _avg, score, path = detected
    threshold = template_confidence.threshold_for(path, selection)
    logger.debug('点击%s的最高匹配模板%s，匹配率 %.4f，独立阈值 %.4f',
                 name, path, score, threshold)
    result = click_behavior.click_auto(click_point, can_click)
    if result == 2:
        _emit_template_click(
            self,
            f'已点击模板 {name}（{path}），置信度 {score:.4f}，阈值 {threshold:.4f}',
        )
        if _wait(self, POST_CLICK_DELAY):
            return 1
    return result


def click_contextual_item_with_result(self, context_picture, context_name,
                                      picture, name, search_region=None):
    """仅在上下文和目标同帧稳定存在时点击目标，避免通用按钮跨页面误识别。"""
    context_files = _template_files(context_picture)
    target_files = _template_files(picture)
    can_click = getattr(self, '_running', None)
    selection = _template_selection(self)
    if can_click is not None and not can_click():
        return 1
    if not context_files or not target_files or not _wait_for_user(can_click):
        return 1

    def detect_once():
        return click_behavior.best_template_matches(
            (context_files, target_files), search_region=search_region,
        )

    def accepted(detections):
        return len(detections) == 2 \
            and _template_match_accepted(detections[0], selection) \
            and _template_match_accepted(detections[1], selection)

    confirmed = _confirm_stable_detection(
        self,
        detect_once,
        accepted,
        lambda detections: detections[1][0] if len(detections) == 2 else None,
        f'{context_name}+{name}',
    )
    if confirmed is None:
        logger.debug('%s上下文中的%s未通过0.6秒三次同帧稳定性确认',
                     context_name, name)
        return 1
    detections, click_point = confirmed
    context_detected, target_detected = detections
    _context_point, context_score, context_path = context_detected
    _target_point, target_score, target_path = target_detected
    context_threshold = template_confidence.threshold_for(context_path, selection)
    target_threshold = template_confidence.threshold_for(target_path, selection)
    result = click_behavior.click_auto(click_point, can_click)
    if result == 2:
        _emit_template_click(
            self,
            f'已在{context_name}上下文中点击模板 {name}（{target_path}），'
            f'上下文 {context_path} {context_score:.4f}/{context_threshold:.4f}，'
            f'目标 {target_score:.4f}/{target_threshold:.4f}',
        )
        if _wait(self, POST_CLICK_DELAY):
            return 1
    return result


def click_fixed_position_for_item_with_result(self, picture, name, x_2k, y_2k,
                                              search_region=None,
                                              foreground_variants=None):
    """稳定识别页面后点击固定的 2K 基准坐标，不使用检测模板的位置。"""
    files = _template_files_for_variants(picture, foreground_variants)
    can_click = getattr(self, '_running', None)
    selection = _template_selection(self)
    if can_click is not None and not can_click():
        return 1
    if not files or not _wait_for_user(can_click):
        return 1
    detected = _confirm_stable_presence(
        self,
        lambda: click_behavior.best_template_match(
            files, search_region=search_region,
            foreground=foreground_variants is not None,
        ),
        lambda detected: _template_match_accepted(detected, selection),
        name,
    )
    if detected is None:
        logger.debug('比较了%s个文字前景模板，%s未通过0.6秒三次页面确认',
                     len(files), name)
        return 1
    _avg, score, path = detected
    threshold = template_confidence.threshold_for(path, selection)
    result = click_position_scaled(x_2k, y_2k, can_click)
    if result == 2:
        _emit_template_click(
            self,
            f'已通过文字前景轮廓识别页面 {name}（检测模板 {path}），置信度 {score:.4f}，'
            f'阈值 {threshold:.4f}；已点击安全位置 ({x_2k}, {y_2k})',
        )
        if _wait(self, POST_CLICK_DELAY):
            return 1
    return result



#尝试寻找目标一次，查询组内所有图片，返回寻找结果return
def find_item_with_result(self, picture, name):
    files = _template_files(picture)
    can_find = getattr(self, '_running', None)
    selection = _template_selection(self)
    if can_find is not None and not can_find():
        return 1
    if not files or not _wait_for_user(can_find):
        return 1
    _avg, score, path = click_behavior.best_template_match(files)
    threshold = template_confidence.threshold_for(path, selection)
    found = _avg is not None and threshold is not None and score > threshold
    logger.debug('寻找%s的最高匹配模板%s，匹配率 %.4f，独立阈值 %s，结果%s',
                 name, path, score,
                 f'{threshold:.4f}' if threshold is not None else '不可用',
                 2 if found else 1)
    return 2 if found else 1


def find_first_item_with_result(self, items):
    """在同一帧内检查多组下一步模板，返回首个命中的 (picture, name)。"""
    entries = tuple(items)
    if not entries:
        return None
    can_find = getattr(self, '_running', None)
    selection = _template_selection(self)
    if can_find is not None and not can_find():
        return None
    normalized = []
    groups = []
    foreground_groups = []
    for entry in entries:
        picture, name = entry[:2]
        options = entry[2] if len(entry) > 2 else {}
        variants = options.get('foreground_variants')
        normalized.append((picture, name))
        groups.append(_template_files_for_variants(picture, variants))
        foreground_groups.append(variants is not None)
    if any(not files for files in groups) or not _wait_for_user(can_find):
        return None
    detections = click_behavior.best_template_matches(
        groups, foreground_groups=foreground_groups,
    )
    for entry, detected in zip(normalized, detections):
        point, score, path = detected
        threshold = template_confidence.threshold_for(path, selection) if path else None
        if point is not None and threshold is not None and score > threshold:
            logger.debug('同帧下一步识别命中%s：%s %.4f/%.4f',
                         entry[1], path, score, threshold)
            return entry
    return None


def _best_accepted_competing_detection(selected, groups, selection, search_region=None,
                                       skip_crowded=False, name=''):
    matches = click_behavior.best_competing_template_matches(
        selected, groups, search_region=search_region,
    )
    for detected in matches:
        if not _competing_match_accepted(detected, selected, selection):
            continue
        if skip_crowded:
            crowded_status = click_behavior.participant_count_crowded_near(detected[2])
            if crowded_status is not False:
                if crowded_status is True:
                    logger.info('%s候选条目参加人数为 9/10 或 10/10，跳过: %s',
                                name, detected[2])
                else:
                    logger.warning('%s候选条目参加人数无法确认，安全跳过: %s', name, detected[2])
                continue
        return detected
    return None, None, None, 0.0, 0.0, None, None


def click_competing_item_with_result(self, selected, pictures, name, search_region=None,
                                    skip_crowded=False):
    groups = {key: _template_files(picture) for key, picture in pictures.items()}
    can_click = getattr(self, '_running', None)
    selection = _template_selection(self)
    if can_click is not None and not can_click():
        return 1
    if any(not files for files in groups.values()) or not _wait_for_user(can_click):
        return 1
    confirmed = _confirm_stable_detection(
        self,
        lambda: _best_accepted_competing_detection(
            selected, groups, selection, search_region, skip_crowded, name,
        ),
        lambda detected: _competing_match_accepted(detected, selected, selection),
        lambda detected: detected[2],
        name,
    )
    if confirmed is None:
        logger.debug('竞争识别%s未通过0.6秒三次采样稳定性确认', name)
        return 1
    detected, click_point = confirmed
    label, text_label, _avg, score, text_score, path, text_path = detected
    full_threshold = template_confidence.threshold_for(path, selection) if path else None
    text_threshold = template_confidence.threshold_for(text_path, selection) if text_path else None
    logger.debug('竞争识别点击%s：整图%s %.4f/%.4f，文字%s %.4f/%.4f',
                 name, path, score, full_threshold, text_path, text_score, text_threshold)
    result = click_behavior.click_auto(click_point, can_click)
    if result == 2:
        _emit_template_click(
            self,
            f'已点击模板 {name}（整图 {path}），置信度 {score:.4f}，阈值 {full_threshold:.4f}；'
            f'等级文字 {text_path}，置信度 {text_score:.4f}，阈值 {text_threshold:.4f}',
        )
        if _wait(self, POST_CLICK_DELAY):
            return 1
    return result


def find_competing_item_with_result(self, selected, pictures, name, search_region=None,
                                   skip_crowded=False):
    groups = {key: _template_files(picture) for key, picture in pictures.items()}
    can_find = getattr(self, '_running', None)
    selection = _template_selection(self)
    if can_find is not None and not can_find():
        return 1
    if any(not files for files in groups.values()) or not _wait_for_user(can_find):
        return 1
    label, text_label, _avg, score, text_score, path, text_path = \
        _best_accepted_competing_detection(
            selected, groups, selection, search_region, skip_crowded, name,
        )
    detected = (label, text_label, _avg, score, text_score, path, text_path)
    found = _competing_match_accepted(detected, selected, selection)
    full_threshold = template_confidence.threshold_for(path, selection) if path else None
    text_threshold = template_confidence.threshold_for(text_path, selection) if text_path else None
    logger.debug('竞争寻找%s：整图=%s/%s %.4f/%s，文字=%s/%s %.4f/%s，结果%s',
                 name, label, path, score,
                 f'{full_threshold:.4f}' if full_threshold is not None else '不可用',
                 text_label, text_path, text_score,
                 f'{text_threshold:.4f}' if text_threshold is not None else '不可用',
                 2 if found else 1)
    return 2 if found else 1

#用于点击客户区内的特定位置，输入坐标依次为从客户区左侧、顶部开始的偏移。
def click_position(move_lelt, move_top, can_click=None):
    if not _wait_for_user(can_click):
        return 1
    # 把游戏窗口弄出来
    if click_behavior.find_win('MadokaExedra') is None:
        return 1
    client = click_behavior.get_client_region('MadokaExedra')
    if client is None:
        return 1
    left, top, width, height = client
    if not (0 <= move_lelt < width and 0 <= move_top < height):
        logger.warning('点击坐标超出游戏客户区: (%s, %s)，客户区大小 %sx%s', move_lelt, move_top, width, height)
        return 1
    if not click_behavior.wait_for_automation_input_deadline(can_click):
        return 1
    if not _wait_for_user(can_click):
        return 1
    try:
        time.sleep(0.1)
        if can_click is not None and not can_click():
            return 1
        with _automation_input(can_click):
            pyautogui.moveTo(left + move_lelt, top + move_top)
            time.sleep(0.1)
            if can_click is not None and not can_click():
                return 1
            pyautogui.click(left + move_lelt, top + move_top, button='left')
            click_behavior._record_automation_click(can_click)
            _record_automation_position(can_click, (left + move_lelt, top + move_top))
        time.sleep(0.1)
    except Exception as e:
        logger.warning('坐标点击失败: %s', e)
        return 1
    return 2


def move_position(move_lelt, move_top, can_move=None):
    """只移动鼠标到客户区坐标，用于移开会触发悬停状态的指针。"""
    if not _wait_for_user(can_move):
        return 1
    if click_behavior.find_win('MadokaExedra') is None:
        return 1
    client = click_behavior.get_client_region('MadokaExedra')
    if client is None:
        return 1
    left, top, width, height = client
    if not (0 <= move_lelt < width and 0 <= move_top < height):
        logger.warning('移动坐标超出游戏客户区: (%s, %s)，客户区大小 %sx%s',
                       move_lelt, move_top, width, height)
        return 1
    if not click_behavior.wait_for_automation_input_deadline(can_move):
        return 1
    if not _wait_for_user(can_move):
        return 1
    try:
        with _automation_input(can_move):
            pyautogui.moveTo(left + move_lelt, top + move_top)
            _record_automation_position(
                can_move, (left + move_lelt, top + move_top),
            )
        time.sleep(0.1)
    except Exception as e:
        logger.warning('鼠标移动失败: %s', e)
        return 1
    return 2

def move_a_to_b(move_lelt_a, move_top_a, move_lelt_b, move_top_b, can_move=None):
    if not _wait_for_user(can_move):
        return 1
    if click_behavior.find_win('MadokaExedra') is None:
        return 1
    client = click_behavior.get_client_region('MadokaExedra')
    if client is None:
        return 1
    left, top, width, height = client
    points = ((move_lelt_a, move_top_a), (move_lelt_b, move_top_b))
    if any(not (0 <= x < width and 0 <= y < height) for x, y in points):
        logger.warning('拖拽坐标超出游戏客户区: %s，客户区大小 %sx%s', points, width, height)
        return 1
    if not click_behavior.wait_for_automation_input_deadline(can_move):
        return 1
    if not _wait_for_user(can_move):
        return 1
    try:
        time.sleep(0.1)
        if can_move is not None and not can_move():
            return 1
        with _automation_input(can_move):
            pyautogui.moveTo(left + move_lelt_a, top + move_top_a)
            time.sleep(0.1)
            if can_move is not None and not can_move():
                return 1
            pyautogui.dragTo(
                left + move_lelt_b, top + move_top_b,
                duration=DRAG_DURATION, button='left',
            )
            _record_automation_position(can_move, (left + move_lelt_b, top + move_top_b))
        time.sleep(0.1)
    except Exception as e:
        logger.warning('坐标拖拽失败: %s', e)
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
        logger.warning('无法确认模板 pack 的坐标缩放倍率，拒绝位置点击')
        return 1
    return click_position(round(x_2k * f), round(y_2k * f), can_click)


def move_position_scaled(x_2k, y_2k, can_move=None):
    # 把 2K 基准坐标按当前分辨率缩放后移动鼠标，不点击。
    f = _res_scale_factor()
    if f is None:
        logger.warning('无法确认模板 pack 的坐标缩放倍率，拒绝移动鼠标')
        return 1
    return move_position(round(x_2k * f), round(y_2k * f), can_move)


def move_a_to_b_scaled(ax_2k, ay_2k, bx_2k, by_2k, can_move=None):
    #把 2K 基准起止坐标按当前分辨率缩放后拖拽
    f = _res_scale_factor()
    if f is None:
        logger.warning('无法确认模板 pack 的坐标缩放倍率，拒绝拖拽')
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

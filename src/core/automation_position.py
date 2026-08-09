"""记录并恢复相对于游戏客户区的安全自动化位置。"""


def capture_client_position(screen_position, client_region):
    """把屏幕绝对坐标转换为带客户区尺寸的相对位置。"""
    if screen_position is None or client_region is None:
        return None
    try:
        x, y = screen_position
        left, top, width, height = client_region
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0 or not (left <= x < left + width and top <= y < top + height):
        return None
    return x - left, y - top, width, height


def resolve_client_position(record, client_region):
    """按当前客户区原点恢复屏幕坐标；尺寸变化时拒绝使用旧位置。"""
    if record is None or client_region is None:
        return None
    try:
        rel_x, rel_y, recorded_width, recorded_height = record
        left, top, width, height = client_region
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0 or (width, height) != (recorded_width, recorded_height):
        return None
    if not (0 <= rel_x < width and 0 <= rel_y < height):
        return None
    return left + rel_x, top + rel_y

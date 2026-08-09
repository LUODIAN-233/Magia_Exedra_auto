import ctypes
import ctypes.wintypes
import threading
import time
from contextlib import contextmanager


class UserActivityGuard:
    """监测真实键盘活动和累计鼠标移动，给自动化操作让出输入焦点。"""

    _MOUSE_BUTTON_NAMES = {
        1: '鼠标左键',
        2: '鼠标右键',
        4: '鼠标中键',
        5: '鼠标侧键 X1',
        6: '鼠标侧键 X2',
    }
    _SPECIAL_KEY_NAMES = {
        0x08: 'Backspace', 0x09: 'Tab', 0x0D: 'Enter', 0x10: 'Shift',
        0x11: 'Ctrl', 0x12: 'Alt', 0x13: 'Pause', 0x14: 'Caps Lock',
        0x1B: 'Esc', 0x20: 'Space', 0x21: 'Page Up', 0x22: 'Page Down',
        0x23: 'End', 0x24: 'Home', 0x25: '←', 0x26: '↑', 0x27: '→',
        0x28: '↓', 0x2C: 'Print Screen', 0x2D: 'Insert', 0x2E: 'Delete',
        0x5B: '左 Windows', 0x5C: '右 Windows', 0x5D: '菜单键',
        0x90: 'Num Lock', 0x91: 'Scroll Lock',
    }

    def __init__(self, idle_seconds=5, mouse_threshold=80, state_callback=None):
        self.idle_seconds = idle_seconds
        self.mouse_threshold = mouse_threshold
        self.state_callback = state_callback
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._automation_depth = 0
        self._last_activity = 0.0
        self._mouse_travel = 0
        self._paused = False
        self._thread = None
        self._last_position = self._cursor_position()

    @staticmethod
    def _cursor_position():
        point = ctypes.wintypes.POINT()
        if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            return None
        return point.x, point.y

    @classmethod
    def _key_name(cls, key):
        if key in cls._SPECIAL_KEY_NAMES:
            return cls._SPECIAL_KEY_NAMES[key]
        if 0x30 <= key <= 0x39 or 0x41 <= key <= 0x5A:
            return chr(key)
        if 0x60 <= key <= 0x69:
            return f'数字键盘 {key - 0x60}'
        if 0x70 <= key <= 0x87:
            return f'F{key - 0x6F}'
        # Windows 10 的手柄虚拟键范围；保留键码便于定位驱动或摇杆漂移。
        if 0xC3 <= key <= 0xDA:
            return f'手柄虚拟键 0x{key:02X}'
        return f'虚拟键 0x{key:02X}'

    @classmethod
    def _keyboard_active(cls):
        # 1-6 是鼠标键，由 _mouse_active() 单独读取。
        get_key_state = ctypes.windll.user32.GetAsyncKeyState
        for key in range(7, 256):
            # 只使用“当前按下”的最高位；最低位“自上次查询后曾按过”在 Windows 上不可靠。
            if get_key_state(key) & 0x8000:
                return f'键盘按键 {cls._key_name(key)}（VK 0x{key:02X}）'
        return None

    @classmethod
    def _mouse_active(cls):
        get_key_state = ctypes.windll.user32.GetAsyncKeyState
        for key in range(1, 7):
            if get_key_state(key) & 0x8000:
                return cls._MOUSE_BUTTON_NAMES.get(key, f'鼠标按键 VK 0x{key:02X}')
        return None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        position = self._cursor_position()
        with self._lock:
            self._automation_depth = 0
            self._last_activity = 0.0
            self._mouse_travel = 0
            self._paused = False
            self._last_position = position
        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=0.5)
        self._thread = None

    def _set_paused(self, paused, reason=None):
        callback = None
        with self._lock:
            if self._paused != paused:
                self._paused = paused
                callback = self.state_callback
        if callback:
            callback(paused, reason)

    def _record_activity(self, reason):
        with self._lock:
            self._last_activity = time.monotonic()
            self._mouse_travel = 0
        self._set_paused(True, reason)

    def _observe_mouse_movement(self, position):
        """累计非自动化鼠标轨迹；触发暂停时返回可读原因。"""
        if position is None:
            return False
        with self._lock:
            if self._automation_depth > 0:
                return False
            previous = self._last_position
            self._last_position = position
            if previous is None:
                return False
            dx = position[0] - previous[0]
            dy = position[1] - previous[1]
            step = max(abs(dx), abs(dy))
            if self._paused:
                if step < 3:
                    return None
                return f'鼠标移动 Δx={dx}px、Δy={dy}px，当前位置 {position}'
            self._mouse_travel += step
            if self._mouse_travel < self.mouse_threshold:
                return None
            return (f'鼠标累计移动 {self._mouse_travel}px'
                    f'（本次 Δx={dx}px、Δy={dy}px，当前位置 {position}）')

    def _monitor(self):
        while not self._stop.wait(0.05):
            now = time.monotonic()
            position = self._cursor_position()
            keyboard_reason = self._keyboard_active()
            mouse_reason = self._mouse_active()
            with self._lock:
                automated = self._automation_depth > 0

            if keyboard_reason:
                self._record_activity(keyboard_reason)
            elif mouse_reason and not automated:
                self._record_activity(mouse_reason)
            else:
                movement_reason = self._observe_mouse_movement(position)
                if movement_reason:
                    self._record_activity(movement_reason)

            with self._lock:
                paused = self._paused
                last_activity = self._last_activity
            if paused and now - last_activity >= self.idle_seconds:
                with self._lock:
                    self._last_position = position
                    self._mouse_travel = 0
                self._set_paused(False)

    def wait_until_idle(self, is_cancelled):
        while not is_cancelled():
            with self._lock:
                paused = self._paused
            if not paused:
                return True
            self._stop.wait(0.05)
        return False

    @contextmanager
    def automation_input(self):
        with self._lock:
            self._automation_depth += 1
        try:
            yield
        finally:
            position = self._cursor_position()
            with self._lock:
                self._automation_depth = max(0, self._automation_depth - 1)
                self._last_position = position
                self._mouse_travel = 0

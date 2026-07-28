import ctypes
import ctypes.wintypes
import threading
import time
from contextlib import contextmanager


class UserActivityGuard:
    """监测真实键盘活动和累计鼠标移动，给自动化操作让出输入焦点。"""

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

    @staticmethod
    def _keyboard_active():
        # 1-6 是鼠标键，由 _mouse_active() 单独读取。
        get_key_state = ctypes.windll.user32.GetAsyncKeyState
        return any(get_key_state(key) & 0x8001 for key in range(7, 256))

    @staticmethod
    def _mouse_active():
        get_key_state = ctypes.windll.user32.GetAsyncKeyState
        return any(get_key_state(key) & 0x8001 for key in range(1, 7))

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

    def _set_paused(self, paused):
        callback = None
        with self._lock:
            if self._paused != paused:
                self._paused = paused
                callback = self.state_callback
        if callback:
            callback(paused)

    def _record_activity(self):
        with self._lock:
            self._last_activity = time.monotonic()
            self._mouse_travel = 0
        self._set_paused(True)

    def _observe_mouse_movement(self, position):
        """累计非自动化鼠标轨迹；返回本次观察是否应触发暂停。"""
        if position is None:
            return False
        with self._lock:
            if self._automation_depth > 0:
                return False
            previous = self._last_position
            self._last_position = position
            if previous is None:
                return False
            step = max(abs(position[0] - previous[0]), abs(position[1] - previous[1]))
            if self._paused:
                return step >= 3
            self._mouse_travel += step
            return self._mouse_travel >= self.mouse_threshold

    def _monitor(self):
        while not self._stop.wait(0.05):
            now = time.monotonic()
            position = self._cursor_position()
            keyboard_active = self._keyboard_active()
            mouse_active = self._mouse_active()
            with self._lock:
                automated = self._automation_depth > 0

            if keyboard_active or (mouse_active and not automated):
                self._record_activity()
            elif self._observe_mouse_movement(position):
                self._record_activity()

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

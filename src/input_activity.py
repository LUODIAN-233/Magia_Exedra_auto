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
        self._paused = False
        self._thread = None
        self._anchor = self._cursor_position()
        self._last_position = self._anchor

    @staticmethod
    def _cursor_position():
        point = ctypes.wintypes.POINT()
        if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            return None
        return point.x, point.y

    @staticmethod
    def _keyboard_active():
        # 1-6 是鼠标键；只监测键盘，脚本自己的鼠标点击不会触发暂停。
        get_key_state = ctypes.windll.user32.GetAsyncKeyState
        return any(get_key_state(key) & 0x8001 for key in range(7, 256))

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        position = self._cursor_position()
        with self._lock:
            self._automation_depth = 0
            self._last_activity = 0.0
            self._paused = False
            self._anchor = position
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
        self._set_paused(True)

    def _monitor(self):
        while not self._stop.wait(0.05):
            now = time.monotonic()
            position = self._cursor_position()
            keyboard_active = self._keyboard_active()
            with self._lock:
                automated = self._automation_depth > 0
                paused = self._paused

            if keyboard_active:
                self._record_activity()
            elif not automated and position is not None:
                if paused:
                    previous = self._last_position
                    if previous is not None and max(
                            abs(position[0] - previous[0]), abs(position[1] - previous[1])) >= 3:
                        self._record_activity()
                elif self._anchor is not None and max(
                        abs(position[0] - self._anchor[0]), abs(position[1] - self._anchor[1])) >= self.mouse_threshold:
                    self._record_activity()

            if position is not None:
                self._last_position = position

            with self._lock:
                paused = self._paused
                last_activity = self._last_activity
            if paused and now - last_activity >= self.idle_seconds:
                self._anchor = position
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
                self._anchor = position
                self._last_position = position

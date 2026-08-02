class ConsecutiveLogFolder:
    """把连续且完全相同的 GUI 日志行合并为一行。"""

    def __init__(self):
        self._key = None
        self._count = 0

    def render(self, timestamp, level, source, text):
        key = (str(level), str(source), str(text))
        replace = key == self._key
        if replace:
            self._count += 1
        else:
            self._key = key
            self._count = 1
        rendered = f'[{timestamp}] [{level}] [{source}] {text}'
        if self._count > 1:
            rendered += f' （连续重复 {self._count} 次）'
        return replace, rendered

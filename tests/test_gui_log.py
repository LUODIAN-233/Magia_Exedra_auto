import os
import types
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QPlainTextEdit

from main import mywindow


class GuiLogReplacementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_replacing_repeated_line_preserves_previous_blocks(self):
        editor = QPlainTextEdit()
        editor.appendPlainText('保留日志 1')
        editor.appendPlainText('保留日志 2')
        editor.appendPlainText('重复日志 1')
        holder = types.SimpleNamespace(textedit_1=editor)

        for count in range(2, 101):
            mywindow._replace_last_gui_line(holder, f'重复日志 {count}')

        self.assertEqual(editor.blockCount(), 3)
        self.assertEqual(
            editor.toPlainText().splitlines(),
            ['保留日志 1', '保留日志 2', '重复日志 100'],
        )


if __name__ == '__main__':
    unittest.main()

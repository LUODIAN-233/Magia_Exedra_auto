import tempfile
import threading
import unittest

from src.packs.file_lock import TemplateOperationCancelled, template_write_lock


class TemplateWriteLockTests(unittest.TestCase):
    def test_second_thread_times_out_while_lock_is_held(self):
        acquired = threading.Event()
        release = threading.Event()
        errors = []

        with tempfile.TemporaryDirectory() as temp_dir:
            def hold_lock():
                try:
                    with template_write_lock(temp_dir, timeout=1):
                        acquired.set()
                        release.wait(2)
                except Exception as error:  # pragma: no cover - reported by assertion below
                    errors.append(error)
                    acquired.set()

            thread = threading.Thread(target=hold_lock)
            thread.start()
            self.assertTrue(acquired.wait(1))
            try:
                self.assertFalse(errors)
                with self.assertRaises(TimeoutError):
                    with template_write_lock(temp_dir, timeout=0.15):
                        self.fail('不应在另一个线程持锁时进入临界区')
            finally:
                release.set()
                thread.join(2)

            self.assertFalse(thread.is_alive())
            self.assertFalse(errors)

    def test_cancelled_wait_does_not_enter_critical_section(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(TemplateOperationCancelled):
                with template_write_lock(
                        temp_dir, timeout=1, is_cancelled=lambda: True):
                    self.fail('取消后不应进入临界区')


if __name__ == '__main__':
    unittest.main()

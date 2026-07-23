import ctypes
import hashlib
import os
import time
from contextlib import contextmanager


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
_kernel32.CreateMutexW.restype = ctypes.c_void_p
_kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
_kernel32.WaitForSingleObject.restype = ctypes.c_uint32
_kernel32.ReleaseMutex.argtypes = (ctypes.c_void_p,)
_kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)

WAIT_OBJECT_0 = 0
WAIT_ABANDONED = 0x80
WAIT_TIMEOUT = 0x102


class TemplateOperationCancelled(Exception):
    pass


def template_mutex_name(base_dir):
    identity = os.path.normcase(os.path.realpath(base_dir)).encode("utf-8")
    return "Global\\MagiaExedraTemplates_" + hashlib.sha256(identity).hexdigest()


@contextmanager
def template_write_lock(base_dir, timeout=None, is_cancelled=None):
    #切换、缩放和 worker 运行期租约共用互斥量，避免 aim 在识图期间被其它进程改写。
    #Global 命名空间同时覆盖本机不同登录/RDP session，避免共享安装目录被并发改写。
    name = template_mutex_name(base_dir)
    handle = _kernel32.CreateMutexW(None, False, name)
    if not handle:
        raise OSError(ctypes.get_last_error(), "创建模板管理互斥量失败")
    acquired = False
    deadline = None if timeout is None else time.monotonic() + timeout
    try:
        while not acquired:
            if is_cancelled and is_cancelled():
                raise TemplateOperationCancelled("模板管理操作已取消")
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("另一个程序正在管理模板，请稍后重试")
            result = _kernel32.WaitForSingleObject(handle, 100)
            if result in (WAIT_OBJECT_0, WAIT_ABANDONED):
                acquired = True
            elif result != WAIT_TIMEOUT:
                raise OSError(ctypes.get_last_error(), "等待模板管理互斥量失败")
        yield
    finally:
        if acquired:
            _kernel32.ReleaseMutex(handle)
        _kernel32.CloseHandle(handle)

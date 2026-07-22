#模板包管理
#把管理 aim 联接与分辨率缩放的两个纯标准库模块归到一起，方便单独测试：
#  language_switcher.py  管理 aim 联接：list_packs / current_selection / switch / ensure_active / pack_usable
#  image_scaler.py       用 tools/ImageMagick 把 2K 源 pack 缩放到其它分辨率
#两个文件都只依赖标准库，不依赖 PySide6，可单独运行排查。

from . import language_switcher, image_scaler

__all__ = ["language_switcher", "image_scaler"]

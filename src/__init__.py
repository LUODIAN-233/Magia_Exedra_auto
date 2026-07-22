#项目源码包
#把 click / workers / packs 三个子包统一放在 src 下，顶层只剩 main.py（GUI 入口）和资源目录。
#子包之间的相对导入不变（from . import / from .base import），跨包引用改用 from src.xxx import。

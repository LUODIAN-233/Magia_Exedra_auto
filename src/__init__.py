#项目源码包
#按职责拆分 click / workers / packs / core / update，src 根只保留包入口。
#子包之间的相对导入不变（from . import / from .base import），跨包引用改用 from src.xxx import。

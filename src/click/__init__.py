#点击模块包
#把窗口截图、模板匹配、点击的底层逻辑和高层动作拆成两个文件：
#  click_behavior.py  底层：截图、OpenCV 匹配、窗口查找、原始点击
#  click_action.py    高层：模板组遍历点击、窗口相对坐标点击/拖拽、2K 基准缩放
#workers/ 的工作线程通过 click_action 调用；main.py 不直接用本包，只直接用 packs/。

from . import click_behavior, click_action

__all__ = ["click_behavior", "click_action"]

#点击模块包
#把窗口截图、模板匹配、点击动作和逐图片阈值拆成独立文件：
#  click_behavior.py  底层：截图、OpenCV 匹配、窗口查找、原始点击
#  click_action.py    高层：模板组遍历点击、窗口相对坐标点击/拖拽、2K 基准缩放
#  template_confidence.py  resource TXT 解析、热重载和模板阈值完整性校验
#workers/ 通过 click_action 调用；main.py 在启动任务时做窗口、模板和阈值校验。

from . import click_behavior, click_action, template_confidence

__all__ = ["click_behavior", "click_action", "template_confidence"]

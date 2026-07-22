import os
import sys
import threading
import winreg

# 必须在间接导入 cv2 前设置，打包环境下才会生效。
if getattr(sys, "frozen", False):
    os.environ["OPENCV_SKIP_PYTHON_LOADER"] = "1"

from datetime import datetime

from PySide6.QtWidgets import QApplication, QButtonGroup, QHBoxLayout, QRadioButton, QPlainTextEdit, QWidget, QPushButton, QLabel, QLineEdit, QComboBox, QVBoxLayout
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QIntValidator

#其他自己写的文件
import language_switcher
import image_scaler
from workers import LinkRaidWorker, CrystalisWorker


# pyinstaller.exe -D -i resource/main.ico  main.py
#这个是导出用的

# ---- GUI 参数状态（仅作为启动入口的输入，挂机运行逻辑已移到 workers/ 包）----
#link raid 挂机选择的等级，默认 6，和选择框相同
link_raid_lv_choice = 6

#link raid 喝体力药的次数 1 是不喝药，4 是喝三次，要多一次
link_raid_lp_recover_times = 1

#晶花喝体力药的次数 1 是不喝药，4 是喝三次，要多一次
crystalis_lp_recover_times = 9


class LanguageSwitcherWidget(QWidget):
    #语言/分辨率切换控件，切换的是根目录 aim 这个 junction 的指向
    #选好语言和分辨率后会自动切换，不需要点按钮；只剩"刷新列表"用于重新扫描 pack
    switched = Signal(str)  #切换完成或失败时发出，用于在日志框显示
    scaleFinished = Signal()
    scalingChanged = Signal(bool)
    #语言代码 -> 显示用的中文名；新增语言时在这里加一项
    LANG_LABELS = {'EN': '英语', 'JP': '日语'}
    def __init__(self, busy_check=None):
        super().__init__()
        self.busy_check = busy_check or (lambda: False)
        self.titleLabel = QLabel('语言 / 分辨率切换')
        self.langCombo = QComboBox()
        self.resCombo = QComboBox()
        self.statusLabel = QLabel('正在检测模板...')
        self.refreshBtn = QPushButton('刷新列表')
        self.refreshBtn.clicked.connect(self._refresh_clicked)
        #activated 只在用户从下拉里选定一项时触发，程序里 setCurrentIndex 不会触发，所以刷新/重填时不会误切换
        self.langCombo.activated.connect(self._on_lang_activated)
        self.resCombo.activated.connect(self._on_res_activated)
        self.scaleFinished.connect(self._scale_finished)

        row = QHBoxLayout()
        row.addWidget(self.langCombo)
        row.addWidget(self.resCombo)
        layout = QVBoxLayout()
        layout.addWidget(self.titleLabel)
        layout.addLayout(row)
        layout.addWidget(self.statusLabel)
        layout.addWidget(self.refreshBtn)
        self.setLayout(layout)

        self.packs = {}
        self._refresh()

    def _lang_label(self, code):
        return self.LANG_LABELS.get(code, code)

    def _refresh(self):
        #启动时保证 aim 可用，再扫描 pack 填充下拉框
        lang, res, msg = language_switcher.ensure_active()
        self.packs = language_switcher.list_packs()

        self.langCombo.blockSignals(True)
        self.langCombo.clear()
        for lg in sorted(self.packs.keys()):
            self.langCombo.addItem(self._lang_label(lg), lg)
        if lang:
            idx = self.langCombo.findData(lang)
            if idx >= 0:
                self.langCombo.setCurrentIndex(idx)
        self.langCombo.blockSignals(False)

        self._populate_res(res)
        self._update_status(lang, res, msg)

    def _refresh_clicked(self):
        if self.busy_check():
            self.switched.emit('挂机运行中，不能刷新或切换模板。')
            return
        #点"刷新列表"：先重新扫描 pack，再后台从 2K 源生成其它分辨率模板
        self._refresh()
        self._scale_async()

    def _scale_async(self):
        #后台跑素材缩放，不阻塞界面；已有目标会跳过，重复点也不会并发
        if getattr(self, '_scaling', False):
            return
        self._scaling = True
        self.refreshBtn.setEnabled(False)
        self.langCombo.setEnabled(False)
        self.resCombo.setEnabled(False)
        self.scalingChanged.emit(True)
        def _work():
            try:
                summary = image_scaler.scale_all(progress_cb=lambda s: self.switched.emit(s))
                if summary:
                    self.switched.emit(summary)
            except Exception as e:
                self.switched.emit(f'素材缩放出错: {e}')
            finally:
                self._scaling = False
                self.scaleFinished.emit()
        threading.Thread(target=_work, daemon=True).start()

    def _scale_finished(self):
        self.refreshBtn.setEnabled(True)
        self.langCombo.setEnabled(True)
        self.resCombo.setEnabled(True)
        self._refresh()
        self.scalingChanged.emit(False)

    def _populate_res(self, current_res):
        self.resCombo.blockSignals(True)
        self.resCombo.clear()
        lang = self.langCombo.currentData()
        if lang in self.packs:
            for res, usable in self.packs[lang]:
                label = res if usable else f'{res}（空）'
                self.resCombo.addItem(label, res)
            #优先选 current_res，没有就选第一个可用的
            pick = self.resCombo.findData(current_res) if current_res else -1
            if pick < 0:
                for i, (_r, usable) in enumerate(self.packs[lang]):
                    if usable:
                        pick = i
                        break
            if pick >= 0:
                self.resCombo.setCurrentIndex(pick)
        self.resCombo.blockSignals(False)

    def _update_status(self, lang, _res, msg):
        cur = language_switcher.current_selection()
        if cur:
            base = f'当前激活: {self._lang_label(cur[0])} {cur[1]}'
        else:
            base = '当前无激活模板'
        self.statusLabel.setText(f'{base}  |  {self._localize(msg, lang)}')

    def _localize(self, msg, lang):
        #把消息里出现的语言代码换成中文名，仅用于显示
        if not msg or not lang:
            return msg
        label = self._lang_label(lang)
        return msg.replace(lang + ' ', label + ' ').replace(lang + '/', label + '/')

    def _on_lang_activated(self, _idx):
        #用户选了语言：重填该语言的分辨率（选第一个可用的），然后自动切换过去
        self._populate_res(None)
        self._auto_switch()

    def _on_res_activated(self, _idx):
        #用户选了分辨率：自动切换过去
        self._auto_switch()

    def _auto_switch(self):
        if self.busy_check():
            text = '挂机运行中，不能切换语言或分辨率。'
            self._refresh()
            self.switched.emit(text)
            return
        lang = self.langCombo.currentData()
        res = self.resCombo.currentData()
        if not lang or not res:
            return
        #实时查这个 pack 是否可用（缓存的 self.packs 可能是旧的）
        if not language_switcher.pack_usable(lang, res):
            text = f'{self._lang_label(lang)} {res} 这个 pack 是空的，没法切换。请先往对应文件夹放入模板图片。'
            self.statusLabel.setText(text)
            self.switched.emit(text)
            return
        ok, msg = language_switcher.switch(lang, res)
        out = self._localize(msg, lang)
        if ok:
            self._refresh()  #刷新让（空）标记和"当前激活"同步
        else:
            self._update_status(lang, res, out)
        self.switched.emit(out)

class mywindow(QWidget):
    def __init__(self):
        super().__init__()

        #启动时确保 aim 联接可用（aim 被移走时按 config 或第一个可用 pack 自动恢复）
        language_switcher.ensure_active()

        #左上角页面名字
        self.setWindowTitle('圆哆啦挂机器')
        #图标
        self.setWindowIcon(QIcon('./resource/main.ico'))
        #窗体尺寸
        self.resize(250,740)

        #框体顶部的提示
        self.textedit_1_title = QLabel('输出运行结果的框框')
        # 用于输出运行日志的框体
        self.textedit_1=QPlainTextEdit()

    #各种进程
        #刷raid进程（运行逻辑在 workers/link_raid.py，GUI 只负责启动/停止和传参）
        self.workthread_1 = LinkRaidWorker()
        self.workthread_1.signal.connect(lambda x :self.textedit_1.appendPlainText(f"[{datetime.now().strftime('%H:%M:%S')}]: {x}"))
        # self.workthread_1.finished.connect(lambda :self.workthread_1.deleteLater()) #这一条不知道为啥加入了就无法二次启动了
        self.workthread_1.finished.connect(lambda: print('link raid挂机结束'))
        self.workthread_1.finished.connect(lambda: self.textedit_1.appendPlainText(f"[{datetime.now().strftime('%H:%M:%S')}]: link raid挂机结束或被主动停止\n"))
        self.workthread_1.finished.connect(self._automation_finished)


        self.workthread_2 = CrystalisWorker()
        self.workthread_2.signal.connect(lambda x :self.textedit_1.appendPlainText(f"[{datetime.now().strftime('%H:%M:%S')}]: {x}"))
        # self.workthread_1.finished.connect(lambda :self.workthread_1.deleteLater()) #这一条不知道为啥加入了就无法二次启动了
        self.workthread_2.finished.connect(lambda: print('crystalis挂机结束'))
        self.workthread_2.finished.connect(lambda: self.textedit_1.appendPlainText(f"[{datetime.now().strftime('%H:%M:%S')}]: crystalis挂机结束或被主动停止\n"))
        self.workthread_2.finished.connect(self._automation_finished)

    #各种按钮
        #停止按钮，按下启动停止进程，会调用工作线程的 stop()
        self.button_1=QPushButton('停下当前运行的脚本')
        self.button_1.clicked.connect(self._stop_automation)

        #语言/分辨率切换控件，切换 aim 联接指向
        self.lang_switcher = LanguageSwitcherWidget(self._automation_running)
        self.lang_switcher.switched.connect(lambda x :self.textedit_1.appendPlainText(f"[{datetime.now().strftime('%H:%M:%S')}]: {x}"))
        self.lang_switcher.switched.connect(lambda : self.setWindowIcon(QIcon('./resource/main.ico')))
        self.lang_switcher.scalingChanged.connect(self._scaling_changed)

        #启动link raid挂机进程
        self.button_2=QPushButton('link raid挂机启动')
        self.button_2.clicked.connect(self._start_link_raid)

        #启动link raid挂机进程
        self.button_3=QPushButton('自动刷晶花，需要在play界面启动')
        self.button_3.clicked.connect(self._start_crystalis)

    #link raid等级选择器

        self.group_choice_lv_label=QLabel('link raid挂机部分\n选择link raid要挂机的等级')
        #按钮和加入组别
        self.group_choice_lv = QButtonGroup(self)#等级选择的组
        self.group_choice_lv.setExclusive(True)

        self.lv_6_btn= QRadioButton('lv6')
        self.group_choice_lv.addButton(self.lv_6_btn)
        self.lv_6_btn.clicked.connect(lambda : self.change_value(6))

        self.lv_7_btn = QRadioButton('lv7')
        self.group_choice_lv.addButton(self.lv_7_btn)
        self.lv_7_btn.clicked.connect(lambda: self.change_value(7))

        self.lv_8_btn = QRadioButton('lv8')
        self.group_choice_lv.addButton(self.lv_8_btn)
        self.lv_8_btn.clicked.connect(lambda: self.change_value(8))

        self.lv_9_btn = QRadioButton('lv9')
        self.group_choice_lv.addButton(self.lv_9_btn)
        self.lv_9_btn.clicked.connect(lambda: self.change_value(9))

        self.lv_10_btn = QRadioButton('lv10')
        self.group_choice_lv.addButton(self.lv_10_btn)
        self.lv_10_btn.clicked.connect(lambda: self.change_value(10))

        self.lv_11_btn = QRadioButton('lv11')
        self.group_choice_lv.addButton(self.lv_11_btn)
        self.lv_11_btn.clicked.connect(lambda: self.change_value(11))

        self.lv_12_btn = QRadioButton('lv12')
        self.group_choice_lv.addButton(self.lv_12_btn)
        self.lv_12_btn.clicked.connect(lambda: self.change_value(12))

        self.lv_6_btn.setChecked(True)#默认选6

        #按钮的排列
        self.lv_choice_layout_1=QHBoxLayout()#横向排列
        self.lv_choice_layout_1.addWidget(self.group_choice_lv_label)#这是标识符，后面开始是按钮

        self.lv_choice_layout_2 = QHBoxLayout()  # 横向排列2
        self.lv_choice_layout_2.addWidget(self.lv_6_btn)
        self.lv_choice_layout_2.addWidget(self.lv_7_btn)
        self.lv_choice_layout_2.addWidget(self.lv_8_btn)

        self.lv_choice_layout_3 = QHBoxLayout()  # 横向排列2
        self.lv_choice_layout_3.addWidget(self.lv_9_btn)
        self.lv_choice_layout_3.addWidget(self.lv_10_btn)
        self.lv_choice_layout_3.addWidget(self.lv_11_btn)

        self.lv_choice_layout_4 = QHBoxLayout()  # 横向排列3
        self.lv_choice_layout_4.addWidget(self.lv_12_btn)

        self.lv_choice_layout_row = QVBoxLayout()  # 横向排列2
        self.lv_choice_layout_row.addLayout(self.lv_choice_layout_1)
        self.lv_choice_layout_row.addLayout(self.lv_choice_layout_2)
        self.lv_choice_layout_row.addLayout(self.lv_choice_layout_3)
        self.lv_choice_layout_row.addLayout(self.lv_choice_layout_4)

    #link raid 喝药次数选择器
        self.group_link_raid_lp_recover_label=QLabel('link raid挂机要喝体力药几次')
        self.link_raid_lp_recover_layout_raw = QVBoxLayout()
        self.link_raid_lp_recover_layout_2=QHBoxLayout()

        self.lp_recover_min_btn, self.lp_recover_minus_btn, self.lp_recover_input, self.lp_recover_plus_btn, self.lp_recover_max_btn = self.create_lp_recover_input(
            min_num=0,
            max_num=10,
            default_num=link_raid_lp_recover_times - 1,
            change_func=self.change_value_lp_recover
        )

        self.link_raid_lp_recover_layout_2.addWidget(self.lp_recover_min_btn)
        self.link_raid_lp_recover_layout_2.addWidget(self.lp_recover_minus_btn)
        self.link_raid_lp_recover_layout_2.addWidget(self.lp_recover_input)
        self.link_raid_lp_recover_layout_2.addWidget(self.lp_recover_plus_btn)
        self.link_raid_lp_recover_layout_2.addWidget(self.lp_recover_max_btn)

        self.link_raid_lp_recover_layout_raw.addWidget(self.group_link_raid_lp_recover_label) # 这是标识符，后面开始是按钮
        self.link_raid_lp_recover_layout_raw.addLayout(self.link_raid_lp_recover_layout_2)

    #刷圣遗物界面布局器
        self.group_crystalis_lp_recover_label = QLabel('刷晶花部分\n晶花挂机要喝体力药几次')

    #刷圣遗物布局
        self.crystalis_lp_recover_layout = QVBoxLayout()

        self.crystalis_lp_recover_layout_row1 = QHBoxLayout()
        self.crystalis_lp_recover_min_btn, self.crystalis_lp_recover_minus_btn, self.crystalis_lp_recover_input, self.crystalis_lp_recover_plus_btn, self.crystalis_lp_recover_max_btn = self.create_lp_recover_input(
            min_num=0,
            max_num=8,
            default_num=crystalis_lp_recover_times - 1,
            change_func=self.change_value_crystalis_lp_recover_times
        )
        self.crystalis_lp_recover_layout_row1.addWidget(self.crystalis_lp_recover_min_btn)
        self.crystalis_lp_recover_layout_row1.addWidget(self.crystalis_lp_recover_minus_btn)
        self.crystalis_lp_recover_layout_row1.addWidget(self.crystalis_lp_recover_input)
        self.crystalis_lp_recover_layout_row1.addWidget(self.crystalis_lp_recover_plus_btn)
        self.crystalis_lp_recover_layout_row1.addWidget(self.crystalis_lp_recover_max_btn)

        self.crystalis_lp_recover_layout.addWidget(self.group_crystalis_lp_recover_label)
        self.crystalis_lp_recover_layout.addLayout(self.crystalis_lp_recover_layout_row1)
        self.crystalis_lp_recover_layout.addWidget(self.button_3)



    #主页布局
        self.mainlayout = QVBoxLayout()

        #顶部提示框
        self.mainlayout.addWidget(self.textedit_1_title)
        self.mainlayout.addWidget(self.textedit_1)
        #停止按钮
        self.mainlayout.addWidget(self.button_1)

        #语言/分辨率切换
        self.mainlayout.addWidget(self.lang_switcher)

        #先择linkraid等级，回体力次数部分
        self.mainlayout.addLayout(self.lv_choice_layout_row)
        self.mainlayout.addLayout(self.link_raid_lp_recover_layout_raw)

        #link raid挂机启动按钮
        self.mainlayout.addWidget(self.button_2)


        #圣遗物部分

        self.mainlayout.addLayout(self.crystalis_lp_recover_layout)

        self.setLayout(self.mainlayout)

    def _automation_running(self):
        return (self.workthread_1.isRunning() or self.workthread_2.isRunning()
                or getattr(self.lang_switcher, '_scaling', False))

    def _stop_automation(self):
        #请求两个工作线程停止；互斥运行时只有一个在跑，对没在跑的调用 stop() 也是安全的
        self.workthread_1.stop()
        self.workthread_2.stop()

    def _set_automation_controls(self, enabled):
        self.button_2.setEnabled(enabled)
        self.button_3.setEnabled(enabled)
        self.lang_switcher.setEnabled(enabled)

    def _start_link_raid(self):
        if self._automation_running():
            self.textedit_1.appendPlainText('已有挂机任务运行中，请先停止。')
            return
        #把 GUI 当前参数传给工作线程，运行逻辑在 workers/link_raid.py
        self.workthread_1.level_choice = link_raid_lv_choice
        self.workthread_1.lp_recover_times = link_raid_lp_recover_times
        self._set_automation_controls(False)
        self.workthread_1.start()

    def _start_crystalis(self):
        if self._automation_running():
            self.textedit_1.appendPlainText('已有挂机任务运行中，请先停止。')
            return
        #运行逻辑在 workers/crystalis.py
        self.workthread_2.lp_recover_times = crystalis_lp_recover_times
        self._set_automation_controls(False)
        self.workthread_2.start()

    def _automation_finished(self):
        if not self._automation_running():
            self._set_automation_controls(True)

    def _scaling_changed(self, scaling):
        if scaling:
            self.button_2.setEnabled(False)
            self.button_3.setEnabled(False)
        elif not self.workthread_1.isRunning() and not self.workthread_2.isRunning():
            self._set_automation_controls(True)

    def create_lp_recover_input(self, min_num, max_num, default_num, change_func):
        default_num = max(min_num, min(max_num, default_num))

        min_btn = QPushButton('最小')
        minus_btn = QPushButton('-1')
        plus_btn = QPushButton('+1')
        max_btn = QPushButton('最大')
        min_btn.setFixedWidth(40)
        minus_btn.setFixedWidth(30)
        plus_btn.setFixedWidth(30)
        max_btn.setFixedWidth(40)
        value_input = QLineEdit(str(default_num))
        value_input.setValidator(QIntValidator(min_num, max_num, self))
        value_input.setAlignment(Qt.AlignCenter)
        value_input.setFixedWidth(40)

        def get_current_num():
            text = value_input.text()
            if text == '':
                return min_num
            return max(min_num, min(max_num, int(text)))

        def set_visible_num(value_num):
            value_num = max(min_num, min(max_num, value_num))
            if value_input.text() == str(value_num):
                change_func(value_num + 1)
            else:
                value_input.setText(str(value_num))

        def change_from_input(text):
            if text == '':
                return
            value_num = max(min_num, min(max_num, int(text)))
            change_func(value_num + 1)

        def fix_input():
            set_visible_num(get_current_num())

        min_btn.clicked.connect(lambda: set_visible_num(min_num))
        minus_btn.clicked.connect(lambda: set_visible_num(get_current_num() - 1))
        plus_btn.clicked.connect(lambda: set_visible_num(get_current_num() + 1))
        max_btn.clicked.connect(lambda: set_visible_num(max_num))
        value_input.textChanged.connect(change_from_input)
        value_input.editingFinished.connect(fix_input)

        return min_btn, minus_btn, value_input, plus_btn, max_btn

    #用于改变link raid选择的等级
    def change_value(self,value_num):
        global link_raid_lv_choice
        print(f'link raid的等级修改之前是{link_raid_lv_choice}\n')
        link_raid_lv_choice=value_num
        print(f'link raid的等级变成了{value_num}\n')

    #用于改变link raid选择的等级
    def change_value_lp_recover(self,value_num):
        global link_raid_lp_recover_times
        print(f'link_raid_lp_recover_times修改之前是{link_raid_lp_recover_times}\n')
        link_raid_lp_recover_times=value_num
        print(f'link_raid_lp_recover_times的数据变成了{value_num}\n')

    # 用于改变晶花吃体力药次数
    def change_value_crystalis_lp_recover_times(self,value_num):
        global crystalis_lp_recover_times
        print(f'link_raid_lp_recover_times修改之前是{crystalis_lp_recover_times}\n')
        crystalis_lp_recover_times=value_num
        print(f'link_raid_lp_recover_times的数据变成了{value_num}\n')


if __name__ == '__main__':
    #这些据说能让导出程序的时候不出奇怪的bug
    def get_edge_path():
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe")
            edge_path, _ = winreg.QueryValueEx(key, "")
            winreg.CloseKey(key)
            return edge_path
        except FileNotFoundError:
            return None

    def get_executable_directory():
        if hasattr(sys, '_MEIPASS'):
            return os.path.dirname(sys.executable)  # 获取打包后可执行文件的真实路径
        else:
            return os.path.dirname(os.path.abspath(__file__))  # 获取脚本路径

    folder_path = get_executable_directory()
    print('运行路径：', folder_path)

    # 如果程序被打包为可执行文件
    if getattr(sys, "frozen", False):
        # 获取可执行文件所在的目录
        BASE_PATH = os.path.dirname(sys.executable)
        print(f'脚本执行路径：{BASE_PATH}')
        # 将当前工作目录设置为可执行文件所在的目录
        os.chdir(BASE_PATH)
    else:
        # 如果程序作为脚本运行，使用脚本目录
        BASE_PATH = os.path.dirname(__file__)
        print(f'脚本执行路径：{BASE_PATH}')
        os.chdir(BASE_PATH)


    #这里开始是正常的pyside6的启动，前面的是据说能让导出稳定的东西
    app = QApplication([])
    window = mywindow()
    window.show()
    app.exec()

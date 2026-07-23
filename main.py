import os
import sys
import threading
import winreg

# 必须在间接导入 cv2 前设置，打包环境下才会生效。
if getattr(sys, "frozen", False):
    os.environ["OPENCV_SKIP_PYTHON_LOADER"] = "1"

from datetime import datetime

from PySide6.QtWidgets import (QApplication, QButtonGroup, QHBoxLayout, QRadioButton,
                               QPlainTextEdit, QWidget, QPushButton, QLabel, QLineEdit,
                               QComboBox, QSizePolicy, QStackedWidget, QVBoxLayout)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QIntValidator

#其他自己写的文件
from src.packs import language_switcher, image_scaler


def get_worker_registry():
    #PyAutoGUI 导入时会设置进程 DPI 模式，因此必须等 QApplication 先完成 Qt 的 DPI 初始化。
    from src.workers import get_registry
    return get_registry()


# pyinstaller.exe -D -i resource/main.ico  main.py
#这个是导出用的


class LanguageSwitcherWidget(QWidget):
    #语言/分辨率切换控件，切换的是根目录 aim 这个 junction 的指向
    #选好语言和分辨率后会自动切换，不需要点按钮；只剩"刷新列表"用于重新扫描 pack
    switched = Signal(str)  #切换完成或失败时发出，用于在日志框显示
    scaleFinished = Signal()
    scalingChanged = Signal(bool)
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
        self._scaling = False
        self._scale_cancel = threading.Event()
        self._scale_thread = None
        self._refresh()

    def _lang_label(self, code):
        #语言中文名从 language_switcher 统一读取，新增语言只改 packs 不改 GUI
        return language_switcher.lang_label(code)

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
        if self._scaling:
            return
        self._scaling = True
        self._scale_cancel.clear()
        self.refreshBtn.setEnabled(False)
        self.langCombo.setEnabled(False)
        self.resCombo.setEnabled(False)
        self.scalingChanged.emit(True)
        def _work():
            try:
                summary = image_scaler.scale_all(
                    progress_cb=lambda s: self.switched.emit(s),
                    is_cancelled=self._scale_cancel.is_set,
                )
                if summary:
                    self.switched.emit(summary)
            except Exception as e:
                self.switched.emit(f'素材缩放出错: {e}')
            finally:
                self.scaleFinished.emit()
        self._scale_thread = threading.Thread(target=_work, daemon=True)
        self._scale_thread.start()

    def _scale_finished(self):
        self._scaling = False
        self._scale_thread = None
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
    #GUI 入口。遍历 workers 的 REGISTRY 自动生成脚本选项和各自的参数页，
    #新增挂机模式只需在 workers/ 里写一个文件并 @register，不用改这里的 GUI 代码。
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
        self.textedit_1 = QPlainTextEdit()
        self.textedit_1.document().setMaximumBlockCount(2000)

        #遍历注册表，为每个挂机模式创建 worker 和参数页；下拉选择后只显示当前脚本的参数。
        self._entries = []
        for meta in get_worker_registry():
            self._entries.append(self._build_worker_entry(meta))

        self.scriptTitle = QLabel('选择挂机脚本')
        self.scriptCombo = QComboBox()
        self.paramStack = QStackedWidget()
        self.paramStack.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        for entry in self._entries:
            self.scriptCombo.addItem(entry['meta'].label)
            self.paramStack.addWidget(entry['param_widget'])
        self.scriptCombo.currentIndexChanged.connect(self._script_changed)

        self.startButton = QPushButton()
        self.startButton.clicked.connect(self._start_selected_worker)
        self._script_changed(self.scriptCombo.currentIndex())

        #停止按钮，按下启动停止进程，会调用所有工作线程的 stop()
        self.button_1 = QPushButton('停下当前运行的脚本')
        self.button_1.clicked.connect(self._stop_automation)

        #更新来源尚未确定，先保留统一入口，之后只需替换槽函数里的实现。
        self.checkUpdateBtn = QPushButton('检查更新')
        self.checkUpdateBtn.clicked.connect(self._check_update)

        #语言/分辨率切换控件，切换 aim 联接指向
        self.lang_switcher = LanguageSwitcherWidget(self._automation_running)
        self.lang_switcher.switched.connect(self._append_log)
        self.lang_switcher.switched.connect(lambda: self.setWindowIcon(QIcon('./resource/main.ico')))
        self.lang_switcher.scalingChanged.connect(self._scaling_changed)

        #主页布局
        self.mainlayout = QVBoxLayout()

        #顶部提示框
        self.mainlayout.addWidget(self.textedit_1_title)
        self.mainlayout.addWidget(self.textedit_1)
        #停止按钮
        self.mainlayout.addWidget(self.button_1)

        #语言/分辨率切换
        self.mainlayout.addWidget(self.lang_switcher)

        #脚本选择区：只展示当前选择脚本的参数，新增模式不会继续向下堆叠界面。
        self.mainlayout.addWidget(self.scriptTitle)
        self.mainlayout.addWidget(self.scriptCombo)
        self.mainlayout.addWidget(self.paramStack)
        self.mainlayout.addWidget(self.startButton)
        self.mainlayout.addWidget(self.checkUpdateBtn)

        self.setLayout(self.mainlayout)

    def _build_worker_entry(self, meta):
        #为一个挂机模式创建 worker 和独立参数页，返回 entry 字典
        worker = meta.worker_class()
        worker.signal.connect(self._append_log)
        display_name = meta.name.replace('_', ' ')
        worker.finished.connect(lambda n=display_name: print(f'{n}挂机结束'))
        worker.finished.connect(lambda n=display_name: self._append_log(f'{n}挂机结束或被主动停止\n'))
        worker.finished.connect(self._automation_finished)

        #参数控件区
        param_layout = QVBoxLayout()
        getters = {}
        controls = []
        for spec in meta.params:
            sub_layout, getter, sub_controls = self._build_param_widget(spec)
            param_layout.addLayout(sub_layout)
            getters[spec.key] = getter
            controls.extend(sub_controls)

        param_widget = QWidget()
        if not meta.params:
            param_layout.addWidget(QLabel('该脚本没有可配置参数'))
        param_widget.setLayout(param_layout)
        entry = {
            'meta': meta,
            'worker': worker,
            'param_widget': param_widget,
            'getters': getters,
            'controls': controls,
        }
        return entry

    def _script_changed(self, index):
        if not 0 <= index < len(self._entries):
            self.startButton.setText('没有可用的挂机脚本')
            self.startButton.setEnabled(False)
            return
        self.paramStack.setCurrentIndex(index)
        current_page = self.paramStack.currentWidget()
        if current_page is not None:
            self.paramStack.setFixedHeight(current_page.sizeHint().height())
        self.startButton.setText(f"启动：{self._entries[index]['meta'].label}")

    def _start_selected_worker(self):
        index = self.scriptCombo.currentIndex()
        if 0 <= index < len(self._entries):
            self._start_worker(self._entries[index])

    def _check_update(self):
        self._append_log('检查更新功能已预留，尚未配置版本号和更新来源。')

    def _append_log(self, text):
        self.textedit_1.appendPlainText(f"[{datetime.now().strftime('%H:%M:%S')}]: {text}")

    def _build_param_widget(self, spec):
        #根据 ParamSpec.kind 生成对应控件，返回 (QLayout, getter函数, 可禁用控件列表)
        layout = QVBoxLayout()
        label = QLabel(spec.label)
        layout.addWidget(label)
        controls = [label]

        if spec.kind == 'choice':
            #单选按钮组，每 3 个一行
            group = QButtonGroup(self)
            group.setExclusive(True)
            buttons = []
            for val in spec.choices:
                btn = QRadioButton(str(val))
                if val == spec.default:
                    btn.setChecked(True)
                group.addButton(btn)
                buttons.append(btn)
            row = QHBoxLayout()
            for i, btn in enumerate(buttons):
                row.addWidget(btn)
                if (i + 1) % 3 == 0:
                    layout.addLayout(row)
                    row = QHBoxLayout()
            if row.count() > 0:
                layout.addLayout(row)
            choice_pairs = list(zip(buttons, spec.choices))
            def getter():
                for btn, val in choice_pairs:
                    if btn.isChecked():
                        return val
                return spec.default
            controls.extend(buttons)

        elif spec.kind == 'lp_recover':
            #喝体力药次数：最小/-1/输入/+1/最大 五件套；显示的是"喝几次"，传给 worker 时 +1
            min_btn, minus_btn, input_edit, plus_btn, max_btn = self.create_lp_recover_input(
                min_num=spec.min, max_num=spec.max, default_num=spec.default,
            )
            row = QHBoxLayout()
            row.addWidget(min_btn)
            row.addWidget(minus_btn)
            row.addWidget(input_edit)
            row.addWidget(plus_btn)
            row.addWidget(max_btn)
            layout.addLayout(row)
            lo, hi = spec.min, spec.max
            def getter():
                text = input_edit.text()
                if text == '':
                    return lo + 1
                return max(lo, min(hi, int(text))) + 1  #显示值 +1 = 存储值
            controls.extend([min_btn, minus_btn, input_edit, plus_btn, max_btn])

        else:  # 'int' 普通整数输入，留作扩展
            input_edit = QLineEdit(str(spec.default))
            input_edit.setValidator(QIntValidator(spec.min, spec.max, self))
            input_edit.setAlignment(Qt.AlignCenter)
            layout.addWidget(input_edit)
            lo, hi = spec.min, spec.max
            def getter():
                text = input_edit.text()
                if text == '':
                    return lo
                return max(lo, min(hi, int(text)))
            controls.append(input_edit)

        return layout, getter, controls

    def create_lp_recover_input(self, min_num, max_num, default_num):
        #喝药次数的五件套输入控件。值由调用方用 getter 读取，不再需要 change_func 回调。
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

        def current_num():
            text = value_input.text()
            if text == '':
                return min_num
            return max(min_num, min(max_num, int(text)))

        def set_visible_num(value_num):
            value_num = max(min_num, min(max_num, value_num))
            if value_input.text() != str(value_num):
                value_input.setText(str(value_num))

        min_btn.clicked.connect(lambda: set_visible_num(min_num))
        minus_btn.clicked.connect(lambda: set_visible_num(current_num() - 1))
        plus_btn.clicked.connect(lambda: set_visible_num(current_num() + 1))
        max_btn.clicked.connect(lambda: set_visible_num(max_num))
        value_input.editingFinished.connect(lambda: set_visible_num(current_num()))

        return min_btn, minus_btn, value_input, plus_btn, max_btn

    def _automation_running(self):
        #任何一个 worker 在跑，或正在缩放素材，都算"忙"
        return any(e['worker'].isRunning() for e in self._entries) \
            or getattr(self.lang_switcher, '_scaling', False)

    def closeEvent(self, event):
        #先协作停止后台任务，避免窗口销毁后线程继续点击或向 Qt 对象发信号。
        for entry in self._entries:
            entry['worker'].stop()
        self.lang_switcher._scale_cancel.set()

        workers_stopped = True
        for entry in self._entries:
            worker = entry['worker']
            if worker.isRunning() and not worker.wait(5000):
                workers_stopped = False
        scale_thread = self.lang_switcher._scale_thread
        if scale_thread and scale_thread.is_alive():
            scale_thread.join(timeout=5)

        if not workers_stopped or (scale_thread and scale_thread.is_alive()):
            self._append_log('后台任务尚未安全停止，请稍后再关闭窗口。')
            event.ignore()
            return
        event.accept()

    def _stop_automation(self):
        #请求所有工作线程停止；互斥运行时只有一个在跑，对没在跑的调用 stop() 也是安全的
        for e in self._entries:
            e['worker'].stop()

    def _set_automation_controls(self, enabled):
        #统一启用/禁用脚本选择、启动按钮、参数控件和语言切换器（停止按钮始终可用）
        self.scriptTitle.setEnabled(enabled)
        self.scriptCombo.setEnabled(enabled)
        self.startButton.setEnabled(enabled and bool(self._entries))
        for e in self._entries:
            for c in e['controls']:
                c.setEnabled(enabled)
        self.lang_switcher.setEnabled(enabled)

    def _start_worker(self, entry):
        if self._automation_running():
            self.textedit_1.appendPlainText('已有挂机任务运行中，请先停止。')
            return
        from src.click import click_behavior, click_action
        if click_behavior.find_win('MadokaExedra') is None:
            self._append_log('未找到游戏窗口 MadokaExedra，本次挂机已停止。请先启动游戏。')
            return
        #识别游戏窗口分辨率并与当前模板 pack 容差比对（标题栏/边框/DPI 的小幅偏差可容忍）
        res_info = click_action.detect_window_resolution()
        self._append_log(res_info['message'])
        if not res_info['matched']:
            self._append_log('分辨率不一致可能导致识图失败，请确认游戏窗口分辨率与所选模板 pack 一致。')
        #收集 GUI 参数到 worker（lp_recover 已在 getter 里 +1 为存储值）
        worker = entry['worker']
        for key, getter in entry['getters'].items():
            setattr(worker, key, getter())
        if entry['meta'].start_hint:
            self.textedit_1.appendPlainText(f"[{datetime.now().strftime('%H:%M:%S')}]: {entry['meta'].start_hint}")
        self._set_automation_controls(False)
        worker.start()

    def _automation_finished(self):
        #某个 worker 结束时：若已无 worker 在跑（且没在缩放），恢复所有控件
        if not self._automation_running():
            self._set_automation_controls(True)

    def _scaling_changed(self, scaling):
        if scaling:
            self.scriptTitle.setEnabled(False)
            self.scriptCombo.setEnabled(False)
            self.startButton.setEnabled(False)
            for e in self._entries:
                for c in e['controls']:
                    c.setEnabled(False)
        elif not self._automation_running():
            self._set_automation_controls(True)


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

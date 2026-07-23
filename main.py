import os
import sys
import threading
import webbrowser
import subprocess
import tempfile
import shutil
import uuid
import time
import winreg

# 必须在间接导入 cv2 前设置，打包环境下才会生效。
if getattr(sys, "frozen", False):
    os.environ["OPENCV_SKIP_PYTHON_LOADER"] = "1"

from datetime import datetime

from PySide6.QtWidgets import (QApplication, QButtonGroup, QHBoxLayout, QRadioButton,
                               QPlainTextEdit, QWidget, QPushButton, QLabel, QLineEdit,
                               QComboBox, QSizePolicy, QStackedWidget, QVBoxLayout,
                               QMessageBox, QProgressDialog, QCheckBox)
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
    updateChecked = Signal(str, object)
    updateProgress = Signal(str, int, int)
    updateReady = Signal(str, object)
    updateFailed = Signal(str, str)
    def __init__(self):
        super().__init__()

        self._update_state = 'idle'
        self._update_job_id = None
        self._update_cancel = threading.Event()
        self._update_check_thread = None
        self._update_prepare_thread = None
        self._update_job_dir = None
        self._pending_update = None
        self._update_lock_path = None
        self._closing = False
        self._update_manual = False

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

        #检查更新：点击触发；启动时也会自动后台跑一次
        self.checkUpdateBtn = QPushButton('检查更新')
        self.checkUpdateBtn.clicked.connect(self._check_update)
        #勾选后检查更新时包含预发布（beta）版本；默认不勾选，只更新到正式版
        self.betaCheckBox = QCheckBox('更新至 beta 版')
        self.betaCheckBox.setToolTip('勾选后检查更新会包含预发布（beta）版本；不勾选则只更新到正式版')
        self.updateChecked.connect(self._on_update_checked)
        self.updateProgress.connect(self._on_update_progress)
        self.updateReady.connect(self._on_update_ready)
        self.updateFailed.connect(self._on_update_failed)

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
        update_row = QHBoxLayout()
        update_row.addWidget(self.checkUpdateBtn)
        update_row.addWidget(self.betaCheckBox)
        self.mainlayout.addLayout(update_row)

        self.setLayout(self.mainlayout)

        #启动时自动后台检查一次更新（不阻塞界面，结果进日志）
        self._check_update_async()

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
        self._check_update_async(manual=True)

    def _check_update_async(self, manual=False):
        #后台线程查 GitHub 最新发布版本，避免阻塞界面；同时只允许一个检查在跑
        if self._update_state != 'idle' or self._closing:
            return
        job_id = uuid.uuid4().hex
        self._update_job_id = job_id
        self._update_state = 'checking'
        self._update_manual = manual
        self._refresh_control_state()
        channel = 'beta' if self.betaCheckBox.isChecked() else 'stable'
        self._append_log('正在检查更新...' + ('（含 beta）' if channel == 'beta' else ''))
        def _work():
            try:
                from src.update_check import check_for_update
                r = check_for_update(channel=channel, is_cancelled=self._update_cancel.is_set)
            except Exception as e:
                r = {'has_update': False, 'message': f'检查更新出错：{e}'}
            try:
                self.updateChecked.emit(job_id, r)
            except RuntimeError:
                pass  #窗口已关闭，忽略
        self._update_check_thread = threading.Thread(target=_work, daemon=True)
        self._update_check_thread.start()

    def _on_update_checked(self, job_id, r):
        if self._closing or job_id != self._update_job_id or self._update_state != 'checking':
            return
        self._update_check_thread = None
        self._update_state = 'idle'
        self._update_cancel.clear()
        self._refresh_control_state()
        if not isinstance(r, dict):
            self._append_log(str(r))
            return
        self._append_log(r.get('message', ''))
        if r.get('has_update'):
            self._offer_update(r)

    def _local_version_disp(self):
        from src.update_check import VERSION
        return VERSION if VERSION[:1] in ('v', 'V') else f'v{VERSION}'

    def _offer_update(self, r):
        #有新版本时：打包版弹对话框询问是否更新；源码模式回退为打开 Release 页
        from src.update_check import is_frozen
        tag = r.get('latest_tag', '')
        url = r.get('url') or r.get('asset_url') or 'https://github.com/LUODIAN-233/Magia_Exedra_auto/releases'
        if not is_frozen():
            if self._update_manual:
                self._append_log('当前为源码运行模式，已打开 Release 页面，请手动更新或 git pull。')
                webbrowser.open(url)
            else:
                self._append_log(f'当前为源码运行模式，请前往 {url} 手动更新或 git pull。')
            return
        asset_url = r.get('asset_url')
        if not asset_url or not r.get('asset_sha256'):
            self._append_log('Release 未提供唯一且带 SHA-256 的更新 ZIP，已禁用自动安装。')
            if self._update_manual:
                webbrowser.open(url)
            return
        if self._automation_running():
            self._append_log('挂机或素材缩放正在运行，请停止后再开始更新。')
            return
        size_mb = (r.get('asset_size') or 0) // 1024 // 1024
        reply = QMessageBox.question(
            self, '发现新版本',
            f'发现新版本 {tag}（当前 {self._local_version_disp()}）。\n'
            f'是否现在下载并更新？\n\n'
            f'更新包约 {size_mb} MB，下载完成后程序将退出、自动替换文件并重启。',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply == QMessageBox.Yes:
            try:
                self._start_download(r)
            except Exception as e:
                self._append_log(f'无法开始更新：{e}')
                self._reset_update_state(cleanup=True)

    def _start_download(self, r):
        from src.update_check import (download_asset, extract_update, UpdateCancelled,
                                      acquire_update_lock)
        if self._update_state != 'idle' or self._automation_running() or self._closing:
            self._append_log('当前有其它任务运行，不能开始更新。')
            return
        job_id = uuid.uuid4().hex
        asset_url = r['asset_url']
        job_dir = tempfile.mkdtemp(prefix=f'magia_exedra_update_{os.getpid()}_')
        zip_path = os.path.join(job_dir, 'update.zip')
        staging = os.path.join(job_dir, 'staging')
        self._update_job_id = job_id
        self._update_job_dir = job_dir
        try:
            self._update_lock_path = acquire_update_lock(
                os.path.dirname(sys.executable), job_id, job_dir,
            )
        except Exception:
            shutil.rmtree(job_dir, ignore_errors=True)
            self._update_job_id = None
            self._update_job_dir = None
            raise
        self._update_cancel.clear()
        self._update_state = 'downloading'
        self._progress = QProgressDialog('正在下载更新包...', '取消', 0, 100, self)
        self._progress.setWindowTitle('更新')
        self._progress.setWindowModality(Qt.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.setAutoClose(False)
        self._progress.setAutoReset(False)
        self._progress.setValue(0)
        self._progress.canceled.connect(self._on_update_cancel)
        self._refresh_control_state()
        def _work():
            try:
                def _cb(done, total):
                    try:
                        self.updateProgress.emit(job_id, done, total)
                    except RuntimeError:
                        pass
                download_asset(
                    asset_url, zip_path, r['asset_size'], r['asset_sha256'],
                    progress_cb=_cb, is_cancelled=self._update_cancel.is_set,
                )
                self.updateProgress.emit(job_id, -1, -1)
                src = extract_update(
                    zip_path, staging, r.get('latest_tag', ''), self._update_cancel.is_set,
                )
                self.updateReady.emit(job_id, {'src_dir': src, 'job_dir': job_dir})
            except UpdateCancelled as e:
                shutil.rmtree(job_dir, ignore_errors=True)
                self.updateFailed.emit(job_id, str(e))
            except Exception as e:
                shutil.rmtree(job_dir, ignore_errors=True)
                self.updateFailed.emit(job_id, str(e))
        self._update_prepare_thread = threading.Thread(target=_work, daemon=True)
        self._update_prepare_thread.start()

    def _on_update_progress(self, job_id, done, total):
        if self._closing or job_id != self._update_job_id or not hasattr(self, '_progress'):
            return
        if done < 0:  #解压阶段
            self._update_state = 'extracting'
            self._progress.setMaximum(0)
            self._progress.setLabelText('正在解压更新包...')
            return
        if total > 0:
            self._progress.setMaximum(100)
            self._progress.setValue(int(done * 100 / total))
            self._progress.setLabelText(f'正在下载... {done // 1024 // 1024}/{total // 1024 // 1024} MB')
        else:
            self._progress.setMaximum(0)
            self._progress.setLabelText('正在下载更新包...')

    def _on_update_ready(self, job_id, payload):
        if self._closing or job_id != self._update_job_id \
                or self._update_state not in ('downloading', 'extracting'):
            return
        self._update_prepare_thread = None
        self._update_state = 'ready'
        if hasattr(self, '_progress'):
            self._progress.close()
        self._pending_update = payload
        self._append_log('更新包已通过校验，正在安全停止后台任务并准备安装...')
        self.close()

    def _on_update_failed(self, job_id, msg):
        if self._closing or job_id != self._update_job_id:
            return
        self._update_prepare_thread = None
        if hasattr(self, '_progress'):
            self._progress.close()
        self._append_log(msg if '取消' in msg else f'更新失败：{msg}')
        self._reset_update_state(cleanup=False)

    def _on_update_cancel(self):
        if self._update_state not in ('downloading', 'extracting'):
            return
        self._update_cancel.set()
        self._progress.setLabelText('正在取消更新并清理临时文件...')
        self._progress.setCancelButton(None)

    def _apply_update(self, payload):
        #写批处理：等本进程退出后 robocopy 覆盖安装目录并重启；然后退出
        from src.update_check import write_update_bat
        exe_path = sys.executable
        bat_path = write_update_bat(
            exe_path, payload['src_dir'], os.getpid(), payload['job_dir'], self._update_lock_path,
            self._update_job_id,
        )
        self._append_log('更新已准备就绪，程序即将退出完成安装。')
        subprocess.Popen(['cmd', '/c', bat_path],
                         creationflags=subprocess.CREATE_NO_WINDOW,
                         close_fds=True)

    def _reset_update_state(self, cleanup=True):
        from src.update_check import release_update_lock
        release_update_lock(self._update_lock_path, self._update_job_id)
        if cleanup and self._update_job_dir:
            shutil.rmtree(self._update_job_dir, ignore_errors=True)
        self._update_state = 'idle'
        self._update_job_id = None
        self._update_job_dir = None
        self._pending_update = None
        self._update_lock_path = None
        self._update_cancel.clear()
        self._refresh_control_state()

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
                if not input_edit.hasAcceptableInput() or text == '':
                    raise ValueError(f'{spec.label} 输入无效，请输入 {lo} 到 {hi} 的整数。')
                value = int(text)
                if not lo <= value <= hi:
                    raise ValueError(f'{spec.label} 超出范围。')
                return value + 1  #显示值 +1 = 存储值
            controls.extend([min_btn, minus_btn, input_edit, plus_btn, max_btn])

        elif spec.kind == 'int':
            input_edit = QLineEdit(str(spec.default))
            input_edit.setValidator(QIntValidator(spec.min, spec.max, self))
            input_edit.setAlignment(Qt.AlignCenter)
            layout.addWidget(input_edit)
            lo, hi = spec.min, spec.max
            def getter():
                text = input_edit.text()
                if not input_edit.hasAcceptableInput() or text == '':
                    raise ValueError(f'{spec.label} 输入无效，请输入 {lo} 到 {hi} 的整数。')
                return int(text)
            controls.append(input_edit)

        else:
            raise ValueError(f'不支持的参数控件类型: {spec.kind}')

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

    def _update_busy(self):
        return self._update_state in ('downloading', 'extracting', 'ready', 'closing')

    def _refresh_control_state(self):
        if not hasattr(self, 'checkUpdateBtn'):
            return
        automation_busy = self._automation_running()
        update_busy = self._update_busy()
        controls_enabled = not automation_busy and not update_busy and not self._closing
        self.scriptTitle.setEnabled(controls_enabled)
        self.scriptCombo.setEnabled(controls_enabled)
        self.startButton.setEnabled(controls_enabled and bool(self._entries))
        for entry in self._entries:
            for control in entry['controls']:
                control.setEnabled(controls_enabled)
        self.lang_switcher.setEnabled(controls_enabled)
        checking = self._update_state == 'checking'
        self.checkUpdateBtn.setEnabled(not checking and not update_busy and not self._closing)
        self.betaCheckBox.setEnabled(not checking and not update_busy and not self._closing)

    def closeEvent(self, event):
        #先协作停止后台任务，避免窗口销毁后线程继续点击或向 Qt 对象发信号。
        self._closing = True
        self._refresh_control_state()
        for entry in self._entries:
            entry['worker'].stop()
        self.lang_switcher._scale_cancel.set()
        self._update_cancel.set()

        workers_stopped = True
        deadline = time.monotonic() + 12
        for entry in self._entries:
            worker = entry['worker']
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            if worker.isRunning() and not worker.wait(remaining_ms):
                workers_stopped = False
        scale_thread = self.lang_switcher._scale_thread
        if scale_thread and scale_thread.is_alive():
            scale_thread.join(timeout=max(0, deadline - time.monotonic()))
        for thread in (self._update_check_thread, self._update_prepare_thread):
            if thread and thread.is_alive():
                thread.join(timeout=max(0, deadline - time.monotonic()))

        update_alive = any(t and t.is_alive() for t in (self._update_check_thread, self._update_prepare_thread))
        if not workers_stopped or (scale_thread and scale_thread.is_alive()) or update_alive:
            self._append_log('后台任务尚未安全停止，请稍后再关闭窗口。')
            self._closing = False
            self._refresh_control_state()
            event.ignore()
            return
        if self._pending_update:
            try:
                self._update_state = 'closing'
                self._apply_update(self._pending_update)
            except Exception as e:
                self._append_log(f'启动更新安装器失败：{e}')
                self._closing = False
                self._reset_update_state(cleanup=True)
                event.ignore()
                return
        else:
            self._reset_update_state(cleanup=True)
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
        if self._automation_running() or self._update_busy() or self._closing:
            self.textedit_1.appendPlainText('已有挂机任务运行中，请先停止。')
            return
        from src.update_check import update_recovery_issue
        recovery = update_recovery_issue(os.path.dirname(sys.executable))
        if recovery:
            self._append_log(f'检测到上次更新回滚不完整，已禁止挂机。请按文件提示恢复：{recovery}')
            return
        from src.click import click_behavior, click_action
        if click_behavior.find_win('MadokaExedra') is None:
            self._append_log('未找到游戏窗口 MadokaExedra，本次挂机已停止。请先启动游戏。')
            return
        #识别游戏窗口分辨率并与当前模板 pack 容差比对（标题栏/边框/DPI 的小幅偏差可容忍）
        res_info = click_action.detect_window_resolution()
        self._append_log(res_info['message'])
        if not res_info['matched']:
            self._append_log('无法确认窗口与模板分辨率一致，为防止坐标误点，本次挂机未启动。')
            return
        selection = language_switcher.current_selection()
        if selection is None:
            self._append_log('当前没有有效的模板 pack，本次挂机未启动。')
            return
        valid, errors = language_switcher.validate_template_groups(
            selection[0], selection[1], entry['meta'].required_templates,
        )
        if not valid:
            self._append_log('当前模板 pack 不完整，本次挂机未启动：\n' + '\n'.join(errors[:20]))
            return
        #收集 GUI 参数到 worker（lp_recover 已在 getter 里 +1 为存储值）
        worker = entry['worker']
        try:
            for key, getter in entry['getters'].items():
                setattr(worker, key, getter())
        except (TypeError, ValueError) as e:
            self._append_log(str(e))
            return
        worker.expected_pack = selection
        if entry['meta'].start_hint:
            self.textedit_1.appendPlainText(f"[{datetime.now().strftime('%H:%M:%S')}]: {entry['meta'].start_hint}")
        self._set_automation_controls(False)
        if not worker.start():
            self._set_automation_controls(True)

    def _automation_finished(self):
        #某个 worker 结束时：若已无 worker 在跑（且没在缩放），恢复所有控件
        if not self._automation_running():
            self._refresh_control_state()

    def _scaling_changed(self, scaling):
        if scaling:
            self.scriptTitle.setEnabled(False)
            self.scriptCombo.setEnabled(False)
            self.startButton.setEnabled(False)
            for e in self._entries:
                for c in e['controls']:
                    c.setEnabled(False)
        elif not self._automation_running():
            self._refresh_control_state()


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
    health_path = os.environ.get('MAGIA_UPDATE_HEALTH')
    if health_path:
        try:
            with open(health_path, 'x', encoding='ascii') as f:
                f.write('ok')
        except OSError:
            pass
    app.exec()

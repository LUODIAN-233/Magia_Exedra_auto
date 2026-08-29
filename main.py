import os
import sys
import threading
import webbrowser
import subprocess
import tempfile
import shutil
import uuid
import time
import logging
import winreg
import ctypes


def _hide_frozen_console():
    #兼容已经按 console 模式构建的发行版；新的 --windowed 构建不会创建控制台。
    if not getattr(sys, 'frozen', False):
        return
    try:
        console = ctypes.windll.kernel32.GetConsoleWindow()
        if console:
            ctypes.windll.user32.ShowWindow(console, 0)  # SW_HIDE
    except (AttributeError, OSError):
        pass


_hide_frozen_console()

# 必须在间接导入 cv2 前设置，打包环境下才会生效。
if getattr(sys, "frozen", False):
    os.environ["OPENCV_SKIP_PYTHON_LOADER"] = "1"

#日志要在业务模块导入前配置好，后续所有 logger 才能被统一 handler 接管。
#MAGIA_LOG_LEVEL 环境变量可覆盖控制台级别（默认 WARNING，开发时设 DEBUG 看全部）。
from src.core.log_setup import cleanup_old_logs, configure_logging, set_file_log_level
configure_logging()

from datetime import datetime

from PySide6.QtWidgets import (QApplication, QButtonGroup, QHBoxLayout, QRadioButton,
                               QPlainTextEdit, QWidget, QPushButton, QLabel, QLineEdit,
                               QComboBox, QSizePolicy, QStackedWidget, QVBoxLayout,
                               QMessageBox, QProgressDialog, QCheckBox, QGroupBox,
                               QDialog, QDialogButtonBox, QFormLayout, QSpinBox,
                               QListWidget, QListWidgetItem, QGridLayout,
                               QScrollArea, QFrame)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QIcon, QIntValidator, QTextCursor

#其他自己写的文件
from src.packs import language_switcher, image_scaler
from src.core.app_settings import (GUI_LOG_LEVELS, MAX_SERVERCHAN_CHANNELS,
                                   load_automation_mode, load_log_level,
                                   load_log_retention_days, load_notification_settings,
                                   load_worker_params,
                                   save_automation_mode, save_log_level,
                                   save_log_retention_days, save_notification_settings,
                                   save_worker_params)
from src.core.log_fold import ConsecutiveLogFolder
from src.core.notification import (NOTIFICATION_EVENTS, SERVERCHAN_CHANNELS,
                                   NotificationManager, valid_send_key)

logger = logging.getLogger(__name__)
runtime_logger = logging.getLogger('magia.runtime')
GUI_LOG_MAX_LINES = 500


def _notify_if_available(owner, event_key, mode, reason, params=None):
    handler = getattr(owner, '_notify_major_event', None)
    if handler is not None:
        handler(event_key, mode, reason, params)


class GuiLogHandler(logging.Handler):
    def __init__(self, emit_log):
        super().__init__()
        self.emit_log = emit_log

    def emit(self, record):
        try:
            #运行消息已经直接显示到 GUI，只需继续交给文件/控制台 handler。
            if getattr(record, '_magia_gui_displayed', False):
                return
            timestamp = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
            self.emit_log(timestamp, record.levelname, record.name, self.format(record))
        except (RuntimeError, RecursionError):
            pass


class CurrentPageStack(QStackedWidget):
    """只按当前参数页计算高度，避免首次显示时缓存未完成的布局尺寸。"""

    def sizeHint(self):
        current = self.currentWidget()
        return current.sizeHint() if current is not None else super().sizeHint()

    def minimumSizeHint(self):
        current = self.currentWidget()
        return current.minimumSizeHint() if current is not None else super().minimumSizeHint()


class SettingsDialog(QDialog):
    notificationChanged = Signal(object)

    def __init__(self, initial_log_level, retention_days, beta_checked,
                 notification_settings, parent=None):
        super().__init__(parent)
        self.setObjectName('settingsDialog')
        self.setWindowTitle('设置')
        self.setModal(True)
        self.setMinimumSize(420, 480)
        self.resize(520, 660)

        self.logLevelCombo = QComboBox()
        self.logLevelCombo.addItems(GUI_LOG_LEVELS)
        self.logLevelCombo.setCurrentText(initial_log_level)
        self.logLevelCombo.setToolTip(
            '同步控制 GUI 调试记录和 logs 文件；INFO/DEBUG 会记录完整挂机流程'
        )
        self.retentionSpin = QSpinBox()
        self.retentionSpin.setRange(1, 365)
        self.retentionSpin.setValue(retention_days)
        self.retentionSpin.setSuffix(' 天')
        self.retentionSpin.setToolTip('程序启动时自动删除超过该天数的历史日志')
        self.betaCheckBox = QCheckBox('更新至 beta 版')
        self.betaCheckBox.setChecked(beta_checked)
        self.betaCheckBox.setToolTip(
            '勾选后检查更新会包含预发布（beta）版本；不勾选则只更新到正式版'
        )
        self.checkUpdateBtn = QPushButton('立即检查更新')
        self.cleanLogsBtn = QPushButton('清理过时日志')
        self.cleanLogsBtn.setToolTip('删除此前会话的 Magia 日志，保留当前会话日志')

        self.notificationEnableCheckBox = QCheckBox('启用 Server酱 通知')
        self.notificationEnableCheckBox.setChecked(notification_settings['enabled'])
        self.sendKeyEdit = QLineEdit(notification_settings['send_key'])
        self.sendKeyEdit.setEchoMode(QLineEdit.Password)
        self.sendKeyEdit.setPlaceholderText('SCT 开头的 SendKey')
        self.sendKeyEdit.setToolTip('SendKey 仅明文保存在本机 settings.json，不会写入日志')

        self.channelChecks = {}
        channels_layout = QGridLayout()
        channels_layout.setHorizontalSpacing(12)
        channels_layout.setVerticalSpacing(6)
        selected_channels = set(notification_settings['channels'])
        for index, (channel_id, label) in enumerate(SERVERCHAN_CHANNELS):
            checkbox = QCheckBox(label)
            checkbox.setChecked(channel_id in selected_channels)
            self.channelChecks[channel_id] = checkbox
            channels_layout.addWidget(checkbox, index // 2, index % 2)
        channels_label = QLabel(f'推送通道（最多 {MAX_SERVERCHAN_CHANNELS} 个）')
        channels_label.setToolTip('通道需先在 Server酱官网完成绑定')
        channels_widget = QWidget()
        channels_widget.setLayout(channels_layout)

        self.eventChecks = {}
        events_layout = QVBoxLayout()
        events_layout.setSpacing(5)
        for event_key, label in NOTIFICATION_EVENTS:
            checkbox = QCheckBox(label)
            checkbox.setChecked(notification_settings['events'][event_key])
            self.eventChecks[event_key] = checkbox
            events_layout.addWidget(checkbox)
        events_label = QLabel('重大事件')
        events_widget = QWidget()
        events_widget.setLayout(events_layout)

        self.testNotificationBtn = QPushButton('发送测试通知')
        self.notificationStatusLabel = QLabel()
        self.notificationStatusLabel.setObjectName('secondaryText')
        self.notificationStatusLabel.setWordWrap(True)
        self._notification_test_running = False

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)
        form.addRow('日志等级', self.logLevelCombo)
        form.addRow('日志保留', self.retentionSpin)
        form.addRow('', self.betaCheckBox)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText('关闭')
        buttons.rejected.connect(self.reject)

        content_widget = QWidget()
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(14, 12, 14, 12)
        content_layout.setSpacing(14)
        content_layout.addLayout(form)
        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        action_row.addWidget(self.cleanLogsBtn)
        action_row.addWidget(self.checkUpdateBtn)
        content_layout.addLayout(action_row)

        notification_group = QGroupBox('通知设置')
        notification_layout = QVBoxLayout()
        notification_layout.setSpacing(9)
        notification_layout.addWidget(self.notificationEnableCheckBox)
        send_key_form = QFormLayout()
        send_key_form.addRow('SendKey', self.sendKeyEdit)
        notification_layout.addLayout(send_key_form)
        notification_layout.addWidget(channels_label)
        notification_layout.addWidget(channels_widget)
        notification_layout.addWidget(events_label)
        notification_layout.addWidget(events_widget)
        test_row = QHBoxLayout()
        test_row.addWidget(self.testNotificationBtn)
        test_row.addWidget(self.notificationStatusLabel, 1)
        notification_layout.addLayout(test_row)
        notification_group.setLayout(notification_layout)
        content_layout.addWidget(notification_group)
        content_layout.addStretch(1)
        content_widget.setLayout(content_layout)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setWidget(content_widget)

        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 12)
        layout.setSpacing(8)
        layout.addWidget(scroll_area, 1)
        layout.addWidget(buttons)
        self.setLayout(layout)

        self.notificationEnableCheckBox.toggled.connect(self._emit_notification_settings)
        self.sendKeyEdit.textChanged.connect(self._emit_notification_settings)
        for checkbox in self.channelChecks.values():
            checkbox.toggled.connect(
                lambda checked, current=checkbox: self._channel_toggled(current, checked)
            )
        for checkbox in self.eventChecks.values():
            checkbox.toggled.connect(self._emit_notification_settings)
        self._refresh_notification_status()

    def notification_settings(self):
        return {
            'enabled': self.notificationEnableCheckBox.isChecked(),
            'send_key': self.sendKeyEdit.text().strip(),
            'channels': [
                channel_id for channel_id, checkbox in self.channelChecks.items()
                if checkbox.isChecked()
            ],
            'events': {
                event_key: checkbox.isChecked()
                for event_key, checkbox in self.eventChecks.items()
            },
        }

    def _channel_toggled(self, checkbox, checked):
        selected_count = sum(
            item.isChecked() for item in self.channelChecks.values()
        )
        message = ''
        if checked and selected_count > MAX_SERVERCHAN_CHANNELS:
            checkbox.blockSignals(True)
            checkbox.setChecked(False)
            checkbox.blockSignals(False)
            message = f'最多选择 {MAX_SERVERCHAN_CHANNELS} 个推送通道。'
        elif not checked and selected_count == 0:
            checkbox.blockSignals(True)
            checkbox.setChecked(True)
            checkbox.blockSignals(False)
            message = '至少选择一个推送通道。'
        self._emit_notification_settings()
        if message:
            self.notificationStatusLabel.setText(message)

    def _emit_notification_settings(self, *_args):
        self._refresh_notification_status()
        self.notificationChanged.emit(self.notification_settings())

    def _refresh_notification_status(self):
        settings = self.notification_settings()
        valid = valid_send_key(settings['send_key']) and bool(settings['channels'])
        self.testNotificationBtn.setEnabled(valid and not self._notification_test_running)
        if not settings['enabled']:
            self.notificationStatusLabel.setText('通知默认关闭；测试按钮不受总开关限制。')
        elif not valid_send_key(settings['send_key']):
            self.notificationStatusLabel.setText('请填写有效的 SCT SendKey。')
        else:
            self.notificationStatusLabel.setText('通知配置有效。')

    def set_notification_test_state(self, running, message=''):
        self._notification_test_running = bool(running)
        self.testNotificationBtn.setEnabled(
            not running and valid_send_key(self.sendKeyEdit.text().strip())
            and any(item.isChecked() for item in self.channelChecks.values())
        )
        if message:
            self.notificationStatusLabel.setText(message)


def get_worker_registry():
    #PyAutoGUI 导入时会设置进程 DPI 模式，因此必须等 QApplication 先完成 Qt 的 DPI 初始化。
    from src.workers import get_registry
    return get_registry()


# pyinstaller -D --windowed -i resource/main.ico -n Magia_Exedra_auto main.py
#这个是导出用的


class LanguageSwitcherWidget(QWidget):
    #语言由用户选择，分辨率按游戏客户区自动匹配；最终切换根目录 aim junction。
    switched = Signal(str, str)  #消息、日志等级
    scaleFinished = Signal()
    scalingChanged = Signal(bool)
    def __init__(self, busy_check=None):
        super().__init__()
        self.busy_check = busy_check or (lambda: False)
        self.langCombo = QComboBox()
        self.langCombo.setMinimumWidth(150)
        self.statusLabel = QLabel('正在检测模板...')
        self.statusLabel.setWordWrap(True)
        self.statusLabel.setObjectName('secondaryText')
        self.refreshBtn = QPushButton('刷新列表')
        self.refreshBtn.clicked.connect(self._refresh_clicked)
        #activated 只响应用户选择；程序刷新下拉框不会误切换语言。
        self.langCombo.activated.connect(self._on_lang_activated)
        self.scaleFinished.connect(self._scale_finished)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel('游戏语言'))
        row.addWidget(self.langCombo)
        row.addStretch(1)
        row.addWidget(self.refreshBtn)
        self.actionRow = row
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(row)
        layout.addWidget(self.statusLabel)
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
        selected_lang = language_switcher.preferred_language() or lang

        self.langCombo.blockSignals(True)
        self.langCombo.clear()
        for lg in sorted(self.packs.keys()):
            self.langCombo.addItem(self._lang_label(lg), lg)
        if selected_lang:
            idx = self.langCombo.findData(selected_lang)
            if idx >= 0:
                self.langCombo.setCurrentIndex(idx)
        self.langCombo.blockSignals(False)

        self._update_status(selected_lang, res, msg)

    def _refresh_clicked(self):
        self.refresh_packs()

    def refresh_packs(self):
        """重新扫描模板，并在后台增量生成派生分辨率。"""
        if self.busy_check():
            self.switched.emit('挂机运行中，不能刷新或切换模板。', 'WARNING')
            return False
        #启动和手动刷新共用这条路径，确保全新安装也会生成空的派生模板目录。
        self._refresh()
        return self._scale_async()

    def _scale_async(self):
        #后台跑素材缩放，不阻塞界面；已有目标会跳过，重复点也不会并发
        if self._scaling:
            return False
        self._scaling = True
        self._scale_cancel.clear()
        self.refreshBtn.setEnabled(False)
        self.langCombo.setEnabled(False)
        self.scalingChanged.emit(True)
        def _work():
            try:
                summary = image_scaler.scale_all(
                    progress_cb=lambda s: self.switched.emit(s, 'INFO'),
                    is_cancelled=self._scale_cancel.is_set,
                )
                if summary:
                    self.switched.emit(summary, self._scale_summary_level(summary))
            except Exception as e:
                self.switched.emit(f'素材缩放出错: {e}', 'ERROR')
            finally:
                self.scaleFinished.emit()
        self._scale_thread = threading.Thread(target=_work, daemon=True)
        self._scale_thread.start()
        return True

    @staticmethod
    def _scale_summary_level(summary):
        text = str(summary)
        if any(marker in text for marker in (
                '失败 ', '缩放出错', '无法确认 ImageMagick',
                '没找到 ImageMagick', 'language/ 不存在', '没有安全可用')):
            return 'ERROR'
        if any(marker in text for marker in ('损坏', '清理失败', '扫描不完整', '不安全', '已取消')):
            return 'WARNING'
        return 'INFO'

    def _scale_finished(self):
        self._scaling = False
        self._scale_thread = None
        self.refreshBtn.setEnabled(True)
        self.langCombo.setEnabled(True)
        self._refresh()
        self.auto_select_resolution(allow_fallback=True, announce=False)
        self.scalingChanged.emit(False)

    def _update_status(self, lang, _res, msg):
        cur = language_switcher.current_selection()
        if cur:
            base = f'当前模板：{self._lang_label(cur[0])} · {cur[1]}'
        else:
            base = '当前无激活模板'
        detail = self._localize(msg, lang)
        self.statusLabel.setText(f'{base}\n{detail}' if detail else base)

    def _localize(self, msg, lang):
        #把消息里出现的语言代码换成中文名，仅用于显示
        if not msg or not lang:
            return msg
        label = self._lang_label(lang)
        return msg.replace(lang + ' ', label + ' ').replace(lang + '/', label + '/')

    def _on_lang_activated(self, _idx):
        #游戏已运行时直接自动匹配；否则沿用当前分辨率，启动挂机前会重新检测。
        lang = self.langCombo.currentData()
        if not language_switcher.remember_language(lang):
            text = '保存游戏语言失败，请检查 language/active.json 是否可写。'
            self.statusLabel.setText(text)
            self.switched.emit(text, 'ERROR')
            return
        self.auto_select_resolution(allow_fallback=True)

    def auto_select_resolution(self, detected=None, allow_fallback=False, announce=True):
        if self.busy_check():
            text = '挂机运行中，不能切换模板。'
            self._refresh()
            if announce:
                self.switched.emit(text, 'WARNING')
            return False, text
        lang = self.langCombo.currentData()
        if not lang:
            text = '没有可用的语言模板。'
            self.statusLabel.setText(text)
            if announce:
                self.switched.emit(text, 'ERROR')
            return False, text

        if detected is None:
            from src.click import click_behavior
            detected = click_behavior.get_client_size('MadokaExedra')
        res = language_switcher.match_client_resolution(lang, detected) if detected else None
        fallback_used = False
        if res is None and allow_fallback and detected is None:
            current = language_switcher.current_selection()
            current_res = current[1] if current else None
            usable = [item_res for item_res, ok in language_switcher.list_packs().get(lang, ()) if ok]
            if current_res in usable:
                res = current_res
            elif image_scaler.SOURCE_RES in usable:
                res = image_scaler.SOURCE_RES
            elif usable:
                res = usable[0]
            fallback_used = res is not None
        if res is None:
            if detected:
                supported = '、'.join(
                    item_res for item_res, ok in language_switcher.list_packs().get(lang, ()) if ok
                ) or '无'
                text = (f'游戏客户区 {detected[0]}x{detected[1]} 无法匹配可用模板。'
                        f'当前语言支持：{supported}')
            else:
                text = '未检测到游戏窗口；启动游戏后会自动选择模板分辨率。'
            self.statusLabel.setText(text)
            if announce:
                self.switched.emit(text, 'WARNING')
            return False, text

        ok, msg = language_switcher.switch(lang, res)
        out = self._localize(msg, lang)
        if ok:
            self._refresh()
            if fallback_used:
                out = (f'已切换到{self._lang_label(lang)}；暂用 {res} 模板。'
                       '启动挂机时会按游戏窗口重新检测分辨率。')
            elif detected:
                out = (f'已自动匹配 {self._lang_label(lang)} {res} 模板'
                       f'（游戏客户区 {detected[0]}x{detected[1]}）。')
            self.statusLabel.setText(out)
        else:
            self._update_status(lang, res, out)
        if announce:
            self.switched.emit(out, 'INFO' if ok else 'ERROR')
        return ok, out


class mywindow(QWidget):
    #GUI 入口。遍历 workers 的 REGISTRY 自动生成脚本选项和各自的参数页，
    #新增挂机模式只需在 workers/ 里写一个文件并 @register，不用改这里的 GUI 代码。
    updateChecked = Signal(str, object)
    updateProgress = Signal(str, int, int)
    updateReady = Signal(str, object)
    updateFailed = Signal(str, str)
    notificationTested = Signal(bool, str)
    debugLog = Signal(str, str, str, str)
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
        self._initial_layout_sized = False
        self._startup_update_check_pending = True
        self._startup_template_refresh_pending = False
        self._log_scroll_pending = False
        self._gui_log_folder = ConsecutiveLogFolder()
        self._notification_manager = NotificationManager(load_notification_settings())

        #启动时确保 aim 联接可用（aim 被移走时按 config 或第一个可用 pack 自动恢复）
        language_switcher.ensure_active()

        self.setWindowTitle('Magia Exedra 自动挂机')
        self.setObjectName('mainWindow')
        #图标
        self.setWindowIcon(QIcon('./resource/main.ico'))
        self.setMinimumSize(500, 640)
        self._apply_style()

        self.textedit_1 = QPlainTextEdit()
        self.textedit_1.setReadOnly(True)
        self.textedit_1.setMinimumHeight(150)
        self.textedit_1.setPlaceholderText('运行消息会显示在这里')
        #GUI 只保留最近日志；完整历史仍由 logs/ 下的滚动文件负责。
        self.textedit_1.document().setMaximumBlockCount(GUI_LOG_MAX_LINES)
        self.debugLog.connect(self._append_logging_record)
        initial_log_level = load_log_level()
        self._gui_log_handler = GuiLogHandler(self.debugLog.emit)
        self._gui_log_handler.setLevel(getattr(logging, initial_log_level))
        self._gui_log_handler.setFormatter(logging.Formatter('%(message)s'))
        logging.getLogger().addHandler(self._gui_log_handler)
        set_file_log_level(initial_log_level)

        #遍历注册表，为每个挂机模式创建 worker 和参数页；下拉选择后只显示当前脚本的参数。
        self._entries = []
        for meta in get_worker_registry():
            self._entries.append(self._build_worker_entry(meta))

        self.scriptTitle = QLabel('挂机模式')
        self.scriptCombo = QComboBox()
        self.paramStack = CurrentPageStack()
        self.paramStack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        for entry in self._entries:
            self.scriptCombo.addItem(entry['meta'].label, entry['meta'].name)
            self.paramStack.addWidget(entry['param_widget'])
        remembered_mode = load_automation_mode()
        remembered_index = self.scriptCombo.findData(remembered_mode)
        if remembered_index >= 0:
            self.scriptCombo.setCurrentIndex(remembered_index)
        self.scriptCombo.currentIndexChanged.connect(self._script_changed)

        self.startButton = QPushButton()
        self.startButton.clicked.connect(self._start_selected_worker)
        self._script_changed(self.scriptCombo.currentIndex())

        #停止按钮，按下启动停止进程，会调用所有工作线程的 stop()
        self.button_1 = QPushButton('停止挂机')
        self.button_1.setObjectName('stopButton')
        self.button_1.clicked.connect(self._stop_automation)
        self.startButton.setObjectName('startButton')

        #应用级选项集中放进设置对话框，主界面只保留一个入口。
        from src.update.update_check import VERSION, is_prerelease_version
        self.settingsDialog = SettingsDialog(
            initial_log_level, load_log_retention_days(),
            is_prerelease_version(VERSION), load_notification_settings(), self,
        )
        self.logLevelCombo = self.settingsDialog.logLevelCombo
        self.betaCheckBox = self.settingsDialog.betaCheckBox
        self.checkUpdateBtn = self.settingsDialog.checkUpdateBtn
        self.cleanLogsBtn = self.settingsDialog.cleanLogsBtn
        self.retentionSpin = self.settingsDialog.retentionSpin
        self.settingsButton = QPushButton('设置')
        self.settingsButton.setFixedWidth(90)
        self.settingsButton.clicked.connect(self._open_settings)
        self.checkUpdateBtn.clicked.connect(self._check_update_from_settings)
        self.cleanLogsBtn.clicked.connect(self._cleanup_old_logs)
        self.logLevelCombo.currentTextChanged.connect(self._change_log_level)
        self.retentionSpin.valueChanged.connect(self._change_log_retention_days)
        self.settingsDialog.notificationChanged.connect(
            self._notification_settings_changed
        )
        self.settingsDialog.testNotificationBtn.clicked.connect(
            self._send_test_notification
        )
        self.notificationTested.connect(self._on_notification_tested)
        self.updateChecked.connect(self._on_update_checked)
        self.updateProgress.connect(self._on_update_progress)
        self.updateReady.connect(self._on_update_ready)
        self.updateFailed.connect(self._on_update_failed)

        #语言由用户选择，分辨率按游戏客户区自动选择。
        self.lang_switcher = LanguageSwitcherWidget(self._automation_running)
        self.lang_switcher.switched.connect(
            lambda text, level: self._append_log(text, level=level, source='模板')
        )
        self.lang_switcher.switched.connect(
            lambda _text, _level: self.setWindowIcon(QIcon('./resource/main.ico'))
        )
        self.lang_switcher.scalingChanged.connect(self._scaling_changed)
        self.lang_switcher.actionRow.addWidget(self.settingsButton)

        self.mainlayout = QVBoxLayout()
        self.mainlayout.setContentsMargins(18, 16, 18, 16)
        self.mainlayout.setSpacing(12)

        run_group = QGroupBox('运行设置')
        run_layout = QVBoxLayout()
        run_layout.setSpacing(8)
        run_layout.addWidget(self.scriptTitle)
        run_layout.addWidget(self.scriptCombo)
        run_layout.addWidget(self.paramStack)
        action_row = QHBoxLayout()
        action_row.addWidget(self.startButton, 2)
        action_row.addWidget(self.button_1, 1)
        run_layout.addLayout(action_row)
        run_group.setLayout(run_layout)
        self.mainlayout.addWidget(run_group)

        template_group = QGroupBox('模板设置')
        template_layout = QVBoxLayout()
        template_layout.addWidget(self.lang_switcher)
        template_group.setLayout(template_layout)
        self.mainlayout.addWidget(template_group)

        log_group = QGroupBox('运行日志')
        log_layout = QVBoxLayout()
        log_layout.addWidget(self.textedit_1)
        log_group.setLayout(log_layout)
        self.mainlayout.addWidget(log_group, 1)

        self.setLayout(self.mainlayout)
        self.mainlayout.activate()
        self.resize(560, 820)

        #先完成自动更新检查；没有进入更新安装时，再增量生成派生模板并检测游戏。
        self._check_update_async()

    def _apply_style(self):
        self.setStyleSheet('''
            QWidget {
                color: #20242a;
                font-family: "Microsoft YaHei UI";
                font-size: 13px;
            }
            QWidget#mainWindow { background: #f4f6f8; }
            QDialog#settingsDialog { background: #f4f6f8; }
            QLabel#secondaryText { color: #5d6673; }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #d9dee5;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 5px;
                color: #343a43;
                background: #f4f6f8;
                font-weight: 600;
            }
            QComboBox, QLineEdit {
                min-height: 32px;
                background: #ffffff;
                border: 1px solid #c9d0d9;
                border-radius: 4px;
                padding: 0 8px;
            }
            QComboBox:focus, QLineEdit:focus { border-color: #2474c6; }
            QPushButton {
                min-height: 32px;
                background: #ffffff;
                border: 1px solid #bcc5d0;
                border-radius: 4px;
                padding: 0 12px;
            }
            QPushButton:hover { background: #eef2f6; }
            QPushButton:disabled { color: #939ba6; background: #eceff2; }
            QPushButton#startButton {
                background: #1769aa;
                color: #ffffff;
                border-color: #1769aa;
                font-weight: 600;
            }
            QPushButton#startButton:hover { background: #12598f; }
            QPushButton#stopButton {
                color: #b42318;
                border-color: #d9a5a0;
            }
            QPushButton#stopButton:hover { background: #fff1f0; }
            QPlainTextEdit {
                background: #171a1f;
                color: #e7ebf0;
                border: 1px solid #2a3038;
                border-radius: 4px;
                padding: 8px;
                font-family: Consolas, "Microsoft YaHei UI";
            }
            QRadioButton { spacing: 6px; min-height: 26px; }
            QCheckBox { spacing: 7px; }
        ''')

    def _build_worker_entry(self, meta):
        #为一个挂机模式创建 worker 和独立参数页，返回 entry 字典
        worker = meta.worker_class()
        worker.signal.connect(self._append_log)
        worker.logSignal.connect(self._append_log)
        worker.majorEvent.connect(
            lambda event_key, reason, params, mode=meta.name:
            self._notify_major_event(event_key, mode, reason, params)
        )
        display_name = meta.name.replace('_', ' ')
        worker.finished.connect(lambda n=display_name: logger.info('%s挂机结束', n))
        worker.finished.connect(lambda n=display_name: self._append_log(f'{n}挂机结束或被主动停止\n'))
        worker.finished.connect(self._automation_finished)

        #参数控件区
        param_layout = QVBoxLayout()
        param_layout.setContentsMargins(0, 0, 0, 0)
        param_layout.setSpacing(8)
        getters = {}
        settings_getters = {}
        controls = []
        change_connectors = []
        saved_params = load_worker_params(meta.name)
        for spec in meta.params:
            initial_value = spec.normalize(saved_params.get(spec.key, spec.default))
            sub_layout, getter, settings_getter, sub_controls, connect_change = \
                self._build_param_widget(spec, initial_value)
            param_layout.addLayout(sub_layout)
            getters[spec.key] = getter
            settings_getters[spec.key] = settings_getter
            controls.extend(sub_controls)
            change_connectors.append(connect_change)

        param_widget = QWidget()
        if not meta.params:
            param_layout.addWidget(QLabel('该脚本没有可配置参数'))
        param_widget.setLayout(param_layout)
        entry = {
            'meta': meta,
            'worker': worker,
            'param_widget': param_widget,
            'getters': getters,
            'settings_getters': settings_getters,
            'controls': controls,
        }
        for connect_change in change_connectors:
            connect_change(lambda e=entry: self._save_worker_params(e))
        return entry

    def _save_worker_params(self, entry):
        try:
            params = {
                key: getter() for key, getter in entry['settings_getters'].items()
            }
        except (TypeError, ValueError):
            return
        if not save_worker_params(entry['meta'].name, params):
            logger.warning('保存 %s 挂机参数失败', entry['meta'].name)

    def _script_changed(self, index):
        if not 0 <= index < len(self._entries):
            self.startButton.setText('没有可用的挂机脚本')
            self.startButton.setEnabled(False)
            return
        self.paramStack.setCurrentIndex(index)
        current_page = self.paramStack.currentWidget()
        if current_page is not None:
            current_page.updateGeometry()
        self.paramStack.updateGeometry()
        self.startButton.setText('启动挂机')
        self.startButton.setToolTip(self._entries[index]['meta'].label)
        if not save_automation_mode(self._entries[index]['meta'].name):
            logger.warning('保存挂机模式失败: %s', self._entries[index]['meta'].name)

    def _start_selected_worker(self):
        index = self.scriptCombo.currentIndex()
        if 0 <= index < len(self._entries):
            self._start_worker(self._entries[index])

    def _open_settings(self):
        self.settingsDialog.exec()

    def _check_update_from_settings(self):
        self.settingsDialog.accept()
        self._check_update()

    def _check_update(self):
        self._check_update_async(manual=True)

    def _notification_settings_changed(self, settings):
        self._notification_manager.configure(settings)
        if not save_notification_settings(settings):
            logger.warning('保存通知设置失败')

    def _send_test_notification(self):
        settings = self.settingsDialog.notification_settings()
        self._notification_manager.configure(settings)
        self.settingsDialog.set_notification_test_state(True, '正在发送测试通知...')
        self._notification_manager.send_test(
            self._emit_notification_test_result
        )

    def _emit_notification_test_result(self, success, message):
        try:
            self.notificationTested.emit(success, message)
        except RuntimeError:
            pass

    def _on_notification_tested(self, success, message):
        if self._closing:
            return
        self.settingsDialog.set_notification_test_state(False, message)
        self._append_log(
            message,
            level='INFO' if success else 'WARNING',
            source='通知',
        )

    def _notify_major_event(self, event_key, mode, reason, params=None):
        self._notification_manager.notify(event_key, mode, reason, params)

    def _check_update_async(self, manual=False):
        #后台线程查 GitHub 最新发布版本，避免阻塞界面；同时只允许一个检查在跑
        if self._update_state != 'idle' or self._closing:
            return
        self._update_cancel.clear()
        job_id = uuid.uuid4().hex
        self._update_job_id = job_id
        self._update_state = 'checking'
        self._update_manual = manual
        self._refresh_control_state()
        channel = 'beta' if self.betaCheckBox.isChecked() else 'stable'
        self._append_log(
            '正在检查更新...' + ('（含 beta）' if channel == 'beta' else ''),
            source='更新',
        )
        def _work():
            try:
                from src.update.update_check import check_for_update
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
            self._append_log(str(r), level='ERROR', source='更新')
            _notify_if_available(
                self, 'update_failed', '应用更新', '更新检查返回了无效结果。'
            )
            self._continue_startup_after_update()
            return
        message = r.get('message', '')
        error_prefixes = ('查询更新失败：', '检查更新出错：', '本地版本号无法解析：')
        level = 'ERROR' if message.startswith(error_prefixes) else 'INFO'
        self._append_log(message, level=level, source='更新')
        if level == 'ERROR':
            _notify_if_available(
                self, 'update_failed', '应用更新', message or '更新检查失败。'
            )
        if r.get('has_update'):
            self._offer_update(r)
        self._continue_startup_after_update()

    def _local_version_disp(self):
        from src.update.update_check import VERSION
        return VERSION if VERSION[:1] in ('v', 'V') else f'v{VERSION}'

    def _offer_update(self, r):
        #有新版本时：打包版弹对话框询问是否更新；源码模式回退为打开 Release 页
        from src.update.update_check import is_frozen
        tag = r.get('latest_tag', '')
        url = r.get('url') or r.get('asset_url') or 'https://github.com/LUODIAN-233/Magia_Exedra_auto/releases'
        if not is_frozen():
            if self._update_manual:
                self._append_log(
                    '当前为源码运行模式，已打开 Release 页面，请手动更新或 git pull。',
                    source='更新',
                )
                webbrowser.open(url)
            else:
                self._append_log(
                    f'当前为源码运行模式，请前往 {url} 手动更新或 git pull。',
                    source='更新',
                )
            return
        asset_url = r.get('asset_url')
        if not asset_url or not r.get('asset_sha256'):
            self._append_log(
                'Release 未提供唯一且带 SHA-256 的更新 ZIP，已禁用自动安装。',
                level='ERROR', source='更新',
            )
            _notify_if_available(
                self, 'update_failed', '应用更新',
                'Release 未提供唯一且带 SHA-256 的更新 ZIP。',
            )
            if self._update_manual:
                webbrowser.open(url)
            return
        if self._automation_running():
            self._append_log(
                '挂机或素材缩放正在运行，请停止后再开始更新。',
                level='WARNING', source='更新',
            )
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
                self._append_log(f'无法开始更新：{e}', level='ERROR', source='更新')
                _notify_if_available(
                    self, 'update_failed', '应用更新', '无法开始准备更新。'
                )
                self._reset_update_state(cleanup=True)

    def _start_download(self, r):
        from src.update.update_check import (download_asset, extract_update, UpdateCancelled,
                                             acquire_update_lock)
        if self._update_state != 'idle' or self._automation_running() or self._closing:
            self._append_log('当前有其它任务运行，不能开始更新。', level='WARNING', source='更新')
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
        self._append_log('更新包已通过校验，正在安全停止后台任务并准备安装...', source='更新')
        self.close()

    def _on_update_failed(self, job_id, msg):
        if self._closing or job_id != self._update_job_id:
            return
        self._update_prepare_thread = None
        if hasattr(self, '_progress'):
            self._progress.close()
        cancelled = '取消' in msg
        self._append_log(
            msg if cancelled else f'更新失败：{msg}',
            level='WARNING' if cancelled else 'ERROR', source='更新',
        )
        if not cancelled:
            _notify_if_available(
                self, 'update_failed', '应用更新', msg or '更新准备失败。'
            )
        self._reset_update_state(cleanup=False)
        self._continue_startup_after_update()

    def _on_update_cancel(self):
        if self._update_state not in ('downloading', 'extracting'):
            return
        self._update_cancel.set()
        self._progress.setLabelText('正在取消更新并清理临时文件...')
        self._progress.setCancelButton(None)

    def _apply_update(self, payload):
        #写批处理：等本进程退出后 robocopy 覆盖安装目录并重启；然后退出
        from src.update.update_check import write_update_bat
        exe_path = sys.executable
        bat_path = write_update_bat(
            exe_path, payload['src_dir'], os.getpid(), payload['job_dir'], self._update_lock_path,
            self._update_job_id,
        )
        self._append_log('更新已准备就绪，程序即将退出完成安装。', source='更新')
        subprocess.Popen(['cmd', '/c', bat_path],
                         creationflags=subprocess.CREATE_NO_WINDOW,
                         close_fds=True)

    def _reset_update_state(self, cleanup=True):
        from src.update.update_check import release_update_lock
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

    def _append_gui_lines(self, timestamp, level, source, text):
        #异常堆栈和其它多行消息也逐行带上完整前缀，便于筛选和复制排查。
        lines = str(text).splitlines() or ['']
        for line in lines:
            replace, rendered = self._gui_log_folder.render(
                timestamp, level, source, line,
            )
            if replace:
                self._replace_last_gui_line(rendered)
            else:
                self.textedit_1.appendPlainText(rendered)
        scrollbar = self.textedit_1.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        if not self._log_scroll_pending:
            self._log_scroll_pending = True
            QTimer.singleShot(0, self._scroll_log_to_bottom)

    def _replace_last_gui_line(self, rendered):
        block = self.textedit_1.document().lastBlock()
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cursor.insertText(rendered)

    def _scroll_log_to_bottom(self):
        self._log_scroll_pending = False
        try:
            scrollbar = self.textedit_1.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        except RuntimeError:
            pass  #窗口已经销毁

    def _append_log(self, text, level='INFO', source='运行'):
        level_name = str(level).strip().upper()
        level_value = getattr(logging, level_name, logging.INFO)
        message = str(text)
        self._append_gui_lines(
            datetime.now().strftime('%H:%M:%S'),
            logging.getLevelName(level_value), source, message,
        )
        #运行消息在 GUI 中始终可见，同时按所选等级进入文件；额外标记防止 GUI handler 重复显示。
        runtime_logger.log(
            level_value, message,
            extra={'_magia_gui_displayed': True, 'gui_source': source},
        )

    def _append_logging_record(self, timestamp, level, source, text):
        self._append_gui_lines(timestamp, level, source, text)

    def _change_log_level(self, level):
        self._gui_log_handler.setLevel(getattr(logging, level))
        file_enabled = set_file_log_level(level)
        if save_log_level(level):
            target = 'GUI 调试记录和日志文件' if file_enabled else 'GUI 调试记录'
            self._append_log(f'日志等级已切换并记忆为 {level}，已应用到{target}；挂机运行消息始终显示。')
        else:
            self._append_log(
                f'日志等级已切换为 {level}，但保存失败；下次启动将使用原设置。',
                level='WARNING', source='日志',
            )

    def _cleanup_old_logs(self):
        retention_days = self.retentionSpin.value()
        reply = QMessageBox.question(
            self, '清理过时日志',
            f'将删除超过 {retention_days} 天的 Magia 日志，当前会话日志会保留。\n\n是否继续？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        result = cleanup_old_logs(retention_days)
        removed_count = len(result['removed'])
        failed_count = len(result['failed'])
        if failed_count:
            message = f'已清理 {removed_count} 个过时日志，另有 {failed_count} 个文件无法删除。'
            QMessageBox.warning(self, '日志清理未完全完成', message)
            self._append_log(message, level='WARNING', source='日志')
        elif removed_count:
            message = f'已清理 {removed_count} 个过时日志，当前会话日志已保留。'
            QMessageBox.information(self, '日志清理完成', message)
            self._append_log(message, source='日志')
        else:
            message = '没有需要清理的过时日志，当前会话日志已保留。'
            QMessageBox.information(self, '日志清理完成', message)
            self._append_log(message, source='日志')

    def _change_log_retention_days(self, days):
        if save_log_retention_days(days):
            self._append_log(
                f'日志保留天数已设为 {days} 天；下次启动时自动清理过期日志。',
                source='日志',
            )
        else:
            self._append_log(
                f'日志保留天数已改为 {days} 天，但保存失败。',
                level='WARNING', source='日志',
            )

    def _build_param_widget(self, spec, initial_value=None):
        #返回布局、Worker getter、持久化 getter、可禁用控件和变更信号连接器。
        initial_value = spec.normalize(
            spec.default if initial_value is None else initial_value
        )
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        controls = []
        if spec.kind != 'bool':
            label = QLabel(spec.label)
            layout.addWidget(label)
            controls.append(label)

        if spec.kind == 'choice':
            #单选按钮组，每 4 个一行
            group = QButtonGroup(self)
            group.setExclusive(True)
            buttons = []
            for val in spec.choices:
                btn = QRadioButton(str(val))
                if val == initial_value:
                    btn.setChecked(True)
                group.addButton(btn)
                buttons.append(btn)
            row = QHBoxLayout()
            for i, btn in enumerate(buttons):
                row.addWidget(btn)
                if (i + 1) % 4 == 0:
                    layout.addLayout(row)
                    row = QHBoxLayout()
            if row.count() > 0:
                layout.addLayout(row)
            choice_pairs = list(zip(buttons, spec.choices))
            def getter():
                for btn, val in choice_pairs:
                    if btn.isChecked():
                        return val
                return initial_value
            settings_getter = getter
            def connect_change(callback):
                group.buttonToggled.connect(
                    lambda _button, checked: callback() if checked else None
                )
            controls.extend(buttons)

        elif spec.kind == 'ordered_multi_choice':
            selected = list(initial_value)
            values = selected + [value for value in spec.choices if value not in selected]
            choice_list = QListWidget()
            choice_list.setMaximumHeight(170)
            for value in values:
                item = QListWidgetItem(f'LV{value}')
                item.setData(Qt.UserRole, value)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if value in selected else Qt.Unchecked)
                choice_list.addItem(item)
            choice_list.setCurrentRow(0)

            up_button = QPushButton('↑')
            down_button = QPushButton('↓')
            up_button.setToolTip('提高当前等级的优先级')
            down_button.setToolTip('降低当前等级的优先级')
            up_button.setFixedWidth(40)
            down_button.setFixedWidth(40)

            def checked_values():
                return [
                    choice_list.item(index).data(Qt.UserRole)
                    for index in range(choice_list.count())
                    if choice_list.item(index).checkState() == Qt.Checked
                ]

            def keep_one_selected(item):
                if item.checkState() == Qt.Unchecked and not checked_values():
                    choice_list.blockSignals(True)
                    item.setCheckState(Qt.Checked)
                    choice_list.blockSignals(False)
                    return
                row = choice_list.row(item)
                selected_count = len(checked_values())
                target = selected_count - 1 if item.checkState() == Qt.Checked \
                    else choice_list.count() - 1
                if row != target:
                    choice_list.blockSignals(True)
                    moved_item = choice_list.takeItem(row)
                    choice_list.insertItem(target, moved_item)
                    choice_list.setCurrentItem(moved_item)
                    choice_list.blockSignals(False)

            def move_current(delta):
                row = choice_list.currentRow()
                target = row + delta
                item = choice_list.item(row) if row >= 0 else None
                if item is None or item.checkState() != Qt.Checked \
                        or not 0 <= target < len(checked_values()):
                    return
                moved_item = choice_list.takeItem(row)
                choice_list.insertItem(target, moved_item)
                choice_list.setCurrentItem(moved_item)

            choice_list.itemChanged.connect(keep_one_selected)
            up_button.clicked.connect(lambda: move_current(-1))
            down_button.clicked.connect(lambda: move_current(1))
            layout.addWidget(choice_list)
            button_row = QHBoxLayout()
            button_row.addStretch(1)
            button_row.addWidget(up_button)
            button_row.addWidget(down_button)
            layout.addLayout(button_row)

            def getter():
                values = checked_values()
                if not values:
                    raise ValueError(f'{spec.label} 至少选择一个等级。')
                return values
            settings_getter = getter
            def connect_change(callback):
                choice_list.itemChanged.connect(lambda _item: callback())
                up_button.clicked.connect(callback)
                down_button.clicked.connect(callback)
            controls.extend([choice_list, up_button, down_button])

        elif spec.kind == 'bool':
            checkbox = QCheckBox(spec.label)
            checkbox.setChecked(initial_value)
            if spec.hint:
                checkbox.setToolTip(spec.hint)
            layout.addWidget(checkbox)
            def getter():
                return checkbox.isChecked()
            settings_getter = getter
            def connect_change(callback):
                checkbox.toggled.connect(lambda _checked: callback())
            controls.append(checkbox)

        elif spec.kind == 'lp_recover':
            #喝体力药次数：最小/-1/输入/+1/最大 五件套；显示的是"喝几次"，传给 worker 时 +1
            min_btn, minus_btn, input_edit, plus_btn, max_btn = self.create_lp_recover_input(
                min_num=spec.min, max_num=spec.max, default_num=initial_value,
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
            def settings_getter():
                text = input_edit.text()
                if not input_edit.hasAcceptableInput() or text == '':
                    raise ValueError
                return int(text)
            def connect_change(callback):
                for button in (min_btn, minus_btn, plus_btn, max_btn):
                    button.clicked.connect(callback)
                input_edit.editingFinished.connect(callback)
            controls.extend([min_btn, minus_btn, input_edit, plus_btn, max_btn])

        elif spec.kind == 'int':
            input_edit = QLineEdit(str(initial_value))
            input_edit.setValidator(QIntValidator(spec.min, spec.max, self))
            input_edit.setAlignment(Qt.AlignCenter)
            layout.addWidget(input_edit)
            lo, hi = spec.min, spec.max
            def getter():
                text = input_edit.text()
                if not input_edit.hasAcceptableInput() or text == '':
                    raise ValueError(f'{spec.label} 输入无效，请输入 {lo} 到 {hi} 的整数。')
                return int(text)
            settings_getter = getter
            def connect_change(callback):
                input_edit.editingFinished.connect(callback)
            controls.append(input_edit)

        else:
            raise ValueError(f'不支持的参数控件类型: {spec.kind}')

        if spec.hint and spec.kind != 'bool':
            hint = QLabel(spec.hint)
            hint.setObjectName('secondaryText')
            hint.setWordWrap(True)
            layout.addWidget(hint)
            controls.append(hint)

        return layout, getter, settings_getter, controls, connect_change

    def create_lp_recover_input(self, min_num, max_num, default_num):
        #喝药次数的五件套输入控件。值由调用方用 getter 读取，不再需要 change_func 回调。
        default_num = max(min_num, min(max_num, default_num))

        min_btn = QPushButton('最小')
        minus_btn = QPushButton('-1')
        plus_btn = QPushButton('+1')
        max_btn = QPushButton('最大')
        min_btn.setFixedWidth(56)
        minus_btn.setFixedWidth(40)
        plus_btn.setFixedWidth(40)
        max_btn.setFixedWidth(56)
        value_input = QLineEdit(str(default_num))
        value_input.setValidator(QIntValidator(min_num, max_num, self))
        value_input.setAlignment(Qt.AlignCenter)
        value_input.setFixedWidth(52)

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

    def _continue_startup_after_update(self):
        #启动缩放必须让自动更新优先；接受更新后保持等待，失败或取消才继续。
        if not self._startup_update_check_pending or self._closing \
                or self._update_state != 'idle':
            return
        self._startup_update_check_pending = False
        QTimer.singleShot(0, self._refresh_templates_at_startup)

    def _refresh_templates_at_startup(self):
        if self._closing:
            return
        self._startup_template_refresh_pending = True
        if not self.lang_switcher.refresh_packs():
            self._startup_template_refresh_pending = False
            self._detect_game_at_startup()
            self._refresh_control_state()

    def _detect_game_at_startup(self):
        if self._closing:
            return
        from src.click import click_behavior
        detected = click_behavior.get_client_size('MadokaExedra')
        if detected is None:
            lang = self.lang_switcher.langCombo.currentData()
            label = self.lang_switcher._lang_label(lang) if lang else '未选择'
            text = f'未检测到游戏运行。已记忆游戏语言：{label}。'
            self.lang_switcher.statusLabel.setText(text)
            self._append_log(text, level='WARNING')
            return
        ok, text = self.lang_switcher.auto_select_resolution(
            detected=detected, announce=False,
        )
        self._append_log(text, level='INFO' if ok else 'ERROR')
        if not ok:
            self._append_log(
                '已检测到游戏，但无法自动选择匹配的模板分辨率。',
                level='ERROR',
            )

    def showEvent(self, event):
        super().showEvent(event)
        if not self._initial_layout_sized:
            self._initial_layout_sized = True
            QTimer.singleShot(0, self._resize_to_layout_hint)

    def _resize_to_layout_hint(self):
        self.mainlayout.invalidate()
        self.mainlayout.activate()
        hint = self.sizeHint()
        self.resize(max(self.width(), 560, hint.width()), max(self.height(), 760, hint.height()))

    def _refresh_control_state(self):
        if not hasattr(self, 'checkUpdateBtn'):
            return
        automation_busy = self._automation_running()
        update_busy = self._update_busy()
        startup_busy = self._startup_update_check_pending
        controls_enabled = not automation_busy and not update_busy \
            and not startup_busy and not self._closing
        self.scriptTitle.setEnabled(controls_enabled)
        self.scriptCombo.setEnabled(controls_enabled)
        self.startButton.setEnabled(controls_enabled and bool(self._entries))
        for entry in self._entries:
            for control in entry['controls']:
                control.setEnabled(controls_enabled)
        self.lang_switcher.setEnabled(controls_enabled)
        checking = self._update_state == 'checking'
        self.settingsButton.setEnabled(not update_busy and not self._closing)
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
            self._append_log('后台任务尚未安全停止，请稍后再关闭窗口。', level='WARNING')
            self._closing = False
            if not update_alive:
                self._update_cancel.clear()
            self._refresh_control_state()
            event.ignore()
            return
        if self._pending_update:
            try:
                self._update_state = 'closing'
                self._apply_update(self._pending_update)
            except Exception as e:
                self._append_log(f'启动更新安装器失败：{e}', level='ERROR', source='更新')
                _notify_if_available(
                    self, 'update_failed', '应用更新', '启动更新安装器失败。'
                )
                self._closing = False
                self._reset_update_state(cleanup=True)
                self._continue_startup_after_update()
                event.ignore()
                return
        else:
            self._reset_update_state(cleanup=True)
        logging.getLogger().removeHandler(self._gui_log_handler)
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
            self._append_log('已有挂机任务运行中，请先停止。', level='WARNING')
            return
        from src.update.update_check import update_recovery_issue
        recovery = update_recovery_issue(os.path.dirname(sys.executable))
        if recovery:
            self._append_log(
                f'检测到上次更新回滚不完整，已禁止挂机。请按文件提示恢复：{recovery}',
                level='CRITICAL', source='更新',
            )
            _notify_if_available(
                self, 'update_recovery_blocked', entry['meta'].name,
                '检测到上次更新未安全完成，已禁止启动挂机。',
            )
            return
        from src.click import click_behavior, click_action, template_confidence
        if click_behavior.find_win('MadokaExedra') is None:
            self._append_log(
                '未找到游戏窗口 MadokaExedra，本次挂机已停止。请先启动游戏。',
                level='WARNING',
            )
            return
        detected = click_behavior.get_client_size('MadokaExedra')
        if detected is None:
            self._append_log('未能读取游戏客户区尺寸，本次挂机已停止。', level='ERROR')
            return
        switched, switch_message = self.lang_switcher.auto_select_resolution(
            detected=detected, announce=False,
        )
        self._append_log(switch_message, level='INFO' if switched else 'ERROR')
        if not switched:
            self._append_log(
                '无法为当前游戏窗口选择安全的模板分辨率，本次挂机未启动。',
                level='ERROR',
            )
            return
        #自动切换后仍复核窗口与模板，避免外部进程同时改变 aim。
        res_info = click_action.detect_window_resolution()
        self._append_log(res_info['message'], level='INFO' if res_info['matched'] else 'ERROR')
        if not res_info['matched']:
            self._append_log(
                '无法确认窗口与模板分辨率一致，为防止坐标误点，本次挂机未启动。',
                level='ERROR',
            )
            return
        selection = language_switcher.current_selection()
        if selection is None:
            self._append_log('当前没有有效的模板 pack，本次挂机未启动。', level='ERROR')
            return
        #先读取参数，动态模板路径才能按当前设置展开后再校验。
        worker = entry['worker']
        try:
            params = {key: getter() for key, getter in entry['getters'].items()}
            notification_params = {
                key: getter() for key, getter in entry['settings_getters'].items()
            }
            required_templates = [
                path.format(**params) for path in entry['meta'].required_templates
            ]
        except (KeyError, TypeError, ValueError) as e:
            self._append_log(str(e), level='ERROR')
            return
        valid, errors = language_switcher.validate_template_groups(
            selection[0], selection[1], required_templates,
        )
        if not valid:
            self._append_log(
                '当前模板 pack 不完整，本次挂机未启动：\n' + '\n'.join(errors[:20]),
                level='ERROR',
            )
            return
        confidence_valid, confidence_errors = template_confidence.validate_pack(
            selection[0], selection[1],
        )
        if not confidence_valid:
            self._append_log(
                '模板置信度配置不完整，本次挂机未启动：\n'
                + '\n'.join(confidence_errors[:20]),
                level='ERROR',
            )
            return
        #注入已校验参数（lp_recover 已在 getter 里由界面值 +1 转为 Worker 内部值）
        for key, value in params.items():
            setattr(worker, key, value)
        worker._notification_params = notification_params
        worker.expected_pack = selection
        if entry['meta'].start_hint:
            self._append_log(entry['meta'].start_hint)
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
        if not scaling and self._startup_template_refresh_pending:
            self._startup_template_refresh_pending = False
            QTimer.singleShot(0, self._detect_game_at_startup)


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
    logger.info('运行路径：%s', folder_path)

    # 如果程序被打包为可执行文件
    if getattr(sys, "frozen", False):
        # 获取可执行文件所在的目录
        BASE_PATH = os.path.dirname(sys.executable)
        logger.info('脚本执行路径：%s', BASE_PATH)
        # 将当前工作目录设置为可执行文件所在的目录
        os.chdir(BASE_PATH)
    else:
        # 如果程序作为脚本运行，使用脚本目录
        BASE_PATH = os.path.dirname(__file__)
        logger.info('脚本执行路径：%s', BASE_PATH)
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

"""A restrained native Swiss-style workspace; media behavior stays in app.py."""
from __future__ import annotations

import bisect
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QListWidget, QSplitter, QFormLayout, QSlider, QProgressBar,
    QPlainTextEdit, QTabWidget, QFrame, QButtonGroup, QScrollArea, QCheckBox)
from .widgets import Collapsible, RangeTimeline, ElidingLabel

COLORS = {'paper': '#f7f8f5', 'panel': '#eef1ed', 'ink': '#19251f',
          'muted': '#66746a', 'line': '#dce2db', 'accent': '#176a51', 'mint': '#d9eee2'}

THEME = """
QWidget { background: #f7f8f5; color: #19251f; font-family: 'Microsoft JhengHei UI'; font-size: 12px; }
QMainWindow { background: #f7f8f5; }
QLabel#Brand { font-family: 'Bahnschrift'; font-size: 21px; font-weight: 600; letter-spacing: 1px; }
QLabel#Eyebrow { font-family: 'Bahnschrift'; color: #66746a; font-size: 10px; font-weight: 600; }
QLabel#Muted { color: #66746a; }
QLabel#Title { font-size: 15px; font-weight: 600; }
QLabel#DurationValue { font-family: 'Bahnschrift'; font-size: 38px; font-weight: 500; }
QLabel#Badge { background: #d9eee2; color: #176a51; border-radius: 4px; padding: 6px; font-family: 'Bahnschrift'; font-weight: 600; }
QWidget#LibraryPanel, QWidget#Inspector { background: #eef1ed; border-radius: 8px; }
QWidget#LibraryPanel QLabel, QWidget#Inspector QLabel, QWidget#Inspector QTabWidget::pane { background: transparent; }
QWidget#PreviewTools { background: transparent; }
QPushButton, QToolButton { background: #f7f8f5; border: 1px solid #d4ddd4; border-radius: 5px; padding: 7px 10px; min-height: 17px; }
QPushButton:hover, QToolButton:hover { background: #e5ece4; border-color: #82998b; }
QPushButton:pressed { background: #d9eee2; }
QPushButton:disabled { color: #9da79f; border-color: #e1e5df; background: #edf0eb; }
QPushButton:focus, QToolButton:focus, QSlider:focus, QComboBox:focus, QLineEdit:focus { border: 2px solid #176a51; }
QPushButton#Primary { background: #176a51; border-color: #176a51; color: #ffffff; font-weight: 600; min-height: 27px; }
QPushButton#Primary:hover { background: #105740; }
QPushButton#Primary:disabled { background: #d7e0d7; border-color: #d7e0d7; color: #748174; }
QPushButton#Quiet, QToolButton#Disclosure { border: 0; background: transparent; color: #516759; }
QPushButton#Chip { padding: 5px 7px; min-height: 16px; border-radius: 4px; }
QPushButton#Chip:checked { background: #d9eee2; color: #176a51; border-color: #82b5a0; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #fafbf8; border: 1px solid #d4ddd4; border-radius: 4px; padding: 5px; min-height: 22px; selection-background-color: #176a51; }
QComboBox QAbstractItemView { background: #fafbf8; selection-background-color: #d9eee2; selection-color: #19251f; }
QListWidget { background: transparent; border: 0; outline: 0; }
QListWidget::item { background: transparent; border: 1px solid transparent; padding: 9px 5px; margin: 3px 0; border-radius: 5px; }
QListWidget::item:selected { background: #d9eee2; color: #153b2b; border: 1px solid #96bea8; }
QListWidget::item:hover { background: #e1e8df; }
QTabWidget::pane { border: 0; top: 4px; }
QTabBar::tab { background: transparent; color: #6d7b70; padding: 10px 10px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #176a51; font-weight: 600; border-bottom-color: #176a51; }
QTabBar::tab:hover { color: #176a51; }
QSlider::groove:horizontal { background: #d1dbd1; height: 4px; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #176a51; height: 4px; border-radius: 2px; }
QSlider::handle:horizontal { background: #176a51; border: 2px solid #ffffff; width: 12px; height: 12px; margin: -5px 0; border-radius: 7px; }
QProgressBar { border: 0; background: #e6ebe3; border-radius: 3px; color: #516759; text-align: center; font-size: 10px; }
QProgressBar::chunk { background: #8cbd9e; border-radius: 3px; }
QPlainTextEdit { background: #eff2ec; color: #536459; border: 1px solid #d4ddd4; border-radius: 4px; font-family: 'Cascadia Mono'; font-size: 11px; }
QSplitter::handle { background: transparent; width: 12px; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 0; }
QScrollBar::handle:vertical { background: #c0cec1; min-height: 26px; border-radius: 3px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolButton#RangeHandle { padding: 0; min-height: 0; color: #ffffff; background: #176a51; border: 1px solid #176a51; border-radius: 3px; font-size: 16px; }
QToolButton#RangeHandle:focus { border: 2px solid #19251f; }
QToolButton#Playhead { padding: 0; min-height: 0; color: #263b2e; background: #ffffff; border: 1px solid #81948a; border-radius: 3px; }
QToolButton#Playhead:focus { border: 2px solid #176a51; }
"""


def _label(text, kind='Muted'):
    widget = QLabel(text)
    widget.setObjectName(kind)
    return widget


def _button(text, function=None, kind=None, tooltip=None):
    widget = QPushButton(text)
    if kind: widget.setObjectName(kind)
    if function: widget.clicked.connect(function)
    widget.setToolTip(tooltip or text)
    widget.setAccessibleName(tooltip or text)
    return widget


def _row(*widgets):
    layout = QHBoxLayout()
    layout.setSpacing(6)
    for widget in widgets: layout.addWidget(widget)
    return layout


def _combo(items):
    widget = QComboBox()
    widget.addItems(items)
    return widget


def _page(tabs, title):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 20, 0, 4)
    layout.setSpacing(14)
    scroll.setWidget(page)
    tabs.addTab(scroll, title)
    return layout


def setup_window(window):
    # Import only at call time: app owns the canvas and delegates construction.
    from .app import CropCanvas
    from . import __version__
    w = window
    w.setStyleSheet(THEME)
    w.resize(1380, 860)
    w.setMinimumSize(1080, 720)
    root = QWidget()
    w.setCentralWidget(root)
    layout = QVBoxLayout(root)
    layout.setContentsMargins(20, 18, 20, 14)
    layout.setSpacing(15)

    header = QHBoxLayout()
    header.setSpacing(12)
    header.addWidget(_label('WS', 'Badge'))
    brand = QVBoxLayout()
    brand.setSpacing(3)
    brand.addWidget(_label('WALLPAPER STUDIO', 'Brand'))
    brand.addWidget(_label('让动态画面，停在你喜欢的瞬间。'))
    header.addLayout(brand)
    header.addStretch()
    w.preview_quality = _combo(['轻量预览 · 640px / 15fps','均衡预览 · 960px / 24fps','清晰预览 · 1280px / 30fps'])
    w.preview_quality.setToolTip('只改变预览，导出仍使用原始素材。首次生成代理在后台运行，可取消。')
    w.preview_quality.setCurrentIndex(max(0,min(2,w.preferences.value('preview_quality',0,type=int))))
    w.preview_quality.currentIndexChanged.connect(w.change_preview_quality)
    header.addWidget(w.preview_quality)
    header.addWidget(_button('设置导出位置…', w.choose_output, 'Quiet'))
    header.addWidget(_label(f'本地处理  /  v{__version__}', 'Eyebrow'))
    w.open_output = _button('导出文件夹 ↗', lambda: w.open_folder(w.output_dir), 'Quiet')
    header.addWidget(w.open_output)
    layout.addLayout(header)

    split = QSplitter()
    split.setChildrenCollapsible(False)
    split.setHandleWidth(12)
    w.workspace_splitter = split
    layout.addWidget(split, 1)

    w.library_panel = QWidget()
    w.library_panel.setObjectName('LibraryPanel')
    w.library_panel.setMinimumWidth(210)
    w.library_panel.setMaximumWidth(270)
    ll = QVBoxLayout(w.library_panel)
    ll.setContentsMargins(14, 17, 14, 14)
    ll.setSpacing(12)
    ll.addWidget(_label('01  /  素材库', 'Eyebrow'))
    ll.addWidget(_label('选择一个开始', 'Title'))
    w.library_path = QComboBox()
    w.library_path.setEditable(True)
    w.library_path.setMinimumWidth(0)
    w.library_path.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    w.library_path.setMinimumContentsLength(8)
    w.library_path.lineEdit().setPlaceholderText('添加 Steam / Workshop 路径')
    w.library_path.setToolTip('可输入 Steam 库、431960 目录或单个壁纸项目路径；回车添加并扫描')
    w.library_path.lineEdit().returnPressed.connect(w.add_library_path)
    ll.addWidget(w.library_path)
    ll.addLayout(_row(_button('添加路径…', w.choose_library, 'Quiet'), _button('移除此路径', w.remove_library_path, 'Quiet')))
    w.search = QLineEdit()
    w.search.setPlaceholderText('搜索素材…')
    w.search.setClearButtonEnabled(True)
    w.search.textChanged.connect(w.filter_library)
    ll.addWidget(w.search)
    w.type_filter = _combo(['全部类型', 'Scene / PKG', '视频', 'Web'])
    w.type_filter.currentIndexChanged.connect(w.filter_library)
    ll.addWidget(w.type_filter)
    w.rating_filter = _combo(['全部分级', '全年龄', '需留意', '18+', '未标注'])
    w.rating_filter.currentIndexChanged.connect(w.filter_library)
    ll.addWidget(w.rating_filter)
    w.tag_filter = _combo(['全部标签'])
    w.tag_filter.currentIndexChanged.connect(w.filter_library)
    ll.addWidget(w.tag_filter)
    w.library_list = QListWidget()
    w.library_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    w.library_list.setTextElideMode(Qt.TextElideMode.ElideRight)
    w.library_list.setIconSize(QSize(64, 45))
    w.library_list.currentItemChanged.connect(w.select_entry)
    ll.addWidget(w.library_list, 1)
    w.count_label = _label('暂无素材 · 可导入或扫描')
    ll.addWidget(w.count_label)
    ll.addWidget(_button('＋ 导入文件', w.import_file))
    ll.addLayout(_row(_button('项目目录', w.import_folder, 'Quiet'), _button('扫描素材', lambda: w.scan(), 'Quiet')))
    ll.addWidget(_button('选择素材库…', w.choose_library, 'Quiet'))
    split.addWidget(w.library_panel)

    editor = QWidget()
    el = QVBoxLayout(editor)
    el.setContentsMargins(2, 5, 2, 0)
    el.setSpacing(10)
    el.addWidget(_label('02  /  编辑预览', 'Eyebrow'))
    w.title = ElidingLabel('选择素材，开始创作')
    w.title.setObjectName('Title')
    w.title.setMaximumHeight(34)
    el.addWidget(w.title)
    w.metadata_label = _label('选择项目后显示原始标签与分级')
    w.metadata_label.setWordWrap(True)
    el.addWidget(w.metadata_label)
    w.canvas = CropCanvas()
    w.canvas.setObjectName('PreviewCanvas')
    el.addWidget(w.canvas, 1)
    frame_row = QHBoxLayout()
    w.frame_label = _label('未加载视频')
    frame_row.addWidget(w.frame_label, 1)
    frame_row.addWidget(_button('重置构图', w.reset_crop, 'Quiet'))
    el.addLayout(frame_row)
    w.duration_range = w.range_timeline = RangeTimeline()
    el.addWidget(w.range_timeline)
    w.selection_label = _label('选择片段 · 拖动两端，或用方向键微调')
    el.addWidget(w.selection_label)
    w.timeline = QSlider(Qt.Orientation.Horizontal)
    w.timeline.setRange(0, 0)
    w.timeline.setAccessibleName('精确逐帧浏览')
    w.timeline.setToolTip('按帧浏览 · 左右键逐帧移动')
    w.timeline.valueChanged.connect(w.frame_changed)
    w.timeline.setParent(root)
    w.timeline.hide()  # Backend frame index; the combined range control scrubs.
    tools = QHBoxLayout()
    for text, function, tip in [
        ('←', lambda: w.move_frame(-1), '上一帧'),
        ('播放', w.toggle_play, '播放 / 暂停预览'),
        ('→', lambda: w.move_frame(1), '下一帧'),
        ('设为封面', w.set_cover, '以当前帧作为 Live Photo 封面')]:
        tools.addWidget(_button(text, function, tooltip=tip))
    tools.addStretch()
    el.addLayout(tools)
    w.log = QPlainTextEdit()
    w.log.setReadOnly(True)
    w.log.setMaximumHeight(95)
    w.log.hide()
    el.addWidget(w.log)
    split.addWidget(editor)

    inspector = QWidget()
    inspector.setObjectName('Inspector')
    inspector.setMinimumWidth(282)
    inspector.setMaximumWidth(315)
    il = QVBoxLayout(inspector)
    il.setContentsMargins(16, 17, 16, 14)
    il.setSpacing(14)
    il.addWidget(_label('03  /  设置', 'Eyebrow'))
    w.inspector_tabs = QTabWidget()
    il.addWidget(w.inspector_tabs, 1)

    capture = _page(w.inspector_tabs, '录制')
    capture.addWidget(_label('先录一段，再慢慢选择。', 'Title'))
    note = _label('真实引擎画面显示在预览区。\n场景录制后可像视频一样点播。')
    note.setWordWrap(True)
    capture.addWidget(note)
    w.auto_preview = QCheckBox('选择场景后自动实时预览')
    w.auto_preview.setChecked(True)
    w.auto_preview.toggled.connect(w.toggle_live_preview)
    capture.addWidget(w.auto_preview)
    capture.addWidget(_label('录制时长', 'Eyebrow'))
    duration_row = QHBoxLayout()
    w.duration_label = _label('10', 'DurationValue')
    duration_row.addWidget(w.duration_label)
    duration_row.addWidget(_label('秒'))
    duration_row.addStretch()
    capture.addLayout(duration_row)
    w.duration_slider = w.capture_duration_slider = QSlider(Qt.Orientation.Horizontal)
    w.duration_slider.setRange(1, 120)
    w.duration_slider.setValue(10)
    w.duration_slider.setAccessibleName('录制秒数（1 至 120）')
    capture.addWidget(w.duration_slider)
    presets = QHBoxLayout()
    presets.setSpacing(5)
    w.duration_presets = QButtonGroup(w)
    w.duration_presets.setExclusive(True)
    for seconds in (3, 5, 10, 20, 30):
        chip = _button(f'{seconds}s', kind='Chip')
        chip.setCheckable(True)
        w.duration_presets.addButton(chip, seconds)
        chip.setChecked(seconds == 10)
        chip.clicked.connect(lambda checked=False, value=seconds: w.duration_slider.setValue(value))
        presets.addWidget(chip)
    capture.addLayout(presets)
    w.record_button = _button('录制可回放片段', w.record, 'Primary')
    capture.addWidget(w.record_button)
    w.preview_button = _button('启动 / 重启实时预览', w.preview_scene)
    capture.addWidget(w.preview_button)
    w.capture_advanced = Collapsible('高级设置')
    cf = QFormLayout(w.capture_advanced.body)
    cf.setContentsMargins(0, 6, 0, 0)
    cf.setHorizontalSpacing(7)
    cf.setVerticalSpacing(8)
    w.capture_width = w.spin(3840, 16, 16384)
    w.capture_height = w.spin(2160, 16, 16384)
    cf.addRow('渲染像素', _row(w.capture_width, _label('×'), w.capture_height))
    w.capture_fps = _combo(['30', '60', '15', '24', '120'])
    cf.addRow('采集帧率', w.capture_fps)
    w.render_multiplier = _combo(['1×','2×','3×','4×','5×','8×','自定义'])
    w.render_multiplier_custom = w.spin(8,1,16)
    cf.addRow('原生渲染倍率', w.render_multiplier)
    cf.addRow('自定义倍率', w.render_multiplier_custom)
    w.render_multiplier_custom.hide()
    w.render_size_label = _label('3840 × 2160 · 1×')
    w.render_size_label.setWordWrap(True)
    cf.addRow(w.render_size_label)
    w.render_multiplier.currentIndexChanged.connect(w.update_render_summary)
    w.render_multiplier_custom.valueChanged.connect(w.update_render_summary)
    w.capture_width.valueChanged.connect(w.update_render_summary)
    w.capture_height.valueChanged.connect(w.update_render_summary)
    fps_note = _label('采集 FPS 不等于引擎渲染 FPS。\n引擎全局画质与 FPS 沿用 WE 设置；\n壁纸自己的质量选项在「部件」页。')
    fps_note.setWordWrap(True)
    cf.addRow(fps_note)
    cf.addRow(_button('打开 Wallpaper Engine 设置…',w.open_engine_settings,'Quiet'))
    w.capture_seconds = w.double(10, .1, 600)
    cf.addRow('精确秒数', w.capture_seconds)
    w.capture_wait = w.double(20, 0, 120)
    cf.addRow('加载等待', w.capture_wait)
    w.resource_button = _button('提取内部素材', w.extract, 'Quiet', '提取原始内部资源，不是最终渲染画面')
    cf.addRow(w.resource_button)
    capture.addWidget(w.capture_advanced)
    capture.addStretch()
    def capture_disclosure(checked):
        # Keep advanced fields within the same compact inspector rather than
        # growing the window or introducing a permanent side scrollbar.
        note.setVisible(not checked)
        capture.setSpacing(6 if checked else 14)
    w.capture_advanced.toggle.toggled.connect(capture_disclosure)
    w.duration_slider.valueChanged.connect(lambda value: w.capture_seconds.setValue(value))
    def sync_duration(value):
        w.duration_slider.blockSignals(True)
        w.duration_slider.setValue(round(value))
        w.duration_slider.blockSignals(False)
        w.duration_label.setText(f'{value:g}')
        w.duration_presets.setExclusive(False)
        for button in w.duration_presets.buttons():
            button.setChecked(abs(value - w.duration_presets.id(button)) < .001)
        w.duration_presets.setExclusive(True)
    w.capture_seconds.valueChanged.connect(sync_duration)

    composition = _page(w.inspector_tabs, '构图')
    composition.addWidget(_label('为你的屏幕，留出空间。', 'Title'))
    form = QFormLayout()
    form.setVerticalSpacing(12)
    w.composition_form = form
    w.ratio = _combo(['iPad Pro 11 M4', '原始比例', '4:3', '16:9', '16:10', '3:2', '9:16', '自定义'])
    w.orientation = _combo(['横屏', '竖屏'])
    w.resolution = _combo(['设备 / 原始尺寸', '2K · 长边2560', '4K · 长边3840', '8K · 长边7680', '自定义像素'])
    w.fit = _combo(['裁切铺满', '完整保留 + 补边', '拉伸'])
    for title, control in [('画面比例', w.ratio), ('方向', w.orientation), ('清晰度', w.resolution), ('适配', w.fit)]:
        form.addRow(title, control)
    w.output_multiplier = _combo(['1×','2×','3×','4×','5×','8×','自定义'])
    w.output_multiplier_custom = w.spin(8,1,16)
    w.output_multiplier_custom.hide()
    form.addRow('输出像素倍率', w.output_multiplier)
    form.addRow('自定义倍率', w.output_multiplier_custom)
    composition.addLayout(form)
    w.pixel_summary = _label('2420 × 1668 px', 'Title')
    composition.addWidget(w.pixel_summary)
    scale_note = _label('输出倍率增加文件像素，不恢复视频细节。\n场景可提高原生渲染倍率后缩小输出，\n得到更好的抗锯齿；预览仍保持轻量。')
    w.scale_help=scale_note
    scale_note.setWordWrap(True)
    composition.addWidget(scale_note)
    w.output_multiplier.currentIndexChanged.connect(w.update_output_summary)
    w.output_multiplier_custom.valueChanged.connect(w.update_output_summary)
    tip = _label('在预览中拖动裁切框。\n右下角可缩放，切换方向分别记忆构图。')
    w.composition_help=tip
    tip.setWordWrap(True)
    composition.addWidget(tip)
    w.rotation_adaptive = QCheckBox('单张方形画布 · 横竖取景')
    w.rotation_adaptive.setToolTip('这是构图取景工具；系统旋转自动重排是另一个待研究的功能。')
    composition.addWidget(w.rotation_adaptive)
    rotation_note = _label('单张方形画布，横竖屏取不同区域。\n绿色区域是两种方向都可见的主体区。\n屏幕边缘内容会随方向裁切。')
    rotation_note.setWordWrap(True)
    w.rotation_note=rotation_note
    composition.addWidget(rotation_note)
    w.rotation_controls = QWidget()
    rf = QFormLayout(w.rotation_controls)
    rf.setContentsMargins(0,0,0,0)
    w.adaptive_zoom = QSlider(Qt.Orientation.Horizontal)
    w.adaptive_zoom.setRange(25,200);w.adaptive_zoom.setValue(100)
    w.adaptive_x = QSlider(Qt.Orientation.Horizontal)
    w.adaptive_x.setRange(0,100);w.adaptive_x.setValue(50)
    w.adaptive_y = QSlider(Qt.Orientation.Horizontal)
    w.adaptive_y.setRange(0,100);w.adaptive_y.setValue(50)
    w.rotation_view = _combo(['完整画布 + 安全区','横屏可见范围','竖屏可见范围'])
    rf.addRow('主体缩放',w.adaptive_zoom)
    rf.addRow('左右位置',w.adaptive_x)
    rf.addRow('上下位置',w.adaptive_y)
    rf.addRow('方向预览',w.rotation_view)
    w.rotation_controls.hide()
    composition.addWidget(w.rotation_controls)
    w.rotation_adaptive.toggled.connect(w.configure_rotation)
    for slider in (w.adaptive_zoom,w.adaptive_x,w.adaptive_y): slider.valueChanged.connect(w.configure_rotation)
    w.rotation_view.currentIndexChanged.connect(w.configure_rotation)
    w.dimensions_advanced = Collapsible('自定义像素')
    df = QFormLayout(w.dimensions_advanced.body)
    df.setContentsMargins(0, 6, 0, 0)
    w.output_width = w.spin(2420, 16, 16384)
    w.output_height = w.spin(1668, 16, 16384)
    df.addRow('宽度', w.output_width)
    df.addRow('高度', w.output_height)
    composition.addWidget(w.dimensions_advanced)
    composition.addStretch()

    export = _page(w.inspector_tabs, '导出')
    export.addWidget(_label('一个片段，多种可能。', 'Title'))
    ef = QFormLayout()
    ef.setVerticalSpacing(13)
    w.format_box = _combo(['PNG · 当前帧', '批量 PNG · 按间隔', 'GIF · 片段循环', 'MP4 · H.264', 'Live Photo · JPEG + MOV', 'iPad 壁纸 · 单文件导出'])
    ef.addRow('文件格式', w.format_box)
    w.export_fps = _combo(['30', '60', '15'])
    ef.addRow('输出帧率', w.export_fps)
    w.interval = w.double(1, .01, 600)
    ef.addRow('间隔秒数', w.interval)
    export.addLayout(ef)
    w.ipad_preset_button=_button('应用 iPad 横竖实测预设', w.apply_ipad_preset, 'Primary')
    export.addWidget(w.ipad_preset_button)
    w.ipad_controls=QWidget()
    ipf=QFormLayout(w.ipad_controls);ipf.setContentsMargins(0,0,0,0)
    w.ipad_fit=_combo(['等比例铺满 · 裁切背景'])
    w.ipad_package=_combo(['动态 HEIC · 单文件','LIVP · 单文件备选','安卓动态 JPG · 荣耀样本（实验）','静态 PNG · 高分辨率'])
    w.ipad_multiplier=_combo(['1× · 2420 × 2420','2× · 4840 × 4840','3× · 7260 × 7260']);w.ipad_multiplier.setCurrentIndex(2)
    w.ipad_sharpen=_combo(['关闭','轻度 · 0.35','标准 · 0.60']);w.ipad_sharpen.setCurrentIndex(1)
    w.ipad_x=QSlider(Qt.Orientation.Horizontal);w.ipad_x.setRange(20,80);w.ipad_x.setValue(50)
    w.ipad_y=QSlider(Qt.Orientation.Horizontal);w.ipad_y.setRange(20,80);w.ipad_y.setValue(38)
    w.ipad_view=_combo(['完整画布 + 坐标区','横屏取景','竖屏取景'])
    ipf.addRow('满屏构图',w.ipad_fit);ipf.addRow('最终文件',w.ipad_package)
    ipf.addRow('静态倍率',w.ipad_multiplier);ipf.addRow('边缘锐化',w.ipad_sharpen)
    ipf.addRow('主体左右',w.ipad_x);ipf.addRow('主体上下',w.ipad_y);ipf.addRow('设备预览',w.ipad_view)
    export.addWidget(w.ipad_controls);w.ipad_controls.hide()
    w.ipad_package.currentIndexChanged.connect(w.update_ipad_preview)
    w.ipad_multiplier.currentIndexChanged.connect(w.update_ipad_preview)
    w.ipad_sharpen.currentIndexChanged.connect(w.update_ipad_preview)
    w.ipad_fit.currentIndexChanged.connect(w.update_ipad_preview)
    w.ipad_view.currentIndexChanged.connect(w.update_ipad_preview)
    w.ipad_x.valueChanged.connect(w.update_ipad_preview);w.ipad_y.valueChanged.connect(w.update_ipad_preview)
    w.format_box.currentIndexChanged.connect(w.ipad_format_changed)
    w.export_note = _label('每次导出创建独立文件夹。\n原始素材保持不变。')
    w.export_note.setWordWrap(True)
    export.addWidget(w.export_note)
    w.output_path_label=ElidingLabel(str(w.output_dir))
    w.output_path_label.setToolTip(str(w.output_dir))
    export.addWidget(w.output_path_label)
    export.addWidget(_button('选择导出目录…', w.choose_output, 'Quiet'))
    export.addStretch()
    w.start = w.double(0, 0, 999999)
    w.end = w.double(0, 0, 999999)
    w.cover = w.double(1.5, 0, 999999)
    for control in (w.start, w.end, w.cover):
        control.setParent(root)
        control.hide()
    properties = _page(w.inspector_tabs, '部件')
    properties.addWidget(_label('按你的喜好，保留动效。','Title'))
    w.property_note = _label('选择 Scene / Web，读取作者开放的部件、动效与质量选项。')
    w.property_note.setWordWrap(True)
    properties.addWidget(w.property_note)
    properties.addWidget(_button('应用到实时预览',w.apply_wallpaper_properties,'Primary'))
    properties.addWidget(_button('恢复作者默认值',w.reset_wallpaper_properties,'Quiet'))
    w.property_form = QFormLayout()
    w.property_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    properties.addLayout(w.property_form)
    properties.addStretch()
    w.property_controls = {}; w.property_schema = {}
    w.export_button = _button('导出所选内容  ↗', w.export, 'Primary')
    il.addWidget(w.export_button)
    il.addWidget(_label('原素材只读  ·  在本机处理'))
    split.addWidget(inspector)
    split.setStretchFactor(0, 0)
    split.setStretchFactor(1, 1)
    split.setStretchFactor(2, 0)
    split.setSizes([230, 780, 290])

    footer = QHBoxLayout()
    w.status = _label('就绪 · 导入素材或扫描素材库')
    footer.addWidget(w.status, 1)
    w.log_toggle = _button('任务日志', kind='Quiet')
    w.log_toggle.setCheckable(True)
    w.log_toggle.toggled.connect(w.log.setVisible)
    footer.addWidget(w.log_toggle)
    w.progress = QProgressBar()
    w.progress.setFixedSize(150, 18)
    w.progress.setValue(0)
    w.progress.hide()
    footer.addWidget(w.progress)
    w.cancel_button = _button('取消', w.cancel_task, 'Quiet')
    w.cancel_button.setEnabled(False)
    footer.addWidget(w.cancel_button)
    layout.addLayout(footer)

    def range_changed(start, end):
        w.start.blockSignals(True)
        w.end.blockSignals(True)
        w.start.setValue(start)
        w.end.setValue(end)
        w.start.blockSignals(False)
        w.end.blockSignals(False)
        w.selection_label.setText(f'片段  {start:.2f} → {end:.2f} s     /     已选 {end-start:.2f} 秒')
    w.range_timeline.rangeChanged.connect(range_changed)
    w.start.valueChanged.connect(lambda _: w.range_timeline.set_range(w.start.value(), w.end.value()))
    w.end.valueChanged.connect(lambda _: w.range_timeline.set_range(w.start.value(), w.end.value()))
    w.cover.valueChanged.connect(w.range_timeline.set_cover)
    def seek(seconds):
        w.seek_time(seconds)
    w.range_timeline.playheadChanged.connect(seek)
    w.timeline.valueChanged.connect(lambda index: w.range_timeline.set_playhead(w.timestamps[index]) if index < len(w.timestamps) else None)

    def pixels(*args):
        w.update_output_summary()
    def context_dimensions(*args):
        w.dimensions_advanced.toggle.setChecked(w.ratio.currentIndex() == 7 or w.resolution.currentIndex() == 4)
    for box in (w.ratio, w.resolution):
        box.currentIndexChanged.connect(w.update_size)
        box.currentIndexChanged.connect(context_dimensions)
        box.currentIndexChanged.connect(pixels)
    w.orientation.currentIndexChanged.connect(w.change_orientation)
    w.orientation.currentIndexChanged.connect(pixels)
    w.fit.currentIndexChanged.connect(w.reset_crop)
    for spin in (w.output_width, w.output_height):
        spin.valueChanged.connect(w.reset_crop)
        spin.valueChanged.connect(pixels)
    def export_context(index):
        w.interval.setVisible(index == 1)
        ef.labelForField(w.interval).setVisible(index == 1)
        w.export_fps.setVisible(index in (2, 3, 4))
        ef.labelForField(w.export_fps).setVisible(index in (2, 3, 4))
        w.export_note.setText('同名 JPEG + MOV 与 ZIP 收纳文件。\n真机相册识别与锁屏播放需单独验收。' if index == 4 else '每次导出创建独立文件夹。\n原始素材保持不变。')
    w.format_box.currentIndexChanged.connect(export_context)
    export_context(0)
    for button in (w.record_button, w.preview_button, w.resource_button, w.export_button):
        button.setEnabled(False)
    w.update_size()


def update_media_window(window):
    """Call after video metadata/range controls are set in app.video_ready."""
    duration = window.info.get('duration', 0.)
    window.range_timeline.set_duration(duration)
    window.range_timeline.set_range(0, duration)
    window.start.setValue(0)
    window.end.setValue(duration)
    window.range_timeline.set_cover(window.cover.value())
    window.pixel_summary.setText(f'{window.output_width.value()} × {window.output_height.value()} px')

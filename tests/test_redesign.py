import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication


@pytest.fixture
def application():
    return QApplication.instance() or QApplication([])


def test_range_timeline_clamps_and_keyboard_is_accessible(application):
    from wallpaper_studio.widgets import RangeTimeline
    widget = RangeTimeline()
    widget.resize(600, 76)
    widget.set_duration(10)
    widget.set_range(2, 8)
    widget.show()
    widget.start_handle.setFocus()
    QTest.keyClick(widget.start_handle, Qt.Key.Key_Right)
    assert widget.start == pytest.approx(2.1)
    widget.end_handle.setFocus()
    QTest.keyClick(widget.end_handle, Qt.Key.Key_Left)
    assert widget.end == pytest.approx(7.9)
    widget.set_range(2, 8)
    from PySide6.QtCore import QPoint
    QTest.mousePress(widget.start_handle, Qt.MouseButton.LeftButton, pos=QPoint(8, 16))
    QTest.mouseMove(widget.start_handle, QPoint(68, 16))
    QTest.mouseRelease(widget.start_handle, Qt.MouseButton.LeftButton, pos=QPoint(8, 16))
    assert widget.start > 2
    widget.set_range(-5, 40)
    assert (widget.start, widget.end) == (0, 10)
    widget.close()


def test_default_start_and_playhead_are_independently_draggable(application):
    from wallpaper_studio.widgets import RangeTimeline
    from PySide6.QtCore import QPoint
    widget = RangeTimeline()
    widget.resize(600, 90)
    widget.set_duration(10)
    widget.show()
    application.processEvents()
    assert widget.start == widget.playhead == 0
    assert not widget.start_handle.geometry().intersects(widget.playhead_handle.geometry())
    QTest.mousePress(widget.start_handle, Qt.MouseButton.LeftButton, pos=QPoint(8, 16))
    QTest.mouseMove(widget.start_handle, QPoint(68, 16))
    QTest.mouseRelease(widget.start_handle, Qt.MouseButton.LeftButton)
    assert widget.start > 0 and widget.playhead == 0
    QTest.mousePress(widget.playhead_handle, Qt.MouseButton.LeftButton, pos=QPoint(8, 12))
    QTest.mouseMove(widget.playhead_handle, QPoint(128, 12))
    QTest.mouseRelease(widget.playhead_handle, Qt.MouseButton.LeftButton)
    assert widget.playhead > 0
    widget.close()


def test_redesign_preserves_backend_bindings_and_duration_sync(application):
    from wallpaper_studio.app import StudioWindow
    from wallpaper_studio.ui import update_media_window
    window = StudioWindow(scan_on_start=False)
    assert window.inspector_tabs.count() == 4
    assert window.capture_duration_slider.minimum() == 1
    assert window.capture_duration_slider.maximum() == 120
    window.capture_duration_slider.setValue(25)
    assert window.capture_seconds.value() == 25
    window.capture_seconds.setValue(7)
    assert window.capture_duration_slider.value() == 7
    window.capture_seconds.setValue(600)
    assert window.capture_duration_slider.value() == 120
    assert window.capture_seconds.value() == 600
    window.info = {'duration': 10, 'width': 64, 'height': 48}
    window.timestamps = [0, .1, .4, .8]
    update_media_window(window)
    window.duration_range.set_range(2, 8)
    assert window.start.value() == 2 and window.end.value() == 8
    window.start.setValue(3)
    assert window.duration_range.start == 3
    assert '5.00' in window.selection_label.text()
    window.resize(1280, 820)
    window.show()
    application.processEvents()
    assert window.centralWidget().height() <= 820
    assert window.library_panel.width() <= 270
    assert not window.log.isVisible()
    assert not window.capture_advanced.body.isVisible()
    assert window.inspector_tabs.widget(0).verticalScrollBar().maximum() == 0
    window.title.setText('很长的素材名称' * 50)
    application.processEvents()
    assert window.width() == 1280
    assert window.title.toolTip() == window.title.text()
    window.close()


def test_small_inspector_advanced_controls_scroll_without_clipping(application):
    from wallpaper_studio.app import StudioWindow
    from PySide6.QtWidgets import QScrollArea
    window = StudioWindow(scan_on_start=False)
    window.resize(1080, 720)
    window.show()
    window.capture_advanced.toggle.setChecked(True)
    application.processEvents()
    application.processEvents()
    scroll = window.inspector_tabs.widget(0)
    assert isinstance(scroll, QScrollArea)
    assert scroll.verticalScrollBar().maximum() > 0
    assert window.resource_button.y() + window.resource_button.height() <= window.capture_advanced.body.height()
    assert window.height() == 720
    window.close()


def test_scan_button_does_not_treat_clicked_boolean_as_root(application, monkeypatch):
    import threading
    from wallpaper_studio import source
    from wallpaper_studio.app import StudioWindow
    from PySide6.QtWidgets import QPushButton
    roots = []
    monkeypatch.setattr(source, 'discover_library', lambda root=None: roots.append(root) or [])
    window = StudioWindow(scan_on_start=False)
    monkeypatch.setattr(window, 'run_task', lambda function, done: function(threading.Event(), lambda *args: None))
    button = next(button for button in window.findChildren(QPushButton) if button.text() == '扫描素材')
    button.click()
    assert roots == [None]
    window.close()

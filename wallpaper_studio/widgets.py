"""Native, keyboard-accessible editing controls for Wallpaper Studio."""
from __future__ import annotations

import math
from PySide6.QtCore import Qt, Signal, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QToolButton, QVBoxLayout, QLabel, QSizePolicy


class ElidingLabel(QLabel):
    """Keep full accessible title/tooltip without widening the workbench."""
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setToolTip(text)

    def setText(self, text):
        super().setText(text)
        self.setToolTip(text)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(self.palette().windowText().color())
        painter.setFont(self.font())
        text = self.fontMetrics().elidedText(self.text(), Qt.TextElideMode.ElideRight, self.contentsRect().width())
        painter.drawText(self.contentsRect(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)


class Collapsible(QWidget):
    def __init__(self, title='高级设置', parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setObjectName('Disclosure')
        self.toggle.setAccessibleName(title)
        self.body = QWidget()
        self.body.hide()
        layout.addWidget(self.toggle)
        layout.addWidget(self.body)
        self.toggle.toggled.connect(self._toggle)

    def _toggle(self, checked):
        self.body.setVisible(checked)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)


class _RangeHandle(QToolButton):
    def __init__(self, owner, role):
        super().__init__(owner)
        self.owner, self.role, self.dragging = owner, role, False
        self.setFixedSize(16, 24 if role == 'playhead' else 32)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setText('│' if role == 'playhead' else ('‹' if role == 'start' else '›'))
        self.setAccessibleName({'start': '片段起点', 'end': '片段终点', 'playhead': '播放位置'}[role])
        self.setToolTip(self.accessibleName() + ' · 拖动或按左右方向键；Shift 加速')
        self.setObjectName('Playhead' if role == 'playhead' else 'RangeHandle')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.setFocus()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging:
            x = self.mapTo(self.owner, event.position().toPoint()).x()
            self.owner._move_handle(self.role, self.owner._time_at(x))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.dragging = False
        event.accept()

    def keyPressEvent(self, event):
        step = 1 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else .1
        value = getattr(self.owner, self.role)
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Down):
            self.owner._move_handle(self.role, value - step)
        elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Up):
            self.owner._move_handle(self.role, value + step)
        elif event.key() == Qt.Key.Key_Home:
            self.owner._move_handle(self.role, 0)
        elif event.key() == Qt.Key.Key_End:
            self.owner._move_handle(self.role, self.owner.duration)
        else:
            super().keyPressEvent(event)
            return
        event.accept()


class RangeTimeline(QWidget):
    """Dual-handle seconds range plus playhead; native focusable handles.

    ``rangeChanged`` emits only when the range changes. Programmatic updates
    clamp to the current duration and preserve a positive selection.
    """
    rangeChanged = Signal(float, float)
    playheadChanged = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.duration = self.start = self.end = self.playhead = 0.
        self.cover = None
        self.scrubbing = False
        self.setMinimumHeight(90)
        self.setMinimumWidth(220)
        self.setAccessibleName('片段范围时间轴')
        self.start_handle = _RangeHandle(self, 'start')
        self.end_handle = _RangeHandle(self, 'end')
        self.playhead_handle = _RangeHandle(self, 'playhead')
        QWidget.setTabOrder(self.start_handle, self.end_handle)
        QWidget.setTabOrder(self.end_handle, self.playhead_handle)
        self._place_handles()

    def set_duration(self, duration):
        duration = float(duration)
        if not math.isfinite(duration) or duration < 0:
            raise ValueError('Timeline duration must be finite and nonnegative')
        changed = duration != self.duration
        self.duration = duration
        if changed:
            self.set_range(0, duration)
        else:
            self.set_range(self.start, self.end)
        self.set_playhead(self.playhead)
        self._place_handles()
        self.update()

    def set_range(self, start, end):
        start, end = float(start), float(end)
        if not math.isfinite(start) or not math.isfinite(end):
            raise ValueError('Range must be finite')
        gap = min(.001, self.duration)
        start = min(max(0., start), max(0., self.duration - gap))
        end = min(self.duration, max(start + gap, end))
        changed = (start, end) != (self.start, self.end)
        self.start, self.end = start, end
        self._place_handles()
        self.update()
        if changed:
            self.rangeChanged.emit(start, end)

    def set_playhead(self, seconds):
        self.playhead = min(self.duration, max(0., float(seconds)))
        self._place_handles()
        self.update()

    def set_cover(self, seconds):
        self.cover = min(self.duration, max(0., float(seconds))) if seconds is not None else None
        self.update()

    def _x_at(self, seconds):
        return 12 + (self.width() - 24) * seconds / self.duration if self.duration else 12

    def _time_at(self, x):
        return min(self.duration, max(0., (x - 12) / max(1, self.width() - 24) * self.duration))

    def _place_handles(self):
        for role in ('start', 'end', 'playhead'):
            handle = getattr(self, role + '_handle')
            handle.move(round(self._x_at(getattr(self, role))) - 8, 44 if role == 'playhead' else 12)
            handle.setEnabled(self.duration > 0)
            handle.setAccessibleDescription(f'{getattr(self, role):.3f} 秒')
        self.playhead_handle.raise_()

    def _move_handle(self, role, seconds):
        if role == 'start':
            self.set_range(min(seconds, self.end - .001), self.end)
        elif role == 'end':
            self.set_range(self.start, max(seconds, self.start + .001))
        else:
            self.set_playhead(seconds)
            self.playheadChanged.emit(self.playhead)

    def resizeEvent(self, event):
        self._place_handles()
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.duration:
            self.scrubbing = True
            self._move_handle('playhead', self._time_at(event.position().x()))
            self.playhead_handle.setFocus()

    def mouseMoveEvent(self, event):
        if self.scrubbing and self.duration:
            self._move_handle('playhead', self._time_at(event.position().x()))
            event.accept()

    def mouseReleaseEvent(self, event):
        self.scrubbing = False
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#dce1de'))
        painter.drawRoundedRect(QRectF(12, 20, self.width() - 24, 16), 4, 4)
        painter.setBrush(QColor('#dce1de'))
        painter.drawRoundedRect(QRectF(12, 55, self.width() - 24, 2), 1, 1)
        if self.duration:
            painter.setBrush(QColor('#a9dccc'))
            painter.drawRoundedRect(QRectF(self._x_at(self.start), 20, self._x_at(self.end) - self._x_at(self.start), 16), 3, 3)
            if self.cover is not None:
                painter.setPen(QPen(QColor('#158567'), 2))
                x = self._x_at(self.cover)
                painter.drawLine(round(x), 5, round(x), 11)
        painter.setPen(QColor('#68716b'))
        painter.drawText(QRectF(12, 70, 100, 18), Qt.AlignmentFlag.AlignLeft, '0:00')
        seconds = int(self.duration)
        painter.drawText(QRectF(self.width()-112, 70, 100, 18), Qt.AlignmentFlag.AlignRight, f'{seconds//60}:{seconds%60:02}')
        painter.drawText(QRectF(100, 70, self.width()-200, 18), Qt.AlignmentFlag.AlignCenter, '上方选择片段 · 下方浏览画面')

from __future__ import annotations

import argparse
import bisect
import json
import os
import sys
import threading
import time
import traceback
import tempfile
import queue
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPointF, QThread, Signal, QTimer, QUrl, QSettings
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QDesktopServices, QIcon, QFont, QImage, QImageReader
from PySide6.QtMultimedia import QMediaPlayer, QVideoSink
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QComboBox, QListWidget, QListWidgetItem,
    QSplitter, QGroupBox, QFormLayout, QSpinBox, QDoubleSpinBox, QSlider,
    QProgressBar, QFileDialog, QMessageBox, QPlainTextEdit, QScrollArea, QCheckBox, QColorDialog,
)

from . import __version__
from .models import CaptureSettings, EditSettings, WallpaperEntry, output_size, scaled_size, rotation_regions

from .ui import THEME


def normalized_crop(rect: QRectF, width: int, height: int) -> tuple[int, int, int, int]:
    x = max(0, min(width - 1, round(rect.x() * width)))
    y = max(0, min(height - 1, round(rect.y() * height)))
    w = max(1, min(width - x, round(rect.width() * width)))
    h = max(1, min(height - y, round(rect.height() * height)))
    return x, y, w, h


class CropCanvas(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.setMinimumSize(420, 270)
        self.pixmap = QPixmap()
        self.crop = QRectF(0, 0, 1, 1)
        self.active_crop = False
        self.drag_start = None
        self.saved_crop = QRectF(self.crop)
        self.resizing = False
        self.adaptive = None
        self.ipad_profile = False
        self.ipad_options = {}
        self.ipad_view = 0
        self.background_cache = None

    def set_image(self, path):
        self.pixmap = QPixmap(str(path))
        self.update()

    def image_rect(self):
        if self.pixmap.isNull():
            return QRectF()
        if self.adaptive or self.ipad_profile:
            edge=min(self.width(),self.height())
            return QRectF((self.width()-edge)/2,(self.height()-edge)/2,edge,edge)
        factor = min(self.width() / self.pixmap.width(), self.height() / self.pixmap.height())
        w, h = self.pixmap.width() * factor, self.pixmap.height() * factor
        return QRectF((self.width()-w)/2, (self.height()-h)/2, w, h)

    def crop_rect(self):
        r = self.image_rect()
        return QRectF(r.x()+self.crop.x()*r.width(), r.y()+self.crop.y()*r.height(),
                      self.crop.width()*r.width(), self.crop.height()*r.height())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#191f24"))
        if self.pixmap.isNull():
            cx,cy=self.width()/2,self.height()/2
            painter.setPen(QPen(QColor("#42564d"),1))
            painter.drawRoundedRect(QRectF(cx-36,cy-106,72,54),10,10)
            painter.setPen(QPen(QColor("#96d9bd"),2))
            painter.drawLine(QPointF(cx-8,cy-92),QPointF(cx+10,cy-79))
            painter.drawLine(QPointF(cx+10,cy-79),QPointF(cx-8,cy-66))
            painter.drawLine(QPointF(cx-8,cy-66),QPointF(cx-8,cy-92))
            font=QFont(self.font()); font.setPointSize(19); font.setWeight(QFont.Weight.DemiBold); painter.setFont(font)
            painter.setPen(QColor("#eef3f0"))
            painter.drawText(QRectF(0,cy-28,self.width(),40),Qt.AlignmentFlag.AlignCenter,"让壁纸，成为你的画面")
            font.setPointSize(10); font.setWeight(QFont.Weight.Normal); painter.setFont(font); painter.setPen(QColor("#91a099"))
            painter.drawText(QRectF(0,cy+20,self.width(),30),Qt.AlignmentFlag.AlignCenter,"从素材库选择，或把文件拖到这里")
            painter.setPen(QColor("#6d8177"))
            painter.drawText(QRectF(0,cy+72,self.width(),24),Qt.AlignmentFlag.AlignCenter,"SCENE  /  PKG  /  VIDEO  /  WEB")
            return
        r = self.image_rect()
        if self.adaptive or self.ipad_profile:
            self.paint_adaptive(painter,r)
            return
        painter.drawPixmap(r.toRect(), self.pixmap)
        if self.active_crop:
            c = self.crop_rect()
            painter.fillRect(QRectF(r.x(),r.y(),r.width(),c.y()-r.y()), QColor(0,0,0,145))
            painter.fillRect(QRectF(r.x(),c.bottom(),r.width(),r.bottom()-c.bottom()), QColor(0,0,0,145))
            painter.fillRect(QRectF(r.x(),c.y(),c.x()-r.x(),c.height()), QColor(0,0,0,145))
            painter.fillRect(QRectF(c.right(),c.y(),r.right()-c.right(),c.height()), QColor(0,0,0,145))
            painter.setPen(QPen(QColor("#8bddbb"),2))
            painter.drawRect(c)
            painter.setPen(QPen(QColor(139,221,187,90),1))
            for n in (1,2):
                painter.drawLine(QPointF(c.x()+c.width()*n/3,c.y()),QPointF(c.x()+c.width()*n/3,c.bottom()))
                painter.drawLine(QPointF(c.x(),c.y()+c.height()*n/3),QPointF(c.right(),c.y()+c.height()*n/3))
            painter.fillRect(QRectF(c.right()-9,c.bottom()-9,9,9),QColor("#8bddbb"))

    def paint_adaptive(self,painter,r):
        key=self.pixmap.cacheKey()
        if not self.ipad_profile and (self.background_cache is None or self.background_cache[0]!=key):
            # Small separable Qt resampling keeps animated preview overhead bounded.
            tiny=self.pixmap.scaled(64,64,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
            edge=min(tiny.width(),tiny.height())
            tiny=tiny.copy((tiny.width()-edge)//2,(tiny.height()-edge)//2,edge,edge)
            from PIL import Image, ImageFilter
            scaled=tiny.scaled(64,64,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation).toImage().convertToFormat(QImage.Format.Format_RGBA8888)
            im=Image.frombytes('RGBA',(64,64),bytes(scaled.bits())).filter(ImageFilter.BoxBlur(8)).filter(ImageFilter.BoxBlur(8))
            blur=QImage(im.tobytes(),64,64,256,QImage.Format.Format_RGBA8888).copy()
            self.background_cache=(key,QPixmap.fromImage(blur))
        if not self.ipad_profile:painter.drawPixmap(r.toRect(),self.background_cache[1])
        if self.ipad_profile:
            from .ipad_export import ipad_composition,IPAD_PROFILE
            layout=ipad_composition((self.pixmap.width(),self.pixmap.height()),**self.ipad_options)
            scale=r.width()/2420
            fw,fh=layout['foreground_size'];ox,oy=layout['foreground_offset']
            painter.save();painter.setClipRect(r)
            if layout['fit']=='stretch':
                cw,ch=layout['coded_source_size']
                for source,target in zip(layout['source_tiles'],layout['target_tiles']):
                    x,y,w,h=source;tx,ty,tw,th=target
                    source_rect=QRectF(x*self.pixmap.width()/cw,y*self.pixmap.height()/ch,w*self.pixmap.width()/cw,h*self.pixmap.height()/ch)
                    target_rect=QRectF(r.x()+tx*scale,r.y()+ty*scale,tw*scale,th*scale)
                    painter.drawPixmap(target_rect,self.pixmap,source_rect)
            else:painter.drawPixmap(QRectF(r.x()+ox*scale,r.y()+oy*scale,fw*scale,fh*scale).toRect(),self.pixmap)
            for key,color in [('landscape_rect','#f6bd60'),('portrait_rect','#8ebaf2'),('shared_rect','#8bddbb')]:
                x,y,w,h=IPAD_PROFILE[key]
                painter.setPen(QPen(QColor(color),2,Qt.PenStyle.DashLine))
                painter.drawRect(QRectF(r.x()+x*scale,r.y()+y*scale,w*scale,h*scale))
            if self.ipad_view:
                key='landscape_rect' if self.ipad_view==1 else 'portrait_rect'
                x,y,w,h=IPAD_PROFILE[key];visible=QRectF(r.x()+x*scale,r.y()+y*scale,w*scale,h*scale)
                for mask in (QRectF(r.x(),r.y(),r.width(),visible.top()-r.top()),QRectF(r.x(),visible.bottom(),r.width(),r.bottom()-visible.bottom()),QRectF(r.x(),visible.top(),visible.left()-r.left(),visible.height()),QRectF(visible.right(),visible.top(),r.right()-visible.right(),visible.height())):
                    painter.fillRect(mask,QColor(0,0,0,215))
            painter.restore();return
        zoom,x,y,ratio,view=self.adaptive
        scale=min(r.width()/self.pixmap.width(),r.height()/self.pixmap.height())*zoom
        width,height=self.pixmap.width()*scale,self.pixmap.height()*scale
        painter.save();painter.setClipRect(r)
        painter.drawPixmap(QRectF(r.x()+(r.width()-width)*x,r.y()+(r.height()-height)*y,width,height).toRect(),self.pixmap)
        short=r.width()*ratio;offset=(r.width()-short)/2
        landscape=QRectF(r.x(),r.y()+offset,r.width(),short)
        portrait=QRectF(r.x()+offset,r.y(),short,r.height())
        shared=landscape.intersected(portrait)
        if view:
            visible=landscape if view==1 else portrait
            painter.fillRect(QRectF(r.x(),r.y(),r.width(),visible.top()-r.top()),QColor(0,0,0,210))
            painter.fillRect(QRectF(r.x(),visible.bottom(),r.width(),r.bottom()-visible.bottom()),QColor(0,0,0,210))
            painter.fillRect(QRectF(r.x(),visible.top(),visible.left()-r.left(),visible.height()),QColor(0,0,0,210))
            painter.fillRect(QRectF(visible.right(),visible.top(),r.right()-visible.right(),visible.height()),QColor(0,0,0,210))
        painter.setPen(QPen(QColor('#f6bd60'),1,Qt.PenStyle.DashLine));painter.drawRect(landscape)
        painter.drawText(landscape.topLeft()+QPointF(8,18),'横屏')
        painter.setPen(QPen(QColor('#8ebaf2'),1,Qt.PenStyle.DashLine));painter.drawRect(portrait)
        painter.drawText(portrait.topLeft()+QPointF(8,18),'竖屏')
        painter.fillRect(shared,QColor(139,221,187,18));painter.setPen(QPen(QColor('#8bddbb'),2));painter.drawRect(shared)
        painter.drawText(shared.bottomLeft()+QPointF(8,-8),'横竖共同可见 · 主体安全区')
        painter.restore()

    def mousePressEvent(self, event):
        if self.active_crop and self.crop_rect().adjusted(-10,-10,10,10).contains(event.position()):
            self.drag_start = event.position()
            self.saved_crop = QRectF(self.crop)
            self.resizing = (event.position()-self.crop_rect().bottomRight()).manhattanLength()<28

    def mouseMoveEvent(self, event):
        if self.drag_start is None:
            return
        r = self.image_rect()
        d = event.position()-self.drag_start
        dx,dy = d.x()/r.width(),d.y()/r.height()
        c = self.saved_crop
        if self.resizing:
            # Keep the selected target aspect ratio while resizing.
            nw = max(.04,min(1-c.x(),c.width()+dx))
            nh = nw * c.height()/c.width()
            if nh > 1-c.y():
                nh=1-c.y(); nw=nh*c.width()/c.height()
            self.crop=QRectF(c.x(),c.y(),nw,nh)
        else:
            self.crop=QRectF(max(0,min(1-c.width(),c.x()+dx)),
                            max(0,min(1-c.height(),c.y()+dy)),c.width(),c.height())
        self.update(); self.changed.emit()

    def mouseReleaseEvent(self,event):
        self.drag_start=None


class Task(QThread):
    progress = Signal(int, str)
    result = Signal(object)
    error = Signal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function=function
        self.cancel=threading.Event()

    def run(self):
        try:
            self.result.emit(self.function(self.cancel,self.progress.emit))
        except Exception as exc:
            self.error.emit(f"{exc}\n{traceback.format_exc()}")


class StudioWindow(QMainWindow):
    def __init__(self, scan_on_start=True, experimental=False):
        super().__init__()
        self.setWindowTitle("Wallpaper Studio")
        self.resize(1440,920)
        self.setAcceptDrops(True)
        self.entries=[]; self.entry=None; self.video=None; self.info={}; self.timestamps=[]
        self.worker=None; self.preview_worker=None; self.pending_frame=None; self._close_pending=False
        self.live_worker=None; self.live_frames={}; self.after_live_stop=None; self.saved_record_crop=None
        self.preferences=QSettings('WallpaperStudio','WallpaperStudio')
        self.library_roots=self.preferences.value('library_roots',[],type=list)
        self.workspace=Path(tempfile.gettempdir()) / "WallpaperStudio" / "jobs"
        self.output_dir=Path(self.preferences.value('output_dir',str(Path.home()/"Pictures"/"Wallpaper Studio")))
        self.playback_proxy=None;self.last_display=0.;self.thumbnail_cache={};self.video_jobs={}
        self.orientation_crops={}
        self.play_timer=QTimer(self); self.play_timer.timeout.connect(self.next_frame)
        self.seek_timer=QTimer(self); self.seek_timer.setSingleShot(True); self.seek_timer.setInterval(90)
        self.seek_timer.timeout.connect(self.preview_frame)
        self.setup_ui()
        for index in (4,5):
            self.format_box.model().item(index).setEnabled(experimental)
            self.format_box.view().setRowHidden(index,not experimental)
        self.ipad_preset_button.setVisible(experimental)
        self.rotation_adaptive.setVisible(experimental)
        self.rotation_note.setVisible(experimental)
        self.player=QMediaPlayer(self)
        self.video_sink=QVideoSink(self)
        self.player.setVideoSink(self.video_sink)
        self.video_sink.videoFrameChanged.connect(self.playback_frame)
        self.player.errorOccurred.connect(lambda error,message:self.note(f"播放预览：{message}；精确导出仍使用 FFmpeg。"))
        self.library_path.addItems(self.library_roots)
        self.auto_preview.setChecked(self.preferences.value('auto_preview',True,type=bool))
        self.live_timer=QTimer(self); self.live_timer.setInterval(67)
        self.live_timer.timeout.connect(self.show_live_frame);self.live_timer.start()
        if scan_on_start:
            QTimer.singleShot(100,self.scan)

    def setup_ui(self):
        from .ui import setup_window
        setup_window(self)

    @staticmethod
    def spin(value,minimum,maximum):
        b=QSpinBox(); b.setRange(minimum,maximum); b.setValue(value); return b

    @staticmethod
    def double(value,minimum,maximum):
        b=QDoubleSpinBox(); b.setDecimals(3); b.setRange(minimum,maximum); b.setValue(value); return b

    def note(self,text):
        self.log.appendPlainText(text)

    def run_task(self,fn,done):
        if self.stop_live(lambda:self.run_task(fn,done)): return
        if self.worker and self.worker.isRunning():
            self.note("已有任务运行，请等待或取消。"); return
        self.play_timer.stop()
        self.player.pause()
        self.worker=Task(fn,self); self.worker.progress.connect(self.on_progress)
        self.worker.result.connect(done); self.worker.error.connect(self.task_error)
        self.worker.finished.connect(self.task_finished)
        self.cancel_button.setEnabled(True); self.export_button.setEnabled(False); self.record_button.setEnabled(False); self.preview_button.setEnabled(False); self.resource_button.setEnabled(False)
        self.library_panel.setEnabled(False)
        self.progress.setValue(0); self.worker.start()
        self.progress.show()

    def on_progress(self,value,message):
        self.progress.setValue(max(0,min(100,value))); self.status.setText(message)

    def task_error(self,message):
        self.note(message); self.status.setText("任务结束 · 查看日志")
        QMessageBox.information(self,"任务结果",message.split("Traceback")[0][:1400])

    def task_finished(self):
        self.progress.hide()
        self.cancel_button.setEnabled(False); self.export_button.setEnabled(self.video is not None)
        self.record_button.setEnabled(self.entry is not None and self.entry.kind in ("scene","web"))
        self.preview_button.setEnabled(self.record_button.isEnabled())
        self.library_panel.setEnabled(True)
        self.resource_button.setEnabled(self.entry is not None and self.entry.kind == "scene")
        worker=self.worker
        self.worker=None
        if worker: worker.deleteLater()
        if self._close_pending: self.close()

    def cancel_task(self):
        if self.live_worker: self.stop_live()
        if self.worker: self.worker.cancel.set(); self.status.setText("正在取消并关闭本工具的临时窗口…")

    def scan(self,root=None):
        from .source import discover_library
        roots=[root] if root else list(self.library_roots)
        def find(cancel,progress):
            entries=[]
            for p in roots or [None]:
                if cancel.is_set(): raise RuntimeError('已取消')
                entries.extend(discover_library(p))
            return list({str(e.source.resolve()).casefold():e for e in entries}.values())
        self.run_task(find,self.library_ready)

    def choose_library(self):
        p=QFileDialog.getExistingDirectory(self,"选择 Wallpaper Engine Workshop 库")
        if p: self.library_path.setEditText(p); self.add_library_path()

    def add_library_path(self):
        from .source import normalize_library_root
        text=self.library_path.currentText().strip().strip('"')
        if not text: return
        path=normalize_library_root(Path(text))
        if not path.is_dir(): self.status.setText('路径不存在，请重新选择'); return
        text=str(path)
        if text.casefold() not in [p.casefold() for p in self.library_roots]: self.library_roots.append(text)
        self.preferences.setValue('library_roots',self.library_roots)
        self.library_path.clear();self.library_path.addItems(self.library_roots);self.library_path.setCurrentText(text)
        self.scan()

    def remove_library_path(self):
        text=self.library_path.currentText()
        self.library_roots=[p for p in self.library_roots if p!=text]
        self.preferences.setValue('library_roots',self.library_roots)
        self.library_path.clear();self.library_path.addItems(self.library_roots);self.scan()

    def library_ready(self,entries):
        self.entries=entries
        self.tag_filter.blockSignals(True);self.tag_filter.clear();self.tag_filter.addItem('全部标签')
        self.tag_filter.addItems(sorted({t for e in entries for t in e.tags}));self.tag_filter.blockSignals(False)
        self.filter_library(); self.progress.setValue(100);self.status.setText(f"扫描完成 · {len(entries)} 个项目")

    def filter_library(self,*args):
        self.library_list.clear(); query=self.search.text().casefold()
        kind={1:"scene",2:"video",3:"web"}.get(self.type_filter.currentIndex())
        for entry in self.entries:
            rating={1:'Everyone',2:'Questionable',3:'Mature',4:'Unknown'}.get(self.rating_filter.currentIndex())
            if rating and entry.content_rating.casefold()!=rating.casefold(): continue
            if self.tag_filter.currentIndex()>0 and self.tag_filter.currentText() not in entry.tags: continue
            if kind and entry.kind != kind: continue
            if query and query not in (entry.title+str(entry.source)+' '.join(entry.tags)).casefold(): continue
            labels={"scene":"SCENE / PKG","video":"VIDEO","web":"WEB"}
            level={'Everyone':'全年龄','Questionable':'需留意','Mature':'18+','Unknown':'未标注'}.get(entry.content_rating,entry.content_rating)
            badge=level+'  ·  '+(' / '.join(entry.tags[:2]) or '无标签')
            item=QListWidgetItem(f"{entry.title}\n{labels.get(entry.kind,'未知类型')}  ·  {entry.source.name}\n{badge}")
            item.setData(Qt.ItemDataRole.UserRole,entry)
            item.setToolTip(str(entry.source)+'\n分级：'+entry.content_rating+'\n标签：'+' / '.join(entry.tags))
            if entry.preview and entry.preview.exists():
                key=str(entry.preview)
                icon=self.thumbnail_cache.get(key)
                if icon is None:
                    reader=QImageReader(key);reader.setAutoTransform(True)
                    reader.setScaledSize(reader.size().scaled(96,64,Qt.AspectRatioMode.KeepAspectRatio))
                    icon=QIcon(QPixmap.fromImage(reader.read()));self.thumbnail_cache[key]=icon
                    if len(self.thumbnail_cache)>512: self.thumbnail_cache.pop(next(iter(self.thumbnail_cache)))
                item.setIcon(icon)
            self.library_list.addItem(item)
        self.count_label.setText(f"显示 {self.library_list.count()} / {len(self.entries)}")

    def select_entry(self,current,previous):
        if current is None: return
        if self.worker and self.worker.isRunning(): return
        if self.stop_live(lambda:self.select_entry(current,previous)): return
        self.video=None; self.info={}; self.timestamps=[]
        self.orientation_crops.clear()
        self.range_timeline.set_duration(0)
        self.player.stop(); self.timeline.setRange(0,0); self.export_button.setEnabled(False)
        self.entry=current.data(Qt.ItemDataRole.UserRole)
        self.load_wallpaper_properties()
        self.inspector_tabs.setCurrentIndex(1 if self.entry.kind == "video" else 0)
        self.title.setText(self.entry.title)
        rating={'Everyone':'全年龄','Questionable':'需留意','Mature':'18+','Unknown':'未标注'}.get(self.entry.content_rating,self.entry.content_rating)
        self.metadata_label.setText('分级：'+rating+'  ·  标签：'+(' / '.join(self.entry.tags) or '未标注'))
        self.record_button.setEnabled(self.entry.kind in ("scene","web") and not(self.worker and self.worker.isRunning()))
        self.preview_button.setEnabled(self.record_button.isEnabled())
        self.resource_button.setEnabled(self.entry.kind == "scene" and not(self.worker and self.worker.isRunning()))
        self.canvas.pixmap=QPixmap();self.canvas.update()
        if self.entry.kind == "video": self.load_video(self.entry.wallpaper_file or self.entry.source)
        else:
            self.video=None; self.timestamps=[]; self.timeline.setRange(0,0); self.export_button.setEnabled(False)
            self.frame_label.setText("先录制场景；完整渲染由 Wallpaper Engine 执行")
            self.range_timeline.setEnabled(False)
            self.selection_label.setText('实时场景没有视频时间轴 · 录制后可点播、逐帧与选片段')
            if self.auto_preview.isChecked(): QTimer.singleShot(0,self.preview_scene)

    def import_file(self):
        p,_=QFileDialog.getOpenFileName(self,"导入壁纸或视频",filter="素材 (*.pkg *.json *.mp4 *.webm *.mkv *.mov *.avi);;所有文件 (*)")
        if p: self.add_source(Path(p))

    def import_folder(self):
        p=QFileDialog.getExistingDirectory(self,"导入完整壁纸项目")
        if p: self.add_source(Path(p))

    def add_source(self,path):
        if self.worker and self.worker.isRunning():
            self.note("正在处理任务，请任务结束后导入。"); return
        from .source import discover_library
        if path.is_dir():
            entries=discover_library(path)
            if not entries:
                self.note("目录没有可识别的壁纸项目。"); return
            self.entries.extend(entries)
        elif path.suffix.lower() in (".pkg",".json"):
            kind="scene"; title=path.stem
            if path.suffix.lower()==".json":
                try:
                    data=json.loads(path.read_text(encoding="utf-8-sig")); kind=str(data.get("type","scene")).lower(); title=data.get("title",title)
                except Exception as exc: self.note(str(exc)); return
            if path.name.lower()=="project.json":
                projects=discover_library(path.parent)
                if not projects: self.note("项目主文件缺失或类型未支持。"); return
                self.entries.extend(projects)
            else:
                self.entries.append(WallpaperEntry(path,title,kind,None,path))
        else: self.entries.append(WallpaperEntry(path,path.stem,"video",None,path))
        self.search.clear(); self.type_filter.setCurrentIndex(0); self.filter_library(); self.library_list.setCurrentRow(self.library_list.count()-1)

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()

    def dropEvent(self,event):
        for url in event.mimeData().urls():
            if url.isLocalFile(): self.add_source(Path(url.toLocalFile()))

    def load_video(self,path,staged=False):
        from .media import prepare_preview
        from .source import stage_project,hash_manifest,verify_manifest
        edge,fps=self.preview_profile()
        def load(cancel,progress):
            progress(5,"复制素材并验证源文件…")
            target=path
            if not staged:
                key=str(Path(path).resolve())
                hit=self.video_jobs.get(key)
                valid=False
                if hit and hit[0].is_file() and hash_manifest(path,cancel)==hit[1]:
                    try: verify_manifest(hit[0],hit[1],cancel);valid=True
                    except RuntimeError: pass
                if valid: target=hit[0]
                else:
                    root=stage_project(path,self.workspace,cancel=cancel)
                    target=root/path.name
                    manifest=json.loads((root.parent/'source-manifest.json').read_text(encoding='utf-8'))
                    self.video_jobs[key]=(target,manifest)
            if cancel.is_set(): raise RuntimeError("已取消")
            return prepare_preview(target,self.workspace/'proxies',edge,fps,cancel,progress)
        self.run_task(load,self.video_ready)

    def video_ready(self,result):
        self.video,self.info,self.timestamps=result[:3]
        self.playback_proxy=result[3] if len(result)>3 else self.video
        self.last_display=0
        self.player.setSource(QUrl.fromLocalFile(str(self.playback_proxy)))
        self.timeline.setRange(0,max(0,len(self.timestamps)-1)); self.timeline.setValue(0)
        self.start.setValue(0); self.end.setValue(self.info["duration"])
        self.cover.setValue(min(1.5,self.info["duration"]/2)); self.update_size()
        from .ui import update_media_window
        update_media_window(self)
        self.inspector_tabs.setCurrentIndex(1)
        self.range_timeline.setEnabled(True);self.progress.setValue(100)
        if self.saved_record_crop is not None:
            self.canvas.crop=QRectF(self.saved_record_crop);self.canvas.update();self.saved_record_crop=None
        self.status.setText(f"已加载 · {self.info['width']} × {self.info['height']} · {len(self.timestamps)} 帧")
        self.preview_frame()

    def frame_changed(self,index):
        if not self.timestamps: return
        self.frame_label.setText(f"帧 {index+1} / {len(self.timestamps)}     {self.timestamps[index]:.3f} s     源像素 {self.info['width']} × {self.info['height']}")
        self.seek_timer.start()
        if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState:
            self.player.setPosition(round(self.timestamps[index]*1000))

    def playback_frame(self,frame):
        if self.player.playbackState()!=QMediaPlayer.PlaybackState.PlayingState or not self.timestamps:
            return
        now=time.monotonic()
        if now-self.last_display < 1/self.preview_profile()[1]: return
        self.last_display=now
        image=frame.toImage()
        if image.isNull(): return
        edge=self.preview_profile()[0]
        if max(image.width(),image.height())>edge:
            image=image.scaled(edge,edge,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.FastTransformation)
        self.canvas.pixmap=QPixmap.fromImage(image); self.canvas.update()
        timestamp=max(0,frame.startTime()/1e6)
        index=max(0,min(len(self.timestamps)-1,bisect.bisect_right(self.timestamps,timestamp)-1))
        self.timeline.blockSignals(True); self.timeline.setValue(index); self.timeline.blockSignals(False)
        self.frame_changed_label(index)

    def preview_frame(self):
        if not self.video or not self.timestamps: return
        if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState: return
        if self.preview_worker and self.preview_worker.isRunning():
            self.pending_frame=self.timeline.value(); self.preview_worker.cancel.set();return
        from .media import extract_preview_frame
        index=self.timeline.value(); source=self.video
        timestamps=list(self.timestamps)
        output=self.workspace/"preview"/f"preview-{time.time_ns()}.png"
        w,h=self.info["width"],self.info["height"]
        factor=min(1,self.preview_profile()[0]/max(w,h))
        settings=EditSettings(width=max(1,round(w*factor)),height=max(1,round(h*factor)),fit="stretch")
        self.preview_worker=Task(lambda cancel,progress:extract_preview_frame(source,output,index,settings,timestamps,cancel),self)
        def show(path):
            if self.video == source and self.timeline.value()==index:
                self.canvas.set_image(path); self.frame_changed_label(index)
            Path(path).unlink(missing_ok=True)
        self.preview_worker.result.connect(show)
        worker=self.preview_worker
        worker.error.connect(lambda message:self.note(message) if not worker.cancel.is_set() else None)
        self.preview_worker.finished.connect(self.preview_done); self.preview_worker.start()

    def frame_changed_label(self,index):
        if index < len(self.timestamps):
            self.range_timeline.set_playhead(self.timestamps[index])
            self.frame_label.setText(f"帧 {index+1} / {len(self.timestamps)}     {self.timestamps[index]:.3f} s     源像素 {self.info['width']} × {self.info['height']}")

    def preview_done(self):
        worker=self.preview_worker
        self.preview_worker=None
        if worker: worker.deleteLater()
        if self.pending_frame is not None and not self._close_pending:
            self.pending_frame=None; self.seek_timer.start()

    def preview_profile(self):
        return [(640,15),(960,24),(1280,30)][self.preview_quality.currentIndex()]

    def change_preview_quality(self,index):
        self.preferences.setValue('preview_quality',index)
        if self.worker and self.worker.isRunning(): return
        if self.video:
            self.saved_record_crop=QRectF(self.canvas.crop)
            self.load_video(self.video,staged=True)
        elif self.live_worker: self.preview_scene()

    def move_frame(self,delta):
        self.player.pause(); self.play_timer.stop(); self.timeline.setValue(max(0,min(self.timeline.maximum(),self.timeline.value()+delta)))

    def seek_time(self,seconds):
        if not self.timestamps: return
        self.player.pause();self.play_timer.stop()
        index=max(0,min(len(self.timestamps)-1,bisect.bisect_right(self.timestamps,seconds)-1))
        self.player.setPosition(round(self.timestamps[index]*1000))
        self.timeline.setValue(index);self.frame_changed_label(index);self.seek_timer.start()

    def next_frame(self):
        if self.timeline.value()>=self.timeline.maximum(): self.play_timer.stop(); return
        if not(self.preview_worker and self.preview_worker.isRunning()): self.timeline.setValue(self.timeline.value()+1)

    def toggle_play(self):
        if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause(); self.preview_frame()
        elif self.timestamps:
            self.player.setPosition(round(self.timestamps[self.timeline.value()]*1000)); self.player.play()

    def set_cover(self):
        if self.timestamps: self.cover.setValue(self.timestamps[self.timeline.value()])

    def set_endpoint(self,is_start):
        if self.timestamps:
            value=self.timestamps[self.timeline.value()]
            (self.start if is_start else self.end).setValue(value)

    def update_size(self,*args):
        ratio=["device","original","4:3","16:9","16:10","3:2","9:16","custom"][self.ratio.currentIndex()]
        resolution=["device","2K","4K","8K","custom"][self.resolution.currentIndex()]
        custom=(self.output_width.value(),self.output_height.value())
        original=(self.info.get("width",3840),self.info.get("height",2160))
        if ratio not in ("device","original","custom") and resolution=="device":
            resolution="4K"  # Ratio-only presets need a concrete long-edge pixel size.
        w,h=output_size(ratio,"portrait" if self.orientation.currentIndex() else "landscape",resolution,custom,original)
        self.output_width.blockSignals(True); self.output_height.blockSignals(True)
        self.output_width.setValue(w); self.output_height.setValue(h)
        self.output_width.blockSignals(False); self.output_height.blockSignals(False); self.reset_crop()
        self.update_output_summary()

    def change_orientation(self,index):
        self.orientation_crops[1-index]=QRectF(self.canvas.crop)
        self.update_size()
        if index in self.orientation_crops: self.canvas.crop=QRectF(self.orientation_crops[index]); self.canvas.update()

    def reset_crop(self,*args):
        w,h=self.info.get("width",3840),self.info.get("height",2160)
        target=self.output_width.value()/self.output_height.value(); source=w/h
        cw,ch=(target/source,1) if source>target else (1,source/target)
        self.canvas.crop=QRectF((1-cw)/2,(1-ch)/2,cw,ch)
        self.canvas.active_crop=self.fit.currentIndex()==0 and not self.rotation_adaptive.isChecked(); self.configure_rotation()
        self.canvas.update()

    def edit_settings(self):
        if self.rotation_adaptive.isChecked():
            edge=max(self.output_width.value(),self.output_height.value())
            width,height=scaled_size(edge,edge,self.multiplier(self.output_multiplier,self.output_multiplier_custom))
            return EditSettings(width=width,height=height,fit='adaptive',start=self.start.value(),end=self.end.value(),cover=self.cover.value(),fps=int(self.export_fps.currentText()),anchor_x=self.adaptive_x.value()/100,anchor_y=self.adaptive_y.value()/100,zoom=self.adaptive_zoom.value()/100)
        crop=normalized_crop(self.canvas.crop,self.info["width"],self.info["height"]) if self.fit.currentIndex()==0 else None
        width,height=scaled_size(self.output_width.value(),self.output_height.value(),self.multiplier(self.output_multiplier,self.output_multiplier_custom))
        return EditSettings(width=width,height=height,
                            fit=["crop","contain","stretch"][self.fit.currentIndex()],crop=crop,
                            start=self.start.value(),end=self.end.value(),cover=self.cover.value(),fps=int(self.export_fps.currentText()))

    def open_engine_settings(self):
        from .source import engine_path
        engine=engine_path()
        if engine:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(engine)))
            self.note('在 Wallpaper Engine 的设置 → 性能中选择引擎 FPS 与画质。此处是引擎全局设置，与本工具采集 FPS 独立。')
        else: self.task_error('未找到 Wallpaper Engine')

    @staticmethod
    def multiplier(box, custom):
        return custom.value() if box.currentText()=='自定义' else int(box.currentText().replace('×',''))

    def update_output_summary(self,*args):
        self.output_multiplier_custom.setVisible(self.output_multiplier.currentText()=='自定义')
        if getattr(self.canvas,'ipad_profile',False):
            self.update_ipad_summary();return
        try:
            width,height=self.output_width.value(),self.output_height.value()
            if self.rotation_adaptive.isChecked(): width=height=max(width,height)
            width,height=scaled_size(width,height,self.multiplier(self.output_multiplier,self.output_multiplier_custom))
            self.pixel_summary.setText(f'{width} × {height} px · 最终输出')
        except ValueError as exc: self.pixel_summary.setText(str(exc))
        self.pixel_summary.setWordWrap(True)

    def update_render_summary(self,*args):
        self.render_multiplier_custom.setVisible(self.render_multiplier.currentText()=='自定义')
        multiplier=self.multiplier(self.render_multiplier,self.render_multiplier_custom)
        try:
            width,height=scaled_size(self.capture_width.value(),self.capture_height.value(),multiplier)
            self.render_size_label.setText(f'{width} × {height} · 原生采集\n像素开销约 {multiplier**2} 倍；实际 FPS 见录制报告')
        except ValueError as exc: self.render_size_label.setText(str(exc))

    def configure_rotation(self,*args):
        enabled=self.rotation_adaptive.isChecked()
        self.rotation_controls.setVisible(enabled)
        self.orientation.setEnabled(not enabled);self.fit.setEnabled(not enabled)
        self.composition_form.setRowVisible(self.orientation,not enabled)
        self.composition_form.setRowVisible(self.fit,not enabled)
        self.composition_help.setVisible(not enabled);self.scale_help.setVisible(not enabled)
        self.canvas.active_crop=self.fit.currentIndex()==0 and not enabled
        if enabled:
            ratio=min(self.output_width.value(),self.output_height.value())/max(self.output_width.value(),self.output_height.value())
            if args and type(args[0]) is bool and args[0]:
                self.adaptive_zoom.setValue(max(25,round(ratio*100)))
            self.canvas.adaptive=(self.adaptive_zoom.value()/100,self.adaptive_x.value()/100,self.adaptive_y.value()/100,ratio,self.rotation_view.currentIndex())
        else: self.canvas.adaptive=None
        self.canvas.update();self.update_output_summary()

    def export_variants(self):
        settings=self.edit_settings()
        return {'adaptive' if self.rotation_adaptive.isChecked() else 'portrait' if self.orientation.currentIndex() else 'landscape':settings}

    def load_wallpaper_properties(self):
        from .properties import read_properties, SUPPORTED
        while self.property_form.rowCount(): self.property_form.removeRow(0)
        self.property_controls={}
        try: self.property_schema=read_properties(self.entry.source)
        except Exception as exc:
            self.property_schema={};self.note(str(exc))
        self.property_note.setText('选项来自壁纸作者。更改后应用到预览；录制自动使用这些值。条件关联由引擎处理。' if self.property_schema else '这个项目未开放部件选项；不会虚构粒子或模型开关。')
        for key,p in self.property_schema.items():
            kind=p.get('type');value=p.get('value')
            label=p.get('text',key)
            if label.startswith('ui_'): label={'schemecolor':'主题颜色'}.get(key,key)
            if kind not in SUPPORTED:
                self.property_form.addRow(label,QLabel('作者说明：'+str(value or p.get('text',''))));continue
            if kind=='bool':
                control=QCheckBox();control.setChecked(bool(value))
            elif kind=='slider':
                control=QDoubleSpinBox();control.setDecimals(min(6,max(0,int(p.get('precision',2 if p.get('fraction') else 0)))))
                control.setRange(float(p.get('min',0)),float(p.get('max',100)))
                control.setSingleStep(float(p.get('step',.01 if p.get('fraction') else 1)))
                control.setValue(float(value or 0))
            elif kind=='combo':
                control=QComboBox()
                for option in p.get('options',[]): control.addItem(str(option.get('label',option.get('value'))),option.get('value'))
                control.setCurrentIndex(control.findData(value))
            else:
                control=QLineEdit(str(value or ''))
            control.setToolTip(key+(' · 条件：'+p['condition'] if p.get('condition') else ''))
            self.property_controls[key]=control
            self.property_form.addRow(label,control)
            if kind in ('file','directory','color'):
                button=QPushButton('选择颜色…' if kind=='color' else '选择路径…')
                button.clicked.connect(lambda checked=False,c=control,k=kind:self.choose_property_value(c,k))
                self.property_form.addRow('',button)

    def choose_property_value(self,control,kind):
        if kind=='color':
            try: color=QColor.fromRgbF(*map(float,control.text().split()))
            except Exception: color=QColor('white')
            color=QColorDialog.getColor(color,self)
            if color.isValid(): control.setText(' '.join(f'{v:.6f}' for v in (color.redF(),color.greenF(),color.blueF())))
        elif kind=='directory':
            path=QFileDialog.getExistingDirectory(self,'选择部件目录')
            if path: control.setText(path)
        else:
            path,_=QFileDialog.getOpenFileName(self,'选择部件文件')
            if path: control.setText(path)

    def wallpaper_properties(self):
        from .properties import validate_values
        values={}
        for key,control in self.property_controls.items():
            kind=self.property_schema[key]['type']
            values[key]=control.isChecked() if kind=='bool' else control.value() if kind=='slider' else control.currentData() if kind=='combo' else control.text()
        return validate_values(self.property_schema,values)

    def apply_wallpaper_properties(self):
        try: values=self.wallpaper_properties()
        except ValueError as exc: self.task_error(str(exc));return
        if self.live_worker and self.live_worker.isRunning():
            self.live_commands.put(values);self.status.setText('正在应用壁纸部件选项…')
        elif self.entry and self.entry.kind in ('scene','web'): self.preview_scene()

    def reset_wallpaper_properties(self):
        if self.entry: self.load_wallpaper_properties();self.apply_wallpaper_properties()

    def record(self):
        if not self.entry: return
        if self.stop_live(self.record): return
        self.saved_record_crop=QRectF(self.canvas.crop)
        from .capture import capture_scene
        from .source import assert_output_outside_source
        source=self.entry.wallpaper_file or self.entry.source
        try: assert_output_outside_source(source,self.workspace)
        except Exception as exc: self.task_error(str(exc)); return
        try:
            width,height=scaled_size(self.capture_width.value(),self.capture_height.value(),self.multiplier(self.render_multiplier,self.render_multiplier_custom))
            settings=CaptureSettings(width,height,int(self.capture_fps.currentText()),self.capture_seconds.value(),self.capture_wait.value(),self.wallpaper_properties())
        except Exception as exc: self.task_error(str(exc)); return
        output=self.workspace/f"capture-{time.time_ns()}"/"capture.mp4"
        def done(result):
            self.note("采集报告："+json.dumps(result,ensure_ascii=False,default=str))
            # Wait for QThread finished signal before starting a second long task.
            QTimer.singleShot(80,lambda:self.load_video(output,staged=True))
        self.run_task(lambda cancel,progress:capture_scene(source,output,settings,cancel,progress),done)

    def stop_live(self, after=None):
        if self.live_worker and self.live_worker.isRunning():
            self.after_live_stop=after
            self.live_worker.cancel.set()
            self.status.setText("正在关闭本工具的实时预览窗口…")
            return True
        return False

    def toggle_live_preview(self, enabled):
        self.preferences.setValue('auto_preview',enabled)
        if not enabled: self.stop_live()
        elif self.entry and self.entry.kind in ('scene','web') and not self.video:
            QTimer.singleShot(0,self.preview_scene)

    def preview_scene(self):
        if not self.entry or self.entry.kind not in ('scene','web'): return
        if self.worker and self.worker.isRunning(): return
        try: properties=self.wallpaper_properties()
        except ValueError as exc: self.task_error(str(exc)); return
        if self.stop_live(self.preview_scene): return
        # Restarting the engine replaces recorded-media mode, not just its image.
        self.player.stop();self.video=None;self.timestamps=[]
        self.timeline.setRange(0,0);self.range_timeline.set_duration(0)
        self.range_timeline.setEnabled(False);self.export_button.setEnabled(False)
        self.selection_label.setText('实时场景没有视频时间轴 · 录制后可点播、逐帧与选片段')
        from .preview import live_scene
        source=self.entry.wallpaper_file or self.entry.source
        edge,fps=self.preview_profile()
        scale=min(1,edge/max(self.capture_width.value(),self.capture_height.value()))
        settings=CaptureSettings(round(self.capture_width.value()*scale),round(self.capture_height.value()*scale),
                                 min(15,fps),1,self.capture_wait.value(),properties)
        self.live_commands=queue.SimpleQueue()
        self.live_frames.clear()
        self.live_worker=Task(lambda cancel,progress:live_scene(source,self.workspace,settings,cancel,
                               lambda frame:self.live_frames.update(frame=frame),
                               lambda text:progress(0,text),self.live_commands),self)
        self.live_worker.progress.connect(lambda value,text:self.status.setText(text))
        self.live_worker.error.connect(self.live_error)
        self.live_worker.finished.connect(self.live_finished)
        self.frame_label.setText("正在连接真实引擎画面 · 不是缩略图")
        self.progress.setValue(0)
        self.cancel_button.setEnabled(True)
        self.live_worker.start()

    def live_error(self,message):
        self.note(message)
        self.status.setText("实时预览失败 · 展开任务日志查看原因")
        self.frame_label.setText(message.splitlines()[0][:160])
        self.log_toggle.setChecked(True)

    def show_live_frame(self):
        frame=self.live_frames.pop('frame',None)
        if not frame: return
        pixels,width,height=frame
        image=QImage(pixels,width,height,width*4,QImage.Format.Format_ARGB32).copy()
        first=self.canvas.pixmap.isNull()
        self.canvas.pixmap=QPixmap.fromImage(image)
        self.info={'width':width,'height':height}
        if first:
            self.reset_crop()
            self.raise_();self.activateWindow()
        self.canvas.update()
        self.frame_label.setText(f"Wallpaper Engine 实时渲染 · {width} × {height} · 预览采集最高 15 fps")

    def live_finished(self):
        if not (self.worker and self.worker.isRunning()): self.cancel_button.setEnabled(False)
        worker=self.live_worker;self.live_worker=None
        if worker: worker.deleteLater()
        self.live_frames.clear()
        after=self.after_live_stop;self.after_live_stop=None
        if self._close_pending: self.close()
        elif after: QTimer.singleShot(0,after)

    def extract(self):
        if not self.entry: return
        from .capture import extract_resources
        source=self.entry.wallpaper_file or self.entry.source
        out=self.output_dir/f"resources-{time.time_ns()}"
        self.run_task(lambda cancel,progress:extract_resources(source,out,cancel,progress),self.export_done)

    def choose_output(self):
        p=QFileDialog.getExistingDirectory(self,"选择导出目录",str(self.output_dir))
        if p:
            try: self.set_output_directory(Path(p))
            except Exception as exc: self.task_error(str(exc))

    def set_output_directory(self,path):
        from .source import assert_output_outside_source
        path=Path(path).expanduser().resolve()
        if self.entry: assert_output_outside_source(self.entry.source,path)
        path.mkdir(parents=True,exist_ok=True)
        self.output_dir=path;self.preferences.setValue('output_dir',str(path))
        self.output_path_label.setText(str(path));self.output_path_label.setToolTip(str(path))
        self.note(f"导出目录：{path}")

    def apply_ipad_preset(self):
        self.ipad_package.setCurrentIndex(2)
        self.format_box.setCurrentIndex(5)
        self.ipad_format_changed(5)
        self.inspector_tabs.setCurrentIndex(2)

    def update_ipad_summary(self):
        static=self.ipad_package.currentIndex()==3
        multiplier=self.ipad_multiplier.currentIndex()+1 if static else 1
        self.ipad_multiplier.setEnabled(static)
        edge=2420*multiplier
        self.pixel_summary.setText(f'{edge} × {edge} px · 插值尺寸，非无损细节恢复')
        self.export_note.setText('等比例满屏；保留人物比例。\n只输出一个最终文件：静态 PNG 或所选动态文件。\n锐化增强边缘，不恢复丢失细节。\n预览保持低分辨率，锐化在最终导出应用。\niPad 动态识别尚未通过。')
        if self.info.get('width') and self.info.get('height'):
            from .ipad_export import ipad_composition
            try:
                layout=ipad_composition((self.info['width'],self.info['height']),multiplier=multiplier,anchor=(self.ipad_x.value()/100,self.ipad_y.value()/100))
                fw,fh=layout['foreground_size'];sw,sh=layout['source_size']
                self.pixel_summary.setText(self.pixel_summary.text()+f'\n源裁切约 {edge*sw/fw:.0f} × {edge*sh/fh:.0f}；放大 {fw/sw:.2f}×')
            except ValueError as exc:self.pixel_summary.setText(str(exc))

    def update_ipad_preview(self,*args):
        self.canvas.ipad_options={'fit':'crop','anchor':(self.ipad_x.value()/100,self.ipad_y.value()/100)}
        self.canvas.ipad_view=self.ipad_view.currentIndex()
        if getattr(self.canvas,'ipad_profile',False):self.update_ipad_summary()
        self.canvas.update()

    def ipad_format_changed(self,index):
        self.canvas.ipad_profile=index==5
        self.ipad_controls.setVisible(index==5)
        self.update_ipad_preview()
        for control in (self.ratio,self.orientation,self.resolution,self.fit,self.output_multiplier,self.output_multiplier_custom,self.output_width,self.output_height,self.rotation_adaptive):
            control.setEnabled(index!=5)
        if index==5:
            self.rotation_adaptive.setChecked(False)
            self.export_fps.setCurrentText('60')
            self.export_note.setText('2420 × 2420 · 满屏，不缩成小图\n人物保持比例；只裁切画面边缘。\n按实测坐标对齐主体，可调整位置。\n只输出一个最终文件；设备识别待验证。')
            self.update_ipad_summary()
        else:
            self.export_note.setText('每次导出创建独立文件夹。\n原始素材保持不变。')
            self.update_output_summary()
        self.canvas.active_crop=index!=5 and self.fit.currentIndex()==0 and not self.rotation_adaptive.isChecked()
        self.canvas.update()

    def export(self):
        if not self.video: return
        if self.format_box.currentIndex()==5:
            from .ipad_export import export_ipad
            try:
                from .source import assert_output_outside_source
                if self.entry: assert_output_outside_source(self.entry.source,self.output_dir)
                settings=EditSettings(start=self.start.value(),end=self.end.value(),cover=self.cover.value(),fps=60)
            except Exception as exc:self.task_error(str(exc));return
            source=self.video;folder=self.output_dir/f'ipad-export-{time.time_ns()}'
            options=dict(self.canvas.ipad_options);package=('heic','livp','honor','png')[self.ipad_package.currentIndex()]
            options['multiplier']=self.ipad_multiplier.currentIndex()+1 if package=='png' else 1
            options['sharpen']=(0,.35,.6)[self.ipad_sharpen.currentIndex()]
            work_root=self.workspace/'ipad-export'
            self.run_task(lambda cancel,progress:{'ipad':export_ipad(source,folder,settings,cancel,progress,work_root=work_root,package=package,**options)},self.export_done)
            return
        from .media import extract_frame,export_frames,export_video,export_gif
        from .livephoto import export_live_photo
        from .source import assert_output_outside_source
        try:
            if self.entry: assert_output_outside_source(self.entry.source,self.output_dir)
            variants=self.export_variants()
            settings=next(iter(variants.values()))
            if settings.end is None or settings.end<=settings.start: raise ValueError("终点必须晚于起点")
            index=self.timeline.value(); mode=self.format_box.currentIndex(); source=self.video
            if mode in (3,4) and any(v.width%2 or v.height%2 for v in variants.values()):
                raise ValueError("H.264 要求偶数像素。请明确调整输出宽高后再导出。")
        except Exception as exc: self.task_error(str(exc)); return
        folder=self.output_dir/f"export-{time.time_ns()}"
        interval=self.interval.value()
        timestamps=list(self.timestamps)
        property_snapshot={}
        report=source.parent/(source.name+'.capture.json')
        if report.is_file():
            try: property_snapshot=json.loads(report.read_text(encoding='utf-8')).get('properties',{})
            except (ValueError,OSError): pass
        rotation_metadata=None
        if self.rotation_adaptive.isChecked():
            factor=self.multiplier(self.output_multiplier,self.output_multiplier_custom)
            rotation_metadata=rotation_regions(max(self.output_width.value(),self.output_height.value())*factor,min(self.output_width.value(),self.output_height.value())*factor)
        def job(cancel,progress):
            folder.mkdir(parents=True,exist_ok=False)
            results={}
            for orientation,settings in variants.items():
                target=folder/orientation if len(variants)>1 else folder
                target.mkdir(parents=True,exist_ok=True)
                if mode==0: result=extract_frame(source,target/"frame.png",index,settings,cancel)
                elif mode==1:
                    indices=[]; next_time=settings.start
                    for i,t in enumerate(timestamps):
                        if t >= next_time and t < settings.end:
                            indices.append(i); next_time=t+interval
                    result=export_frames(source,target,indices,settings,cancel,progress)
                elif mode==2: result=export_gif(source,target/"clip.gif",settings,cancel,progress)
                elif mode==3: result=export_video(source,target/"clip.mp4",settings,cancel,progress)
                else: result=export_live_photo(source,target/"live",settings,cancel,progress)
                (target/"edit.json").write_text(json.dumps(settings.__dict__,ensure_ascii=False,indent=2),encoding="utf-8")
                results[orientation]=result
            (folder/"variants.json").write_text(json.dumps({"variants":{k:v.__dict__ for k,v in variants.items()},"properties":property_snapshot,"rotation_regions":rotation_metadata,"automatic_device_rotation":False},ensure_ascii=False,indent=2),encoding="utf-8")
            return results
        self.run_task(job,self.export_done)

    def export_done(self,result):
        self.progress.setValue(100); self.status.setText("导出完成 · 查看导出目录")
        final_outputs=[value for value in result.values() if isinstance(value,dict) and 'final_file' in value] if isinstance(result,dict) else []
        if final_outputs:
            final=Path(final_outputs[0]['final_file'])
            self.status.setText('导出完成 · 只需使用 '+final.name)
            self.note('最终文件：'+str(final))
        else:self.note("已导出："+str(result))
        pairs=[value for value in result.values() if isinstance(value,dict) and 'photo' in value and 'video' in value] if isinstance(result,dict) else []
        if pairs:
            from .pair_preview import LivePairPreview
            self.status.setText('导出完成 · '+Path(pairs[0]['final_file']).name+' · 苹果相册识别待验证' if pairs[0].get('final_file') else 'Live Photo 配对资源已生成 · 苹果相册识别待验证')
            self.live_pair_preview=LivePairPreview(pairs[0],self.workspace,self)
            self.live_pair_preview.show()

    def open_folder(self,path):
        path.mkdir(parents=True,exist_ok=True); QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def closeEvent(self,event):
        self.after_live_stop=None
        active=[worker for worker in self.findChildren(Task) if worker.isRunning()]
        if active:
            self._close_pending=True
            for worker in active: worker.cancel.set()
            for worker in active: worker.finished.connect(self.close)
            event.ignore(); return
        self.play_timer.stop(); event.accept()
        self.player.stop()


def diagnostics():
    from .media import ffmpeg_path
    from .source import engine_path
    return {"version":__version__,"ffmpeg":str(ffmpeg_path()),"wallpaper_engine":str(engine_path()),"python":sys.version.split()[0]}


def main():
    parser=argparse.ArgumentParser(description="Wallpaper Studio")
    parser.add_argument("--experimental",action="store_true",help="显示未完成设备验收的实验导出入口")
    parser.add_argument("--diagnostics",action="store_true")
    parser.add_argument("--smoke-test",action="store_true")
    parser.add_argument("--screenshot",type=Path)
    parser.add_argument("--ipad-package",choices=("heic","livp","honor","png"),default="heic")
    parser.add_argument("--ipad-multiplier",type=int,choices=(1,2,3),default=1)
    parser.add_argument("--ipad-sharpen",type=float,default=0)
    parser.add_argument("--export-ipad",type=Path,help="打包运行时 iPad 导出验收入口")
    parser.add_argument("--export-frame",type=Path,help="非交互精确静帧导出（输入视频）")
    parser.add_argument("--output",type=Path)
    parser.add_argument("--frame-index",type=int,default=0)
    args=parser.parse_args()
    if args.export_ipad:
        if not args.output:parser.error('--export-ipad requires --output')
        from .ipad_export import export_ipad
        export_ipad(args.export_ipad,args.output,package=args.ipad_package,multiplier=args.ipad_multiplier,sharpen=args.ipad_sharpen)
        return 0
    if args.export_frame:
        from .media import probe,extract_frame
        if not args.output: parser.error("--export-frame requires --output")
        from .source import stage_project,assert_output_outside_source
        assert_output_outside_source(args.export_frame,args.output)
        workspace=Path(os.getenv("LOCALAPPDATA",str(Path.home())))/"WallpaperStudio"/"jobs"
        staged=stage_project(args.export_frame,workspace)/args.export_frame.name
        info=probe(staged)
        extract_frame(staged,args.output,args.frame_index,EditSettings(width=info['width'],height=info['height'],fit='stretch'))
        return 0
    if args.diagnostics:
        payload=json.dumps(diagnostics(),ensure_ascii=False,indent=2)
        if sys.stdout: print(payload)
        (Path(os.getenv("TEMP","."))/"wallpaper-studio-diagnostics.json").write_text(payload,encoding="utf-8")
        return 0
    app=QApplication(sys.argv[:1]); app.setStyle("Fusion"); app.setStyleSheet(THEME)
    window=StudioWindow(scan_on_start=not args.smoke_test,experimental=args.experimental); window.show()
    if args.smoke_test or args.screenshot:
        def snapshot():
            if args.screenshot:
                args.screenshot.parent.mkdir(parents=True,exist_ok=True); window.grab().save(str(args.screenshot))
            if args.smoke_test: window.close(); app.quit()
        QTimer.singleShot(800,snapshot)
    return app.exec()

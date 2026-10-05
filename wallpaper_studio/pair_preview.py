"""Local preview of a Live Photo resource pair, not Apple Photos acceptance."""
from pathlib import Path
from PySide6.QtCore import Qt, QUrl, QSize
from PySide6.QtGui import QPixmap, QImageReader, QDesktopServices
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QStackedWidget
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget

class LivePairPreview(QDialog):
    def __init__(self, pair, workspace, parent=None):
        super().__init__(parent)
        self.setWindowTitle('安卓动态 JPG · 实验预览' if pair.get('android') else 'Live Photo · 配对资源预览')
        self.resize(840,660);self.pair=pair;self.closing=False
        layout=QVBoxLayout(self)
        self.summary=QLabel('本机配对预览 · 苹果相册识别待验证')
        self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.stack=QStackedWidget();layout.addWidget(self.stack,1)
        cover=QLabel();cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reader=QImageReader(str(pair['photo']))
        size=reader.size()
        if size.isValid(): reader.setScaledSize(size.scaled(QSize(768,480),Qt.AspectRatioMode.KeepAspectRatio))
        if pair.get('ipad'):
            from PIL import Image
            from .ipad_export import _register_heif
            from PySide6.QtGui import QImage
            _register_heif()
            with Image.open(pair['photo']) as im:
                im=im.convert('RGBA');im.thumbnail((768,480))
                image=QImage(im.tobytes(),im.width,im.height,im.width*4,QImage.Format.Format_RGBA8888).copy()
            cover.setPixmap(QPixmap.fromImage(image))
        else:cover.setPixmap(QPixmap.fromImage(reader.read()))
        self.stack.addWidget(cover)
        video=QVideoWidget();self.stack.addWidget(video)
        self.player=QMediaPlayer(self);self.player.setVideoOutput(video)
        self.hold=QPushButton('按住预览动态 · 松开回到封面')
        self.hold.setEnabled(False);layout.addWidget(self.hold)
        self.hold.pressed.connect(self.play_motion);self.hold.released.connect(self.show_cover)
        self.status=QLabel('正在后台校验 JPEG + MOV 并生成轻量预览…')
        self.status.setWordWrap(True);layout.addWidget(self.status)
        detail=QLabel(f"静态资源：{Path(pair['photo']).name}\n动态资源：{Path(pair['video']).name}\n两种资源必须作为同一个 Photos 资产导入；单独播放 MOV 显示为视频是正常的。")
        if pair.get('ipad'):detail.setText('只需使用：'+str(pair['final_file'])+'\n原始配对资源与校验文件留在程序任务目录。')
        detail.setWordWrap(True);layout.addWidget(detail)
        folder=QPushButton('打开最终文件目录' if pair.get('ipad') else '打开配对资源目录')
        folder.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(pair.get('final_file',pair['photo'])).parent))))
        layout.addWidget(folder)
        from .app import Task
        from .livephoto import validate_pair
        from .media import prepare_preview
        def prepare(cancel,progress):
            if pair.get('android'):
                from .motionphoto import split_honor
                parsed=split_honor(Path(pair['final_file']).read_bytes())
                report={'android':True,'profile':parsed['profile'],'still_image_time':parsed['cover_ms']/1000}
            elif pair.get('ipad'):
                from .ipad_export import validate_ipad_pair
                report=validate_ipad_pair(pair['photo'],pair['video'])
            else:report=validate_pair(pair['photo'],pair['video'])
            _,_,_,proxy=prepare_preview(pair['video'],Path(workspace)/'live-pair-preview',640,15,cancel,progress)
            return report,proxy
        self.worker=Task(prepare,self)
        self.worker.progress.connect(lambda _,text:self.status.setText(text))
        self.worker.result.connect(self.ready)
        self.worker.error.connect(lambda text:self.status.setText('预览校验失败：'+text))
        self.worker.finished.connect(self.worker_finished)
        self.player.playbackStateChanged.connect(lambda state:self.show_cover() if state==QMediaPlayer.PlaybackState.StoppedState else None)
        self.player.errorOccurred.connect(lambda error,text:self.status.setText('本机预览播放错误：'+text))
        self.worker.start()

    def ready(self,result):
        report,proxy=result
        self.player.setSource(QUrl.fromLocalFile(str(proxy)))
        self.hold.setEnabled(True)
        if report.get('android'):
            self.status.setText(f"JPEG + MP4 长度与封面时间已校验：{report['still_image_time']:.3f} 秒\n荣耀/微信动态开关和苹果 LIVE 识别：待设备测试");return
        self.status.setText(f"资源标识一致：{report['identifier']}\n真实封面时间轨道：{report['still_image_time']:.3f} 秒 · 配对结构已校验\n苹果相册 LIVE 标记与锁屏动态：待设备验证")

    def play_motion(self):
        self.stack.setCurrentIndex(1);self.player.setPosition(0);self.player.play()

    def show_cover(self):
        self.player.pause();self.stack.setCurrentIndex(0)

    def worker_finished(self):
        if self.closing: self.close()

    def closeEvent(self,event):
        self.player.stop()
        if self.worker.isRunning():
            self.closing=True;self.worker.cancel.set();self.hide();event.ignore();return
        event.accept()

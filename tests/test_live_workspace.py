import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import json
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt,QPoint
def test_metadata_and_library_root_normalization(tmp_path):
    from wallpaper_studio.source import discover_library, normalize_library_root
    p=tmp_path/'steamapps/workshop/content/431960/123';p.mkdir(parents=True)
    (p/'scene.pkg').write_bytes(b'pkg')
    (p/'project.json').write_text(json.dumps({'title':'Example','type':'scene','contentrating':'Mature','tags':['Anime','Girls']}))
    assert normalize_library_root(tmp_path)==p.parent
    entry=discover_library(normalize_library_root(tmp_path))[0]
    assert entry.tags==('Anime','Girls') and entry.content_rating=='Mature'
def test_video_seek_pauses_and_updates_player():
    from wallpaper_studio.app import StudioWindow
    app=QApplication.instance() or QApplication([])
    w=StudioWindow(False); w.timestamps=[0,1,2,3];w.info={'duration':4,'width':64,'height':48}
    w.timeline.setRange(0,3);w.range_timeline.set_duration(4)
    from unittest.mock import Mock
    real_player=w.player
    w.player=Mock()
    w.seek_time(2.1)
    assert w.timeline.value()==2
    w.player.setPosition.assert_called_with(2000)
    w.player=real_player
    w.close()
def test_timeline_drag_anywhere():
    from wallpaper_studio.widgets import RangeTimeline
    app=QApplication.instance() or QApplication([])
    w=RangeTimeline();w.resize(600,90);w.set_duration(10);w.show()
    QTest.mousePress(w,Qt.MouseButton.LeftButton,pos=QPoint(200,55))
    QTest.mouseMove(w,QPoint(480,55));QTest.mouseRelease(w,Qt.MouseButton.LeftButton)
    assert w.playhead>7
    w.close()
def test_preview_dimensions():
    from wallpaper_studio.preview import preview_size
    assert preview_size(3840,2160)==(1280,720)
    assert preview_size(1668,2420)==(882,1280)

def test_paths_are_persisted_deduplicated_and_removal_does_not_delete(tmp_path):
    from wallpaper_studio.app import StudioWindow
    from PySide6.QtCore import QSettings
    from unittest.mock import Mock
    app=QApplication.instance() or QApplication([])
    w=StudioWindow(False);w.preferences=QSettings(str(tmp_path/'prefs.ini'),QSettings.Format.IniFormat)
    w.library_roots=[];w.library_path.clear();w.scan=Mock()
    folder=tmp_path/'library';folder.mkdir()
    w.library_path.setEditText(str(folder));w.add_library_path()
    w.library_path.setEditText(str(folder));w.add_library_path()
    assert len(w.library_roots)==1
    assert w.preferences.value('library_roots',type=list)==[str(folder)]
    w.remove_library_path()
    assert folder.is_dir() and w.library_roots==[]
    w.close()

def test_rating_and_tag_filters_can_be_combined(tmp_path):
    from wallpaper_studio.app import StudioWindow
    from wallpaper_studio.models import WallpaperEntry
    app=QApplication.instance() or QApplication([])
    w=StudioWindow(False)
    entries=[WallpaperEntry(tmp_path/'1','A','scene',tags=('Anime',),content_rating='Mature'),
             WallpaperEntry(tmp_path/'2','B','scene',tags=('Nature',),content_rating='Everyone')]
    w.library_ready(entries)
    w.rating_filter.setCurrentIndex(3)
    assert w.library_list.count()==1
    w.tag_filter.setCurrentText('Nature')
    assert w.library_list.count()==0
    w.rating_filter.setCurrentIndex(1)
    assert w.library_list.count()==1
    w.close()

def test_restarting_engine_clears_recorded_video_mode(tmp_path,monkeypatch):
    from wallpaper_studio.app import StudioWindow
    from wallpaper_studio.models import WallpaperEntry
    import wallpaper_studio.preview
    monkeypatch.setattr(wallpaper_studio.preview,'live_scene',lambda *args:None)
    app=QApplication.instance() or QApplication([])
    w=StudioWindow(False);w.entry=WallpaperEntry(tmp_path,'Scene','scene')
    w.video=tmp_path/'recorded.mp4';w.timestamps=[0,.5,1];w.range_timeline.set_duration(1)
    w.preview_scene()
    assert w.video is None and not w.timestamps
    assert not w.range_timeline.isEnabled() and not w.export_button.isEnabled()
    QTest.qWait(100);w.close()

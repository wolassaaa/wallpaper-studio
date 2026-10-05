import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

def test_window_defaults_and_modes():
    from PySide6.QtWidgets import QApplication
    from wallpaper_studio.app import StudioWindow
    app = QApplication.instance() or QApplication([])
    window = StudioWindow(scan_on_start=False)
    assert window.windowTitle() == "Wallpaper Studio"
    assert window.output_width.value() == 2420
    assert window.output_height.value() == 1668
    assert window.format_box.count() == 6
    assert window.capture_fps.currentText() == "30"
    assert hasattr(window, "player")
    assert hasattr(window, "preview_button")
    window.ratio.setCurrentIndex(3)
    assert window.output_width.value() == 3840
    assert window.output_height.value() == 2160
    window.close()

def test_import_video_project_resolves_media(monkeypatch,tmp_path):
    import json
    from PySide6.QtWidgets import QApplication
    from wallpaper_studio.app import StudioWindow
    app=QApplication.instance() or QApplication([])
    (tmp_path/'clip.mp4').write_bytes(b'fixture')
    project=tmp_path/'project.json'
    project.write_text(json.dumps({'type':'video','title':'clip','file':'clip.mp4'}))
    window=StudioWindow(scan_on_start=False)
    monkeypatch.setattr(window,'load_video',lambda path:None)
    window.add_source(project)
    assert window.entry.wallpaper_file==tmp_path/'clip.mp4'
    window.close()

def test_original_output_updates_on_new_video(monkeypatch,tmp_path):
    from PySide6.QtWidgets import QApplication
    from wallpaper_studio.app import StudioWindow
    app=QApplication.instance() or QApplication([])
    window=StudioWindow(scan_on_start=False)
    window.ratio.setCurrentIndex(1)
    monkeypatch.setattr(window,'preview_frame',lambda:None)
    window.video_ready((tmp_path/'clip.mp4',{'width':640,'height':360,'duration':2,'fps':30},[0,1]))
    assert window.output_width.value()==640
    assert window.output_height.value()==360
    window.close()

def test_crop_mapping():
    from PySide6.QtCore import QRectF
    from wallpaper_studio.app import normalized_crop
    assert normalized_crop(QRectF(.25,.25,.5,.5), 400, 200) == (100,50,200,100)

def test_new_source_clears_old_video(monkeypatch,tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication,QListWidgetItem
    from wallpaper_studio.app import StudioWindow
    from wallpaper_studio.models import WallpaperEntry
    app=QApplication.instance() or QApplication([])
    window=StudioWindow(scan_on_start=False)
    window.video=tmp_path/'old.mp4'; window.timestamps=[0,1]; window.info={'width':32,'height':24}
    monkeypatch.setattr(window,'load_video',lambda path:None)
    item=QListWidgetItem('new'); item.setData(Qt.ItemDataRole.UserRole,WallpaperEntry(tmp_path/'new.mp4','new','video'))
    window.select_entry(item,None)
    assert window.video is None
    assert window.timestamps==[]
    assert not window.export_button.isEnabled()
    window.close()

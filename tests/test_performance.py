import threading,os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import Mock
from PySide6.QtWidgets import QApplication
def test_metadata_cache_ignores_task_cancel_identity(tmp_path,monkeypatch):
    from wallpaper_studio import media
    p=tmp_path/'fake.mp4';p.write_bytes(b'x')
    scan=Mock(return_value=({'width':64,'height':48,'duration':1,'fps':30,'frame_count':2},[0,.5]))
    monkeypatch.setattr(media,'_scan',scan)
    media.probe(p,threading.Event());media.frame_timestamps(p,threading.Event())
    assert scan.call_count==1
def test_full_resolution_frames_are_throttled_before_readback():
    from wallpaper_studio.app import StudioWindow
    app=QApplication.instance() or QApplication([])
    w=StudioWindow(False)
    assert hasattr(w,'preview_quality')
    w.preview_quality.blockSignals(True)
    w.preview_quality.setCurrentIndex(0)
    w.preview_quality.blockSignals(False)
    assert w.preview_profile()==(640,15)
    w.close()
def test_export_location_is_persistent(tmp_path):
    from wallpaper_studio.app import StudioWindow
    from PySide6.QtCore import QSettings
    app=QApplication.instance() or QApplication([])
    w=StudioWindow(False);w.preferences=QSettings(str(tmp_path/'pref.ini'),QSettings.Format.IniFormat)
    w.set_output_directory(tmp_path/'exports')
    assert w.output_dir==tmp_path/'exports'
    assert w.preferences.value('output_dir')==str(tmp_path/'exports')
    assert str(w.output_dir) in w.output_path_label.text()
    w.close()
def test_proxy_preserves_original_pts_and_exact_export(tmp_path):
    import subprocess,threading
    from wallpaper_studio import media
    from wallpaper_studio.models import EditSettings
    from PIL import Image
    source=tmp_path/'source.mkv'
    subprocess.run([str(media.ffmpeg_path()),'-y','-f','lavfi','-i','testsrc2=s=320x240:r=30:d=1','-c:v','ffv1',str(source)],check=True,capture_output=True)
    original_info=media.probe(source); original_pts=media.frame_timestamps(source)
    _,info,pts,proxy=media.prepare_preview(source,tmp_path/'preview',128,15,threading.Event())
    assert pts==original_pts and info==original_info
    proxy_info=media.probe(proxy)
    assert proxy_info['width']<=128 and proxy_info['height']<=128
    assert proxy_info['fps']==15
    import unittest.mock
    with unittest.mock.patch.object(media,'_run',side_effect=AssertionError('cached proxy should not decode again')):
        assert media.prepare_preview(source,tmp_path/'preview',128,15,threading.Event())[3]==proxy
        assert media.probe(source,threading.Event())==original_info
    out=media.extract_frame(source,tmp_path/'exact.png',20,EditSettings(width=320,height=240,fit='stretch'),threading.Event())
    assert Image.open(out).size==(320,240)
def test_display_throttle_precedes_expensive_readback():
    import time
    from wallpaper_studio.app import StudioWindow
    from PySide6.QtMultimedia import QMediaPlayer
    app=QApplication.instance() or QApplication([])
    w=StudioWindow(False);real=w.player;w.player=Mock()
    w.player.playbackState.return_value=QMediaPlayer.PlaybackState.PlayingState
    w.timestamps=[0,.5];w.last_display=time.monotonic()
    frame=Mock();w.playback_frame(frame)
    frame.toImage.assert_not_called()
    w.player=real;w.close()

def test_reselect_reuses_verified_staged_copy(tmp_path,monkeypatch):
    from wallpaper_studio.app import StudioWindow
    from PySide6.QtTest import QTest
    from wallpaper_studio import source,media
    app=QApplication.instance() or QApplication([])
    w=StudioWindow(False);w.workspace=tmp_path/'jobs'
    path=tmp_path/'sample.mp4';path.write_bytes(b'first')
    stage=Mock(wraps=source.stage_project);monkeypatch.setattr(source,'stage_project',stage)
    monkeypatch.setattr(media,'prepare_preview',lambda target,*args:(target,{},[],target))
    w.video_ready=Mock()
    def wait():
        for _ in range(100):
            app.processEvents()
            if w.worker is None:return
            QTest.qWait(10)
        raise AssertionError('task did not finish')
    w.load_video(path);wait()
    w.load_video(path);wait();assert stage.call_count==1
    path.write_bytes(b'changed');w.load_video(path);wait();assert stage.call_count==2
    w.close()
def test_fast_preview_matches_absolute_frame(tmp_path):
    import subprocess,threading
    from wallpaper_studio import media
    from wallpaper_studio.models import EditSettings
    from PIL import Image,ImageChops
    source=tmp_path/'seek.mkv'
    subprocess.run([str(media.ffmpeg_path()),'-y','-f','lavfi','-i','testsrc2=s=96x64:r=30:d=1','-c:v','ffv1',str(source)],check=True,capture_output=True)
    pts=media.frame_timestamps(source);settings=EditSettings(width=96,height=64,fit='stretch')
    for index in (0,1,20,29):
        expected=media.extract_frame(source,tmp_path/f'exact{index}.png',index,settings)
        actual=media.extract_preview_frame(source,tmp_path/f'preview{index}.png',index,settings,pts,threading.Event())
        assert ImageChops.difference(Image.open(expected),Image.open(actual)).getbbox() is None

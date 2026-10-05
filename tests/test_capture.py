import threading
import sys
import types
from types import SimpleNamespace

import pytest

from wallpaper_studio import capture


def test_capture_command_targets_only_owned_named_window(tmp_path):
    settings = SimpleNamespace(width=3840, height=2160, fps=30, seconds=10, wait=20)
    cmd = capture.open_command(tmp_path / 'wallpaper64.exe', tmp_path / 'project.json', 'WallpaperStudio-unique', settings)
    assert cmd[1:3] == ['-control', 'openWallpaper']
    assert cmd[cmd.index('-playInWindow') + 1] == 'WallpaperStudio-unique'
    assert '-width' in cmd and '-height' in cmd
    assert '-monitor' not in cmd
    assert capture.close_command(tmp_path / 'wallpaper64.exe', 'WallpaperStudio-unique')[-2:] == ['-location', 'WallpaperStudio-unique']


def test_capture_validates_settings():
    with pytest.raises(ValueError):
        capture.validate_settings(SimpleNamespace(width=0, height=2160, fps=30, seconds=10, wait=20))


def test_capture_cancellation_prevents_launch(tmp_path):
    event = threading.Event()
    event.set()
    with pytest.raises(capture.CancelledError):
        capture.capture_scene(tmp_path, tmp_path / 'record.mp4', SimpleNamespace(width=1,height=1,fps=30,seconds=10,wait=20), event, None)


def test_encoder_command_uses_actual_dimensions_not_requested_resolution(tmp_path):
    command = capture.encoder_command(tmp_path / 'ffmpeg.exe', tmp_path / 'out.mp4', 1920, 1080, 30)
    assert command[command.index('-video_size') + 1] == '1920x1080'
    assert '-vf' not in command
    assert command[command.index('-pixel_format') + 1] == 'bgra'


def fake_wgc(monkeypatch, frame, closes=False):
    class FakeControl:
        def stop(self):
            pass
    class FakeCapture:
        def __init__(self, **kwargs):
            assert kwargs['window_name'].startswith('WallpaperStudio-')
            assert kwargs['monitor_index'] is None
            self.handlers = {}
        def event(self, handler):
            self.handlers[handler.__name__] = handler
            return handler
        def start_free_threaded(self):
            control = FakeControl()
            self.handlers['on_frame_arrived'](frame, control)
            if closes:
                self.handlers['on_closed']()
            return control
    module = types.ModuleType('windows_capture')
    module.WindowsCapture = FakeCapture
    monkeypatch.setitem(sys.modules, 'windows_capture', module)


def test_still_wgc_preserves_captured_dimensions_and_pixels(tmp_path, monkeypatch):
    import numpy as np
    from PIL import Image
    pixels = np.full((17, 23, 4), [0, 0, 255, 255], dtype=np.uint8)
    fake_wgc(monkeypatch, SimpleNamespace(width=23, height=17, frame_buffer=pixels))
    output = tmp_path / 'still.png'
    settings = SimpleNamespace(width=3840,height=2160,fps=30,seconds=10,wait=20)
    result = capture._record_window('WallpaperStudio-test', output, settings, still=True)
    with Image.open(output) as image:
        assert image.size == (23, 17)
        assert image.getpixel((0, 0)) == (255, 0, 0, 255)
    assert result['width'] == 23 and result['height'] == 17
    assert result['encoded_frames'] == 1


def test_wgc_rejects_buffer_dimension_disagreement(tmp_path, monkeypatch):
    import numpy as np
    frame = SimpleNamespace(width=24, height=18, frame_buffer=np.zeros((17,23,4),dtype=np.uint8))
    fake_wgc(monkeypatch, frame)
    settings = SimpleNamespace(width=3840,height=2160,fps=30,seconds=10,wait=20)
    with pytest.raises(RuntimeError, match='buffer'):
        capture._record_window('WallpaperStudio-test', tmp_path / 'still.png', settings, still=True)


def test_cfr_writer_preserves_wall_clock_gaps_and_pads_duration():
    encoded = []
    writer = capture.CfrFrames(encoded.append)
    writer.push(b'red', 0)
    writer.push(b'blue', 3)
    writer.pad(6)
    assert encoded == [b'red', b'red', b'red', b'blue', b'blue', b'blue']
    assert writer.encoded == 6
    assert writer.captured == 2
    assert writer.duplicated == 4


def test_video_rejects_requested_resolution_not_delivered_by_engine(tmp_path, monkeypatch):
    import numpy as np
    fake_wgc(monkeypatch, SimpleNamespace(width=23, height=17, frame_buffer=np.zeros((17,23,4),dtype=np.uint8)))
    settings = SimpleNamespace(width=3840,height=2160,fps=30,seconds=.2,wait=0)
    with pytest.raises(RuntimeError, match='requested'):
        capture._record_window('WallpaperStudio-test', tmp_path / 'video.mp4', settings)


def test_early_window_close_is_not_padded_into_success(tmp_path, monkeypatch):
    import numpy as np
    fake_wgc(monkeypatch, SimpleNamespace(width=24, height=18, frame_buffer=np.zeros((18,24,4),dtype=np.uint8)), closes=True)
    settings = SimpleNamespace(width=24,height=18,fps=30,seconds=10,wait=0)
    with pytest.raises(RuntimeError, match='closed'):
        capture._record_window('WallpaperStudio-test', tmp_path / 'video.mp4', settings)


def test_real_ffmpeg_cfr_static_capture_has_requested_duration(tmp_path, monkeypatch):
    import numpy as np
    from wallpaper_studio.media import probe
    fake_wgc(monkeypatch, SimpleNamespace(width=24,height=18,frame_buffer=np.full((18,24,4),255,dtype=np.uint8)))
    settings = SimpleNamespace(width=24,height=18,fps=30,seconds=.2,wait=0)
    output = tmp_path / 'static.mp4'
    result = capture._record_window('WallpaperStudio-test', output, settings)
    actual = probe(output)
    assert actual['width'] == 24 and actual['height'] == 18
    assert actual['duration'] == pytest.approx(.2, abs=.02)
    assert result['encoded_frames'] == 6
    assert result['captured_frames'] == 1
    assert result['duplicated_frames'] == 5


def test_geometry_crop_matches_verified_window_or_dwm_bounds_only():
    geometry = {'window':(0,0,656,399),'client':(8,31,648,391),'dwm':(7,0,649,392)}
    assert capture.capture_region((656,399), geometry) == (8,31,640,360)
    assert capture.capture_region((642,392), geometry) == (1,31,640,360)
    with pytest.raises(RuntimeError, match='geometry'):
        capture.capture_region((700,400), geometry)


def test_render_window_size_adjusts_outer_to_requested_true_client():
    assert capture.render_window_size((656,399),(656,399),(640,360)) == (640,360)
    assert capture.render_window_size((656,399),(640,360),(640,360)) == (656,399)

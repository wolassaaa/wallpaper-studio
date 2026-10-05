from pathlib import Path
from dataclasses import replace
import hashlib
import subprocess
import threading

import pytest
from PIL import Image

from wallpaper_studio import media
from wallpaper_studio.models import EditSettings


@pytest.fixture
def sample(tmp_path):
    for i, color in enumerate(['red', 'green', 'blue', 'yellow']):
        Image.new('RGB', (64, 48), color).save(tmp_path / f'{i}.png')
    video = tmp_path / 'vfr.mkv'
    subprocess.run([str(media.ffmpeg_path()), '-y', '-framerate', '10', '-i', str(tmp_path / '%d.png'),
                    '-vf', r'setpts=if(eq(N\,0)\,0\,if(eq(N\,1)\,1\,if(eq(N\,2)\,4\,8)))',
                    '-fps_mode', 'vfr', '-c:v', 'ffv1', str(video)], check=True, capture_output=True)
    return video


def test_actual_vfr_timestamps_and_absolute_frame(sample, tmp_path):
    assert media.frame_timestamps(sample) == pytest.approx([0, .1, .4, .8], abs=.002)
    info = media.probe(sample)
    assert (info['width'], info['height'], info['frame_count']) == (64, 48, 4)
    out = media.extract_frame(sample, tmp_path / 'blue.png', 2,
                              EditSettings(width=32, height=32, fit='contain', start=.6))
    im = Image.open(out)
    assert im.size == (32, 32)
    assert im.getpixel((16, 16))[:3] == (0, 0, 255)
    assert im.getpixel((16, 0))[:3] == (0, 0, 0)


def test_exports_and_crop(sample, tmp_path):
    original_hash = hashlib.sha256(sample.read_bytes()).hexdigest()
    settings = EditSettings(width=32, height=24, fit='stretch', crop=(0, 0, 32, 24), start=.1, end=.6, fps=10)
    out = media.export_video(sample, tmp_path / 'result.mp4', settings)
    assert media.probe(out)['frame_count'] == 5
    gif = media.export_gif(sample, tmp_path / 'result.gif', settings)
    with Image.open(gif) as im:
        assert im.size == (32, 24)
        assert im.n_frames >= 2
    outputs = media.export_frames(sample, tmp_path / 'frames', [0, 3], settings)
    assert len(outputs) == 2 and all(p.exists() for p in outputs)
    assert hashlib.sha256(sample.read_bytes()).hexdigest() == original_hash


def test_trim_preserves_vfr_frame_preceding_cut(sample, tmp_path):
    settings = EditSettings(width=32, height=24, fit='stretch', start=.2, end=.6, fps=10)
    progress = []
    out = media.export_video(sample, tmp_path / 'cut.mp4', settings,
                             progress=lambda percent, message: progress.append(percent))
    assert media.probe(out)['frame_count'] == 4
    image = media.extract_frame(out, tmp_path / 'first.png', 0, settings)
    with Image.open(image) as im:
        r, g, b = im.getpixel((16, 12))[:3]
        assert g > r + 80 and g > b + 80
    assert progress[-1] == 100


def test_failures(sample, tmp_path):
    with pytest.raises(FileNotFoundError):
        media.probe(tmp_path / 'missing.mp4')
    with pytest.raises(ValueError, match='even'):
        media.export_video(sample, tmp_path / 'odd.mp4', EditSettings(width=31, height=24))
    with pytest.raises(IndexError):
        media.extract_frame(sample, tmp_path / 'bad.png', 20, EditSettings(width=32, height=24))
    with pytest.raises(ValueError, match='source'):
        media.export_video(sample, sample, EditSettings(width=32, height=24))
    stop = threading.Event()
    stop.set()
    with pytest.raises(InterruptedError):
        media.export_gif(sample, tmp_path / 'cancel.gif', EditSettings(width=32, height=24), stop)
    assert not (tmp_path / 'cancel.gif').exists()


def test_rotation_uses_decoded_orientation(sample, tmp_path):
    plain = media.export_video(sample, tmp_path / 'plain.mp4', EditSettings(width=64, height=48, fit='stretch', fps=10))
    rotated = tmp_path / 'rotated.mp4'
    subprocess.run([str(media.ffmpeg_path()), '-y', '-display_rotation', '90', '-i', str(plain), '-c', 'copy', str(rotated)],
                   check=True, capture_output=True)
    info = media.probe(rotated)
    assert (info['width'], info['height']) == (48, 64)
    out = media.extract_frame(rotated, tmp_path / 'rotated.png', 0, EditSettings(width=48, height=64, fit='stretch'))
    assert Image.open(out).size == (48, 64)
    encoded = media.export_video(rotated, tmp_path / 'normalized.mp4', EditSettings(width=48, height=64, fit='stretch', fps=10))
    normalized = media.probe(encoded)
    assert (normalized['width'], normalized['height']) == (48, 64)
    # A second encode catches accidental preservation of the source display
    # matrix after autorotation, which would rotate pixels twice.
    second = media.export_video(encoded, tmp_path / 'second.mp4', EditSettings(width=48, height=64, fit='stretch', fps=10))
    assert (media.probe(second)['width'], media.probe(second)['height']) == (48, 64)


def test_inflight_cancel_keeps_existing_destination(sample, tmp_path):
    output = tmp_path / 'existing.mp4'
    output.write_bytes(b'previous export')
    stop = threading.Event()
    timer = threading.Timer(.03, stop.set)
    timer.start()
    try:
        with pytest.raises(InterruptedError):
            media.export_video(sample, output, EditSettings(width=3840, height=2160, fps=120), stop)
    finally:
        timer.cancel()
    assert output.read_bytes() == b'previous export'
    assert not list(tmp_path.glob('.existing-*.mp4'))


def test_webm_input_probe_exact_frame_and_all_exports(tmp_path):
    source = tmp_path / 'source.webm'
    subprocess.run([str(media.ffmpeg_path()), '-y', '-f', 'lavfi', '-i',
                    'testsrc2=size=96x64:rate=12:duration=1', '-c:v', 'libvpx-vp9', '-lossless', '1', str(source)],
                   check=True, capture_output=True)
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    info = media.probe(source)
    assert (info['width'], info['height'], info['frame_count']) == (96, 64, 12)
    assert media.frame_timestamps(source)[5] == pytest.approx(5 / 12, abs=.001)
    settings = EditSettings(width=48, height=32, fit='crop', start=.25, end=.75, fps=12)
    assert media.extract_frame(source, tmp_path / 'frame.png', 5, settings).is_file()
    movie = media.export_video(source, tmp_path / 'movie.mp4', settings)
    assert media.probe(movie)['frame_count'] == 6
    gif = media.export_gif(source, tmp_path / 'movie.gif', settings)
    with Image.open(gif) as image:
        assert image.size == (48, 32) and image.n_frames > 1
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash


def test_public_metadata_apis_cancel_before_cached_read(sample):
    media.probe(sample)
    media.frame_timestamps(sample)
    stop = threading.Event()
    stop.set()
    with pytest.raises(InterruptedError):
        media.probe(sample, cancel=stop)
    with pytest.raises(InterruptedError):
        media.frame_timestamps(sample, cancel=stop)

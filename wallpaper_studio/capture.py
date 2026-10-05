"""Window-only Windows Graphics Capture with native-size FFmpeg encoding.

The Wallpaper Engine command syntax follows wallpaper-engine-exporter (MIT).
No desktop capture or global wallpaper settings are used.
"""
from __future__ import annotations

import ctypes
import json
import math
import queue
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

from .source import (CancelledError, _no_links, assert_output_outside_source, check_cancel,
                     engine_path, extract_resources, hash_manifest, project_root,
                     run_tool, stage_project, verify_manifest)


def validate_settings(settings):
    if settings.width < 1 or settings.height < 1 or settings.fps < 1 or settings.fps > 240:
        raise ValueError('Invalid capture dimensions/frame rate')
    if not math.isfinite(settings.seconds) or settings.seconds <= 0 or not math.isfinite(settings.wait) or settings.wait < 0:
        raise ValueError('Invalid capture duration/loading wait')


def open_command(engine: Path, project: Path, name: str, settings) -> list[str]:
    return [str(engine), '-control', 'openWallpaper', '-file', str(project),
            '-playInWindow', name, '-width', str(settings.width), '-height', str(settings.height),
            '-x', '0', '-y', '0', '-activate', '-borderless']


def close_command(engine: Path, name: str) -> list[str]:
    return [str(engine), '-control', 'closeWallpaper', '-location', name]


def encoder_command(ffmpeg: Path, output: Path, width: int, height: int, fps: int) -> list[str]:
    return [str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-y', '-f', 'rawvideo',
            '-pixel_format', 'bgra', '-video_size', f'{width}x{height}', '-framerate', str(fps),
            '-i', 'pipe:0', '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '18',
            '-pix_fmt', 'yuv420p' if width % 2 == 0 and height % 2 == 0 else 'yuv444p',
            '-movflags', '+faststart', str(output)]


def _find_window(name: str) -> int:
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    user32.FindWindowW.restype = ctypes.c_void_p
    return user32.FindWindowW(None, name) or 0


def render_window_size(outer, client, requested):
    return (requested[0] + outer[0] - client[0], requested[1] + outer[1] - client[1])


def capture_region(frame_size, geometry):
    client = geometry['client']
    width, height = client[2] - client[0], client[3] - client[1]
    if frame_size == (width, height):
        return (0, 0, width, height)
    for key in ('window', 'dwm'):
        bounds = geometry.get(key)
        if bounds and frame_size == (bounds[2] - bounds[0], bounds[3] - bounds[1]):
            x, y = client[0] - bounds[0], client[1] - bounds[1]
            if 0 <= x and 0 <= y and x + width <= frame_size[0] and y + height <= frame_size[1]:
                return (x, y, width, height)
    raise RuntimeError('WGC dimensions disagree with verified client/window geometry')


def _configure_owned_window(name, width, height):
    """Set the engine's real client render size; preserve all other windows."""
    from ctypes import wintypes as W
    hwnd = _find_window(name)
    if not hwnd:
        raise RuntimeError('Owned wallpaper window disappeared')
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetWindowRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
    user32.GetClientRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
    user32.ClientToScreen.argtypes = [W.HWND, ctypes.POINTER(W.POINT)]
    user32.SetWindowPos.argtypes = [W.HWND, W.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    previous = user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    try:
        outer, client = W.RECT(), W.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(outer)) or not user32.GetClientRect(hwnd, ctypes.byref(client)):
            raise ctypes.WinError(ctypes.get_last_error())
        size = render_window_size((outer.right - outer.left, outer.bottom - outer.top),
                                  (client.right - client.left, client.bottom - client.top), (width, height))
        if not user32.SetWindowPos(hwnd, None, 0, 0, *size, 0x0002 | 0x0004 | 0x0010):
            raise ctypes.WinError(ctypes.get_last_error())
        origin = W.POINT()
        user32.GetWindowRect(hwnd, ctypes.byref(outer))
        user32.GetClientRect(hwnd, ctypes.byref(client))
        user32.ClientToScreen(hwnd, ctypes.byref(origin))
        geometry = {'hwnd': hwnd, 'window': (outer.left, outer.top, outer.right, outer.bottom),
                    'client': (origin.x, origin.y, origin.x + client.right - client.left, origin.y + client.bottom - client.top)}
        dwm = ctypes.WinDLL('dwmapi')
        dwm.DwmGetWindowAttribute.argtypes = [W.HWND, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        bounds = W.RECT()
        if dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(bounds), ctypes.sizeof(bounds)) == 0:
            geometry['dwm'] = (bounds.left, bounds.top, bounds.right, bounds.bottom)
        if (client.right - client.left, client.bottom - client.top) != (width, height):
            raise RuntimeError('Engine did not accept the requested native client render size')
        return geometry
    finally:
        if previous:
            user32.SetThreadDpiAwarenessContext(previous)


class CfrFrames:
    """Preserve sampled wall-clock slots without presenting repeats as captures."""
    def __init__(self, write):
        self.write = write
        self.encoded = 0
        self.captured = 0
        self.duplicated = 0
        self.last = None

    def push(self, pixels: bytes, slot: int):
        if slot < self.encoded:
            return
        while self.encoded < slot:
            self.write(self.last if self.last is not None else pixels)
            self.encoded += 1
            self.duplicated += 1
        self.write(pixels)
        self.last = pixels
        self.encoded += 1
        self.captured += 1

    def pad(self, total: int):
        if self.last is not None:
            while self.encoded < total:
                self.write(self.last)
                self.encoded += 1
                self.duplicated += 1


def _record_window(name, output, settings, cancel=None, progress=None, still=False, geometry=None):
    """Record continuous WGC events; bound memory and report real frame loss."""
    from windows_capture import WindowsCapture
    from .media import ffmpeg_path

    frames = queue.Queue(maxsize=3)
    finished = threading.Event()
    writer_done = threading.Event()
    errors = []
    state = {'received_frames': 0, 'encoded_frames': 0, 'dropped_frames': 0,
             'throttled_frames': 0, 'width': None, 'height': None, 'first': None,
             'last': None, 'last_slot': -1, 'encoder': None, 'closed': False,
             'duplicated_frames': 0, 'captured_frames': 0, 'native_capture_size': None, 'capture_crop': None}

    # A UUID title is unique; WGC is explicitly window-only, never monitor-based.
    capture = WindowsCapture(cursor_capture=False, draw_border=False,
                             monitor_index=None, window_name=name,
                             window_hwnd=None)

    @capture.event
    def on_frame_arrived(frame, capture_control):
        try:
            check_cancel(cancel)
            if finished.is_set():
                capture_control.stop()
                return
            now = time.monotonic()
            state['received_frames'] += 1
            if frame.frame_buffer.shape != (frame.height, frame.width, 4) or frame.frame_buffer.dtype.name != 'uint8':
                raise RuntimeError('WGC frame buffer dimensions/pixel format do not match the capture metadata')
            region = capture_region((frame.width, frame.height), geometry) if geometry else (0, 0, frame.width, frame.height)
            x, y, width, height = region
            if state['first'] is None:
                state.update(first=now, width=width, height=height, native_capture_size=(frame.width, frame.height), capture_crop=region)
                if not still and (width, height) != (settings.width, settings.height):
                    raise RuntimeError(f'Engine captured {width}x{height}, not requested {settings.width}x{settings.height}; select a supported native size')
            if (width, height) != (state['width'], state['height']):
                raise RuntimeError('Capture window dimensions changed while recording')
            elapsed = now - state['first']
            if not still and elapsed >= settings.seconds:
                finished.set()
                capture_control.stop()
                return
            slot = int(elapsed * settings.fps)
            if slot <= state['last_slot']:
                state['throttled_frames'] += 1
                return
            state['last_slot'] = slot
            pixels = frame.frame_buffer[y:y + height, x:x + width].copy()
            try:
                frames.put_nowait((pixels, slot))
                state['last'] = now
            except queue.Full:
                state['dropped_frames'] += 1
            if still:
                finished.set()
                capture_control.stop()
        except Exception as exc:
            errors.append(exc)
            finished.set()
            capture_control.stop()

    @capture.event
    def on_closed():
        state['closed'] = True
        finished.set()

    log = tempfile.TemporaryFile()

    def write_frames():
        try:
            cfr = None
            while not finished.is_set() or not frames.empty():
                try:
                    pixels, slot = frames.get(timeout=0.1)
                except queue.Empty:
                    continue
                check_cancel(cancel)
                if still:
                    from PIL import Image
                    Image.fromarray(pixels[:, :, [2, 1, 0, 3]]).save(output, format='PNG')
                else:
                    if state['encoder'] is None:
                        state['encoder'] = subprocess.Popen(
                            encoder_command(ffmpeg_path(), output, state['width'], state['height'], settings.fps),
                            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                        cfr = CfrFrames(state['encoder'].stdin.write)
                    cfr.push(pixels.tobytes(), slot)
                if still:
                    state['encoded_frames'] += 1
                    state['captured_frames'] += 1
            encoder = state['encoder']
            if encoder:
                cfr.pad(math.ceil(settings.seconds * settings.fps))
                state.update(encoded_frames=cfr.encoded, captured_frames=cfr.captured, duplicated_frames=cfr.duplicated)
                encoder.stdin.close()
                if encoder.wait(timeout=60):
                    log.seek(0)
                    raise RuntimeError(f'FFmpeg capture failed: {log.read().decode(errors="replace")}')
        except Exception as exc:
            errors.append(exc)
            finished.set()
        finally:
            writer_done.set()

    writer = threading.Thread(target=write_frames, name='WallpaperStudio-encoder', daemon=True)
    control = None
    started = time.monotonic()
    writer.start()
    try:
        control = capture.start_free_threaded()
        while not finished.wait(0.05):
            check_cancel(cancel)
            now = time.monotonic()
            first = state['first']
            if first is None and now - started > 30:
                raise RuntimeError('WGC did not deliver a frame within 30 seconds')
            if first is not None and now - first >= settings.seconds:
                finished.set()
            if progress and first is not None:
                progress(min(98, 30 + int(68 * (now - first) / settings.seconds)), '录制窗口（WGC）')
        check_cancel(cancel)
        if not still and state['closed'] and (state['first'] is None or time.monotonic() - state['first'] < settings.seconds):
            raise RuntimeError('Wallpaper capture window closed before the requested duration completed')
        control.stop()
        control = None
        deadline = time.monotonic() + 60
        while not writer_done.wait(0.1):
            check_cancel(cancel)
            if time.monotonic() > deadline:
                raise RuntimeError('Capture encoder did not finish within 60 seconds')
        if errors:
            raise errors[0]
        if not state['encoded_frames']:
            raise RuntimeError('WGC recording produced no frames')
        duration = max(0.0, state['last'] - state['first'])
        result = {key: state[key] for key in ('width', 'height', 'received_frames', 'encoded_frames', 'dropped_frames', 'throttled_frames', 'duplicated_frames', 'captured_frames', 'native_capture_size', 'capture_crop')}
        result.update(method='Windows Graphics Capture', requested_width=settings.width,
                      requested_height=settings.height, requested_fps=settings.fps,
                      capture_span=duration, observed_fps=(state['captured_frames'] - 1) / duration if duration else 0,
                      encoded_fps=settings.fps if not still else None,
                      encoded_duration=state['encoded_frames'] / settings.fps if not still else 0,
                      client_render_size=(state['width'], state['height']),
                      window_closed_early=state['closed'], output=str(output))
        return result
    finally:
        finished.set()
        if control:
            control.stop()
        encoder = state['encoder']
        if encoder and encoder.poll() is None:
            encoder.terminate()
            try:
                encoder.wait(timeout=3)
            except subprocess.TimeoutExpired:
                encoder.kill()
                encoder.wait()
        writer.join(timeout=5)
        log.close()


def _capture(source, output, settings, cancel, progress, still=False):
    check_cancel(cancel)
    validate_settings(settings)
    output = Path(output).absolute()
    assert_output_outside_source(source, output)
    _no_links(output)
    _no_links(output.parent / (output.name + '.capture.json'))
    engine = engine_path()
    if engine is None:
        raise FileNotFoundError('未找到 Wallpaper Engine，请先安装并启动引擎')
    expected = hash_manifest(source, cancel)
    output.parent.mkdir(parents=True, exist_ok=True)
    name = 'WallpaperStudio-' + uuid.uuid4().hex
    opened = False
    with tempfile.TemporaryDirectory(prefix='capture-job-', dir=output.parent) as workspace:
        staged = stage_project(source, Path(workspace), cancel)
        original = Path(source)
        project = staged / (original.name if original.is_file() else 'project.json')
        if not project.is_file():
            raise FileNotFoundError(f'Wallpaper project not found: {project}')
        from .properties import prepare_properties, properties_command
        prepare_properties(project, settings.properties)
        temporary_output = Path(workspace) / ('capture.png' if still else 'capture.mp4')
        try:
            if progress:
                progress(1, '启动隔离的壁纸窗口')
            # Close the unique named window even if command completion is interrupted.
            opened = True
            run_tool(open_command(engine, project, name, settings), cancel)
            started = time.monotonic()
            while time.monotonic() - started < max(30.0, settings.wait):
                check_cancel(cancel)
                elapsed = time.monotonic() - started
                if elapsed >= settings.wait and _find_window(name):
                    break
                if progress:
                    progress(min(29, 2 + int(27 * min(elapsed / max(settings.wait, 1), 1))), '等待壁纸加载')
                time.sleep(0.1)
            else:
                raise RuntimeError('Wallpaper Engine did not create the owned capture window')
            if settings.properties:
                run_tool(properties_command(engine, name, settings.properties), cancel, timeout=10)
            geometry = _configure_owned_window(name, settings.width, settings.height)
            time.sleep(0.15)  # the owned engine renderer receives its resize notification
            result = _record_window(name, temporary_output, settings, cancel, progress, still, geometry)
            check_cancel(cancel)
            verify_manifest(source, expected)
            temporary_output.replace(output)
            result['output'] = str(output)
            result['properties'] = settings.properties
            if not still:
                (output.parent / (output.name + '.capture.json')).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
            if progress:
                progress(100, '录制完成' if not still else '加载画面预览完成')
            return result
        finally:
            primary = sys.exception()
            cleanup_errors = []
            if opened:
                # Never close all wallpapers, stop the engine, or target a monitor.
                try:
                    run_tool(close_command(engine, name), timeout=5)
                except Exception as exc:
                    cleanup_errors.append(exc)
            try:
                verify_manifest(source, expected)
            except Exception as exc:
                cleanup_errors.append(exc)
            if cleanup_errors:
                if primary is not None:
                    for exc in cleanup_errors:
                        primary.add_note(f'Cleanup verification: {exc}')
                else:
                    raise cleanup_errors[0]


def capture_scene(source: Path, output: Path, settings, cancel=None, progress=None) -> dict:
    return _capture(source, output, settings, cancel, progress)


def capture_still(source: Path, output: Path, settings, cancel=None, progress=None) -> dict:
    return _capture(source, output, settings, cancel, progress, still=True)

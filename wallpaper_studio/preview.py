"""Live Wallpaper Engine renderer mirrored into the editor with window-only WGC."""
from __future__ import annotations
import queue
import tempfile
import threading
import time
import uuid
from pathlib import Path
from dataclasses import replace
from .source import (CancelledError, check_cancel, engine_path, hash_manifest,
                     verify_manifest, stage_project, run_tool)
from .capture import (open_command, close_command, _find_window,
                      _configure_owned_window, capture_region)
def preview_size(width, height):
    scale=min(1,1280/max(width,height))
    return max(1,round(width*scale)),max(1,round(height*scale))
def live_scene(source, workspace, settings, cancel, deliver, status, commands=None):
    from windows_capture import WindowsCapture
    engine=engine_path()
    if engine is None: raise FileNotFoundError('未找到 Wallpaper Engine，请安装并启动后重试实时预览')
    expected=hash_manifest(source,cancel)
    workspace=Path(workspace);workspace.mkdir(parents=True,exist_ok=True)
    width,height=preview_size(settings.width,settings.height)
    settings=replace(settings,width=width,height=height)
    name='WallpaperStudio-Live-'+uuid.uuid4().hex
    opened=False;control=None
    errors=queue.SimpleQueue();closed=threading.Event()
    last=[0.0];first=[None]
    try:
        with tempfile.TemporaryDirectory(prefix='live-',dir=workspace) as job:
            status('正在复制项目并准备真实预览…')
            staged=stage_project(source,Path(job),cancel)
            original=Path(source)
            project=staged/(original.name if original.is_file() else 'project.json')
            from .properties import prepare_properties, properties_command
            prepare_properties(project, settings.properties)
            opened=True
            run_tool(open_command(engine,project,name,settings),cancel,timeout=15)
            deadline=time.monotonic()+30
            while not _find_window(name):
                check_cancel(cancel)
                if time.monotonic()>deadline: raise RuntimeError('引擎预览窗口未出现')
                time.sleep(.1)
            geometry=_configure_owned_window(name,width,height)
            capture=WindowsCapture(cursor_capture=False,draw_border=False,monitor_index=None,
                                   window_name=name,window_hwnd=None)
            @capture.event
            def on_frame_arrived(frame, capture_control):
                try:
                    if cancel.is_set(): capture_control.stop();return
                    now=time.monotonic()
                    if now-last[0]<1/15: return
                    x,y,w,h=capture_region((frame.width,frame.height),geometry)
                    if (w,h)!=(width,height): raise RuntimeError('实际预览采集尺寸与窗口不符')
                    pixels=frame.frame_buffer[y:y+h,x:x+w].copy()
                    deliver((pixels.tobytes(),w,h))
                    last[0]=now
                    if first[0] is None: first[0]=now
                except Exception as exc:
                    errors.put(exc);closed.set();capture_control.stop()
            @capture.event
            def on_closed(): closed.set()
            control=capture.start_free_threaded()
            started=time.monotonic();loaded=False
            while not cancel.wait(.1):
                if not errors.empty(): raise errors.get()
                if closed.is_set(): raise RuntimeError('实时预览窗口已关闭')
                if first[0] is None and time.monotonic()-started>30: raise RuntimeError('WGC 未收到真实渲染帧')
                if commands is not None and loaded:
                    latest = None
                    while not commands.empty():
                        latest = commands.get_nowait()
                    if latest is not None:
                        run_tool(properties_command(engine,name,latest),cancel,timeout=10)
                        status('壁纸部件选项已应用 · 录制将使用相同设置')
                if not loaded and first[0] is not None and time.monotonic()-started>=settings.wait:
                    if settings.properties: run_tool(properties_command(engine,name,settings.properties),cancel,timeout=10)
                    status(f'引擎实时画面 · {width} × {height} · 时间轴将在录制后启用')
                    loaded=True
            control.stop();control=None
            run_tool(close_command(engine,name),timeout=5);opened=False
    except CancelledError:
        pass
    finally:
        if control: control.stop()
        if opened: run_tool(close_command(engine,name),timeout=5)
        verify_manifest(source,expected)

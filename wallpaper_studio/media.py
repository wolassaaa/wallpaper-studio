"""Frame-accurate, cancellable FFmpeg exports. No source is ever overwritten."""
from __future__ import annotations

from collections import OrderedDict
import threading
from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid


def ffmpeg_path() -> Path:
    bundled = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'tools'
    for name in ('ffmpeg.exe', 'ffmpeg'):
        candidate = bundled / name
        if candidate.is_file():
            return candidate
    import imageio_ffmpeg
    return Path(imageio_ffmpeg.get_ffmpeg_exe())


def _run(args, cancel=None, progress=None, duration=None):
    if cancel is not None and cancel.is_set():
        raise InterruptedError('Export cancelled')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with tempfile.TemporaryDirectory(prefix='wallpaper-ffmpeg-') as logs:
        progress_log = Path(logs) / 'progress.log'
        with progress_log.open('w+b') as stdout, tempfile.TemporaryFile() as stderr:
            process = subprocess.Popen([str(ffmpeg_path()), '-hide_banner', '-nostdin', *args],
                                       stdout=stdout, stderr=stderr, creationflags=flags)
            try:
                while process.poll() is None:
                    if cancel is not None and cancel.is_set():
                        process.terminate()
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
                        raise InterruptedError('Export cancelled')
                    if progress and duration:
                        # A separate reader avoids moving the child's shared file
                        # descriptor offset while FFmpeg is writing progress.
                        records = re.findall(rb'out_time_us=(\d+)', progress_log.read_bytes())
                        if records:
                            progress(min(99, int(int(records[-1]) / 1e6 / duration * 100)), '正在导出')
                    time.sleep(.05)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
            stderr.seek(0)
            text = stderr.read().decode('utf-8', errors='replace')
            if process.returncode:
                raise RuntimeError(f'FFmpeg exited {process.returncode}: {text[-6000:]}')
            return text


def _source(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


_METADATA_CACHE = OrderedDict()
_METADATA_LOCK = threading.Lock()

def _scan(path, size, mtime, cancel=None):
    text = _run(['-threads', '2', '-i', path, '-map', '0:v:0', '-an', '-vf', 'showinfo=checksum=0', '-fps_mode', 'passthrough', '-f', 'null', '-'], cancel)
    return _parse_scan(text)


def _parse_scan(text):
    records = re.findall(r'\bn:\s*\d+\s+pts:\s*-?\d+\s+pts_time:([\d.eE+\-]+).*?\bs:(\d+)x(\d+)', text)
    if not records:
        raise ValueError('Source contains no decodable video frames')
    timestamps = [float(t) for t, _, _ in records]
    match = re.search(r'Duration:\s*(\d+):(\d+):([\d.]+)', text)
    duration = (int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])) if match else 0
    fps_match = re.search(r'(\d+(?:\.\d+)?) fps', text)
    fps = float(fps_match[1]) if fps_match else (1 / (timestamps[-1] - timestamps[-2]) if len(timestamps) > 1 else 1.)
    durations = re.findall(r'\bn:\s*\d+.*?\bduration_time:([\d.eE+\-]+)', text)
    last_duration = float(durations[-1]) if durations else 0
    duration = max(duration, timestamps[-1] + (last_duration if last_duration > 0 else 1 / fps))
    return {'width': int(records[0][1]), 'height': int(records[0][2]), 'duration': duration,
            'fps': fps, 'frame_count': len(records)}, timestamps


def _metadata(path, cancel=None):
    if cancel is not None and cancel.is_set():
        raise InterruptedError('Export cancelled')
    path = _source(path)
    stat = path.stat()
    key=(str(path),stat.st_size,stat.st_mtime_ns)
    with _METADATA_LOCK:
        cached=_METADATA_CACHE.get(key)
        if cached is not None: return cached
    result=_scan(*key,cancel)
    _remember_metadata(key,result)
    return result


def probe(path, cancel=None) -> dict:
    return dict(_metadata(path, cancel)[0])


def frame_timestamps(path, cancel=None) -> list[float]:
    """Decoded presentation timestamps, not frame number / nominal frame rate."""
    return list(_metadata(path, cancel)[1])


def _geometry(source, settings, info=None):
    width, height = int(settings.width), int(settings.height)
    if width <= 0 or height <= 0 or width != settings.width or height != settings.height:
        raise ValueError('Output dimensions must be positive integers')
    filters = []
    if settings.crop is not None:
        x, y, w, h = settings.crop
        info = info or probe(source)
        if any(int(v) != v for v in (x, y, w, h)) or x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > info['width'] or y + h > info['height']:
            raise ValueError('Crop must be an integer rectangle within the decoded source')
        filters.append(f'crop={w}:{h}:{x}:{y}:exact=1')
    if settings.fit == 'adaptive':
        import math
        if width!=height or not all(math.isfinite(v) for v in (settings.zoom,settings.anchor_x,settings.anchor_y)) or not .25<=settings.zoom<=2 or not 0<=settings.anchor_x<=1 or not 0<=settings.anchor_y<=1:
            raise ValueError('Adaptive canvas requires a square, zoom .25–2 and anchors 0–1')
        edge=max(1,round(width*settings.zoom))
        # Blur at thumbnail size, then enlarge: bounded work even for large exports.
        filters.append(f'split[wsbg][wsfg];[wsbg]scale=64:64:force_original_aspect_ratio=increase,crop=64:64,boxblur=8:2,scale={width}:{height}:flags=lanczos[wsbackground];[wsfg]scale={edge}:{edge}:force_original_aspect_ratio=decrease:flags=lanczos[wsforeground];[wsbackground][wsforeground]overlay=x=(W-w)*{settings.anchor_x}:y=(H-h)*{settings.anchor_y}:shortest=1')
    elif settings.fit == 'crop':
        filters += [f'scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos', f'crop={width}:{height}:exact=1']
    elif settings.fit == 'contain':
        filters += [f'scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos', f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black']
    elif settings.fit == 'stretch':
        filters.append(f'scale={width}:{height}:flags=lanczos')
    else:
        raise ValueError('fit must be crop, contain or stretch')
    return filters + ['setsar=1']


def _range(settings):
    start = float(settings.start)
    end = None if settings.end is None else float(settings.end)
    import math
    if not math.isfinite(start) or start < 0 or (end is not None and (not math.isfinite(end) or end <= start)):
        raise ValueError('Trim range must satisfy 0 <= start < end')
    if not math.isfinite(float(settings.fps)) or settings.fps <= 0:
        raise ValueError('fps must be positive')
    return start, end


def _target(source, output):
    output = Path(output).resolve()
    if output == source:
        raise ValueError('Output must not overwrite the source')
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(f'.{output.stem}-{uuid.uuid4().hex}{output.suffix}')
    return output, temp


def _export(source, output, settings, kind, cancel=None, progress=None):
    source = _source(source)
    if cancel is not None and cancel.is_set():
        raise InterruptedError('Export cancelled')
    if kind == 'video' and (settings.width % 2 or settings.height % 2):
        raise ValueError('H.264 yuv420p output dimensions must be even')
    start, end = _range(settings)
    info = _metadata(source, cancel)[0]
    if start >= info['duration']:
        raise ValueError('Trim start lies beyond source duration')
    # Resample before trimming: a VFR frame preceding the cut remains visible
    # until its next presentation timestamp, rather than being discarded.
    filters = [f'fps={settings.fps}:round=down', f'trim=start={start}:end={min(end or info["duration"], info["duration"])}', 'setpts=PTS-STARTPTS']
    filters += _geometry(source, settings, info)
    output, temp = _target(source, output)
    args = ['-y', '-filter_threads', '1', '-filter_complex_threads', '1', '-i', str(source), '-an']
    if kind == 'video':
        args += ['-vf', ','.join(filters), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', '-movflags', '+faststart']
    else:
        args += ['-filter_complex', ','.join(filters) + ',split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a', '-loop', '0']
    # fps filters can leave zero frame-duration metadata on VFR sources;
    # explicit CFR timing preserves the final frame in MP4/GIF muxers.
    args += ['-r', str(settings.fps), '-fps_mode', 'cfr', '-progress', 'pipe:1', str(temp)]
    try:
        _run(args, cancel, progress, max(.001, min(end or info['duration'], info['duration']) - start))
        if not temp.is_file() or not temp.stat().st_size:
            raise ValueError('Export produced no frames')
        temp.replace(output)
        if progress:
            progress(100, '导出完成')
        return output
    finally:
        temp.unlink(missing_ok=True)


def export_video(source, output, settings, cancel=None, progress=None) -> Path:
    return _export(source, output, settings, 'video', cancel, progress)


def export_gif(source, output, settings, cancel=None, progress=None) -> Path:
    return _export(source, output, settings, 'gif', cancel, progress)


def extract_frame(source, output, index, settings, cancel=None) -> Path:
    """Extract the absolute decoded frame index; trim settings do not renumber it."""
    source = _source(source)
    if cancel is not None and cancel.is_set():
        raise InterruptedError('Export cancelled')
    info = _metadata(source, cancel)[0]
    if not isinstance(index, int) or index < 0 or index >= info['frame_count']:
        raise IndexError('Frame index outside decoded frame range')
    output, temp = _target(source, output)
    filters = [f'select=eq(n\\,{index})'] + _geometry(source, settings, info)
    try:
        _run(['-y', '-threads', '2', '-filter_threads', '1', '-i', str(source), '-an', '-vf', ','.join(filters), '-frames:v', '1', '-fps_mode', 'passthrough', str(temp)], cancel)
        if not temp.is_file():
            raise ValueError('Frame extraction produced no image')
        temp.replace(output)
        return output
    finally:
        temp.unlink(missing_ok=True)


def export_frames(source, output_dir, indices, settings, cancel=None, progress=None) -> list[Path]:
    indices = list(indices)
    outputs = []
    for position, index in enumerate(indices):
        outputs.append(extract_frame(source, Path(output_dir) / f'frame_{index:06d}.png', index, settings, cancel))
        if progress:
            progress(int((position + 1) / len(indices) * 100), '正在导出帧')
    return outputs


def _remember_metadata(key, result):
    with _METADATA_LOCK:
        _METADATA_CACHE[key]=result
        _METADATA_CACHE.move_to_end(key)
        while len(_METADATA_CACHE)>16: _METADATA_CACHE.popitem(last=False)

def prepare_preview(source, folder, edge=640, fps=15, cancel=None, progress=None):
    """One background decode builds a bounded proxy AND exact original frame PTS."""
    import hashlib,json
    source=_source(source);stat=source.stat()
    key=(str(source),stat.st_size,stat.st_mtime_ns)
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    token=hashlib.sha256(repr((key,edge,fps)).encode()).hexdigest()[:24]
    proxy=folder/(token+'.mp4');index=folder/(token+'.json')
    if proxy.is_file() and index.is_file():
        if cancel is not None and cancel.is_set(): raise InterruptedError('Export cancelled')
        data=json.loads(index.read_text(encoding='utf-8'))
        result=data['info'],data['timestamps'];_remember_metadata(key,result)
        return source,result[0],result[1],proxy
    temp=folder/(token+'.partial.mp4')
    try:
        if progress: progress(35,'生成轻量预览和精确帧索引（后台，可取消）…')
        from .source import runtime_tool,run_tool
        header=json.loads(run_tool([str(runtime_tool('ffprobe.exe')),'-v','error','-show_format','-of','json',str(source)],cancel,timeout=15))
        duration=float(header.get('format',{}).get('duration',0))
        filters=f"showinfo=checksum=0,scale=w='min(iw,{edge})':h='min(ih,{edge})':force_original_aspect_ratio=decrease:force_divisible_by=2:flags=fast_bilinear,fps={fps},setsar=1"
        args=['-y','-progress','pipe:1','-threads','2','-filter_threads','1','-i',str(source),
                   '-map','0:v:0','-an','-vf',filters,'-c:v','libx264','-threads','2',
                   '-preset','ultrafast','-crf','28','-pix_fmt','yuv420p',
                   '-g',str(fps),'-movflags','+faststart',str(temp)]
        update=(lambda value,text:progress(35+int(value*.64),'正在生成轻量预览…')) if progress else None
        try:
            text=_run(['-hwaccel','auto',*args],cancel,update,duration)
        except RuntimeError:
            if cancel is not None and cancel.is_set(): raise InterruptedError('Export cancelled')
            text=_run(args,cancel,update,duration)
        result=_parse_scan(text)
        if cancel is not None and cancel.is_set(): raise InterruptedError('Export cancelled')
        temp.replace(proxy)
        index.write_text(json.dumps({'info':result[0],'timestamps':result[1]}),encoding='utf-8')
        _remember_metadata(key,result)
        if progress: progress(100,'轻量预览准备完成')
        return source,result[0],result[1],proxy
    finally: temp.unlink(missing_ok=True)

def extract_preview_frame(source, output, index, settings, timestamps, cancel=None):
    """Fast timestamp seek for viewing; verify decoded PTS, fall back to absolute index."""
    if index<0 or index>=len(timestamps): raise IndexError('Preview index out of range')
    stamp=timestamps[index]
    if stamp<0 or timestamps.count(stamp)>1:
        return extract_frame(source,output,index,settings,cancel)
    source=_source(source);output,temp=_target(source,output)
    try:
        neighbors=[abs(timestamps[n]-stamp) for n in (index-1,index+1) if 0<=n<len(timestamps) and timestamps[n]!=stamp]
        seek=max(0,stamp-(min(neighbors)/8 if neighbors else 1e-5))
        args=['-y','-hwaccel','auto','-threads','2','-filter_threads','1',
              '-seek_timestamp','1','-ss',f'{seek:.9f}','-copyts','-i',str(source),'-an',
              '-vf','showinfo=checksum=0,'+','.join(_geometry(source,settings)),
              '-frames:v','1','-fps_mode','passthrough',str(temp)]
        try:
            text=_run(args,cancel)
            pts=re.search(r'\bpts_time:([\d.eE+\-]+)',text)
            tolerance=min(neighbors)/4 if neighbors else 1e-5
            valid=pts and abs(float(pts[1])-stamp)<max(1e-5,tolerance) and temp.is_file()
        except RuntimeError: valid=False
        if valid:
            temp.replace(output);return output
        return extract_frame(source,output,index,settings,cancel)
    finally: temp.unlink(missing_ok=True)

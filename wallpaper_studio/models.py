from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class WallpaperEntry:
    source: Path
    title: str
    kind: str
    preview: Path | None = None
    wallpaper_file: Path | None = None
    tags: tuple[str, ...] = ()
    content_rating: str = "Unknown"


@dataclass(frozen=True)
class EditSettings:
    width: int = 2420
    height: int = 1668
    fit: str = "crop"
    crop: tuple[int, int, int, int] | None = None
    start: float = 0.0
    end: float | None = None
    cover: float = 1.5
    fps: int = 30
    anchor_x: float = .5
    anchor_y: float = .5
    zoom: float = 1.0


@dataclass(frozen=True)
class CaptureSettings:
    width: int = 3840
    height: int = 2160
    fps: int = 30
    seconds: float = 10.0
    wait: float = 20.0
    properties: dict = field(default_factory=dict)


def output_size(ratio: str, orientation: str, resolution: str,
                custom: tuple[int, int] = (2420, 1668),
                original: tuple[int, int] = (3840, 2160)) -> tuple[int, int]:
    presets = {"device": (2420, 1668), "original": original, "custom": custom}
    if resolution == "custom":
        w, h = custom
    elif ratio in presets:
        w, h = presets[ratio]
    else:
        w, h = (int(v) for v in ratio.split(":"))
    if w <= 0 or h <= 0:
        raise ValueError("尺寸必须为正数")
    if orientation == "portrait" and w > h or orientation == "landscape" and h > w:
        w, h = h, w
    if resolution in ("device", "original", "custom"):
        return w, h
    long_edge = {"2K": 2560, "4K": 3840, "8K": 7680}[resolution]
    factor = long_edge / max(w, h)
    return round(w * factor), round(h * factor)


def scaled_size(width: int, height: int, multiplier: int) -> tuple[int, int]:
    if not isinstance(multiplier, int) or not 1 <= multiplier <= 16:
        raise ValueError("倍率应为 1 至 16 的整数")
    w, h = width * multiplier, height * multiplier
    if min(w,h) < 1 or max(w,h) > 16384 or w*h > 67108864:
        raise ValueError(f"请求 {w} × {h} 超出单边 16384 / 6710 万像素预算，请降低基础尺寸或倍率")
    return w, h


def rotation_regions(long_edge: int, short_edge: int) -> dict:
    if not 0 < short_edge <= long_edge: raise ValueError('Invalid rotation dimensions')
    offset=(long_edge-short_edge)//2
    return {'canvas':(long_edge,long_edge),'landscape':(0,offset,long_edge,short_edge),
            'portrait':(offset,0,short_edge,long_edge),'shared':(offset,offset,short_edge,short_edge)}

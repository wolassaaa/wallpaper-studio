"""Deterministic UI contract check for redesign and rollback copies."""
import argparse
import os
import sys
from pathlib import Path

os.environ['QT_QPA_PLATFORM']='offscreen'
parser=argparse.ArgumentParser()
parser.add_argument('--source',type=Path,required=True)
parser.add_argument('--baseline',action='store_true')
args=parser.parse_args()
sys.path.insert(0,str(args.source.resolve()))
from PySide6.QtWidgets import QApplication
from wallpaper_studio.app import StudioWindow

app=QApplication([])
window=StudioWindow(scan_on_start=False)
if args.baseline:
    assert not hasattr(window,'inspector_tabs')
    assert window.capture_seconds.value()==10
    print('UI_BASELINE_OK: stacked controls; recording duration=10s')
else:
    assert window.inspector_tabs.count()==3
    window.capture_duration_slider.setValue(25)
    assert window.capture_seconds.value()==25
    window.info={'duration':10,'width':640,'height':360}
    from wallpaper_studio.ui import update_media_window
    update_media_window(window)
    window.duration_range.set_range(2,8)
    assert (window.start.value(),window.end.value())==(2,8)
    assert not window.log.isVisible()
    assert not window.capture_advanced.body.isVisible()
    print('UI_MODIFIED_OK: 3 tabs; duration slider=25s; selected range=2..8s; advanced/log hidden')
window.close()

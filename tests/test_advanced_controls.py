import json, os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication

def test_read_properties_and_validate(tmp_path):
    from wallpaper_studio.properties import read_properties, validate_values
    p=tmp_path/'project.json'
    p.write_text(json.dumps({'general':{'properties':{'clock':{'type':'bool','text':'时钟','value':True},'speed':{'type':'slider','value':2,'min':0,'max':5},'quality':{'type':'combo','value':'low','options':[{'label':'低','value':'low'},{'label':'高','value':'high'}]}}}}))
    schema=read_properties(p)
    assert validate_values(schema,{'clock':False,'speed':3,'quality':'high'})['clock'] is False
    for v in ({'speed':7},{'clock':'false'},{'quality':'fake'},{'unknown':1}):
        with pytest.raises(ValueError): validate_values(schema,v)

def test_command_is_window_scoped():
    from wallpaper_studio.properties import properties_command
    command=properties_command(Path('engine.exe'),'WallpaperStudio-owned',{'clock':False})
    assert command[-2:]==['-location','WallpaperStudio-owned']
    assert json.loads(command[4][5:-5])=={'clock':False}
    with pytest.raises(ValueError): properties_command(Path('engine.exe'),'',{'clock':False})

def test_scale_dimensions_exact_not_silent_clamp():
    from wallpaper_studio.models import scaled_size
    assert scaled_size(2420,1668,2)==(4840,3336)
    assert scaled_size(320,240,8)==(2560,1920)
    with pytest.raises(ValueError): scaled_size(3840,2160,8)

def test_ui_controls_and_dual_composition(tmp_path):
    from wallpaper_studio.app import StudioWindow
    app=QApplication.instance() or QApplication([])
    w=StudioWindow(False)
    w.info={'width':3840,'height':2160}
    assert hasattr(w,'property_form') and hasattr(w,'render_multiplier')
    w.output_multiplier.setCurrentText('2×')
    assert (w.edit_settings().width,w.edit_settings().height)==(4840,3336)
    w.rotation_adaptive.setChecked(True)
    settings=w.edit_settings()
    assert (settings.width,settings.height)==(4840,4840)
    assert settings.fit=='adaptive'
    assert len(w.export_variants())==1
    w.close()

def test_staged_properties_leave_original_unchanged(tmp_path):
    from wallpaper_studio.properties import prepare_properties
    from wallpaper_studio.source import stage_project,hash_manifest,verify_manifest
    source=tmp_path/'source';source.mkdir()
    p=source/'project.json';p.write_text(json.dumps({'general':{'properties':{'clock':{'type':'bool','value':True}}}}))
    before=hash_manifest(source)
    staged=stage_project(source,tmp_path/'jobs')
    prepare_properties(staged/'project.json',{'clock':False})
    assert json.loads((staged/'project.json').read_text())['general']['properties']['clock']['value'] is False
    verify_manifest(source,before)

def test_real_dual_png_export_dimensions(tmp_path,monkeypatch):
    import subprocess
    from PIL import Image
    from wallpaper_studio import media
    from wallpaper_studio.app import StudioWindow
    from PySide6.QtCore import QRectF
    app=QApplication.instance() or QApplication([])
    source=tmp_path/'grid.mkv'
    subprocess.run([str(media.ffmpeg_path()),'-y','-f','lavfi','-i','testsrc2=s=320x240:r=5:d=1','-c:v','ffv1',str(source)],check=True,capture_output=True)
    w=StudioWindow(False);w.video=source;w.info=media.probe(source);w.timestamps=media.frame_timestamps(source)
    w.output_dir=tmp_path/'out';w.output_width.setValue(160);w.output_height.setValue(120)
    w.output_multiplier.setCurrentText('2×');w.end.setValue(1)
    w.rotation_adaptive.setChecked(True);w.canvas.crop=QRectF(0,0,1,1)
    observed=[]
    monkeypatch.setattr(w,'run_task',lambda job,done:observed.append(job(None,lambda *a:None)))
    w.export()
    folder=next(w.output_dir.iterdir())
    assert Image.open(folder/'frame.png').size==(320,320)
    assert not (folder/'landscape').exists() and not (folder/'portrait').exists()
    assert json.loads((folder/'variants.json').read_text(encoding='utf-8'))['automatic_device_rotation'] is False
    assert observed
    w.close()


def test_adaptive_canvas_has_shared_safe_area():
    from wallpaper_studio.models import rotation_regions
    regions=rotation_regions(2420,1668)
    assert regions['landscape']==(0,376,2420,1668)
    assert regions['portrait']==(376,0,1668,2420)
    assert regions['shared']==(376,376,1668,1668)

def test_invalid_property_does_not_discard_recording(monkeypatch,tmp_path):
    from wallpaper_studio.app import StudioWindow
    from wallpaper_studio.models import WallpaperEntry
    from PySide6.QtWidgets import QLineEdit
    app=QApplication.instance() or QApplication([])
    w=StudioWindow(False);w.entry=WallpaperEntry(tmp_path,'test','scene')
    w.video=tmp_path/'recording.mp4';w.timestamps=[0,1]
    w.property_schema={'color':{'type':'color'}};w.property_controls={'color':QLineEdit('invalid')}
    errors=[];monkeypatch.setattr(w,'task_error',errors.append)
    w.preview_scene()
    assert w.video==tmp_path/'recording.mp4' and w.timestamps==[0,1]
    assert errors
    w.close()

def test_pending_properties_do_not_block_rendered_export(monkeypatch,tmp_path):
    from wallpaper_studio.app import StudioWindow
    from PySide6.QtWidgets import QLineEdit
    app=QApplication.instance() or QApplication([])
    w=StudioWindow(False);w.video=tmp_path/'video.mp4';w.info={'width':32,'height':24};w.timestamps=[0,1];w.end.setValue(1)
    w.property_schema={'color':{'type':'color'}};w.property_controls={'color':QLineEdit('invalid')}
    jobs=[];monkeypatch.setattr(w,'run_task',lambda *args:jobs.append(args))
    w.export()
    assert len(jobs)==1
    w.close()

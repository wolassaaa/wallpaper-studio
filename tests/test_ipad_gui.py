import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication

def test_ipad_gui_entry():
 from wallpaper_studio.app import StudioWindow
 app=QApplication.instance() or QApplication([])
 w=StudioWindow(False)
 try:
  assert hasattr(w,'apply_ipad_preset')
  w.apply_ipad_preset()
  assert w.format_box.currentIndex()==5
  assert '满屏' in w.export_note.text()
  assert w.canvas.ipad_profile
 finally:w.close()

def test_integrated_module_has_no_private_template_dependency():
 from wallpaper_studio import ipad_export
 assert ipad_export.ipad_composition((1920,1080))['canvas']==[2420,2420]
 assert len(ipad_export.MOTION_SEED)==2
 assert 'artifacts' not in ipad_export.__file__.split('wallpaper_studio')[-1]


def test_packaged_pipeline_synthetic_motion(tmp_path):
 import threading,hashlib,json
 from wallpaper_studio.ipad_export import export_ipad,split_hybrid,validate_ipad_pair
 from wallpaper_studio.media import ffmpeg_path
 from wallpaper_studio.source import run_tool
 from wallpaper_studio.models import EditSettings
 source=tmp_path/'synthetic.mp4'
 run_tool([str(ffmpeg_path()),'-v','error','-f','lavfi','-i','testsrc2=size=320x240:rate=30:duration=2','-c:v','libx264',str(source)])
 before=hashlib.sha256(source.read_bytes()).hexdigest()
 result=export_ipad(source,tmp_path/'output',EditSettings(start=0,end=2,cover=.75),threading.Event())
 assert result['composition']['canvas']==[2420,2420]
 assert result['motion_profile']['cover_time'] in (.5,31/60)
 assert abs(result['source_start_seconds']-.25)<1/30
 assert result['validation']['valid']
 a,b=split_hybrid(result['single_file'].read_bytes())
 assert a==result['photo'].read_bytes() and b==result['video'].read_bytes()
 assert list((tmp_path/'output').iterdir())==[result['final_file']]
 assert result['photo'].parent!=tmp_path/'output'
 assert abs(validate_ipad_pair(result['photo'],result['video'])['still_image_time']-result['motion_profile']['cover_time'])<1e-6
 assert hashlib.sha256(source.read_bytes()).hexdigest()==before

def test_cancel_and_short_selection(tmp_path):
 import threading,pytest
 from wallpaper_studio.ipad_export import export_ipad
 from wallpaper_studio.models import EditSettings
 src=tmp_path/'source.mp4';src.write_bytes(b'fixture')
 with pytest.raises(ValueError,match='1 秒'):
  export_ipad(src,tmp_path/'short',EditSettings(start=0,end=.4,cover=.2))
 cancel=threading.Event();cancel.set()
 with pytest.raises((InterruptedError,RuntimeError)):
  export_ipad(src,tmp_path/'cancel',cancel=cancel)
 assert not (tmp_path/'cancel').exists()


def test_gui_export_routes_to_background_packager(monkeypatch,tmp_path):
 from wallpaper_studio.app import StudioWindow
 from wallpaper_studio import ipad_export
 app=QApplication.instance() or QApplication([])
 w=StudioWindow(False)
 try:
  w.video=tmp_path/'video.mp4';w.output_dir=tmp_path/'exports';w.start.setValue(0);w.end.setValue(2);w.cover.setValue(.8)
  w.apply_ipad_preset()
  calls=[]
  monkeypatch.setattr(ipad_export,'export_ipad',lambda *args,**kwargs:calls.append(args) or {'ipad':True})
  monkeypatch.setattr(w,'run_task',lambda job,done:job(None,lambda *args:None))
  w.export()
  assert len(calls)==1 and calls[0][0]==w.video
  assert calls[0][1].parent==w.output_dir
  assert calls[0][2].cover==.8
  assert not w.output_multiplier.isEnabled()
  w.format_box.setCurrentIndex(0)
  assert not w.canvas.ipad_profile and w.output_multiplier.isEnabled()
 finally:w.close()

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

def test_rgb_static_filter_and_luma_sharpen():
 from wallpaper_studio.ipad_export import ipad_composition, _ipad_filter
 layout=ipad_composition((3840,2160),multiplier=3)
 filt=_ipad_filter(layout,sharpen=.35,static=True)
 assert 'unsharp=5:5:0.35:5:5:0' in filt
 assert 'format=rgb24' in filt and 'format=yuv420p' not in filt
 assert layout['canvas']==[7260,7260]

def test_quality_controls_route_static_export(monkeypatch,tmp_path):
 from PySide6.QtWidgets import QApplication
 from wallpaper_studio.app import StudioWindow
 from wallpaper_studio import ipad_export
 app=QApplication.instance() or QApplication([]);w=StudioWindow(False)
 try:
  w.apply_ipad_preset();w.ipad_package.setCurrentIndex(3)
  assert w.ipad_multiplier.isEnabled()
  assert '7260' in w.pixel_summary.text()
  w.video=tmp_path/'source.mp4';w.output_dir=tmp_path/'exports'
  w.start.setValue(0);w.end.setValue(.4);w.cover.setValue(.2)
  calls=[]
  monkeypatch.setattr(ipad_export,'export_ipad',lambda *a,**k:calls.append(k) or {})
  monkeypatch.setattr(w,'run_task',lambda job,done:job(None,None))
  w.export()
  assert calls[0]['package']=='png' and calls[0]['multiplier']==3
  assert calls[0]['sharpen']==.35
  w.ipad_package.setCurrentIndex(2)
  assert not w.ipad_multiplier.isEnabled() and '2420' in w.pixel_summary.text()
 finally:w.close()

def test_short_video_selected_frame_static_only(tmp_path):
 import hashlib
 from PIL import Image
 from wallpaper_studio.ipad_export import export_ipad
 from wallpaper_studio.media import ffmpeg_path
 from wallpaper_studio.source import run_tool
 from wallpaper_studio.models import EditSettings
 source=tmp_path/'red-blue.mp4'
 run_tool([str(ffmpeg_path()),'-v','error','-f','lavfi','-i','color=red:size=160x160:rate=10:duration=0.2','-f','lavfi','-i','color=blue:size=160x160:rate=10:duration=0.2','-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0[out]','-map','[out]','-c:v','libx264',str(source)])
 before=hashlib.sha256(source.read_bytes()).hexdigest()
 result=export_ipad(source,tmp_path/'delivery',EditSettings(start=0,end=.4,cover=.3),package='png',sharpen=.35,work_root=tmp_path/'jobs')
 assert result['kind']=='static' and result['motion_profile'] is None
 assert len(list((tmp_path/'delivery').iterdir()))==1
 with Image.open(result['final_file']) as im:
  r,g,b=im.convert('RGB').getpixel((1210,1210));assert b>200 and r<30
 assert result['quality']['sharpen']==.35
 assert result['quality']['detail_recovery']=='none'
 assert result['quality']['source_crop_size'][0]<160
 assert hashlib.sha256(source.read_bytes()).hexdigest()==before

def test_invalid_sharpen_fails_before_work(tmp_path):
 import pytest
 from wallpaper_studio.ipad_export import export_ipad
 for value in (-1,2,float('nan')):
  with pytest.raises(ValueError,match='sharpen'):
   export_ipad(tmp_path/'unused.png',tmp_path/'output',sharpen=value,work_root=tmp_path/'jobs')
 assert not (tmp_path/'jobs').exists()

def test_sharpen_changes_edges_not_dimensions(tmp_path):
 from PIL import Image
 import numpy as np
 from wallpaper_studio.ipad_export import _ipad_filter
 from wallpaper_studio.media import ffmpeg_path
 from wallpaper_studio.source import run_tool
 source=tmp_path/'edges.png'
 a=np.full((32,32,3),100,dtype=np.uint8);a[:,16:]=150
 Image.fromarray(a).save(source)
 layout={'fit':'crop','canvas':[96,96],'foreground_size':[96,96],'foreground_offset':[0,0]}
 results=[]
 for i,strength in enumerate((0,.35)):
  output=tmp_path/f'{i}.png'
  run_tool([str(ffmpeg_path()),'-v','error','-i',str(source),'-filter_complex',_ipad_filter(layout,sharpen=strength,static=True),'-map','[out]','-frames:v','1',str(output)])
  with Image.open(output) as im:
   assert im.size==(96,96);results.append(np.asarray(im.convert('RGB')))
 assert np.any(results[0]!=results[1])
 assert np.abs(results[1][:,:20].astype(int)-results[0][:,:20].astype(int)).max()<=2
 assert (int(results[1].max())-int(results[1].min())) >= (int(results[0].max())-int(results[0].min()))

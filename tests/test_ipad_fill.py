from wallpaper_studio.ipad_export import ipad_composition,_ipad_filter

def test_no_small_inset_default():
 layout=ipad_composition((3840,2160))
 edge=layout['canvas'][0];fw,fh=layout['foreground_size'];x,y=layout['foreground_offset']
 assert fw>=edge and fh>=edge
 assert x<=0 and y<=0 and x+fw>=edge and y+fh>=edge
 assert 'boxblur' not in _ipad_filter(layout)
 assert layout['fit']=='crop'

def test_measured_subject_alignment():
 layout=ipad_composition((3840,2160),fit='crop',anchor=(.5,.5))
 fw,fh=layout['foreground_size'];x,y=layout['foreground_offset']
 cx,cy=layout['target_center']
 assert abs(x+fw*.5-cx)<=1 and abs(y+fh*.5-cy)<=1
 assert abs(fw/fh-3840/2160)<.005

def test_png_landscape_portrait_both_fill(tmp_path):
 from PIL import Image
 from wallpaper_studio.ipad_export import export_ipad
 source=tmp_path/'solid.png';Image.new('RGB',(320,180),(240,30,20)).save(source)
 result=export_ipad(source,tmp_path/'export',work_root=tmp_path/'jobs')
 final=result['final_file']
 assert list((tmp_path/'export').iterdir())==[final]
 assert final.name=='wallpaper.png'
 im=Image.open(final).convert('RGB')
 for point in [(0,0),(1210,1210),(2419,2419)]:
  r,g,b=im.getpixel(point);assert r>220 and g<45 and b<35
 assert result['work_dir'].parent==tmp_path/'jobs'


def test_full_bleed_for_both_orientations_and_focus():
 from wallpaper_studio.ipad_export import IPAD_PROFILE
 for size in [(3840,2160),(1080,1920),(2420,2420)]:
  for fit in ('stretch','crop'):
   for anchor in [(.2,.2),(.5,.5),(.8,.8)]:
    layout=ipad_composition(size,fit=fit,anchor=anchor)
    x,y=layout['foreground_offset'];fw,fh=layout['foreground_size']
    assert x<=0 and y<=0 and x+fw>=2420 and y+fh>=2420
    for direction in ('landscape','portrait'):
     vx,vy,vw,vh=IPAD_PROFILE[direction+'_rect']
     assert x<=vx and y<=vy and x+fw>=vx+vw-1 and y+fh>=vy+vh-1

def test_default_gui_single_file_and_uniform_scale():
 import os
 os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
 from PySide6.QtWidgets import QApplication
 from wallpaper_studio.app import StudioWindow
 app=QApplication.instance() or QApplication([]);w=StudioWindow(False)
 try:
  w.apply_ipad_preset()
  assert w.ipad_controls.isHidden()==False
  assert w.canvas.ipad_options['fit']=='crop'
  w.ipad_fit.setCurrentIndex(1);assert w.canvas.ipad_options['fit']=='crop'
  w.ipad_x.setValue(60);assert w.canvas.ipad_options['anchor'][0]==.6
  w.ipad_view.setCurrentIndex(2);assert w.canvas.ipad_view==2
  assert '只输出一个' in w.export_note.text()
 finally:w.close()


def test_stretch_retains_entire_picture_and_maps_focal_point():
 layout=ipad_composition((3840,2160),fit='stretch')
 assert layout['foreground_size']==[2420,2420]
 assert layout['foreground_offset']==[0,0]
 assert len(layout['source_tiles'])==4 and len(layout['target_tiles'])==4
 assert 'hstack' in _ipad_filter(layout) and 'vstack' in _ipad_filter(layout)


def test_stretch_export_retains_source_corner_markers(tmp_path):
 from PIL import Image,ImageDraw
 from wallpaper_studio.ipad_export import export_ipad
 source=tmp_path/'corners.png';im=Image.new('RGB',(320,180),(60,60,60));d=ImageDraw.Draw(im)
 colors=[(240,30,20),(20,240,30),(30,20,240),(240,230,20)]
 for box,color in zip([(0,0,10,10),(309,0,319,10),(0,169,10,179),(309,169,319,179)],colors):d.rectangle(box,fill=color)
 im.save(source);result=export_ipad(source,tmp_path/'delivery',work_root=tmp_path/'jobs',fit='stretch',anchor=(.5,.5))
 final=Image.open(result['final_file']).convert('RGB')
 for point,wanted in zip([(0,0),(2419,0),(0,2419),(2419,2419)],colors):
  actual=final.getpixel(point);assert max(abs(a-b) for a,b in zip(actual,wanted))<20

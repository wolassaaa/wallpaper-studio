def test_default_keeps_uniform_scale():
 from wallpaper_studio.ipad_export import ipad_composition
 layout=ipad_composition((3840,2160))
 assert layout['fit']=='crop'
 w,h=layout['foreground_size']
 assert abs(w/3840-h/2160)<.001
 assert 'source_tiles' not in layout

def test_gui_does_not_offer_distorting_mode():
 import os
 os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
 from PySide6.QtWidgets import QApplication
 from wallpaper_studio.app import StudioWindow
 app=QApplication.instance() or QApplication([]);w=StudioWindow(False)
 try:
  w.apply_ipad_preset()
  assert w.canvas.ipad_options['fit']=='crop'
  assert all('拉伸' not in w.ipad_fit.itemText(i) for i in range(w.ipad_fit.count()))
  assert .3<=w.canvas.ipad_options['anchor'][1]<=.4
 finally:w.close()


def test_export_circle_is_not_stretched(tmp_path):
 from PIL import Image,ImageDraw
 import numpy as np
 from wallpaper_studio.ipad_export import export_ipad
 source=tmp_path/'circle.png';im=Image.new('RGB',(400,224),(10,10,10));ImageDraw.Draw(im).ellipse((150,62,250,162),fill=(240,20,20));im.save(source)
 result=export_ipad(source,tmp_path/'delivery',work_root=tmp_path/'jobs')
 arr=np.asarray(Image.open(result['final_file']).convert('RGB'))
 yy,xx=np.where((arr[:,:,0]>200)&(arr[:,:,1]<60)&(arr[:,:,2]<60))
 assert abs((xx.max()-xx.min())-(yy.max()-yy.min()))<=2
 assert len(list((tmp_path/'delivery').iterdir()))==1

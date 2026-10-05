from pathlib import Path
import pytest

def test_honor_profile_roundtrip_synthetic(tmp_path):
 from wallpaper_studio.motionphoto import build_honor,split_honor,HONOR_HEADER
 from PIL import Image
 import io,struct
 photo=io.BytesIO();Image.new('RGB',(32,32),'red').save(photo,format='JPEG')
 movie=struct.pack('>I',24)+b'ftyp'+b'mp42'+bytes(4)+b'isommp42'
 body=build_honor(photo.getvalue(),movie,400)
 parsed=split_honor(body)
 assert parsed['photo']==photo.getvalue() and parsed['movie']==movie
 assert parsed['cover_ms']==400 and parsed['header']==HONOR_HEADER
 assert body[-20:].strip()==b'LIVE_'+str(len(movie)+20).encode()

def test_invalid_and_no_source_metadata_copy():
 from wallpaper_studio.motionphoto import build_honor,split_honor
 with pytest.raises(ValueError):build_honor(b'not jpeg',b'not mp4',500)
 with pytest.raises(ValueError):split_honor(b'plain jpeg')


def test_corrupt_trailer_and_nested_photo_rejected():
 from wallpaper_studio.motionphoto import build_honor,split_honor
 from PIL import Image
 import io,struct
 p=io.BytesIO();Image.new('RGB',(8,8)).save(p,format='JPEG')
 movie=struct.pack('>I',24)+b'ftyp'+b'mp42'+bytes(4)+b'isommp42'
 body=build_honor(p.getvalue(),movie)
 with pytest.raises(ValueError):split_honor(body[:-1])
 with pytest.raises(ValueError):build_honor(body,movie)
 with pytest.raises(ValueError):build_honor(p.getvalue(),movie,-1)


def test_gui_selects_android_trial():
 import os
 os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
 from PySide6.QtWidgets import QApplication
 from wallpaper_studio.app import StudioWindow
 app=QApplication.instance() or QApplication([]);w=StudioWindow(False)
 try:
  w.apply_ipad_preset()
  assert w.ipad_package.currentIndex()==2
  assert '实验' in w.ipad_package.currentText()
  assert w.canvas.ipad_options['fit']=='crop'
 finally:w.close()

def test_android_single_file_export(tmp_path):
 from wallpaper_studio.ipad_export import export_ipad
 from wallpaper_studio.motionphoto import split_honor
 from wallpaper_studio.media import ffmpeg_path
 from wallpaper_studio.source import run_tool
 from PIL import Image
 source=tmp_path/'video.mp4'
 run_tool([str(ffmpeg_path()),'-v','error','-f','lavfi','-i','testsrc2=size=320x240:rate=30:duration=1.2','-c:v','libx264',str(source)])
 result=export_ipad(source,tmp_path/'delivery',package='honor',work_root=tmp_path/'jobs')
 assert result['android'] and result['final_file'].name=='wallpaper-motion.jpg'
 assert list((tmp_path/'delivery').iterdir())==[result['final_file']]
 parsed=split_honor(result['final_file'].read_bytes())
 assert parsed['movie']==result['video'].read_bytes()
 assert parsed['photo']==result['photo'].read_bytes()
 assert result['validation']['device_acceptance']=='unverified'
 with Image.open(result['final_file']) as im:im.load();assert im.size==(2420,2420)

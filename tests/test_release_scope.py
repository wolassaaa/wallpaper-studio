import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

def test_basic_release_hides_experiments():
 from PySide6.QtWidgets import QApplication
 from wallpaper_studio.app import StudioWindow
 app=QApplication.instance() or QApplication([]);w=StudioWindow(False)
 try:
  assert not w.format_box.model().item(4).isEnabled()
  assert not w.format_box.model().item(5).isEnabled()
  assert w.format_box.view().isRowHidden(4)
  assert w.ipad_preset_button.isHidden()
  assert w.rotation_adaptive.isHidden()
 finally:w.close()

def test_experimental_mode_preserves_existing_work():
 from PySide6.QtWidgets import QApplication
 from wallpaper_studio.app import StudioWindow
 app=QApplication.instance() or QApplication([]);w=StudioWindow(False,experimental=True)
 try:
  assert w.format_box.model().item(4).isEnabled()
  assert not w.format_box.view().isRowHidden(5)
  assert not w.ipad_preset_button.isHidden()
 finally:w.close()

def test_source_bundle_excludes_private_and_generated_files(tmp_path):
 from scripts.release_bundle import public_files
 for name in ('README.md','wallpaper_studio/app.py','artifacts/private.jpg','tests/__pycache__/a.pyc','tools/ffmpeg.exe','docs/.env','docs/private.mp4'):
  p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture')
 assert public_files(tmp_path)==['README.md','wallpaper_studio/app.py']

def test_source_audit_rejects_personal_paths(tmp_path):
 import pytest
 from scripts.release_bundle import public_files
 p=tmp_path/'README.md';p.write_text('C:' + '/' + 'Users/' + 'fixture-user/private')
 with pytest.raises(ValueError,match='personal'):
  public_files(tmp_path)

def test_source_bundle_keeps_distribution_license_names(tmp_path):
 from scripts.release_bundle import public_files
 name='licenses/component/distribution_licenses_LICENSE.APACHE'
 p=tmp_path/name;p.parent.mkdir(parents=True);p.write_text('license fixture')
 assert public_files(tmp_path)==[name]

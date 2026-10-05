import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import Mock
from PySide6.QtWidgets import QApplication

def test_live_result_opens_pair_preview(monkeypatch,tmp_path):
    from wallpaper_studio.app import StudioWindow
    from wallpaper_studio import pair_preview
    app=QApplication.instance() or QApplication([])
    w=StudioWindow(False)
    dialog=Mock();factory=Mock(return_value=dialog)
    monkeypatch.setattr(pair_preview,'LivePairPreview',factory)
    pair={'photo':tmp_path/'live.jpg','video':tmp_path/'live.mov','validation':{'valid':True,'device_acceptance':'unverified'}}
    w.export_done({'adaptive':pair})
    assert factory.call_count==1
    assert '相册识别待验证' in w.status.text()
    dialog.show.assert_called_once()
    w.close()

def test_direction_option_does_not_claim_apple_runtime():
    from wallpaper_studio.app import StudioWindow
    app=QApplication.instance() or QApplication([])
    w=StudioWindow(False)
    assert '取景' in w.rotation_adaptive.text()
    assert '系统旋转' in w.rotation_adaptive.toolTip()
    w.close()

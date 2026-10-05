def test_ipad_and_resolution():
    from wallpaper_studio.models import output_size
    assert output_size("device", "landscape", "device") == (2420, 1668)
    assert output_size("device", "portrait", "device") == (1668, 2420)
    assert output_size("4:3", "landscape", "4K") == (3840, 2880)
    assert output_size("16:9", "landscape", "8K") == (7680, 4320)
    assert output_size("device", "landscape", "custom", (1920,1080)) == (1920,1080)
    assert output_size("16:9", "portrait", "custom", (1920,1080)) == (1080,1920)

def test_defaults():
    from wallpaper_studio.models import EditSettings, CaptureSettings
    assert EditSettings().width == 2420
    assert CaptureSettings().fps == 30
    assert CaptureSettings().seconds == 10

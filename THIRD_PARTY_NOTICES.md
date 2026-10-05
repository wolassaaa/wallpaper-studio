# Third-party notices

Wallpaper Studio source: GPL-3.0-or-later.

## wallpaper-engine-exporter
Reference/control syntax and Steam discovery adapted from https://github.com/suye-sama/wallpaper-engine-exporter v0.4.1 (5d1f915).

MIT License

Copyright (c) 2026 suye-sama

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.


## RePKG
https://github.com/notscuffed/repkg commit 8005eb2; packaged binary supplied by wallpaper-engine-exporter v0.4.1.

MIT License

Copyright (c) 2019 notscuffed

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.


## FFmpeg
Distributed as a separate executable from Gyan Windows GPLv3 builds. Exact archive URL/hash are recorded in tools-manifest.json. Corresponding source and build configuration: https://www.gyan.dev/ffmpeg/builds/ and https://github.com/FFmpeg/FFmpeg . GPL text: LICENSE. FFmpeg -buildconf lists enabled libraries.

## Qt/PySide6
LGPL-3.0 / GPL-3.0 / commercial. Qt DLLs remain dynamically loaded. License texts shipped by PySide6 are included by PyInstaller collection. Source: https://code.qt.io/pyside/pyside-setup.git/ and https://code.qt.io/qt/ .

## Other runtime dependencies
Pillow (HPND), NumPy (BSD-3-Clause), OpenCV (Apache-2.0), windows-capture (MIT), imageio-ffmpeg (BSD-2-Clause), PyInstaller (GPL with bootloader exception). Package LICENSE files distributed in the portable package; dependencies pinned in requirements-lock.txt.


## pillow-heif 1.8.0
BSD-3-Clause. HEIF codec wheels include libheif and codec dependencies; their distributed license files are collected into the portable package. Source: https://github.com/bigcat88/pillow_heif .

## Experimental LIVP ZIP comment layout
Layout reference: Hiwoniu/live-photos (MIT), https://github.com/Hiwoniu/live-photos . Implemented independently; no repository code copied. Private wallpaper/camera media is not distributed. The experimental repeated motion-metadata seed contains only format descriptors, constant samples, and reference framework build strings, not media or personal asset identifiers.

# Acceptance record

Release: 0.1.0. Device acceptance is distinct from structural validation.

| Check | Evidence / status |
|---|---|
| PNG/GIF/MP4 decoded frames and crop | Automated synthetic-media tests |
| JPEG MakerApple key 17 matches MOV identifier | Automated binary/EXIF tests |
| Real mebx timed metadata track and marker sample | Automated atom parser + FFmpeg decode |
| Apple Photos recognizes LIVE and plays | Pending physical device test |
| Lock-screen motion | Pending separate device/system test |
| Scene/Web native window capture | Local integration report, when generated |
| 4K/8K actual capture | Local integration report, when generated; no guarantee from requested size alone |
| Clean Windows without Python | Pending separate machine test; frozen-process smoke runs are recorded separately |

Apple-device test: record model, OS version, transfer method, whether both resources preserved, LIVE badge, playback, cover/frame alignment, and lock-screen result. A transport failure is not automatically a format failure. No Photos/lock-screen compatibility claim before this result exists.

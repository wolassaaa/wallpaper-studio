$ErrorActionPreference='Stop'
$Root=Split-Path -Parent $PSScriptRoot
$Tools=Join-Path $Root 'tools'
$Cache=Join-Path $Root 'build\downloads'
New-Item -ItemType Directory -Force -Path $Tools,$Cache | Out-Null
$RePkgUrl='https://raw.githubusercontent.com/suye-sama/wallpaper-engine-exporter/5d1f9158742ffa008c136f4782b9f2c266f6c8d3/tools/RePKG/RePKG.exe'
$RePkgHash='b5e0d603bad5be7c6605c31b96ddfb8bc2391658f777872a56f283ab2038acf1'
$RePkg=Join-Path $Tools 'RePKG.exe'
if (-not (Test-Path -LiteralPath $RePkg)) { Invoke-WebRequest $RePkgUrl -OutFile $RePkg }
if ((Get-FileHash -LiteralPath $RePkg).Hash -ine $RePkgHash) { throw 'RePKG SHA256 mismatch' }
$FfmpegUrl='https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip'
$FfmpegHash='60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba'
if (-not (Test-Path -LiteralPath (Join-Path $Tools 'ffmpeg.exe')) -or -not (Test-Path -LiteralPath (Join-Path $Tools 'ffprobe.exe'))) {
    $Archive=Join-Path $Cache 'ffmpeg.zip'
    Invoke-WebRequest $FfmpegUrl -OutFile $Archive
    if ((Get-FileHash -LiteralPath $Archive).Hash -ine $FfmpegHash) { throw 'FFmpeg archive SHA256 mismatch' }
    Expand-Archive -LiteralPath $Archive -DestinationPath (Join-Path $Cache 'ffmpeg') -Force
    Get-ChildItem (Join-Path $Cache 'ffmpeg') -Recurse -File | Where-Object {$_.Name -in 'ffmpeg.exe','ffprobe.exe'} | Copy-Item -Destination $Tools
}
foreach ($Check in @(@{name='ffmpeg.exe';hash='3256173f3f8bffd7df12227c68adf68025edb1832273a9530688a7bb1ed8edec'},@{name='ffprobe.exe';hash='f0d36ecbbdd3bcfac3efa078c96c7271c2e68b3810595552ac3b7f17e9a65c52'})) {
    if ((Get-FileHash -LiteralPath (Join-Path $Tools $Check.name)).Hash -ine $Check.hash) { throw "Bundled binary SHA256 mismatch: $($Check.name)" }
}
@{repkg=@{url=$RePkgUrl;sha256=$RePkgHash};ffmpeg=@{url=$FfmpegUrl;sha256=$FfmpegHash}} | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 (Join-Path $Root 'tools-manifest.json')
& (Join-Path $Root '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'collect_licenses.py')
if ($LASTEXITCODE -ne 0) { throw 'License collection failed' }

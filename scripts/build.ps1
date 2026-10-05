param([switch]$OneFile, [switch]$Both)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Version = (& $Python -c "from wallpaper_studio import __version__; print(__version__)").Trim()
$DistRoot = "dist\v$Version"
if (-not (Test-Path -LiteralPath $Python)) { throw 'Run scripts/setup.ps1 first' }
foreach ($Tool in @('RePKG.exe','ffmpeg.exe','ffprobe.exe')) {
    if (-not (Test-Path -LiteralPath (Join-Path $Root "tools\$Tool"))) { throw "Missing bundled tool: $Tool" }
}
& "$PSScriptRoot\prepare-tools.ps1"
if ($LASTEXITCODE -ne 0) { throw 'Tool verification failed' }
Push-Location $Root
$OriginalPath = $env:PATH
try {
    # Isolate DLL discovery from unrelated host tools (e.g. Poppler's ICU).
    # Qt uses Windows' unversioned ICU API, not third-party versioned exports.
    $env:PATH = "$Root\.venv\Scripts;$env:SystemRoot\System32;$env:SystemRoot"
    & $Python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
    $Modes = @('onedir')
    if ($OneFile) { $Modes = @('onefile') }
    if ($Both) { $Modes = @('onedir','onefile') }
    foreach ($Mode in $Modes) {
        & $Python -m PyInstaller --noconfirm --clean --windowed "--$Mode" --name WallpaperStudio --distpath "$DistRoot\$Mode" --workpath "build\$Mode" --specpath build --paths $Root --add-binary "$Root\tools\ffmpeg.exe;tools" --add-binary "$Root\tools\ffprobe.exe;tools" --add-binary "$Root\tools\RePKG.exe;tools" --add-data "$Root\THIRD_PARTY_NOTICES.md;." --add-data "$Root\LICENSE;." --add-data "$Root\licenses;licenses" --collect-all pillow_heif --collect-all windows_capture --hidden-import cv2 --exclude-module tkinter scripts/entry.py
        if ($LASTEXITCODE -ne 0) { throw "Packaging failed: $Mode" }
    }
    if (Test-Path "$DistRoot\onedir\WallpaperStudio") {
        Copy-Item README.md,THIRD_PARTY_NOTICES.md,LICENSE -Destination "$DistRoot\onedir\WallpaperStudio"
        Compress-Archive -LiteralPath "$DistRoot\onedir\WallpaperStudio" -DestinationPath "$DistRoot\WallpaperStudio-$Version-win64.zip" -Force
    }
    $Files = @(Get-ChildItem $DistRoot -Recurse -File | Where-Object {$_.Name -eq 'WallpaperStudio.exe' -or $_.Extension -eq '.zip'})
    $Files | ForEach-Object { $Hash=Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256; "$($Hash.Hash.ToLower())  $($_.FullName.Substring($Root.Length+1))" } | Set-Content -Encoding utf8 "$DistRoot\SHA256SUMS.txt"
} finally { $env:PATH = $OriginalPath; Pop-Location }

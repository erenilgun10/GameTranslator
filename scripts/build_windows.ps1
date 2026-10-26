param([string]$Python = '.\.venv\Scripts\python.exe')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Push-Location -LiteralPath $projectRoot
try {
    & $Python -m pytest -q --tb=short
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed; package not built.' }
    & $Python -m PyInstaller --noconfirm --clean --onedir --windowed --name GameTranslator --paths src scripts/desktop_entry.py
    if ($LASTEXITCODE -ne 0) { throw 'Desktop packaging failed.' }
    & $Python -m PyInstaller --noconfirm --clean --onefile --console --name GameTranslator-CLI --paths src scripts/cli_entry.py
    if ($LASTEXITCODE -ne 0) { throw 'CLI packaging failed.' }
    Copy-Item -LiteralPath 'dist/GameTranslator-CLI.exe' -Destination 'dist/GameTranslator/GameTranslator-CLI.exe' -Force
    Copy-Item -LiteralPath 'README.md','LICENSE','scripts/Install-GameTranslator.ps1' -Destination 'dist/GameTranslator' -Force
    Copy-Item -LiteralPath 'examples' -Destination 'dist/GameTranslator/examples' -Recurse -Force
    $pythonRoot = & $Python -c 'import sys; print(sys.base_prefix)'
    $licenseDirectory = 'dist/GameTranslator/licenses'
    New-Item -ItemType Directory -Path $licenseDirectory -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $pythonRoot 'LICENSE.txt') -Destination (Join-Path $licenseDirectory 'Python-LICENSE.txt') -Force
    $tclVersion = & $Python -c "import tkinter; t=tkinter.Tcl(); print(t.call('info', 'patchlevel'))"
    if ($LASTEXITCODE -ne 0) { throw 'Tcl runtime version detection failed.' }
    $tclLicense = "licenses/Tcl-$tclVersion-license.terms"
    if (-not (Test-Path -LiteralPath $tclLicense)) { throw "Review and add Tcl $tclVersion license before packaging." }
    Copy-Item -LiteralPath $tclLicense -Destination $licenseDirectory -Force
    Copy-Item -LiteralPath (Join-Path $pythonRoot 'tcl/tk8.6/license.terms') -Destination (Join-Path $licenseDirectory 'Tk-license.terms') -Force
    $version = & $Python -c 'from game_translator import __version__; print(__version__)'
    & $Python scripts/smoke_windows.py dist/GameTranslator
    if ($LASTEXITCODE -ne 0) { throw 'Frozen package smoke test failed.' }
    $releaseDirectory = Join-Path $projectRoot 'release'
    New-Item -ItemType Directory -Path $releaseDirectory -Force | Out-Null
    $zip = Join-Path $releaseDirectory "GameTranslator-$version-windows-x64.zip"
    Compress-Archive -Path 'dist/GameTranslator' -DestinationPath $zip -Force
    $hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $(Split-Path $zip -Leaf)" | Set-Content -LiteralPath "$zip.sha256" -Encoding ascii
    Write-Output "PACKAGE=$zip"
    Write-Output "SHA256=$hash"
} finally {
    Pop-Location
}

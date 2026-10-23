param([string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'Programs/GameTranslator'))
$ErrorActionPreference = 'Stop'
$sourceDir = $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $sourceDir 'GameTranslator.exe'))) {
    throw 'Run this installer from the extracted Windows release folder.'
}
$targetDir = [IO.Path]::GetFullPath($InstallDir)
if ($targetDir.TrimEnd('\') -eq $sourceDir.TrimEnd('\') -or $targetDir.StartsWith($sourceDir.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Choose an installation target outside the extracted package.'
}
$parentDir = [IO.DirectoryInfo]$targetDir
while ($null -ne $parentDir) {
    if ($parentDir.Exists -and ($parentDir.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Symlink/junction installation targets are unsupported.' }
    $parentDir = $parentDir.Parent
}
if (Test-Path -LiteralPath $targetDir) {
    throw 'Installation target already exists. Choose a new empty location; existing files will not be overwritten.'
}
New-Item -ItemType Directory -Path $targetDir | Out-Null
Get-ChildItem -LiteralPath $sourceDir | Copy-Item -Destination $targetDir -Recurse
if (-not (Test-Path -LiteralPath (Join-Path $targetDir 'GameTranslator.exe'))) {
    throw 'Installation verification failed.'
}
Write-Output "Installed: $targetDir"
Write-Output 'Launch GameTranslator.exe. To uninstall, remove this application folder; projects and backups are separate.'

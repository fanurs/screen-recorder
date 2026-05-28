# Create a Start-menu shortcut to the built ScreenRecorder.exe.
#
# Usage:
#   tools/install_shortcut.ps1               # after running pyinstaller
#
# What it does:
#   - Resolves dist/ScreenRecorder/ScreenRecorder.exe to an absolute path.
#   - Drops a .lnk into the current user's Start menu so Win+S finds it.
#   - Uses the bundled app.ico as the icon.

$ErrorActionPreference = "Stop"

$root      = Split-Path -Parent $PSScriptRoot      # project root
$target    = Join-Path $root "dist\ScreenRecorder\ScreenRecorder.exe"
$workDir   = Split-Path -Parent $target
$icon      = Join-Path $root "src\screen_recorder\assets\app.ico"
$startMenu = [Environment]::GetFolderPath("Programs")
$lnk       = Join-Path $startMenu "Screen Recorder.lnk"

if (-not (Test-Path $target)) {
    Write-Error "Not found: $target`nBuild first with: uv run pyinstaller screen-recorder.spec"
}

$wsh = New-Object -ComObject WScript.Shell
$s   = $wsh.CreateShortcut($lnk)
$s.TargetPath       = $target
$s.WorkingDirectory = $workDir
$s.IconLocation     = "$icon,0"
$s.Description      = "Screen Recorder"
$s.Save()

Write-Output "Created shortcut: $lnk"
Write-Output "Press the Windows key and type 'Screen Recorder' to launch."

# Build the Windows release: fresh web UI, then the PyInstaller folder, then the installer if Inno Setup is present.
#   powershell -ExecutionPolicy Bypass -File scripts\build.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$python = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "== web UI ==" -ForegroundColor Cyan
Push-Location web
npm ci
npm run build
Pop-Location

Write-Host "== service bundle ==" -ForegroundColor Cyan
Push-Location build
& $python -m PyInstaller orion.spec --noconfirm --distpath ..\dist --workpath ..\build\work
Pop-Location

$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    Write-Host "== installer ==" -ForegroundColor Cyan
    & $iscc build\orion.iss
    Write-Host "Installer: dist\installer\" -ForegroundColor Green
} else {
    Write-Host "Inno Setup 6 is not installed, so only dist\ORION was built. Get it from https://jrsoftware.org/isinfo.php" -ForegroundColor Yellow
}

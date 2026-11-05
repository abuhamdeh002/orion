# First launch on a PC. Asks for the license key, then starts ORION.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$data = Join-Path $env:LOCALAPPDATA "ORION"
New-Item -ItemType Directory -Force -Path $data | Out-Null
$keyFile = Join-Path $data "license.key"
if (-not (Test-Path $keyFile)) {
    $key = Read-Host "Paste the ORION license key"
    if ($key) { Set-Content -Path $keyFile -Value $key.Trim() -Encoding utf8 }
}
$exe = Join-Path $root "dist\ORION\ORION.exe"
if (Test-Path $exe) { Start-Process $exe } else { Write-Output "Build dist\ORION\ORION.exe first. See docs\BUILD.md." }

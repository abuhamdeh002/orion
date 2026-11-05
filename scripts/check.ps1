# Run every test suite in the repo. Exit code is non-zero if any fails.
#   powershell -ExecutionPolicy Bypass -File scripts\check.ps1
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }
$failed = @()

function Step($name, [scriptblock]$body) {
    Write-Host "`n== $name ==" -ForegroundColor Cyan
    & $body
    if ($LASTEXITCODE -ne 0) { $script:failed += $name }
}

if (& $python -m ruff --version 2>$null) {
    Step "ruff" { & $python -m ruff check . --select E9,F63,F7,F82 --exclude .venv,node_modules }
}
Step "pytest" { & $python -m pytest -q }
Step "web typecheck" { Push-Location web; npx tsc --noEmit -p .; Pop-Location }
Step "web tests" { Push-Location web; node --test wake.test.ts; Pop-Location }
Step "relay tests" { Push-Location cloud\relay; npx vitest run; Pop-Location }
Step "site tests" { Push-Location cloud\site; npx vitest run; Pop-Location }
if (Test-Path android\gradlew.bat) {
    Step "android unit tests" { Push-Location android; .\gradlew.bat test; Pop-Location }
}

if ($failed.Count) {
    Write-Host "`nFailed: $($failed -join ', ')" -ForegroundColor Red
    exit 1
}
Write-Host "`nAll checks passed." -ForegroundColor Green

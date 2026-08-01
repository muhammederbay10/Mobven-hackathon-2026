# YetkiCheck — safe demo reset (Windows).
#
# Restores the database, the runtime registry and demo uploads to their
# committed baseline (plan section 8.2). The extraction cache is deliberately
# preserved: GAP-11 pre-warms cases 2-4 during final rehearsal and the section 16
# runbook runs this reset immediately before the judged run.

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

Push-Location $repoRoot
try {
    & $python -m api.services.demo_service
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

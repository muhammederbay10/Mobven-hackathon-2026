# YetkiCheck — clear reusable AI results (Windows).
#
# Removes every validated /extract response from the backend-owned extraction
# cache. It deliberately does not touch SQLite, registry.json, uploads, or
# source documents. For a completely fresh application run, use the dashboard's
# "Demoyu sıfırla" action as well; the order does not matter.

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { $python = "python" }

Push-Location $repoRoot
try {
    & $python -m api.services.cache_cli
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}

<#
GroundTruth one-shot runner (Windows).   .\run.ps1 [local|docker|test|setup]
  local  (default): create venv, install deps, migrate the DB, start API (:8000) + worker + web (:3000)
  docker          : docker compose up --build (API, worker, Postgres, web)
#>
param([ValidateSet('local','docker','test','setup')][string]$Mode = 'local')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host 'Created .env from .env.example' }

if ($Mode -eq 'docker') { docker compose up --build; exit $LASTEXITCODE }

if (-not (Test-Path .venv)) { python -m venv .venv }
$py = '.venv\Scripts\python.exe'
& $py -m pip install -q --upgrade pip
& $py -m pip install -q -e 'packages/groundtruth[api,db,genai,dev]'
Push-Location apps\web; npm ci; Pop-Location

if ($Mode -eq 'setup') { Write-Host 'Setup complete.'; exit 0 }
if ($Mode -eq 'test')  { & $py -m pytest; exit $LASTEXITCODE }

# Create/upgrade tables once, then run the API and the background worker. Without the worker,
# a queued analysis stays "queued" forever and the Run page never completes.
& $py -m apps.worker.main --migrate --exit-when-idle
if ($LASTEXITCODE -ne 0) { throw 'Database migration failed (is DATABASE_URL set in .env?)' }
$api = Start-Process -PassThru -NoNewWindow $py -ArgumentList '-m','uvicorn','apps.api.main:app','--port','8000'
$worker = Start-Process -PassThru -NoNewWindow $py -ArgumentList '-m','apps.worker.main'
try {
  Push-Location apps\web
  $env:NEXT_PUBLIC_API_URL = 'http://localhost:8000'
  npx next dev -p 3000
} finally { Pop-Location; Stop-Process -Id $api.Id,$worker.Id -ErrorAction SilentlyContinue }

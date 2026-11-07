<#
GroundTruth one-shot runner (Windows).   .\run.ps1 [local|docker|test|setup]
  local  (default): create venv, install deps, start API (:8000) + web (:3000)
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

$api = Start-Process -PassThru -NoNewWindow $py -ArgumentList '-m','uvicorn','apps.api.main:app','--port','8000'
try {
  Push-Location apps\web
  $env:NEXT_PUBLIC_API_URL = 'http://localhost:8000'
  npx next dev -p 3000
} finally { Pop-Location; Stop-Process -Id $api.Id -ErrorAction SilentlyContinue }

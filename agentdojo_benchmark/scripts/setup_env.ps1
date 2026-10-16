# One-time setup for Windows (NIM phases 1-5 and local development). From the agentdojo_benchmark folder:
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup_env.ps1

Set-Location (Split-Path $PSScriptRoot -Parent)   # work from agentdojo_benchmark/, wherever this is started

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt   # installs this project and its dependencies
if (-not (Test-Path .env)) { Copy-Item .env.example .env }      # then put your NIM key in .env
.\.venv\Scripts\python.exe scripts\phase1_check_env.py
Write-Host "Activate later with: .\.venv\Scripts\Activate.ps1"

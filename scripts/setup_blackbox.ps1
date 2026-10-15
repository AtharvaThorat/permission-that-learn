# FOR LATER USER EXECUTION. Not run during implementation.
param([Parameter(Mandatory=$true)][string]$Python)
$ErrorActionPreference = 'Stop'
if (Test-Path -LiteralPath '.venv-blackbox') { throw 'Choose a fresh environment; .venv-blackbox already exists.' }
& $Python -m venv .venv-blackbox
if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed.' }
& '.\.venv-blackbox\Scripts\python.exe' -m pip install -r requirements-blackbox.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency resolution/install failed. Do not alter historical pins automatically.' }

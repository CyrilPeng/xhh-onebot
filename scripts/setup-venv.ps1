param(
    [string]$Python = $env:XHH_ONEBOT_PYTHON
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = $env:PYTHON
}

if ([string]::IsNullOrWhiteSpace($Python)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) {
        throw "Python executable not found. Set XHH_ONEBOT_PYTHON or PYTHON to a valid python.exe path."
    }
    $Python = $pythonCommand.Source
}

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$venvPath = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    & $Python -m venv $venvPath
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create virtual environment with: $Python"
    }
}

& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upgrade pip in: $venvPath"
}

& $venvPython -m pip install --upgrade setuptools wheel
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install build tools in: $venvPath"
}

& $venvPython -m pip install --no-build-isolation -e $projectRoot
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install xhh-onebot in editable mode."
}

Write-Host "Virtual environment is ready: $venvPath"
Write-Host "Activate with: .\.venv\Scripts\Activate.ps1"

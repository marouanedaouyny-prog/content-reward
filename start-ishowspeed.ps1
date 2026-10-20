$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$previewPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $previewPython)) {
    throw 'Run setup-transcription.ps1 first to install the clipping environment.'
}
& $previewPython -m clipping --ishowspeed

$ErrorActionPreference = 'Stop'
$instagramPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $instagramPython -PathType Leaf)) {
    throw 'Run setup-transcription.ps1 to prepare the Python environment first.'
}
Push-Location -LiteralPath $PSScriptRoot
try {
    Write-Host 'Connecting Instagram using a hidden local token prompt. No tunnel or callback URL is required.'
    & $instagramPython -m clipping.instagram_token
    if ($LASTEXITCODE -ne 0) {
        throw 'Instagram token connection did not finish. The safe status above identifies the remaining step.'
    }
} finally {
    Pop-Location
}

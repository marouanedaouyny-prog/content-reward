param([ValidateSet('tiny.en', 'small')][string]$Model = 'tiny.en')

$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $subtitlePython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    if (!(Test-Path -LiteralPath $subtitlePython)) {
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            & uv venv --python 3.11 --cache-dir .uv-cache .venv
        } else {
            & py -3.11 -m venv .venv
        }
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the project Python 3.11 environment.' }
    }

    & $subtitlePython -c 'import fastapi, uvicorn, multipart, yt_dlp, faster_whisper, requests'
    if ($LASTEXITCODE -ne 0) {
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            if (Test-Path -LiteralPath '.workflow-tests/cached-wheels') {
                & uv pip install --python $subtitlePython --cache-dir .uv-cache --offline --no-index --find-links .workflow-tests/cached-wheels -r requirements-clipping.txt -r requirements-transcription.txt
            } else {
                & uv pip install --python $subtitlePython --cache-dir .uv-cache -r requirements-clipping.txt -r requirements-transcription.txt
            }
        } else {
            & $subtitlePython -m pip install -r requirements-clipping.txt -r requirements-transcription.txt
        }
        if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check internet access or the local wheel cache.' }
    }

    & $subtitlePython -m clipping.transcription_setup --model $Model
    if ($LASTEXITCODE -ne 0) { throw 'Whisper model preparation failed.' }
    Write-Output 'Start the app with: .\.venv\Scripts\python.exe -m clipping'
    if ($Model -eq 'tiny.en') { Write-Output 'Select English as the spoken language for this model.' }
} finally {
    Pop-Location
}

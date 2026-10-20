param(
    [ValidateRange(1024, 65535)]
    [int]$Port = 8000,
    [switch]$Selenium,
    [string]$BrowserPython
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$clippingPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $clippingPython -PathType Leaf)) {
    throw 'Run setup-transcription.ps1 first to install the clipping environment.'
}
if ($Selenium) {
    if (-not $BrowserPython) {
        $BrowserPython = & python -c 'import sys; print(sys.executable)'
        if ($LASTEXITCODE -ne 0) { throw 'Could not find the Python where you installed Selenium. Supply -BrowserPython with its full path.' }
    }
    if (-not (Test-Path -LiteralPath $BrowserPython -PathType Leaf)) {
        throw 'The Selenium Python path does not exist. Supply -BrowserPython with its full path.'
    }
    & $BrowserPython -c 'import selenium'
    if ($LASTEXITCODE -ne 0) { throw 'Selenium is missing from this Python. Supply -BrowserPython with the Python where pip installed Selenium.' }
    $env:CLIPPING_SELENIUM_PYTHON = (Resolve-Path -LiteralPath $BrowserPython).Path
    $env:CLIPPING_DISCOVERY_PROVIDER = 'selenium'
    Write-Host 'Checking an isolated Chrome session and YouTube access. Your personal browser profile is not used.'
    $clippingBrowserStatus = & $BrowserPython (Join-Path $PSScriptRoot 'clipping/youtube_browser.py') --check
    if ($LASTEXITCODE -ne 0) { throw 'The Selenium readiness check could not run.' }
    $clippingBrowserCheck = $clippingBrowserStatus | ConvertFrom-Json
    if ($clippingBrowserCheck.status -ne 'ok') {
        Write-Host $clippingBrowserStatus
        throw 'Chrome setup or YouTube access failed. Selenium Manager needs access to download the matching driver; run this launcher in your normal terminal.'
    }
} else {
    $env:CLIPPING_DISCOVERY_PROVIDER = ''
}
if (-not (Get-Command deno -ErrorAction SilentlyContinue)) {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        throw 'YouTube downloads need Node.js 22 or newer, or Deno 2.3 or newer. Install one, then run this launcher again.'
    }
    $clippingNodeVersion = & node --version
    if ([int]($clippingNodeVersion.TrimStart('v').Split('.')[0]) -lt 22) {
        throw 'Update Node.js to version 22 or newer, then run this launcher again.'
    }
}
# Install only the solver version required by the already installed downloader.
# This runs in the user's normal terminal and preserves its network configuration.
$clippingEjsRequirement = & $clippingPython -c "import importlib.metadata as m, importlib.util; requirements = [r.split(';')[0].strip() for r in m.requires('yt-dlp') if r.startswith('yt-dlp-ejs')]; installed = m.version('yt-dlp-ejs') if importlib.util.find_spec('yt_dlp_ejs') else ''; print(requirements[0] if requirements and requirements[0] != 'yt-dlp-ejs==' + installed else '')"
if ($LASTEXITCODE -ne 0) { throw 'The YouTube downloader is missing. Run setup-transcription.ps1 first.' }
if ($clippingEjsRequirement) {
    Write-Host 'Installing the matching YouTube downloader component in the project environment.'
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv pip install --python $clippingPython --no-cache $clippingEjsRequirement
    } else {
        & $clippingPython -m ensurepip --upgrade
        if ($LASTEXITCODE -ne 0) { throw 'The project installer could not be prepared. Install uv, then run this launcher again.' }
        & $clippingPython -m pip install --disable-pip-version-check --no-cache-dir $clippingEjsRequirement
    }
    if ($LASTEXITCODE -ne 0) { throw 'The YouTube component could not be installed. Check this terminal can reach PyPI, then run the launcher again.' }
}
Write-Host 'Searching real long YouTube videos and preparing one captioned highlight.'
Write-Host "Open http://127.0.0.1:$Port/ to see sources, selection evidence, captions and progress."
& $clippingPython -m clipping --discover --port $Port
if ($LASTEXITCODE -ne 0) {
    throw 'The YouTube clipping workspace did not start. Follow the status above.'
}

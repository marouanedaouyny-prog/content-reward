param([string]$NgrokPath, [switch]$NoBrowser, [switch]$Diagnose)

$ErrorActionPreference = 'Stop'
if (-not $NgrokPath) {
    $instagramCachedAgent = Join-Path $PSScriptRoot '.workflow-tests/ngrok-runtime/ngrok.exe'
    if (Test-Path -LiteralPath $instagramCachedAgent -PathType Leaf) { $NgrokPath = $instagramCachedAgent }
}
if (-not $NgrokPath) {
    $instagramNgrokCommand = Get-Command ngrok -ErrorAction SilentlyContinue
    if ($instagramNgrokCommand) { $NgrokPath = $instagramNgrokCommand.Source }
}
if (-not $NgrokPath) {
    $instagramPackageRoot = Join-Path $env:LOCALAPPDATA 'Microsoft/WinGet/Packages'
    if (Test-Path -LiteralPath $instagramPackageRoot) {
        foreach ($instagramPackage in (Get-ChildItem -LiteralPath $instagramPackageRoot -Directory -Filter 'Ngrok.Ngrok_*')) {
            $instagramCandidate = Join-Path $instagramPackage.FullName 'ngrok.exe'
            if (Test-Path -LiteralPath $instagramCandidate) { $NgrokPath = $instagramCandidate; break }
        }
    }
}
if (-not $NgrokPath -or -not (Test-Path -LiteralPath $NgrokPath -PathType Leaf)) {
    throw 'Ngrok was not found. Supply its executable path with -NgrokPath.'
}
$NgrokPath = (Resolve-Path -LiteralPath $NgrokPath).ProviderPath
$instagramPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $instagramPython)) { throw 'Run setup-transcription.ps1 to prepare the Python environment first.' }
$instagramArguments = @('-m', 'clipping.instagram_tunnel', '--ngrok-exe', $NgrokPath)
if ($NoBrowser) { $instagramArguments += '--no-browser' }
if ($Diagnose) { $instagramArguments += '--diagnose' }
Push-Location -LiteralPath $PSScriptRoot
try {
    if ($Diagnose) {
        Write-Host 'Checking executable paths and Instagram connectivity. No password or token is displayed.'
    } else {
        Write-Host 'Starting protected Instagram authentication. No password or token needs to be pasted into chat.'
    }
    & $instagramPython @instagramArguments
    if ($LASTEXITCODE -ne 0) { throw 'Instagram authentication did not finish. The status above identifies the remaining step.' }
} finally {
    Pop-Location
}

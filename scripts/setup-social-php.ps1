$ErrorActionPreference = 'Stop'
function Get-PublishedHash([string]$Uri) {
    $content = (Invoke-WebRequest -UseBasicParsing -Uri $Uri).Content
    if ($content -is [byte[]]) { $content = [Text.Encoding]::UTF8.GetString($content) }
    $hash = ([string]$content -split '\s+')[0].ToLowerInvariant()
    if ($hash -notmatch '^[0-9a-f]{64}$') { throw 'Invalid published SHA256 checksum.' }
    return $hash
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$toolRoot = Join-Path $projectRoot '.tools'
$phpRoot = Join-Path $toolRoot 'php'
$phpVersion = '8.4.27'
$archiveName = "php-$phpVersion-nts-Win32-vs17-x64.zip"
$archiveHash = '93bd8a815a52156606fb906d0573437908c61f96e2cc52c03a51e36a41bf5236'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
New-Item -ItemType Directory -Path $toolRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath (Join-Path $phpRoot 'php.exe'))) {
    $archivePath = Join-Path $toolRoot $archiveName
    Invoke-WebRequest -UseBasicParsing -Uri "https://downloads.php.net/~windows/releases/$archiveName" -OutFile $archivePath
    if ((Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $archiveHash) {
        throw 'PHP archive checksum mismatch. Nothing was extracted.'
    }
    Expand-Archive -LiteralPath $archivePath -DestinationPath $phpRoot
}
$php = Join-Path $phpRoot 'php.exe'
& $php -n --version
if ($LASTEXITCODE -ne 0) { throw 'PHP cannot start. Install the Microsoft Visual C++ x64 Redistributable, then retry.' }

$caPath = Join-Path $phpRoot 'cacert.pem'
$caHash = Get-PublishedHash 'https://curl.se/ca/cacert.pem.sha256'
if (-not (Test-Path -LiteralPath $caPath) -or (Get-FileHash -LiteralPath $caPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $caHash) {
    $caDownload = "$caPath.download"
    Invoke-WebRequest -UseBasicParsing -Uri 'https://curl.se/ca/cacert.pem' -OutFile $caDownload
    if ((Get-FileHash -LiteralPath $caDownload -Algorithm SHA256).Hash.ToLowerInvariant() -ne $caHash) {
        throw 'CA bundle checksum mismatch.'
    }
    Move-Item -LiteralPath $caDownload -Destination $caPath -Force
}
$ini = @"
[PHP]
extension_dir="$($phpRoot.Replace('\','/'))/ext"
extension=curl
extension=openssl
extension=mbstring
extension=fileinfo
extension=zip
date.timezone=UTC
display_errors=stderr
log_errors=Off
memory_limit=256M
curl.cainfo="$($caPath.Replace('\','/'))"
openssl.cafile="$($caPath.Replace('\','/'))"
"@
[IO.File]::WriteAllText((Join-Path $phpRoot 'php.ini'), $ini, [Text.UTF8Encoding]::new($false))
$composer = Join-Path $toolRoot 'composer.phar'
$composerVersion = '2.10.3'
$composerUrl = "https://getcomposer.org/download/$composerVersion/composer.phar"
$composerHash = Get-PublishedHash "$composerUrl.sha256sum"
if (-not (Test-Path -LiteralPath $composer) -or (Get-FileHash -LiteralPath $composer -Algorithm SHA256).Hash.ToLowerInvariant() -ne $composerHash) {
    $composerDownload = "$composer.download"
    Invoke-WebRequest -UseBasicParsing -Uri $composerUrl -OutFile $composerDownload
    if ((Get-FileHash -LiteralPath $composerDownload -Algorithm SHA256).Hash.ToLowerInvariant() -ne $composerHash) {
        throw 'Composer checksum mismatch. Composer was not executed.'
    }
    Move-Item -LiteralPath $composerDownload -Destination $composer -Force
}
& $php $composer --version
if ($LASTEXITCODE -ne 0) { throw 'Composer failed to start.' }
& $php $composer install --working-dir="$projectRoot/integrations/social-php" --no-interaction --no-plugins --no-scripts --prefer-dist
if ($LASTEXITCODE -ne 0) { throw 'Composer dependency installation failed.' }
Write-Output 'Local PHP runtime and TikTok SDK installed. No account connection or publication was attempted.'

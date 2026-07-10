$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:FLET_CLI_NO_RICH_OUTPUT = "1"
$env:HTTP_PROXY = "http://127.0.0.1:7897"
$env:HTTPS_PROXY = "http://127.0.0.1:7897"
$env:NO_PROXY = "localhost,127.0.0.1,::1"

Set-Location $PSScriptRoot

# Android 只有在包名、签名证书相同且版本号不降低时，才会显示“更新”。
$userHome = $env:USERPROFILE
if ([string]::IsNullOrWhiteSpace($userHome)) {
    $userHome = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)
}
if ([string]::IsNullOrWhiteSpace($userHome)) {
    $userHome = $HOME
}
if ([string]::IsNullOrWhiteSpace($userHome)) {
    $userHome = $PSScriptRoot
    Write-Warning "User home directory was not detected; signing key backup will be kept beside the project."
}

$debugKey = Join-Path $userHome ".android\debug.keystore"
$keyBackupDir = Join-Path $userHome ".carbs_king_signing"
$debugKeyBackup = Join-Path $keyBackupDir "debug.keystore"

if (-not (Test-Path $debugKeyBackup) -and (Test-Path $debugKey)) {
    New-Item -ItemType Directory -Force -Path $keyBackupDir | Out-Null
    Copy-Item $debugKey $debugKeyBackup -Force
}

# Once captured, always sign Carb King with its private copy instead of relying
# on a possibly replaced global debug key.
if (Test-Path $debugKeyBackup) {
    $env:FLET_ANDROID_SIGNING_KEY_STORE = $debugKeyBackup
    $env:FLET_ANDROID_SIGNING_KEY_ALIAS = "androiddebugkey"
    $env:FLET_ANDROID_SIGNING_KEY_STORE_PASSWORD = "android"
    $env:FLET_ANDROID_SIGNING_KEY_PASSWORD = "android"
}

$pyprojectPath = Join-Path $PSScriptRoot "pyproject.toml"
$projectText = Get-Content $pyprojectPath -Raw -Encoding UTF8
$utf8NoBom = New-Object System.Text.UTF8Encoding -ArgumentList $false
if ($projectText.Length -gt 0 -and [int]$projectText[0] -eq 0xFEFF) {
    $projectText = $projectText.Substring(1)
}

# Python 3.12 tomllib rejects a UTF-8 BOM at line 1. Normalize the project
# file before every build because Windows PowerShell 5.1 normally writes a BOM
# when Set-Content -Encoding UTF8 is used.
[System.IO.File]::WriteAllText($pyprojectPath, $projectText, $utf8NoBom)

$numberMatch = [regex]::Match($projectText, '(?m)^build_number\s*=\s*(\d+)\s*$')
if (-not $numberMatch.Success) {
    throw "build_number was not found in pyproject.toml"
}
$buildNumber = [int]$numberMatch.Groups[1].Value
$versionMatch = [regex]::Match($projectText, '(?m)^version\s*=\s*"([^"]+)"\s*$')
if (-not $versionMatch.Success) {
    throw "version was not found in pyproject.toml"
}
$buildVersion = $versionMatch.Groups[1].Value

Write-Host "Building com.chenyang.carbs_king, build number $buildNumber..."
$buildArgs = @(
    "build", "apk",
    "--no-rich-output",
    "--project", "carbs_king",
    "--bundle-id", "com.chenyang.carbs_king",
    "--build-version", $buildVersion,
    "--build-number", $buildNumber
)

# Pass the fixed key explicitly so a cache/global debug-key change cannot
# silently produce an APK that Android treats as another installation.
if (Test-Path $debugKeyBackup) {
    $buildArgs += @(
        "--android-signing-key-store", $debugKeyBackup,
        "--android-signing-key-alias", "androiddebugkey",
        "--android-signing-key-store-password", "android",
        "--android-signing-key-password", "android"
    )
}

& flet @buildArgs

if ($LASTEXITCODE -ne 0) {
    throw "APK build failed with exit code $LASTEXITCODE"
}

# On a first-ever Android build Gradle may create the debug key during the build.
# Capture it afterwards; all later builds use this fixed private copy.
if (Test-Path $debugKey) {
    New-Item -ItemType Directory -Force -Path $keyBackupDir | Out-Null
    if (-not (Test-Path $debugKeyBackup)) {
        Copy-Item $debugKey $debugKeyBackup -Force
        Write-Host "Saved the Android signing key for future update builds."
    }
}

# The APK just built used the current number. Prepare the next update number.
$nextBuildNumber = $buildNumber + 1
$nextProjectText = [regex]::Replace(
    $projectText,
    '(?m)^build_number\s*=\s*\d+\s*$',
    "build_number = $nextBuildNumber"
)
[System.IO.File]::WriteAllText($pyprojectPath, $nextProjectText, $utf8NoBom)

Write-Host "APK complete. Next build number prepared: $nextBuildNumber"

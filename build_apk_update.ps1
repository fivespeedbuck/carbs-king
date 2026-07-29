$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:FLET_CLI_NO_RICH_OUTPUT = "1"
$env:HTTP_PROXY = "http://127.0.0.1:7897"
$env:HTTPS_PROXY = "http://127.0.0.1:7897"
$env:NO_PROXY = "localhost,127.0.0.1,::1"

Set-Location $PSScriptRoot

try {
    chcp 65001 | Out-Null
} catch {
    Write-Warning "Could not switch the console code page to UTF-8."
}

$pythonCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
    (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1)
) | Where-Object { $_ -and (Test-Path $_) }
$python = $pythonCandidates | Select-Object -First 1
if (-not $python) {
    throw "Python 3.12 was not found."
}

$fletCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\Scripts\flet.exe"),
    (Get-Command flet -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1)
) | Where-Object { $_ -and (Test-Path $_) }
$flet = $fletCandidates | Select-Object -First 1
if (-not $flet) {
    throw "Flet CLI was not found."
}

$git = Get-Command git -ErrorAction Stop | Select-Object -ExpandProperty Source -First 1
& $git lfs pull --include="assets/exercises/**"
if ($LASTEXITCODE -ne 0) {
    throw "git lfs pull failed with exit code $LASTEXITCODE"
}

& $python "$PSScriptRoot\tools\asset_gate.py" verify-source
if ($LASTEXITCODE -ne 0) {
    throw "Canonical asset verification failed."
}

# Flet packages the directory configured by [tool.flet.app]. This project uses
# `src` as the app path while the canonical media directory lives at root
# `assets`, so mirror it into src/assets before every Android build.
$sourceAssets = Join-Path $PSScriptRoot "assets"
$packageAssets = Join-Path $PSScriptRoot "src\assets"
if (-not (Test-Path $sourceAssets)) {
    throw "Required app assets directory was not found: $sourceAssets"
}
New-Item -ItemType Directory -Force -Path $packageAssets | Out-Null
& robocopy $sourceAssets $packageAssets /MIR /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -gt 7) {
    throw "Could not mirror app assets for APK packaging (robocopy exit code $LASTEXITCODE)"
}

& $python "$PSScriptRoot\tools\asset_gate.py" verify-mirror
if ($LASTEXITCODE -ne 0) {
    throw "Build asset mirror verification failed."
}

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

& $flet @buildArgs

if ($LASTEXITCODE -ne 0) {
    throw "APK build failed with exit code $LASTEXITCODE"
}

$apkPath = Join-Path $PSScriptRoot "build\apk\carbs_king.apk"
& $python "$PSScriptRoot\tools\asset_gate.py" verify-apk $apkPath
if ($LASTEXITCODE -ne 0) {
    throw "Packaged APK asset verification failed. Build number was not advanced."
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

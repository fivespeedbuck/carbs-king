$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$gitCommand = Get-Command git -ErrorAction SilentlyContinue
$gitExe = if ($gitCommand) { $gitCommand.Source } else { $null }

if (-not $gitExe -and $env:LOCALAPPDATA) {
    $candidate = Get-ChildItem `
        -Path "$env:LOCALAPPDATA\GitHubDesktop\app-*\resources\app\git\cmd\git.exe" `
        -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        Select-Object -First 1
    if ($candidate) {
        $gitExe = $candidate.FullName
    }
}

if (-not $gitExe) {
    throw "Git was not found. Please install GitHub Desktop first."
}

& $gitExe remote get-url origin *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Please click Publish repository in GitHub Desktop before uploading tags."
}

& $gitExe push origin --tags
if ($LASTEXITCODE -ne 0) {
    throw "Tag upload failed. Open GitHub Desktop and confirm that the repository is published."
}

Write-Host "All local version tags uploaded successfully."

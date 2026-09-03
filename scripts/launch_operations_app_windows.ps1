$ErrorActionPreference = "Stop"

# Resolve the repository from this script's own location.
# No username, drive letter, repository name, or WSL Linux path is hard-coded.

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

if (-not (Test-Path $repoRoot)) {
    throw "Could not locate the Operations Meta-Agent repository."
}

$linuxLauncher = "scripts/start_operations_app.sh"

# WSL supports --cd with an absolute Windows directory.
# Passing arguments separately avoids the wslpath/backslash quoting bug.
& wsl.exe `
    --cd $repoRoot `
    bash `
    $linuxLauncher

$launcherExitCode = $LASTEXITCODE

if ($launcherExitCode -ne 0) {
    throw "Operations Meta-Agent launcher exited with code $launcherExitCode."
}

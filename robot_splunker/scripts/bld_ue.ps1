<#
.SYNOPSIS
    Builds the SplunkerViz Unreal Engine 5 project (the Windows half of robot_splunker).

.DESCRIPTION
    Compiles the SplunkerVizEditor target with Unreal's Build.bat so the project can be
    opened / played without building it manually in Visual Studio.
    This is the Windows-native equivalent of `./scripts/bld.sh --ue` (which calls this
    script through WSL interop).

    Steps:
      1. Resolve UE_ROOT (parameter, environment, or scripts\.env).
      2. Locate Build.bat and the .uproject.
      3. Optionally clean Binaries\ and Intermediate\.
      4. Run Build.bat SplunkerVizEditor Win64 <Config>.

.PARAMETER UeRoot
    Unreal Engine install folder (contains Engine\). Default: $env:UE_ROOT or UE_ROOT in scripts\.env.

.PARAMETER Config
    Build configuration: Development (default) or DebugGame.

.PARAMETER Clean
    Delete unreal\SplunkerViz\Binaries and Intermediate before building.

.PARAMETER Help
    Print usage and exit.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\bld_ue.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\bld_ue.ps1 -UeRoot "D:\Epic\UE_5.6" -Clean

.NOTES
    Exit codes: 0 success, 1 build/config failure, 2 bad option.
    Related: bld.sh (builds everything from WSL), up.sh --start-ue (launches UE).
#>
[CmdletBinding()]
param(
    [string]$UeRoot = "",
    [ValidateSet("Development", "DebugGame")]
    [string]$Config = "Development",
    [switch]$Clean,
    [Alias("h")]
    [switch]$Help
)

$ErrorActionPreference = "Stop"

# ---- Usage text (printed by -Help / -h) ---------------------------------------------
function Show-Usage {
    @"
Usage: bld_ue.ps1 [-UeRoot <path>] [-Config Development|DebugGame] [-Clean] [-Help]

Compiles the SplunkerViz UE5 C++ project (target SplunkerVizEditor, Win64).

Options:
  -UeRoot <path>   UE install folder containing Engine\  (default: `$env:UE_ROOT, then UE_ROOT in scripts\.env)
  -Config <name>   Development (default) or DebugGame
  -Clean           Delete Binaries\ and Intermediate\ first
  -Help, -h        Show this help and exit (Get-Help .\scripts\bld_ue.ps1 -Full also works)

Examples:
  powershell -ExecutionPolicy Bypass -File scripts\bld_ue.ps1
  powershell -ExecutionPolicy Bypass -File scripts\bld_ue.ps1 -UeRoot "C:\Program Files\Epic Games\UE_5.5" -Clean

Related: bld.sh --ue (same build, started from WSL), up.sh --start-ue (launch UE)
"@ | Write-Output
}

if ($Help) { Show-Usage; exit 0 }

$RepoDir    = Split-Path -Parent $PSScriptRoot
$ProjectDir = Join-Path $RepoDir "unreal\SplunkerViz"
$UProject   = Join-Path $ProjectDir "SplunkerViz.uproject"

# ---- Step 1: Resolve UE_ROOT ----------------------------------------------------------
# Priority: -UeRoot parameter > UE_ROOT environment variable > scripts\.env file.
Write-Output "==== Step 1/4: Resolve Unreal Engine location ===="
if (-not $UeRoot) { $UeRoot = $env:UE_ROOT }
if (-not $UeRoot) {
    $envFile = Join-Path $PSScriptRoot ".env"
    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile) {
            # Lines look like: UE_ROOT='C:\Program Files\Epic Games\UE_5.5'
            if ($line -match "^\s*UE_ROOT\s*=\s*(.*)$") {
                $UeRoot = $Matches[1].Trim().Trim("'").Trim('"')
            }
        }
    }
}
if (-not $UeRoot) {
    Write-Error "UE_ROOT not set. Pass -UeRoot, set `$env:UE_ROOT, or add UE_ROOT to scripts\.env."
    exit 1
}
Write-Output "UE_ROOT = $UeRoot"

# ---- Step 2: Locate Build.bat and the project -------------------------------------------
# Build.bat is UE's wrapper around UnrealBuildTool; it needs no .sln file.
Write-Output "==== Step 2/4: Locate Build.bat and SplunkerViz.uproject ===="
$BuildBat = Join-Path $UeRoot "Engine\Build\BatchFiles\Build.bat"
if (-not (Test-Path $BuildBat)) { Write-Error "Build.bat not found at $BuildBat (is UE_ROOT correct?)"; exit 1 }
if (-not (Test-Path $UProject)) { Write-Error "Project not found at $UProject"; exit 1 }

# ---- Step 3: Optional clean ---------------------------------------------------------------
Write-Output "==== Step 3/4: Clean ===="
if ($Clean) {
    foreach ($d in @("Binaries", "Intermediate")) {
        $p = Join-Path $ProjectDir $d
        if (Test-Path $p) { Remove-Item -Recurse -Force $p; Write-Output "Removed $p" }
    }
} else {
    Write-Output "Skipped (no -Clean)."
}

# ---- Step 4: Build ------------------------------------------------------------------------
# -WaitMutex: wait instead of failing if another UBT instance (e.g. the editor) is running.
Write-Output "==== Step 4/4: Build SplunkerVizEditor Win64 $Config ===="
& $BuildBat SplunkerVizEditor Win64 $Config "-Project=$UProject" -WaitMutex
if ($LASTEXITCODE -ne 0) {
    Write-Error "Unreal build failed with exit code $LASTEXITCODE"
    exit 1
}
Write-Output "Unreal build succeeded."
exit 0

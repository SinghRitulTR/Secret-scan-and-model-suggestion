# TruffleHog wrapper script for Claude Code workflow
# Usage: .\run_trufflehog.ps1 [base-branch] [repo-dir] [output-dir]

param(
    [string]$BaseBranch = "main",
    [string]$RepoDir = ".",
    [string]$OutputDir = ".claude\tmp"
)

$ErrorActionPreference = "Continue"

# Ensure output directory exists
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$JsonOut = Join-Path $OutputDir "trufflehog-results.json"
$SummaryOut = Join-Path $OutputDir "trufflehog-summary.txt"

# Clean previous results
Remove-Item -Path $JsonOut -ErrorAction SilentlyContinue
Remove-Item -Path $SummaryOut -ErrorAction SilentlyContinue

Write-Host "Running TruffleHog scan: $BaseBranch..HEAD in $RepoDir"

# TruffleHog path
$trufflehogPath = "C:\tools\trufflehog.exe"

# Verify TruffleHog exists
if (-not (Test-Path $trufflehogPath)) {
    Write-Host "ERROR: TruffleHog not found at $trufflehogPath"
    @"
STATUS=ERROR
TruffleHog not found at $trufflehogPath
Please install TruffleHog or update the path.
Scan time: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
"@ | Out-File -FilePath $SummaryOut -Encoding utf8
    exit 1
}

# Get the commit hash for base branch
try {
    $baseCommit = git rev-parse "origin/$BaseBranch" 2>$null
    if (-not $baseCommit) {
        $baseCommit = git rev-parse "$BaseBranch" 2>$null
    }
    if (-not $baseCommit) {
        Write-Host "WARNING: Could not find base branch $BaseBranch, scanning full repo"
        $baseCommit = $null
    }
} catch {
    $baseCommit = $null
}

try {
    if ($baseCommit) {
        # Scan only changes since base branch
        Write-Host "Scanning changes since $BaseBranch ($baseCommit)"
        $output = & $trufflehogPath git "file://$RepoDir" --since-commit="$baseCommit" --json --fail 2>$null
    } else {
        # Full repo scan
        Write-Host "Scanning full repository"
        $output = & $trufflehogPath filesystem "$RepoDir" --json --fail 2>$null
    }
    
    $exitCode = $LASTEXITCODE
    
    # Write JSON output
    $output | Out-File -FilePath $JsonOut -Encoding utf8
    
    if ($exitCode -eq 0 -or [string]::IsNullOrWhiteSpace($output)) {
        @"
STATUS=PASS
No TruffleHog findings detected.
Base branch: $BaseBranch
Base commit: $baseCommit
Repo dir: $RepoDir
Scan time: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
"@ | Out-File -FilePath $SummaryOut -Encoding utf8
        
        Write-Host "STATUS=PASS"
        Write-Host "No secrets detected."
        exit 0
    }
    else {
        # Count findings
        $findingCount = ($output | Select-String -Pattern '"DetectorName"' -AllMatches).Matches.Count
        if ($findingCount -eq 0) { $findingCount = 1 }
        
        @"
STATUS=BLOCKED
TruffleHog detected $findingCount potential secret(s).
Review: $JsonOut
Base branch: $BaseBranch
Base commit: $baseCommit
Repo dir: $RepoDir
Scan time: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
"@ | Out-File -FilePath $SummaryOut -Encoding utf8
        
        Write-Host "STATUS=BLOCKED"
        Write-Host "Found $findingCount potential secret(s). Review: $JsonOut"
        exit 2
    }
}
catch {
    Write-Host "ERROR: Failed to run TruffleHog - $_"
    @"
STATUS=ERROR
TruffleHog execution failed.
Error: $_
Scan time: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
"@ | Out-File -FilePath $SummaryOut -Encoding utf8
    exit 1
}

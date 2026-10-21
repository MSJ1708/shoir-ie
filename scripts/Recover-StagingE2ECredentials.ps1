#requires -Version 5.1
<#
.SYNOPSIS
    Safely synchronize the six disposable Shoir-IE staging E2E account passwords
    with the matching GitHub Actions secrets.
.DESCRIPTION
    All credentials are entered via hidden prompts and held only in this process.
    The Python recovery helper is pinned to staging project hfhrosthswcybccepmak.
    It refuses production, missing accounts, unexpected tiers, inactive accounts,
    and unexpected subscription states. It does not create/delete accounts and
    never prints passwords, tokens, or keys.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$scriptExitCode = 1
$serviceKey = $null
$publishableKey = $null
$serviceSecure = $null
$publishableSecure = $null
$locationPushed = $false

try {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        throw "GitHub CLI (gh) is required. Install it, run 'gh auth login', and retry."
    }
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Python is required. Install Python 3.12 or activate the repository environment, then retry."
    }

    # Verify GitHub authentication without echoing CLI output or credential metadata.
    & gh auth status --hostname github.com *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub CLI authentication is unavailable. Run 'gh auth login' and retry."
    }

    Write-Host ""
    Write-Host "Shoir-IE staging E2E credential recovery" -ForegroundColor Cyan
    Write-Host "Target: staging Supabase project hfhrosthswcybccepmak"
    Write-Host "Scope: existing disposable shoir-e2e-* accounts only."
    Write-Host "This does not touch production or the master administrator."
    Write-Host "The helper stops unless all six existing account records match the expected tier/state."
    Write-Host ""

    $serviceSecure = Read-Host "Enter STAGING Supabase server secret/service-role key (input hidden)" -AsSecureString
    $publishableSecure = Read-Host "Enter STAGING Supabase publishable/anon key (input hidden)" -AsSecureString
    $serviceKey = [System.Net.NetworkCredential]::new("", $serviceSecure).Password
    $publishableKey = [System.Net.NetworkCredential]::new("", $publishableSecure).Password

    if ([string]::IsNullOrWhiteSpace($serviceKey) -or [string]::IsNullOrWhiteSpace($publishableKey)) {
        throw "Both staging keys are required. No recovery was started."
    }

    Push-Location $repoRoot
    $locationPushed = $true
    $env:SHOIR_STAGING_SERVICE_KEY = $serviceKey
    $env:SHOIR_STAGING_PUBLISHABLE_KEY = $publishableKey
    & python scripts/recover_staging_e2e_credentials.py
    $scriptExitCode = $LASTEXITCODE
}
finally {
    Remove-Item Env:SHOIR_STAGING_SERVICE_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:SHOIR_STAGING_PUBLISHABLE_KEY -ErrorAction SilentlyContinue
    $serviceKey = $null
    $publishableKey = $null
    $serviceSecure = $null
    $publishableSecure = $null
    if ($locationPushed) {
        Pop-Location
    }
}

if ($scriptExitCode -ne 0) {
    Write-Host "Credential recovery did not complete. Review the safe status message above; do not create duplicate accounts." -ForegroundColor Red
    exit $scriptExitCode
}

Write-Host ""
Write-Host "Recovery passed. GitHub Actions secrets now match the six existing staging test accounts." -ForegroundColor Green
Write-Host "Next: rerun Authenticated release gate on staging-e2e-20261019."

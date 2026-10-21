#requires -Version 5.1
<#
.SYNOPSIS
    Safely synchronize the six disposable Shoir-IE staging E2E account passwords
    with the matching GitHub Actions secrets.
.DESCRIPTION
    Credentials are read from the Windows clipboard without displaying them,
    and the clipboard is cleared after each read. The Python recovery helper is
    pinned to staging project hfhrosthswcybccepmak. It refuses production,
    missing accounts, unexpected tiers, inactive accounts, and unexpected
    subscription states. It does not create/delete accounts and never prints
    passwords, tokens, or keys.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$scriptExitCode = 1
$serviceKey = $null
$publishableKey = $null
$locationPushed = $false

function Read-StagingKeyFromClipboard {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Prompt
    )

    Write-Host ""
    Write-Host $Prompt -ForegroundColor Cyan
    Write-Host "Copy the FULL key from the staging Supabase dashboard, return here, and press Enter."
    Write-Host "Do NOT paste the key into this terminal. It will not be displayed; the clipboard is cleared after reading."

    try {
        while ($true) {
            $keyPress = [Console]::ReadKey($true)
            if ($keyPress.Key -eq [ConsoleKey]::Enter) {
                break
            }
        }
    }
    catch {
        throw "This prompt requires an interactive Windows PowerShell terminal. No recovery was started."
    }

    $value = $null
    $readFailed = $false
    try {
        $clipboardValue = Get-Clipboard -Raw -ErrorAction Stop
        if ($null -ne $clipboardValue) {
            $value = [string]$clipboardValue
        }
    }
    catch {
        $readFailed = $true
    }

    $clearFailed = $false
    try {
        Clear-Clipboard -ErrorAction Stop
    }
    catch {
        $clearFailed = $true
    }

    if ($clearFailed) {
        $value = $null
        throw "Windows could not clear the clipboard. No recovery was started; clear the clipboard manually and retry."
    }
    if ($readFailed) {
        $value = $null
        throw "Windows could not read the clipboard. Copy the key again and retry; no recovery was started."
    }

    $value = ([string]$value).Trim()
    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = $null
        throw "The clipboard was empty. Copy the full key from the staging project and retry; no recovery was started."
    }

    return $value
}

try {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        throw "GitHub CLI (gh) is required. Install it, run 'gh auth login', and retry."
    }
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw "Python is required. Install Python 3.12 or activate the repository environment, then retry."
    }
    if (-not (Get-Command Get-Clipboard -ErrorAction SilentlyContinue) -or
        -not (Get-Command Clear-Clipboard -ErrorAction SilentlyContinue)) {
        throw "Windows clipboard commands are unavailable. Use Windows PowerShell 5.1 or PowerShell 7 on Windows and retry."
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
    Write-Host "For key input, a single masking symbol is no longer involved: the script reads clipboard content directly."
    Write-Host ""

    $serviceKey = Read-StagingKeyFromClipboard -Prompt "STAGING server secret/service-role key"
    $publishableKey = Read-StagingKeyFromClipboard -Prompt "STAGING publishable/anon key"

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

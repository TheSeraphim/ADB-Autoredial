<#
.SYNOPSIS
    Auto-redial with human answer detection via ADB.

.DESCRIPTION
    Repeatedly calls a number until a human answer is detected (call active beyond
    ValidAfterSeconds threshold), or until MaxRetries is reached.

.PARAMETER Number
    Phone number to call.

.PARAMETER ValidAfterSeconds
    Minimum call duration in seconds to consider the call a human answer rather
    than an auto-attendant. Default: 20.

.PARAMETER RetryDelay
    Seconds to wait between attempts. Default: 3.

.PARAMETER MaxRetries
    Maximum number of attempts. If omitted, retries indefinitely.

.PARAMETER TimeoutCall
    Maximum seconds to wait for an answer before considering the call lost. Default: 60.

.PARAMETER LogFile
    Optional path to a log file. If omitted, no log is written.

.PARAMETER DryRun
    Simulates execution without placing real calls.

.EXAMPLE
    .\auto_redial.ps1 -Number 0123456789

.EXAMPLE
    .\auto_redial.ps1 -Number 0123456789 -ValidAfterSeconds 25 -MaxRetries 10 -LogFile C:\log.txt

.EXAMPLE
    .\auto_redial.ps1 -Number 0123456789 -DryRun
#>

[CmdletBinding()]
param (
    [Parameter(Mandatory = $true)]
    [string]$Number,

    [int]$ValidAfterSeconds = 20,
    [int]$RetryDelay = 3,
    [int]$MaxRetries = 0,
    [int]$TimeoutCall = 60,
    [string]$LogFile = "",
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] [$Level] $Message"
    Write-Host $line
    if ($LogFile -ne "") {
        Add-Content -Path $LogFile -Value $line
    }
}

function Write-CallProgress {
    param([int]$Elapsed, [int]$Target, [string]$Status)
    $pct = [math]::Min(100, [math]::Round(($Elapsed / $Target) * 100))
    Write-Progress `
        -Activity "Call in progress" `
        -Status $Status `
        -PercentComplete $pct `
        -CurrentOperation "Elapsed: ${Elapsed}s / Target: ${Target}s"
}

function Write-RetryProgress {
    param([int]$Elapsed, [int]$Total)
    $pct = [math]::Min(100, [math]::Round(($Elapsed / $Total) * 100))
    Write-Progress `
        -Activity "Waiting before retry" `
        -Status "Next attempt in $($Total - $Elapsed)s" `
        -PercentComplete $pct
}

function Invoke-Adb {
    param([string]$Arguments)
    if ($DryRun) {
        Write-Log "[DRY-RUN] adb $Arguments" "DEBUG"
        return ""
    }
    return (adb $Arguments.Split(" ") 2>&1)
}

function Get-CallState {
    if ($DryRun) { return "NONE" }
    $dump = adb shell dumpsys telecom 2>&1
    if ($dump | Select-String "STATE: ACTIVE")  { return "ACTIVE" }
    if ($dump | Select-String "STATE: DIALING") { return "DIALING" }
    if ($dump | Select-String "STATE: RINGING") { return "RINGING" }
    return "NONE"
}

Write-Log "========================================"
Write-Log "Auto-redial starting"
Write-Log "  Target number    : $Number"
Write-Log "  Valid after      : ${ValidAfterSeconds}s"
Write-Log "  Call timeout     : ${TimeoutCall}s"
Write-Log "  Retry delay      : ${RetryDelay}s"
Write-Log "  Max retries      : $(if ($MaxRetries -eq 0) { 'unlimited' } else { $MaxRetries })"
Write-Log "  Log file         : $(if ($LogFile -eq '') { 'none' } else { $LogFile })"
Write-Log "  Dry-run          : $DryRun"
Write-Log "========================================"

$attempt = 0

while ($true) {
    $attempt++

    if ($MaxRetries -gt 0 -and $attempt -gt $MaxRetries) {
        Write-Log "Max retries ($MaxRetries) reached. Exiting." "WARN"
        exit 1
    }

    $attemptLabel = if ($MaxRetries -gt 0) { "$attempt / $MaxRetries" } else { "$attempt" }
    Write-Log "Attempt $attemptLabel -- dialing $Number"

    Invoke-Adb "shell am start -a android.intent.action.CALL -d tel:$Number" | Out-Null

    $start    = Get-Date
    $answered = $false

    while ($true) {
        Start-Sleep -Seconds 1
        $elapsedSec = [math]::Round(((Get-Date) - $start).TotalSeconds)
        $state      = Get-CallState

        switch ($state) {
            "ACTIVE"  { $answered = $true }
            "DIALING" { Write-Log "  Dialing... (${elapsedSec}s)" "DEBUG" }
            "RINGING" { Write-Log "  Ringing... (${elapsedSec}s)" "DEBUG" }
        }

        if ($answered) {
            Write-CallProgress -Elapsed $elapsedSec -Target $ValidAfterSeconds `
                -Status "Call active -- verifying human answer"
        }

        if ($answered -and $elapsedSec -ge $ValidAfterSeconds) {
            Write-Progress -Activity "Call in progress" -Completed
            Write-Log "Human answer confirmed after ${elapsedSec}s. Call left active."
            exit 0
        }

        if ($state -eq "NONE" -and $elapsedSec -gt 5) {
            $outcome = if ($answered) { "auto-attendant (hung up at ${elapsedSec}s)" } else { "no answer / busy" }
            Write-Progress -Activity "Call in progress" -Completed
            Write-Log "Call ended -- $outcome" "WARN"
            break
        }

        if ($elapsedSec -ge $TimeoutCall) {
            Write-Progress -Activity "Call in progress" -Completed
            Write-Log "Call timeout after ${elapsedSec}s -- hanging up" "WARN"
            Invoke-Adb "shell input keyevent KEYCODE_ENDCALL" | Out-Null
            break
        }
    }

    Invoke-Adb "shell input keyevent KEYCODE_ENDCALL" | Out-Null

    Write-Log "Waiting ${RetryDelay}s before next attempt"
    for ($i = 1; $i -le $RetryDelay; $i++) {
        Write-RetryProgress -Elapsed $i -Total $RetryDelay
        Start-Sleep -Seconds 1
    }
    Write-Progress -Activity "Waiting before retry" -Completed
}
function Get-RecallSessionAssessment {
    param(
        [Parameter(Mandatory)][bool]$Started,
        [Parameter(Mandatory)][bool]$TimedOut,
        [Parameter(Mandatory)][int]$ExitCode,
        [Parameter(Mandatory)][int]$AnswerLength,
        [Parameter(Mandatory)][AllowEmptyString()][string]$ReceiptStatus
    )

    $reason = if (-not $Started) {
        'PROCESS_NOT_STARTED'
    }
    elseif ($TimedOut) {
        'TIMEOUT'
    }
    elseif ($ExitCode -ne 0) {
        'CLI_ERROR'
    }
    elseif ($ReceiptStatus -ne 'DELIVERED') {
        'SESSIONSTART_NOT_DELIVERED'
    }
    elseif ($AnswerLength -le 0) {
        'EMPTY_RESPONSE'
    }
    else {
        $null
    }

    [pscustomobject]@{
        scorable = ($null -eq $reason)
        invalid_reason = $reason
    }
}

function Get-RecallProbeAssessment {
    param(
        [Parameter()][AllowNull()][object]$Score,
        [Parameter()][AllowNull()][object]$Total
    )

    if ($null -eq $Score -or $null -eq $Total) {
        return [pscustomobject]@{ status = 'UNAVAILABLE'; score = $null; total = $null }
    }

    $integerTypes = @(
        'System.Byte', 'System.SByte', 'System.Int16', 'System.UInt16',
        'System.Int32', 'System.UInt32', 'System.Int64', 'System.UInt64'
    )
    if ($Score.GetType().FullName -notin $integerTypes -or $Total.GetType().FullName -notin $integerTypes) {
        return [pscustomobject]@{ status = 'INVALID_RANGE'; score = $null; total = $null }
    }

    if ($Total -ne 5 -or $Score -lt 0 -or $Score -gt $Total) {
        return [pscustomobject]@{ status = 'INVALID_RANGE'; score = $null; total = $null }
    }

    $scoreValue = [int]$Score
    $totalValue = [int]$Total
    [pscustomobject]@{ status = 'VALID'; score = $scoreValue; total = $totalValue }
}

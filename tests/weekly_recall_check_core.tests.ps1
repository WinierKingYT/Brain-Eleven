$ErrorActionPreference = 'Stop'
$script:assertionCount = 0
. (Join-Path $PSScriptRoot '..\scripts\weekly_recall_check_core.ps1')

$weeklyScript = Join-Path $PSScriptRoot '..\scripts\weekly_recall_check.ps1'
$tokens = $null
$parseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile($weeklyScript, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -gt 0) {
    throw "Weekly recall script parse failed: $($parseErrors[0].Message)"
}

function Assert-Equal {
    param(
        [Parameter(Mandatory)][AllowNull()][object]$Expected,
        [Parameter(Mandatory)][AllowNull()][object]$Actual,
        [Parameter(Mandatory)][string]$Name
    )

    $script:assertionCount++
    if ($Expected -ne $Actual) {
        throw "$Name expected '$Expected' but received '$Actual'."
    }
}

$valid = Get-RecallSessionAssessment -Started $true -TimedOut $false -ExitCode 0 -AnswerLength 18 -ReceiptStatus 'DELIVERED'
Assert-Equal -Expected $true -Actual $valid.scorable -Name 'successful delivered response is scorable'
Assert-Equal -Expected $null -Actual $valid.invalid_reason -Name 'successful response has no invalid reason'

$providerFailure = Get-RecallSessionAssessment -Started $true -TimedOut $false -ExitCode 1 -AnswerLength 64 -ReceiptStatus 'DELIVERED'
Assert-Equal -Expected $false -Actual $providerFailure.scorable -Name 'nonzero CLI exit is never scorable'
Assert-Equal -Expected 'CLI_ERROR' -Actual $providerFailure.invalid_reason -Name 'CLI error is classified without inspecting response text'

$timeout = Get-RecallSessionAssessment -Started $true -TimedOut $true -ExitCode 1 -AnswerLength 0 -ReceiptStatus 'DELIVERED'
Assert-Equal -Expected 'TIMEOUT' -Actual $timeout.invalid_reason -Name 'timeout classification'

$missingReceipt = Get-RecallSessionAssessment -Started $true -TimedOut $false -ExitCode 0 -AnswerLength 18 -ReceiptStatus 'MISSING'
Assert-Equal -Expected 'SESSIONSTART_NOT_DELIVERED' -Actual $missingReceipt.invalid_reason -Name 'missing delivery is not scorable'

$empty = Get-RecallSessionAssessment -Started $true -TimedOut $false -ExitCode 0 -AnswerLength 0 -ReceiptStatus 'DELIVERED'
Assert-Equal -Expected 'EMPTY_RESPONSE' -Actual $empty.invalid_reason -Name 'empty response is not scorable'

$notStarted = Get-RecallSessionAssessment -Started $false -TimedOut $false -ExitCode -1 -AnswerLength 0 -ReceiptStatus 'NOT_STARTED'
Assert-Equal -Expected 'PROCESS_NOT_STARTED' -Actual $notStarted.invalid_reason -Name 'unstarted process is not scorable'

$probeZero = Get-RecallProbeAssessment -Score 0 -Total 5
Assert-Equal -Expected 'VALID' -Actual $probeZero.status -Name 'zero score is a valid measurement'
Assert-Equal -Expected 0 -Actual $probeZero.score -Name 'valid score is retained'
Assert-Equal -Expected 'VALID' -Actual (Get-RecallProbeAssessment -Score 5 -Total 5).status -Name 'full score is a valid measurement'
Assert-Equal -Expected 'UNAVAILABLE' -Actual (Get-RecallProbeAssessment -Score $null -Total 5).status -Name 'missing score is unavailable'
Assert-Equal -Expected 'INVALID_RANGE' -Actual (Get-RecallProbeAssessment -Score 6 -Total 5).status -Name 'out of range score is invalid'
Assert-Equal -Expected $null -Actual (Get-RecallProbeAssessment -Score 6 -Total 5).score -Name 'invalid score is not persisted'
Assert-Equal -Expected 'INVALID_RANGE' -Actual (Get-RecallProbeAssessment -Score 1 -Total 4).status -Name 'unexpected total is invalid'
Assert-Equal -Expected 'INVALID_RANGE' -Actual (Get-RecallProbeAssessment -Score 2.5 -Total 5).status -Name 'fractional score is invalid'
Assert-Equal -Expected 'INVALID_RANGE' -Actual (Get-RecallProbeAssessment -Score '2' -Total 5).status -Name 'string score is invalid'
Assert-Equal -Expected 'INVALID_RANGE' -Actual (Get-RecallProbeAssessment -Score $true -Total 5).status -Name 'boolean score is invalid'
Assert-Equal -Expected 'INVALID_RANGE' -Actual (Get-RecallProbeAssessment -Score 1 -Total 5000000000).status -Name 'oversized total is invalid without integer overflow'

Write-Output "weekly-recall-check-core: PASS ($script:assertionCount assertions)"

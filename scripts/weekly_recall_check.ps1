[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'weekly_recall_check_core.ps1')

if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw 'PowerShell 7 or later is required for ProcessStartInfo.ArgumentList.'
}

function Invoke-CapturedProcess {
    param(
        [Parameter(Mandatory)][string]$FileName,
        [Parameter()][string[]]$Arguments = @(),
        [Parameter(Mandatory)][string]$WorkingDirectory,
        [Parameter()][ValidateRange(1, 3600)][int]$TimeoutSeconds = 300
    )

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $FileName
    $startInfo.WorkingDirectory = $WorkingDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardOutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $startInfo.StandardErrorEncoding = [System.Text.UTF8Encoding]::new($false)

    foreach ($argument in $Arguments) {
        [void]$startInfo.ArgumentList.Add([string]$argument)
    }

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    $started = $false
    $timedOut = $false
    $stdout = ''
    $stderr = ''
    $exitCode = -1

    try {
        [void]$process.Start()
        $started = $true
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()

        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $timedOut = $true
            try {
                $process.Kill($true)
            }
            catch {
                try { $process.Kill() } catch { }
            }
        }

        $process.WaitForExit()
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        $stderr = $stderrTask.GetAwaiter().GetResult()
        $exitCode = $process.ExitCode
    }
    catch {
        if ($started -and -not $process.HasExited) {
            try { $process.Kill($true) } catch { try { $process.Kill() } catch { } }
        }
    }
    finally {
        $process.Dispose()
    }

    [pscustomobject]@{
        exit_code = $exitCode
        started = $started
        timed_out = $timedOut
        stdout = $stdout
        stderr = $stderr
    }
}

function Get-SessionStartReceiptStatus {
    param(
        [Parameter(Mandatory)][string]$DeliveryDirectory,
        [Parameter()][string[]]$ExistingNames = @(),
        [Parameter(Mandatory)][DateTimeOffset]$StartedAt,
        [Parameter()][ValidateRange(0, 30)][int]$WaitSeconds = 10
    )

    if (-not (Test-Path -LiteralPath $DeliveryDirectory -PathType Container)) {
        return 'MISSING'
    }

    $knownNames = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($name in $ExistingNames) {
        [void]$knownNames.Add($name)
    }

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($WaitSeconds)
    do {
        $receiptMatches = [System.Collections.Generic.List[object]]::new()
        foreach ($file in Get-ChildItem -LiteralPath $DeliveryDirectory -File -Filter '*.json') {
            if ($knownNames.Contains($file.Name)) {
                continue
            }
            if ($file.LastWriteTimeUtc -lt $StartedAt.UtcDateTime.AddSeconds(-3)) {
                continue
            }

            try {
                $record = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json -ErrorAction Stop
            }
            catch {
                continue
            }

            if ([string]$record.event -ne 'SessionStart' -or [string]$record.client -ne 'claude') {
                continue
            }

            try {
                $receiptAt = [DateTimeOffset]::Parse([string]$record.at).ToUniversalTime()
            }
            catch {
                continue
            }
            if ($receiptAt -lt $StartedAt.ToUniversalTime()) {
                continue
            }

            $stage = if ([string]::IsNullOrWhiteSpace([string]$record.stage)) { 'UNKNOWN' } else { [string]$record.stage }
            $receiptMatches.Add([pscustomobject]@{ at = $receiptAt; stage = $stage })
        }

        if ($receiptMatches.Count -gt 0) {
            return [string](($receiptMatches | Sort-Object -Property at | Select-Object -Last 1).stage)
        }

        if ([DateTimeOffset]::UtcNow -lt $deadline) {
            Start-Sleep -Seconds 1
        }
    } while ([DateTimeOffset]::UtcNow -lt $deadline)

    'MISSING'
}

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$questionsPath = Join-Path $repositoryRoot 'evals/recall_probe/questions.json'
$deliveryDirectory = Join-Path $repositoryRoot '.brain-eleven/runtime/deliveries'
$measurementDirectory = Join-Path $repositoryRoot '.brain-eleven/runtime/measurements'
$date = Get-Date -Format 'yyyy-MM-dd'

# Prefer the vault's own virtualenv: a bare 'python' can be the system or
# Store interpreter without Brain-Eleven's dependencies (the /remember bug).
$venvPython = @(
    (Join-Path $repositoryRoot '.venv/Scripts/python.exe'),
    (Join-Path $repositoryRoot '.venv/bin/python')
) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
$pythonCommand = if ($venvPython) { [pscustomobject]@{ Source = $venvPython } } else {
    Get-Command -Name 'python' -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
}
$claudeCommand = Get-Command -Name 'claude' -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
$pythonPath = if ($pythonCommand) { $pythonCommand.Source } else { $null }
$claudePath = if ($claudeCommand) { $claudeCommand.Source } else { $null }

$failedProcess = [pscustomobject]@{ exit_code = -1; started = $false; timed_out = $false; stdout = ''; stderr = '' }
if ($pythonPath) {
    $measureResult = Invoke-CapturedProcess -FileName $pythonPath -Arguments @('-m', 'brain_eleven', 'measure') -WorkingDirectory $repositoryRoot
    $probeResult = Invoke-CapturedProcess -FileName $pythonPath -Arguments @('-m', 'brain_eleven', 'recall-probe') -WorkingDirectory $repositoryRoot
    # Prompt-time memory (2026-09-30) is where recall happens now; measure it
    # too so a regression shows up in the weekly record, not only SessionStart.
    $promptProbeResult = Invoke-CapturedProcess -FileName $pythonPath -Arguments @('-m', 'brain_eleven', 'recall-probe', '--mode', 'prompt') -WorkingDirectory $repositoryRoot
}
else {
    $measureResult = $failedProcess
    $probeResult = $failedProcess
    $promptProbeResult = $failedProcess
}

$promptProbeScore = $null
$promptProbeTotal = $null
if ($promptProbeResult.started -and -not $promptProbeResult.timed_out) {
    try {
        $promptProbeData = ConvertFrom-Json -InputObject $promptProbeResult.stdout -ErrorAction Stop
        $promptProbeScore = $promptProbeData.score
        $promptProbeTotal = $promptProbeData.of
    }
    catch {
        $promptProbeScore = $null
        $promptProbeTotal = $null
    }
}
$promptProbeAssessment = Get-RecallProbeAssessment -Score $promptProbeScore -Total $promptProbeTotal

$probeScore = $null
$probeTotal = $null
if ($probeResult.started -and -not $probeResult.timed_out) {
    try {
        $probeData = ConvertFrom-Json -InputObject $probeResult.stdout -ErrorAction Stop
        $probeScore = $probeData.score
        $probeTotal = $probeData.of
    }
    catch {
        $probeScore = $null
        $probeTotal = $null
    }
}

$questionDocument = Get-Content -LiteralPath $questionsPath -Raw | ConvertFrom-Json -ErrorAction Stop
$questions = @($questionDocument.questions)
if ($questions.Count -ne 5) {
    throw 'Expected exactly five recall questions.'
}

$questionResults = [System.Collections.Generic.List[object]]::new()
$instruction = "Araç kullanma, komut çalıştırma; yalnızca oturum başında sana verilen bağlamla kısaca cevap ver. Bilmiyorsan 'bilmiyorum' de."
foreach ($question in $questions) {
    $questionNumber = [int]$question.id
    $answerLength = 0
    $timedOut = $false
    $receiptStatus = 'NOT_STARTED'
    $claudeResult = $failedProcess

    if ($claudePath) {
        $existingReceiptNames = @()
        if (Test-Path -LiteralPath $deliveryDirectory -PathType Container) {
            $existingReceiptNames = @(Get-ChildItem -LiteralPath $deliveryDirectory -File -Filter '*.json' | ForEach-Object Name)
        }

        $startedAt = [DateTimeOffset]::UtcNow
        $prompt = [string]$question.question + ' — ' + $instruction
        $claudeResult = Invoke-CapturedProcess -FileName $claudePath -Arguments @('-p', $prompt, '--tools', '', '--strict-mcp-config') -WorkingDirectory $repositoryRoot -TimeoutSeconds 120
        $timedOut = [bool]$claudeResult.timed_out
        $answerLength = ([string]$claudeResult.stdout).Trim().Length
        $receiptStatus = Get-SessionStartReceiptStatus -DeliveryDirectory $deliveryDirectory -ExistingNames $existingReceiptNames -StartedAt $startedAt
    }

    $assessment = Get-RecallSessionAssessment `
        -Started ([bool]$claudeResult.started) `
        -TimedOut $timedOut `
        -ExitCode ([int]$claudeResult.exit_code) `
        -AnswerLength $answerLength `
        -ReceiptStatus $receiptStatus

    $questionResults.Add([pscustomobject][ordered]@{
        question = $questionNumber
        answer_length = $answerLength
        timeout = $timedOut
        claude_exit_code = [int]$claudeResult.exit_code
        delivery_receipt_status = $receiptStatus
        scorable = [bool]$assessment.scorable
        invalid_reason = $assessment.invalid_reason
    })
}

$probeAssessment = Get-RecallProbeAssessment -Score $probeScore -Total $probeTotal
$probeStatus = $probeAssessment.status
$probeScore = $probeAssessment.score
$probeTotal = $probeAssessment.total

[void][System.IO.Directory]::CreateDirectory($measurementDirectory)
$report = [ordered]@{
    date = $date
    measure_exit_code = [int]$measureResult.exit_code
    recall_probe_exit_code = [int]$probeResult.exit_code
    recall_probe_score = $probeScore
    recall_probe_total = $probeTotal
    recall_probe_status = $probeStatus
    recall_probe_prompt_exit_code = [int]$promptProbeResult.exit_code
    recall_probe_prompt_score = $promptProbeAssessment.score
    recall_probe_prompt_total = $promptProbeAssessment.total
    recall_probe_prompt_status = $promptProbeAssessment.status
    sessions = @($questionResults.ToArray())
}
$reportJson = ConvertTo-Json -InputObject $report -Depth 6
$reportPath = Join-Path $measurementDirectory "weekly-$date.json"
$tempPath = Join-Path $measurementDirectory ".weekly-$date-$PID.tmp"
[System.IO.File]::WriteAllText($tempPath, $reportJson + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::Move($tempPath, $reportPath, $true)

$deliveredCount = @($questionResults | Where-Object { $_.delivery_receipt_status -eq 'DELIVERED' }).Count
$timeoutCount = @($questionResults | Where-Object { $_.timeout }).Count
$scorableCount = @($questionResults | Where-Object { $_.scorable }).Count
$invalidCount = $questionResults.Count - $scorableCount
$probeDisplay = if ($null -ne $probeScore -and $null -ne $probeTotal) { "$probeScore/$probeTotal" } else { 'unavailable' }
$promptProbeDisplay = if ($promptProbeAssessment.status -eq 'VALID') { "$($promptProbeAssessment.score)/$($promptProbeAssessment.total)" } else { 'unavailable' }
Write-Output "weekly-recall-check date=$date measure_exit=$($measureResult.exit_code) probe_exit=$($probeResult.exit_code) probe=$probeDisplay prompt_probe=$promptProbeDisplay sessions=$($questionResults.Count) scorable=$scorableCount invalid=$invalidCount delivered=$deliveredCount timeouts=$timeoutCount file=weekly-$date.json"

$hasReceiptFailure = @($questionResults | Where-Object { $_.delivery_receipt_status -ne 'DELIVERED' }).Count -gt 0
$hasInvalidSession = $invalidCount -gt 0
if ($measureResult.exit_code -ne 0 -or $probeResult.exit_code -ne 0 -or $probeStatus -ne 'VALID' -or
    $promptProbeResult.exit_code -ne 0 -or $promptProbeAssessment.status -ne 'VALID' -or
    -not $claudePath -or $hasReceiptFailure -or $hasInvalidSession) {
    exit 1
}

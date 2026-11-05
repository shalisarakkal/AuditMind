# Pure process-identity regression: no real processes or files are stopped/deleted.
$ErrorActionPreference = 'Stop'
$parseErrors = $null
$launcher = Join-Path (Split-Path $PSScriptRoot) 'start-demo.ps1'
$ast = [System.Management.Automation.Language.Parser]::ParseFile($launcher, [ref]$null, [ref]$parseErrors)
if ($parseErrors) { throw $parseErrors }
$definition = $ast.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Stop-Demo' }, $false)
if (-not $definition) { throw 'Stop-Demo function not found' }
Invoke-Expression $definition.Extent.Text

$demoPidFile = 'synthetic-process-record'
$instant = [DateTimeOffset]::Parse('2026-11-05T01:38:48.2009537Z').UtcDateTime
function Test-Path { param($LiteralPath) return $true }
function Get-Content { param($LiteralPath, [switch]$Raw) return '{}' }
function ConvertFrom-Json { param([Parameter(ValueFromPipeline)]$InputObject) return $script:record }
function Get-Process {
    param($Id, $ErrorAction)
    return [pscustomobject]@{ Id=$Id; StartTime=$instant }
}
function Get-CimInstance {
    param($ClassName)
    return [pscustomobject]@{ProcessId=41001;ParentProcessId=41000;CreationDate=$instant}
}
function Stop-Process { param($Id, $ErrorAction) $script:stopped += $Id }
function Remove-Item { param($LiteralPath) $script:removed = $true }

foreach ($recorded in @('2026-11-05T01:38:48.2009530Z', $instant, [DateTimeOffset]::new($instant))) {
    $script:record = [pscustomobject]@{Id=41000;Started=$recorded}
    $script:stopped = @()
    $script:removed = $false
    Stop-Demo
    if (($script:stopped -join ',') -ne '41001,41000' -or -not $script:removed) {
        throw 'Rounded/typed timestamp did not stop the verified child and launcher'
    }
}
$script:record = [pscustomobject]@{Id=41000;Started=$instant.AddSeconds(-1).ToString('o')}
$script:stopped = @()
Stop-Demo
if ($script:stopped.Count -ne 0) { throw 'PID reuse protection failed' }
Write-Output 'Four demo-stop regressions passed; no real process/file mutations.'

$ErrorActionPreference = 'Stop'
$Host.UI.RawUI.WindowTitle = 'Shopee Deal Machine - Central Windows'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$LogsDir = Join-Path $Root 'logs'
$LogFile = Join-Path $LogsDir 'central_startup_error.txt'
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

function Format-ErrorDetail($errorRecord) {
    $parts = [System.Collections.Generic.List[string]]::new()
    if($errorRecord.Exception -and $errorRecord.Exception.Message){ $parts.Add($errorRecord.Exception.Message) }
    if($errorRecord.InvocationInfo -and $errorRecord.InvocationInfo.PositionMessage){ $parts.Add($errorRecord.InvocationInfo.PositionMessage) }
    if($errorRecord.ScriptStackTrace){ $parts.Add("Stack do PowerShell:`r`n$($errorRecord.ScriptStackTrace)") }
    if($errorRecord.FullyQualifiedErrorId){ $parts.Add("ID do erro: $($errorRecord.FullyQualifiedErrorId)") }
    return ($parts -join "`r`n`r`n")
}

function Show-StartupError([string]$message) {
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $body = "[$stamp]`r`n$message`r`n"
    try { [IO.File]::WriteAllText($LogFile, $body, [System.Text.UTF8Encoding]::new($false)) } catch {}

    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host ' SHOPEE DEAL MACHINE - ERRO AO ABRIR' -ForegroundColor Red
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host $message -ForegroundColor Yellow
    Write-Host ''
    Write-Host "Log salvo em: $LogFile" -ForegroundColor Cyan
    Write-Host ''

    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        [System.Windows.Forms.MessageBox]::Show(
            "A Central Windows não conseguiu iniciar.`r`n`r`n$message`r`n`r`nO PowerShell ficará aberto com o erro completo.`r`nO log também foi salvo em:`r`n$LogFile",
            'Shopee Deal Machine - erro ao abrir',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
    } catch {}
}

try {
    Write-Host 'Shopee Deal Machine - verificando a Central...' -ForegroundColor Cyan

    if ($PSVersionTable.PSVersion.Major -lt 5) {
        throw "Windows PowerShell 5.1 ou superior é necessário. Versão encontrada: $($PSVersionTable.PSVersion)."
    }

    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        Add-Type -AssemblyName System.Drawing -ErrorAction Stop
    } catch {
        throw "Os componentes gráficos do Windows (Windows Forms/Desktop Experience) não estão disponíveis nesta VPS. Detalhe: $($_.Exception.Message)"
    }

    $control = Join-Path $ScriptDir 'ControlCenter.ps1'
    if (-not (Test-Path $control)) { throw "Arquivo da Central não encontrado: $control" }

    # Pré-validação pelo próprio parser do Windows PowerShell antes de executar.
    $parseTokens = $null
    $parseErrors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($control, [ref]$parseTokens, [ref]$parseErrors) | Out-Null
    if($parseErrors -and $parseErrors.Count -gt 0){
        $parseText = ($parseErrors | ForEach-Object { "Linha $($_.Extent.StartLineNumber): $($_.Message)" }) -join "`r`n"
        throw "O arquivo da Central contém erro de sintaxe:`r`n$parseText"
    }

    Remove-Item $LogFile -Force -ErrorAction SilentlyContinue
    Write-Host 'Validação inicial OK. Abrindo interface...' -ForegroundColor Green
    & $control
    Write-Host 'Central encerrada normalmente.' -ForegroundColor DarkGray
    exit 0
}
catch {
    $detail = Format-ErrorDetail $_
    Show-StartupError $detail
    exit 1
}

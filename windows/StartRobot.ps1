$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'
$Host.UI.RawUI.WindowTitle = 'Shopee Deal Machine - Iniciar robô'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$RuntimeDir = Join-Path $Root 'data\runtime'
$LogsDir = Join-Path $Root 'logs'
$PythonFile = Join-Path $RuntimeDir 'python_path.txt'
$PidFile = Join-Path $RuntimeDir 'supervisor.pid'
$StopFile = Join-Path $RuntimeDir 'stop.flag'
$Supervisor = Join-Path $ScriptDir 'supervisor.py'
$SelfHeal = Join-Path $ScriptDir 'self_heal.py'
$LogFile = Join-Path $LogsDir 'start_robot_error.txt'
$BootstrapOut = Join-Path $LogsDir 'supervisor_bootstrap_out.log'
$BootstrapErr = Join-Path $LogsDir 'supervisor_bootstrap_err.log'
New-Item -ItemType Directory -Force -Path $RuntimeDir,$LogsDir | Out-Null

function Save-Error([string]$messageText) {
    try { [IO.File]::WriteAllText($LogFile, "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')]`r`n$messageText`r`n", [System.Text.UTF8Encoding]::new($false)) } catch {}
}
function Show-ErrorAndWait([string]$messageText) {
    Save-Error $messageText
    Write-Host ''
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host ' SHOPEE DEAL MACHINE - ERRO AO INICIAR O ROBÔ' -ForegroundColor Red
    Write-Host '============================================================' -ForegroundColor Red
    Write-Host $messageText -ForegroundColor Yellow
    Write-Host ''
    Write-Host "Log: $LogFile" -ForegroundColor Cyan
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        [System.Windows.Forms.MessageBox]::Show(
            "O robô não conseguiu iniciar.`r`n`r`n$messageText`r`n`r`nA janela preta ficará aberta com o erro completo.",
            'Shopee Deal Machine - erro ao iniciar','OK','Error') | Out-Null
    } catch {}
    Write-Host ''
    Write-Host 'Pressione ENTER para fechar esta janela.' -ForegroundColor White
    try { [void](Read-Host) } catch { Start-Sleep -Seconds 60 }
}
function Test-PidAlive([int]$PidValue) {
    if ($PidValue -le 0) { return $false }
    try { $p = Get-Process -Id $PidValue -ErrorAction Stop; return -not $p.HasExited } catch { return $false }
}
function Test-RuntimePython([string]$candidate) {
    if([string]::IsNullOrWhiteSpace($candidate)){ return $null }
    try {
        $candidate = [Environment]::ExpandEnvironmentVariables($candidate.Trim().Trim('"'))
        if(-not (Test-Path -LiteralPath $candidate -PathType Leaf)){ return $null }
        $p = Start-Process -FilePath $candidate -ArgumentList '-c "import sys; raise SystemExit(0)"' -WindowStyle Hidden -PassThru -Wait
        if($p.ExitCode -eq 0){ return $candidate }
    } catch {}
    return $null
}
function Get-RuntimePython {
    $candidates = [System.Collections.Generic.List[string]]::new()
    if (Test-Path $PythonFile) { try { $candidates.Add((Get-Content $PythonFile -Raw).Trim().Trim('"')) } catch {} }
    $candidates.Add((Join-Path $env:ProgramData 'ShopeeDealMachine\Python312\python.exe'))
    if($env:ProgramFiles){ $candidates.Add((Join-Path $env:ProgramFiles 'Python312\python.exe')) }
    if($env:LOCALAPPDATA){ $candidates.Add((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe')) }
    foreach($candidate in $candidates){ $found=Test-RuntimePython $candidate; if($found){ return $found } }
    foreach($regPath in @(
        'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Python\PythonCore\3.12\InstallPath',
        'Registry::HKEY_CURRENT_USER\SOFTWARE\Python\PythonCore\3.12\InstallPath',
        'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Python\PythonCore\3.12\InstallPath')){
        try { if(Test-Path $regPath){ $base=(Get-Item $regPath).GetValue(''); if($base){ $found=Test-RuntimePython (Join-Path $base 'python.exe'); if($found){return $found} } } } catch {}
    }
    try {
        $py=Get-Command py.exe -ErrorAction SilentlyContinue
        if($py){ $resolved=& $py.Source -3.12 -c 'import sys; print(sys.executable)' 2>$null; if($LASTEXITCODE -eq 0){ $found=Test-RuntimePython (($resolved|Out-String).Trim()); if($found){return $found} } }
    } catch {}
    foreach($name in @('python.exe','python3.exe')){ try{ $cmd=Get-Command $name -ErrorAction SilentlyContinue; if($cmd -and $cmd.Source -and $cmd.Source -notmatch '\\WindowsApps\\'){ $found=Test-RuntimePython $cmd.Source; if($found){return $found} } }catch{} }
    return $null
}
function Tail-File([string]$path,[int]$count=35) {
    if(-not (Test-Path $path)){ return '' }
    try { return ((Get-Content $path -Tail $count -ErrorAction SilentlyContinue) -join "`r`n") } catch { return '' }
}

try {
    Write-Host 'Shopee Deal Machine - verificando e reparando ambiente...' -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath $Supervisor -PathType Leaf)) { throw "Supervisor não encontrado:`r`n$Supervisor`r`n`r`nExtraia o ZIP completo em uma pasta normal." }
    if (-not (Test-Path -LiteralPath $SelfHeal -PathType Leaf)) { throw "Módulo de reparo não encontrado:`r`n$SelfHeal" }
    $python = Get-RuntimePython
    if (-not $python) { throw "Python não localizado.`r`nAbra a Central Windows e clique em Instalar / Atualizar." }
    [IO.File]::WriteAllText($PythonFile,$python,[Text.Encoding]::ASCII)
    Write-Host "Python: $python" -ForegroundColor DarkGray

    if (Test-Path $PidFile) {
        try { $oldPid=[int](Get-Content $PidFile -Raw); if(Test-PidAlive $oldPid){ Write-Host "Robô já está ligado (PID $oldPid)." -ForegroundColor Green; Start-Sleep 2; exit 0 } } catch {}
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $StopFile -Force -ErrorAction SilentlyContinue

    Write-Host 'Pré-verificação automática: Python, pip, bibliotecas e banco...' -ForegroundColor Cyan
    $healOut = Join-Path $LogsDir 'self_heal_console_out.log'
    $healErr = Join-Path $LogsDir 'self_heal_console_err.log'
    Remove-Item $healOut,$healErr -Force -ErrorAction SilentlyContinue
    $heal = Start-Process -FilePath $python -ArgumentList ('"'+$SelfHeal+'"') -WorkingDirectory $Root -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput $healOut -RedirectStandardError $healErr
    if($heal.ExitCode -ne 0){
        $detail = (Tail-File $healErr 50)
        if(-not $detail){ $detail = Tail-File (Join-Path $LogsDir 'self_heal.log') 50 }
        throw "O reparo automático do ambiente falhou.`r`n`r`n$detail`r`n`r`nLog: $(Join-Path $LogsDir 'self_heal.log')"
    }
    Write-Host 'Ambiente OK.' -ForegroundColor Green

    Remove-Item $BootstrapOut,$BootstrapErr -Force -ErrorAction SilentlyContinue
    Write-Host "Supervisor: $Supervisor" -ForegroundColor DarkGray
    # Use python.exe (not pythonw) and redirect everything so startup failures are never invisible.
    $proc = Start-Process -FilePath $python -ArgumentList ('"'+$Supervisor+'"') -WorkingDirectory $Root -WindowStyle Hidden -PassThru -RedirectStandardOutput $BootstrapOut -RedirectStandardError $BootstrapErr
    if (-not $proc) { throw 'O Windows não retornou o processo do supervisor.' }

    $deadline=(Get-Date).AddSeconds(25); $started=$false
    while((Get-Date)-lt $deadline){
        Start-Sleep -Milliseconds 300
        if(Test-Path $PidFile){ try{ $newPid=[int](Get-Content $PidFile -Raw); if(Test-PidAlive $newPid){$started=$true;break} }catch{} }
        $proc.Refresh(); if($proc.HasExited){break}
    }
    if(-not $started){
        $parts=[System.Collections.Generic.List[string]]::new()
        $parts.Add('O supervisor não confirmou a inicialização.')
        $errTail=Tail-File $BootstrapErr 50; if($errTail){$parts.Add("ERRO REAL DO PYTHON:`r`n$errTail")}
        $outTail=Tail-File $BootstrapOut 50; if($outTail){$parts.Add("SAÍDA DO PYTHON:`r`n$outTail")}
        $supTail=Tail-File (Join-Path $LogsDir 'supervisor.log') 40; if($supTail){$parts.Add("SUPERVISOR.LOG:`r`n$supTail")}
        $healTail=Tail-File (Join-Path $LogsDir 'self_heal.log') 20; if($healTail){$parts.Add("ÚLTIMA VERIFICAÇÃO:`r`n$healTail")}
        throw ($parts -join "`r`n`r`n")
    }
    Remove-Item $LogFile -Force -ErrorAction SilentlyContinue
    Write-Host 'Robô iniciado com sucesso.' -ForegroundColor Green
    Start-Sleep 2
    exit 0
}
catch {
    $parts=[System.Collections.Generic.List[string]]::new()
    if($_.Exception -and $_.Exception.Message){$parts.Add($_.Exception.Message)}
    if($_.InvocationInfo -and $_.InvocationInfo.PositionMessage){$parts.Add($_.InvocationInfo.PositionMessage)}
    if($_.ScriptStackTrace){$parts.Add("Stack:`r`n$($_.ScriptStackTrace)")}
    Show-ErrorAndWait ($parts -join "`r`n`r`n")
    exit 1
}

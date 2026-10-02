$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$RuntimeDir = Join-Path $Root 'data\runtime'
$LogsDir = Join-Path $Root 'logs'
$EnvFile = Join-Path $Root '.env'
$PythonFile = Join-Path $RuntimeDir 'python_path.txt'
$StateFile = Join-Path $RuntimeDir 'state.json'
$PidFile = Join-Path $RuntimeDir 'supervisor.pid'
$StopFile = Join-Path $RuntimeDir 'stop.flag'
$TaskName = 'Shopee Deal Machine'
New-Item -ItemType Directory -Force -Path $RuntimeDir,$LogsDir,(Join-Path $Root 'backups'),(Join-Path $Root 'data\windows'),(Join-Path $Root 'data\telegram') | Out-Null

function Test-Admin {
    $id=[Security.Principal.WindowsIdentity]::GetCurrent(); $p=[Security.Principal.WindowsPrincipal]::new($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
if(-not (Test-Admin)){
    $arg="-NoProfile -STA -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`""
    Start-Process powershell.exe -ArgumentList $arg -Verb RunAs
    exit
}

$Theme = @{
    Bg     = [System.Drawing.Color]::FromArgb(9,13,22)
    Card   = [System.Drawing.Color]::FromArgb(18,25,39)
    Input  = [System.Drawing.Color]::FromArgb(13,20,33)
    Text   = [System.Drawing.Color]::FromArgb(238,242,255)
    Muted  = [System.Drawing.Color]::FromArgb(143,160,190)
    Accent = [System.Drawing.Color]::FromArgb(255,90,31)
    Green  = [System.Drawing.Color]::FromArgb(83,196,132)
    Red    = [System.Drawing.Color]::FromArgb(240,96,96)
    Blue   = [System.Drawing.Color]::FromArgb(58,105,168)
}

function Read-Env {
    $h=@{}
    if(Test-Path $EnvFile){
        foreach($line in Get-Content $EnvFile -Encoding UTF8){
            if($line -match '^\s*#' -or $line -notmatch '='){ continue }
            $i=$line.IndexOf('='); if($i -lt 1){continue}
            $k=$line.Substring(0,$i).Trim(); $v=$line.Substring($i+1)
            $h[$k]=$v
        }
    }
    return $h
}
function Random-Password {
    $chars='abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@#$%_-'
    -join (1..28 | ForEach-Object {$chars[(Get-Random -Minimum 0 -Maximum $chars.Length)]})
}
function Ensure-Env {
    if(Test-Path $EnvFile){ return }
    $pw=Random-Password
    $content=@"
APP_ENV=windows
APP_HOST=127.0.0.1
APP_PORT=8787
APP_TIMEZONE=America/Bahia
LOG_LEVEL=INFO
APP_REQUIRE_AUTH=true
ADMIN_USER=admin
ADMIN_PASSWORD=$pw
APP_SESSION_SECRET=$pw$pw
COOKIE_SECURE=false
PUBLIC_BASE_URL=
SESSION_HOURS=12
SHOPEE_APP_ID=
SHOPEE_SECRET=
SHOPEE_API_URL=https://open-api.affiliate.shopee.com.br/graphql
TELEGRAM_BOT_TOKEN=
TELEGRAM_TARGET_CHAT=
TELEGRAM_ADMIN_CHAT=
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_PHONE=
TELEGRAM_READER_ENABLED=true
TELEGRAM_SESSION_PATH=data/telegram/reader
DATABASE_URL=sqlite:///./data/windows/deals.db
REDIS_URL=
REDIS_REQUIRED=false
WORKER_POLL_SECONDS=10
SHOPEE_REQUEST_TIMEOUT_SECONDS=25
HTTP_MAX_RETRIES=3
BACKUP_INTERVAL_HOURS=12
BACKUP_RETENTION_DAYS=30
"@
    [IO.File]::WriteAllText($EnvFile,$content,([System.Text.UTF8Encoding]::new($false)))
}
Ensure-Env

function Write-Env([hashtable]$updates){
    $envMap=Read-Env; foreach($k in $updates.Keys){$envMap[$k]=[string]$updates[$k]}
    $order=@('APP_ENV','APP_HOST','APP_PORT','APP_TIMEZONE','LOG_LEVEL','APP_REQUIRE_AUTH','ADMIN_USER','ADMIN_PASSWORD','APP_SESSION_SECRET','COOKIE_SECURE','PUBLIC_BASE_URL','SESSION_HOURS','SHOPEE_APP_ID','SHOPEE_SECRET','SHOPEE_API_URL','TELEGRAM_BOT_TOKEN','TELEGRAM_TARGET_CHAT','TELEGRAM_ADMIN_CHAT','TELEGRAM_API_ID','TELEGRAM_API_HASH','TELEGRAM_PHONE','TELEGRAM_READER_ENABLED','TELEGRAM_SESSION_PATH','DATABASE_URL','REDIS_URL','REDIS_REQUIRED','WORKER_POLL_SECONDS','SHOPEE_REQUEST_TIMEOUT_SECONDS','HTTP_MAX_RETRIES','BACKUP_INTERVAL_HOURS','BACKUP_RETENTION_DAYS')
    $lines=[System.Collections.Generic.List[string]]::new()
    foreach($k in $order){ if($envMap.ContainsKey($k)){ $lines.Add("$k=$($envMap[$k])") } }
    foreach($k in ($envMap.Keys | Sort-Object)){ if($k -notin $order){ $lines.Add("$k=$($envMap[$k])") } }
    [IO.File]::WriteAllLines($EnvFile,$lines,([System.Text.UTF8Encoding]::new($false)))
}

function Test-PythonCandidate([string]$candidate){
    if([string]::IsNullOrWhiteSpace($candidate)){ return $null }
    try {
        $candidate = [Environment]::ExpandEnvironmentVariables($candidate.Trim().Trim('"'))
        if(-not (Test-Path -LiteralPath $candidate -PathType Leaf)){ return $null }
        $tmpOut = Join-Path $RuntimeDir ("pycheck_{0}.txt" -f ([Guid]::NewGuid().ToString('N')))
        $tmpErr = Join-Path $RuntimeDir ("pycheck_{0}.err.txt" -f ([Guid]::NewGuid().ToString('N')))
        try {
            $proc = Start-Process -FilePath $candidate -ArgumentList '-c "import sys; print(sys.executable)"' -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput $tmpOut -RedirectStandardError $tmpErr
            if($proc.ExitCode -eq 0){ return $candidate }
        } finally {
            Remove-Item $tmpOut,$tmpErr -Force -ErrorAction SilentlyContinue
        }
    } catch {}
    return $null
}

function Find-PythonFromRegistry {
    $regPaths = @(
        'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Python\PythonCore\3.12\InstallPath',
        'Registry::HKEY_CURRENT_USER\SOFTWARE\Python\PythonCore\3.12\InstallPath',
        'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Python\PythonCore\3.12\InstallPath'
    )
    foreach($regPath in $regPaths){
        try {
            if(Test-Path $regPath){
                $key = Get-Item $regPath -ErrorAction Stop
                $base = $key.GetValue('')
                if($base){
                    $found = Test-PythonCandidate (Join-Path $base 'python.exe')
                    if($found){ return $found }
                }
                $exe = $key.GetValue('ExecutablePath')
                $found = Test-PythonCandidate $exe
                if($found){ return $found }
            }
        } catch {}
    }
    return $null
}

function Get-Python {
    $candidates = [System.Collections.Generic.List[string]]::new()
    if(Test-Path $PythonFile){
        try { $candidates.Add((Get-Content $PythonFile -Raw -ErrorAction Stop).Trim().Trim('"')) } catch {}
    }

    $candidates.Add((Join-Path $env:ProgramData 'ShopeeDealMachine\Python312\python.exe'))
    if($env:ProgramFiles){ $candidates.Add((Join-Path $env:ProgramFiles 'Python312\python.exe')) }
    if(${env:ProgramFiles(x86)}){ $candidates.Add((Join-Path ${env:ProgramFiles(x86)} 'Python312\python.exe')) }
    if($env:LOCALAPPDATA){ $candidates.Add((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe')) }
    if($env:LOCALAPPDATA){ $candidates.Add((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312-32\python.exe')) }

    foreach($candidate in $candidates){
        $found = Test-PythonCandidate $candidate
        if($found){ return $found }
    }

    $reg = Find-PythonFromRegistry
    if($reg){ return $reg }

    try {
        $pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
        if($pyLauncher){
            $tmp = Join-Path $RuntimeDir ("pylauncher_{0}.txt" -f ([Guid]::NewGuid().ToString('N')))
            try {
                $proc = Start-Process -FilePath $pyLauncher.Source -ArgumentList '-3.12 -c "import sys; print(sys.executable)"' -WindowStyle Hidden -PassThru -Wait -RedirectStandardOutput $tmp
                if($proc.ExitCode -eq 0 -and (Test-Path $tmp)){
                    $resolved = ([IO.File]::ReadAllText($tmp)).Trim()
                    $found = Test-PythonCandidate $resolved
                    if($found){ return $found }
                }
            } finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
        }
    } catch {}

    foreach($name in @('python.exe','python3.exe')){
        try {
            $cmd = Get-Command $name -ErrorAction SilentlyContinue
            if($cmd -and $cmd.Source -and $cmd.Source -notmatch '\\WindowsApps\\'){
                $found = Test-PythonCandidate $cmd.Source
                if($found){ return $found }
            }
        } catch {}
    }
    return $null
}

function Quote-Arg([string]$a){
    if($null -eq $a){return '""'}
    if($a -notmatch '[\s"]'){return $a}
    return '"' + ($a -replace '(\\*)"','$1$1\\"' -replace '(\\+)$','$1$1') + '"'
}
function Run-Captured([string]$exe,[string[]]$argumentList,[int]$timeout=600){
    # V3.2: executor nativo robusto. Usa System.Diagnostics.Process diretamente
    # e decide sucesso APENAS pelo ExitCode. Texto em stderr (warnings do pip)
    # nunca e tratado como falha quando o processo retorna codigo 0.
    $argLine = (($argumentList | ForEach-Object { Quote-Arg ([string]$_) }) -join ' ')
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $exe
    $psi.Arguments = $argLine
    $psi.WorkingDirectory = $Root
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    # Force UTF-8 for every Python/subprocess launched by the GUI. Windows Server
    # often defaults redirected console output to a legacy code page (cp1252),
    # which crashes when Telegram names contain emoji or other Unicode chars.
    try { $psi.EnvironmentVariables['PYTHONUTF8'] = '1' } catch {}
    try { $psi.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8' } catch {}
    try { $psi.EnvironmentVariables['PYTHONUNBUFFERED'] = '1' } catch {}
    try { $psi.StandardOutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
    try { $psi.StandardErrorEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    try {
        if(-not $proc.Start()){ throw 'O Windows nao conseguiu iniciar o processo solicitado.' }
        $outTask = $proc.StandardOutput.ReadToEndAsync()
        $errTask = $proc.StandardError.ReadToEndAsync()
        $milliseconds = [Math]::Max(1000, $timeout * 1000)
        if(-not $proc.WaitForExit($milliseconds)){
            try { $proc.Kill() } catch {}
            throw "A operacao excedeu o limite de $timeout segundos."
        }
        $proc.WaitForExit()
        $out = $outTask.Result
        $err = $errTask.Result
        $exitCode = $proc.ExitCode
        if($exitCode -ne 0){
            $message = (($err + [Environment]::NewLine + $out).Trim())
            if(-not $message){ $message = "O processo terminou com codigo $exitCode." }
            throw $message
        }
        return $out.Trim()
    }
    finally {
        try { $proc.Dispose() } catch {}
    }
}
function Test-Pip([string]$py){
    try {
        [void](Run-Captured $py @('-m','pip','--version') 90)
        return $true
    } catch {
        return $false
    }
}

function Ensure-Pip([string]$py){
    if(Test-Pip $py){ return }

    # O instalador oficial normalmente já inclui pip. Só usamos ensurepip como fallback.
    # O aviso "Scripts ... is not on PATH" não é relevante porque o sistema SEMPRE
    # chama pip através de "python.exe -m pip".
    $bootstrapError = ''
    $oldWarn = $env:PIP_NO_WARN_SCRIPT_LOCATION
    try {
        $env:PIP_NO_WARN_SCRIPT_LOCATION = '1'
        try {
            [void](Run-Captured $py @('-m','ensurepip','--upgrade') 600)
        } catch {
            $bootstrapError = $_.Exception.Message
        }
    } finally {
        if($null -eq $oldWarn){ Remove-Item Env:PIP_NO_WARN_SCRIPT_LOCATION -ErrorAction SilentlyContinue }
        else { $env:PIP_NO_WARN_SCRIPT_LOCATION = $oldWarn }
    }

    # Resultado real > texto de warning. Se pip funciona, seguimos normalmente.
    if(-not (Test-Pip $py)){
        $msg = "O Python foi instalado, mas o pip não pôde ser inicializado."
        if($bootstrapError){ $msg += "`r`n`r`nDetalhes:`r`n$bootstrapError" }
        throw $msg
    }
}

function Run-Pip([string]$py,[string[]]$pipArgs,[int]$timeout=900){
    # Nunca dependemos de pip.exe no PATH. Avisos de Scripts fora do PATH são
    # irrelevantes porque sempre chamamos pip por `python.exe -m pip`.
    $oldWarn = $env:PIP_NO_WARN_SCRIPT_LOCATION
    try {
        $env:PIP_NO_WARN_SCRIPT_LOCATION = '1'
        $fullArgs = @('-m','pip','--disable-pip-version-check','--no-input') + $pipArgs
        [void](Run-Captured $py $fullArgs $timeout)
    } finally {
        if($null -eq $oldWarn){ Remove-Item Env:PIP_NO_WARN_SCRIPT_LOCATION -ErrorAction SilentlyContinue }
        else { $env:PIP_NO_WARN_SCRIPT_LOCATION = $oldWarn }
    }
}

function Run-Installer {
    try{
        Set-Status 'Preparando ambiente Windows…' $Theme.Muted
        $py=Get-Python
        if(-not $py){
            $cache=Join-Path $Root 'data\cache'; New-Item -ItemType Directory -Force $cache|Out-Null
            $installer=Join-Path $cache 'python-3.12.10-amd64.exe'
            $installLog=Join-Path $LogsDir 'python_install.log'
            if(-not (Test-Path $installer)){
                Set-Status 'Baixando Python oficial…' $Theme.Muted
                [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
                (New-Object Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe',$installer)
            }
            $target=Join-Path $env:ProgramData 'ShopeeDealMachine\Python312'; New-Item -ItemType Directory -Force $target|Out-Null
            Set-Status 'Instalando o runtime do robô…' $Theme.Muted
            Remove-Item $installLog -Force -ErrorAction SilentlyContinue
            $installArgs = '/quiet InstallAllUsers=1 PrependPath=0 Include_launcher=1 Include_test=0 Include_doc=0 Include_debug=0 Include_symbols=0 Include_tcltk=1 Include_pip=1 AssociateFiles=0 Shortcuts=0 TargetDir="' + $target + '" /log "' + $installLog + '"'
            $proc=Start-Process -FilePath $installer -ArgumentList $installArgs -PassThru -Wait
            if($proc.ExitCode -ne 0){throw "Falha na instalação do Python. Código $($proc.ExitCode).`r`nLog: $installLog"}

            # O instalador pode reutilizar uma instalação existente e ignorar TargetDir.
            # Por isso nunca assumimos o caminho: redetectamos pelo arquivo, registro, launcher e PATH.
            Start-Sleep -Seconds 2
            $py=Get-Python
            if(-not $py){
                $attempts = @(
                    (Join-Path $env:ProgramData 'ShopeeDealMachine\Python312\python.exe'),
                    $(if($env:ProgramFiles){Join-Path $env:ProgramFiles 'Python312\python.exe'}),
                    $(if($env:LOCALAPPDATA){Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'})
                ) | Where-Object { $_ }
                $detail = "O instalador terminou com código 0, mas nenhum Python executável foi localizado.`r`n`r`nCaminhos principais verificados:`r`n - " + ($attempts -join "`r`n - ") + "`r`n`r`nTambém foram verificados Registro do Windows, py.exe e PATH.`r`n`r`nLog do instalador:`r`n$installLog"
                throw $detail
            }
        }
        $py = Test-PythonCandidate $py
        if(-not $py){ throw 'O Python foi localizado, mas não conseguiu executar.' }
        [IO.File]::WriteAllText($PythonFile,$py,[Text.Encoding]::ASCII)
        Set-Status ('Python detectado em: ' + $py) $Theme.Green
        Set-Status 'Verificando pip, dependencias e banco…' $Theme.Muted
        $selfHeal = Join-Path $Root 'windows\self_heal.py'
        if(-not (Test-Path $selfHeal)){ throw 'windows\self_heal.py nao foi encontrado.' }
        [void](Run-Captured $py @($selfHeal) 1800)
        Set-Status 'Ambiente instalado e pronto ✅' $Theme.Green
        [System.Windows.Forms.MessageBox]::Show("Instalação concluída.`r`n`r`nPython:`r`n$py`r`n`r`nAgora preencha a aba Configuração e clique em Salvar.",'Shopee Deal Machine','OK','Information')|Out-Null
        Refresh-All
    }catch{ Set-Status ('Erro: '+$_.Exception.Message) $Theme.Red; Show-UiError 'Instalar / Atualizar' $_ }
}

function Test-ProcessId([int]$processId){
    if($processId -le 0){return $false}; try{$p=Get-Process -Id $processId -ErrorAction Stop; return -not $p.HasExited}catch{return $false}
}
function Runtime-Running {
    if(-not (Test-Path $PidFile)){return $false}; try{$processId=[int](Get-Content $PidFile -Raw); return Test-ProcessId $processId}catch{return $false}
}
function Start-Runtime {
    $py = Get-Python
    if(-not $py){
        [System.Windows.Forms.MessageBox]::Show('Python ainda não foi localizado. Clique em Instalar / Atualizar.','Ambiente não instalado','OK','Warning') | Out-Null
        return
    }
    if(Runtime-Running){ Set-Status 'Robô já está ligado.' $Theme.Green; return }
    Remove-Item $StopFile -Force -ErrorAction SilentlyContinue

    # V3.2: self-heal before every start. This prevents a partial installer run from
    # leaving Python present but FastAPI/SQLAlchemy/etc. missing.
    Set-Status 'Verificando e reparando ambiente automaticamente…' $Theme.Muted
    $selfHeal = Join-Path $Root 'windows\self_heal.py'
    if(-not (Test-Path $selfHeal)){ throw 'windows\self_heal.py não foi encontrado. Extraia o pacote completo.' }
    try {
        [void](Run-Captured $py @($selfHeal) 1800)
    } catch {
        $healLog = Join-Path $LogsDir 'self_heal.log'
        $tail = ''
        if(Test-Path $healLog){ try { $tail = ((Get-Content $healLog -Tail 35) -join "`r`n") } catch {} }
        throw "A verificação automática do ambiente falhou.`r`n`r`n$tail`r`n`r`nLog: $healLog"
    }

    Set-Status 'Iniciando supervisor…' $Theme.Muted
    $sup = Join-Path $Root 'windows\supervisor.py'
    $bootOut = Join-Path $LogsDir 'supervisor_bootstrap_out.log'
    $bootErr = Join-Path $LogsDir 'supervisor_bootstrap_err.log'
    Remove-Item $bootOut,$bootErr -Force -ErrorAction SilentlyContinue
    $proc = Start-Process $py -ArgumentList ('"'+$sup+'"') -WorkingDirectory $Root -WindowStyle Hidden -PassThru -RedirectStandardOutput $bootOut -RedirectStandardError $bootErr
    if(-not $proc){ throw 'O Windows não retornou o processo do supervisor.' }

    $limit = (Get-Date).AddSeconds(25)
    while((-not (Runtime-Running)) -and (Get-Date) -lt $limit){
        [System.Windows.Forms.Application]::DoEvents(); Start-Sleep -Milliseconds 250
        try { $proc.Refresh(); if($proc.HasExited){ break } } catch {}
    }
    if(-not (Runtime-Running)){
        $detail = ''
        if(Test-Path $bootErr){ try{$detail=((Get-Content $bootErr -Tail 50)-join "`r`n")}catch{} }
        if(-not $detail -and (Test-Path $bootOut)){ try{$detail=((Get-Content $bootOut -Tail 50)-join "`r`n")}catch{} }
        if(-not $detail){
            $sl=Join-Path $LogsDir 'supervisor.log'; if(Test-Path $sl){try{$detail=((Get-Content $sl -Tail 40)-join "`r`n")}catch{}}
        }
        throw "O supervisor não iniciou.`r`n`r`n$detail"
    }
    Set-Status 'Robô iniciado e ambiente verificado ✅' $Theme.Green
    Refresh-All
}
function Stop-Runtime {
    if(-not(Runtime-Running)){Set-Status 'Robô já está parado.' $Theme.Muted;return}
    New-Item -ItemType File -Force $StopFile|Out-Null; $limit=(Get-Date).AddSeconds(15)
    while((Runtime-Running) -and (Get-Date) -lt $limit){[System.Windows.Forms.Application]::DoEvents();Start-Sleep -Milliseconds 250}
    if(Runtime-Running){try{$processId=[int](Get-Content $PidFile -Raw); Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue}catch{}}
    Set-Status 'Robô parado.' $Theme.Muted; Refresh-All
}
function Restart-Runtime { Stop-Runtime; Start-Sleep -Milliseconds 500; Start-Runtime }
function Open-Dashboard {
    $envv=Read-Env; $port=if($envv['APP_PORT']){$envv['APP_PORT']}else{'8787'}; Start-Process "http://127.0.0.1:$port/"
}
function Connect-Reader {
    $py=Get-Python; if(-not $py){[System.Windows.Forms.MessageBox]::Show('Instale o ambiente primeiro.','Telegram','OK','Warning')|Out-Null;return}
    Save-Config $false
    $pythonw=$py -replace 'python\.exe$','pythonw.exe'; if(-not(Test-Path $pythonw)){$pythonw=$py}
    $loginGui=Join-Path $Root 'windows\telegram_login_gui.py'; Start-Process $pythonw -ArgumentList ('"'+$loginGui+'"') -WorkingDirectory $Root
}
function Test-Integration([string]$kind){
    try{ Save-Config $false; $py=Get-Python; if(-not $py){throw 'Ambiente ainda não instalado.'}; Set-Status "Testando $kind…" $Theme.Muted; $raw=Run-Captured $py @((Join-Path $Root 'windows\test_integrations.py'),$kind) 90; $obj=$raw|ConvertFrom-Json; if($obj.ok){Set-Status $obj.detail $Theme.Green;[System.Windows.Forms.MessageBox]::Show($obj.detail,'Teste concluído','OK','Information')|Out-Null}else{throw $obj.detail} }catch{Set-Status $_.Exception.Message $Theme.Red;Show-UiError ('Teste ' + $kind) $_}
}
function Create-Backup {
    try{$py=Get-Python;if(-not $py){throw 'Ambiente ainda não instalado.'};$out=Run-Captured $py @((Join-Path $Root 'windows\backup_db.py')) 120; Set-Status 'Backup criado.' $Theme.Green; [System.Windows.Forms.MessageBox]::Show("Backup criado em:`r`n$out",'Backup','OK','Information')|Out-Null;Refresh-Backups}catch{Show-UiError 'Criar backup' $_}
}
function Restore-Backup {
    $dlg=New-Object System.Windows.Forms.OpenFileDialog;$dlg.InitialDirectory=(Join-Path $Root 'backups');$dlg.Filter='Banco de backup (*.db)|*.db';if($dlg.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK){return}
    if([System.Windows.Forms.MessageBox]::Show('Restaurar este backup? O robô será reiniciado.','Confirmar restauração','YesNo','Warning') -ne [System.Windows.Forms.DialogResult]::Yes){return}
    try{$was=Runtime-Running;if($was){Stop-Runtime};$py=Get-Python;[void](Run-Captured $py @((Join-Path $Root 'windows\backup_db.py'),'--restore',$dlg.FileName) 120);if($was){Start-Runtime};Set-Status 'Backup restaurado ✅' $Theme.Green;Refresh-Backups}catch{Show-UiError 'Restaurar backup' $_}
}
function Set-Autostart([bool]$enable){
    try{
        if($enable){
            $py = Get-Python
            if(-not $py){ throw 'Instale o ambiente antes de ativar a inicialização automática.' }
            $autoScript = Join-Path $Root 'windows\AutoSupervisor.ps1'
            if(-not(Test-Path $autoScript)){ throw 'windows\AutoSupervisor.ps1 não foi encontrado.' }
            $psExe = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
            $action = New-ScheduledTaskAction -Execute $psExe -Argument ('-NoProfile -ExecutionPolicy Bypass -File "'+$autoScript+'"') -WorkingDirectory $Root
            $trigger = New-ScheduledTaskTrigger -AtStartup
            $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
            $taskSettings = New-ScheduledTaskSettingsSet `
                -StartWhenAvailable `
                -AllowStartIfOnBatteries `
                -DontStopIfGoingOnBatteries `
                -RestartCount 999 `
                -RestartInterval (New-TimeSpan -Minutes 1) `
                -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
                -MultipleInstances IgnoreNew

            Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $taskSettings -Force | Out-Null
            Set-Status 'Inicialização automática ativada e protegida contra queda.' $Theme.Green
        }else{
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
            Set-Status 'Inicialização automática desativada.' $Theme.Muted
        }
    }catch{
        Show-UiError 'Inicialização automática' $_
    }
    Refresh-Autostart
}

function Autostart-Enabled { try{Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop|Out-Null;return $true}catch{return $false} }


function Show-UiError([string]$context, $errorRecord) {
    $message = if ($errorRecord -and $errorRecord.Exception) { $errorRecord.Exception.Message } else { [string]$errorRecord }
    $detail = "$context`r`n`r`n$message"
    try {
        $runtimeLog = Join-Path $LogsDir 'central_runtime_error.txt'
        $extra = if ($errorRecord -and $errorRecord.ScriptStackTrace) { "`r`n`r`nStack:`r`n$($errorRecord.ScriptStackTrace)" } else { '' }
        [IO.File]::WriteAllText($runtimeLog, "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')]`r`n$detail$extra`r`n", [System.Text.UTF8Encoding]::new($false))
    } catch {}
    Write-Host ''
    Write-Host ('ERRO NA INTERFACE: ' + $context) -ForegroundColor Red
    Write-Host $message -ForegroundColor Yellow
    Write-Host ''
    [System.Windows.Forms.MessageBox]::Show($detail, 'Shopee Deal Machine - erro', 'OK', 'Error') | Out-Null
}

function Run-Diagnostics {
    try {
        $lines = [System.Collections.Generic.List[string]]::new()
        $lines.Add('SHOPEE DEAL MACHINE - DIAGNOSTICO WINDOWS')
        $lines.Add('Data: ' + (Get-Date -Format 'dd/MM/yyyy HH:mm:ss'))
        $lines.Add('Pasta: ' + $Root)
        $lines.Add('')

        $required = @(
            'windows\supervisor.py',
            'windows\StartRobot.ps1',
            'windows\ControlCenter.ps1',
            'app\main.py',
            'app\worker.py',
            'requirements-windows.txt'
        )
        foreach ($rel in $required) {
            $full = Join-Path $Root $rel
            if (Test-Path -LiteralPath $full) {
                $lines.Add('OK   Arquivo: ' + $rel)
            } else {
                $lines.Add('ERRO Arquivo ausente: ' + $rel)
            }
        }

        $py = Get-Python
        if ($py) {
            $lines.Add('OK   Python: ' + $py)
            try {
                $ver = (& $py --version 2>&1 | Out-String).Trim()
                if ($ver) { $lines.Add('OK   ' + $ver) }
            } catch {
                $lines.Add('ERRO Python nao executou: ' + $_.Exception.Message)
            }
            $pyw = Join-Path (Split-Path -Parent $py) 'pythonw.exe'
            if (Test-Path $pyw) {
                $lines.Add('OK   pythonw.exe: ' + $pyw)
            } else {
                $lines.Add('INFO pythonw.exe nao encontrado; python.exe sera usado como fallback')
            }
        } else {
            $lines.Add('ERRO Python: ambiente ainda nao instalado/localizado')
        }

        if (Test-Path $EnvFile) { $lines.Add('OK   Arquivo .env') }
        else { $lines.Add('ERRO Arquivo .env ausente') }

        if ($py) {
            try {
                $smoke = Join-Path $Root 'windows\smoke_imports.py'
                if (Test-Path $smoke) {
                    $smokeOut = Run-Captured $py @($smoke) 90
                    if ($smokeOut -match 'OK') { $lines.Add('OK   Importacao do projeto app/config/db') }
                    else { $lines.Add('ERRO Importacao do projeto sem confirmacao: ' + $smokeOut) }
                } else {
                    $lines.Add('ERRO windows\smoke_imports.py ausente')
                }
            } catch {
                $lines.Add('ERRO Importacao do projeto: ' + $_.Exception.Message)
            }
        }

        $dbPath = Join-Path $Root 'data\windows\deals.db'
        if (Test-Path $dbPath) { $lines.Add('OK   Banco SQLite: ' + $dbPath) }
        else { $lines.Add('INFO Banco SQLite ainda nao criado') }

        if (Runtime-Running) { $lines.Add('OK   Supervisor em execucao') }
        else { $lines.Add('INFO Supervisor parado') }

        $envMap = Read-Env
        foreach ($key in @('SHOPEE_APP_ID','SHOPEE_SECRET','TELEGRAM_BOT_TOKEN','TELEGRAM_TARGET_CHAT','TELEGRAM_API_ID','TELEGRAM_API_HASH','TELEGRAM_PHONE')) {
            $value = ''
            if ($envMap.ContainsKey($key)) { $value = [string]$envMap[$key] }
            if ($value.Trim()) { $lines.Add('OK   Configuracao: ' + $key) }
            else { $lines.Add('INFO Configuracao vazia: ' + $key) }
        }

        $sessionBase = Join-Path $Root 'data\telegram\reader'
        $sessionFile = $sessionBase + '.session'
        $authFile = $sessionBase + '.authorized'
        $sessionOk = (Test-Path $sessionFile) -or (Test-Path $sessionBase)
        $authOk = Test-Path $authFile
        if ($sessionOk -and $authOk) { $lines.Add('OK   Sessao Telegram autorizada') }
        else { $lines.Add('INFO Sessao Telegram ainda nao autorizada') }

        if (Runtime-Running) {
            try {
                $port = '8787'
                if ($envMap.ContainsKey('APP_PORT') -and $envMap['APP_PORT']) { $port = [string]$envMap['APP_PORT'] }
                $healthUri = 'http://127.0.0.1:' + $port + '/api/health'
                $resp = Invoke-WebRequest -UseBasicParsing -Uri $healthUri -TimeoutSec 5
                $lines.Add('OK   Health do painel: HTTP ' + [string]$resp.StatusCode)
            } catch {
                $lines.Add('ERRO Health do painel: ' + $_.Exception.Message)
            }
        }

        $report = $lines -join "`r`n"
        $reportPath = Join-Path $LogsDir 'diagnostico_windows.txt'
        [IO.File]::WriteAllText($reportPath,$report,[System.Text.UTF8Encoding]::new($false))
        Write-Host ''
        Write-Host $report -ForegroundColor Cyan
        [System.Windows.Forms.MessageBox]::Show(
            $report + "`r`n`r`nRelatorio salvo em:`r`n" + $reportPath,
            'Diagnostico completo',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        ) | Out-Null
    } catch {
        Show-UiError 'Diagnostico completo' $_
    }
}

# ---------- UI ----------
$form=New-Object System.Windows.Forms.Form; $form.Text='Shopee Deal Machine · Central Windows v5.0';$form.Size=[System.Drawing.Size]::new(1120,780);$form.StartPosition='CenterScreen';$form.BackColor=$Theme.Bg;$form.ForeColor=$Theme.Text;$form.Font=[System.Drawing.Font]::new('Segoe UI',[single]9);$form.MinimumSize=[System.Drawing.Size]::new(1000,700)
$header=New-Object System.Windows.Forms.Panel;$header.Dock='Top';$header.Height=82;$header.BackColor=$Theme.Card;$form.Controls.Add($header)
$title=New-Object System.Windows.Forms.Label;$title.Text='🛍️  Shopee Deal Machine';$title.Font=[System.Drawing.Font]::new('Segoe UI',[single]19,[System.Drawing.FontStyle]::Bold);$title.ForeColor=$Theme.Text;$title.AutoSize=$true;$title.Location=[System.Drawing.Point]::new(22,14);$header.Controls.Add($title)
$sub=New-Object System.Windows.Forms.Label;$sub.Text='Central visual Enterprise para Windows VPS · operação 24/7';$sub.ForeColor=$Theme.Muted;$sub.AutoSize=$true;$sub.Location=[System.Drawing.Point]::new(26,50);$header.Controls.Add($sub)
$statusTop=New-Object System.Windows.Forms.Label;$statusTop.Text='Carregando…';$statusTop.Font=[System.Drawing.Font]::new('Segoe UI',[single]10,[System.Drawing.FontStyle]::Bold);$statusTop.AutoSize=$true;$statusTop.Location=[System.Drawing.Point]::new(930,30);$header.Controls.Add($statusTop)
$tabs=New-Object System.Windows.Forms.TabControl;$tabs.Dock='Fill';$tabs.Padding=[System.Drawing.Point]::new(18,8);$form.Controls.Add($tabs)
function New-Tab([string]$name){
    $tab = New-Object System.Windows.Forms.TabPage
    $tab.Text = $name
    $tab.BackColor = $Theme.Bg
    $tab.ForeColor = $Theme.Text
    [void]$tabs.TabPages.Add($tab)
    return $tab
}

$tabHome=New-Tab 'Visão geral';$tabCfg=New-Tab 'Configuração';$tabLogs=New-Tab 'Logs';$tabBackup=New-Tab 'Backups'

function New-Button($parent,[string]$buttonText,[int]$x,[int]$y,[int]$w,[int]$h,$color,[scriptblock]$action){
    $button = New-Object System.Windows.Forms.Button
    $button.Text = $buttonText
    $button.Location = [System.Drawing.Point]::new($x,$y)
    $button.Size = [System.Drawing.Size]::new($w,$h)
    $button.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
    $button.FlatAppearance.BorderSize = 0
    $button.BackColor = $color
    $button.ForeColor = [System.Drawing.Color]::White
    $button.Font = [System.Drawing.Font]::new('Segoe UI',[single]9,[System.Drawing.FontStyle]::Bold)
    $actionCopy = $action
    $actionName = $buttonText
    $wrappedAction = {
        try { & $actionCopy }
        catch { Show-UiError $actionName $_ }
    }.GetNewClosure()
    $button.Add_Click($wrappedAction)
    [void]$parent.Controls.Add($button)
    return $button
}

# Navegacao principal visivel. Nao dependemos das abas nativas do TabControl,
# pois em algumas versoes do Windows Server a faixa de abas pode ficar escondida
# atras do cabecalho por causa da ordem de Dock/Z-Order.
$navHome = New-Button $header 'Visão geral' 330 23 120 36 ([System.Drawing.Color]::FromArgb(43,55,78)) { $tabs.SelectedTab = $tabHome }
$navCfg = New-Button $header 'Configurações' 460 23 140 36 $Theme.Accent { $tabs.SelectedTab = $tabCfg }
$navLogs = New-Button $header 'Logs' 610 23 90 36 ([System.Drawing.Color]::FromArgb(43,55,78)) { $tabs.SelectedTab = $tabLogs }
$navBackup = New-Button $header 'Backups' 710 23 105 36 ([System.Drawing.Color]::FromArgb(43,55,78)) { $tabs.SelectedTab = $tabBackup }

# Atalho adicional: F2 sempre abre Configuracoes, mesmo que a faixa de abas nativa
# nao esteja visivel por tema/escala do Windows.
$form.KeyPreview = $true
$form.Add_KeyDown({
    try {
        if ($_.KeyCode -eq [System.Windows.Forms.Keys]::F2) { $tabs.SelectedTab = $tabCfg }
    } catch { Show-UiError 'Navegacao' $_ }
})

function New-Card($parent,[int]$x,[int]$y,[int]$w,[int]$h){
    $panel = New-Object System.Windows.Forms.Panel
    $panel.Location = [System.Drawing.Point]::new($x,$y)
    $panel.Size = [System.Drawing.Size]::new($w,$h)
    $panel.BackColor = $Theme.Card
    [void]$parent.Controls.Add($panel)
    return $panel
}

function Status-Line($parent,[string]$labelText,[int]$y){
    $dot = New-Object System.Windows.Forms.Label
    $dot.Text = '●'
    $dot.AutoSize = $true
    $dot.Location = [System.Drawing.Point]::new(18,$y)
    $dot.ForeColor = $Theme.Muted
    [void]$parent.Controls.Add($dot)

    $label = New-Object System.Windows.Forms.Label
    $label.Text = $labelText
    $label.AutoSize = $true
    $label.Location = [System.Drawing.Point]::new(43,($y + 1))
    $label.ForeColor = $Theme.Text
    [void]$parent.Controls.Add($label)
    return @($dot,$label)
}

$cardStatus=New-Card $tabHome 18 18 510 245
$h=New-Object System.Windows.Forms.Label;$h.Text='STATUS DO SISTEMA';$h.Font=[System.Drawing.Font]::new('Segoe UI',[single]11,[System.Drawing.FontStyle]::Bold);$h.AutoSize=$true;$h.Location=[System.Drawing.Point]::new(18,16);$h.ForeColor=$Theme.Text;$cardStatus.Controls.Add($h)
$stSupervisor=Status-Line $cardStatus 'Supervisor' 55;$stWeb=Status-Line $cardStatus 'Painel web' 85;$stWorker=Status-Line $cardStatus 'Worker de ofertas' 115;$stReader=Status-Line $cardStatus 'Radar Telegram' 145;$stDb=Status-Line $cardStatus 'Banco local' 175;$stSession=Status-Line $cardStatus 'Sessão Telegram' 205

$cardControl=New-Card $tabHome 548 18 520 245
$hh=New-Object System.Windows.Forms.Label;$hh.Text='CONTROLES';$hh.Font=[System.Drawing.Font]::new('Segoe UI',[single]11,[System.Drawing.FontStyle]::Bold);$hh.AutoSize=$true;$hh.Location=[System.Drawing.Point]::new(18,16);$hh.ForeColor=$Theme.Text;$cardControl.Controls.Add($hh)
New-Button $cardControl '▶  Iniciar tudo' 18 52 150 42 $Theme.Accent {Start-Runtime} | Out-Null
New-Button $cardControl '■  Parar' 182 52 120 42 ([System.Drawing.Color]::FromArgb(91,47,56)) {Stop-Runtime} | Out-Null
New-Button $cardControl '↻  Reiniciar' 316 52 145 42 $Theme.Blue {Restart-Runtime} | Out-Null
New-Button $cardControl '🌐  Abrir painel' 18 108 180 42 ([System.Drawing.Color]::FromArgb(34,72,58)) {Open-Dashboard} | Out-Null
New-Button $cardControl '⚙  Instalar / Atualizar' 214 108 165 42 ([System.Drawing.Color]::FromArgb(43,55,78)) {Run-Installer} | Out-Null
New-Button $cardControl '✓  Diagnóstico' 393 108 110 42 $Theme.Blue {Run-Diagnostics} | Out-Null
$auto=New-Object System.Windows.Forms.CheckBox;$auto.Text='Iniciar o robô automaticamente com o Windows';$auto.AutoSize=$true;$auto.Location=[System.Drawing.Point]::new(20,174);$auto.ForeColor=$Theme.Text;$auto.BackColor=$Theme.Card;$auto.Add_CheckedChanged({try{if($script:loadingAuto){return};Set-Autostart $auto.Checked}catch{Show-UiError 'Inicialização automática' $_}});$cardControl.Controls.Add($auto)
$installInfo=New-Object System.Windows.Forms.Label;$installInfo.Text='';$installInfo.AutoSize=$true;$installInfo.ForeColor=$Theme.Muted;$installInfo.Location=[System.Drawing.Point]::new(20,205);$cardControl.Controls.Add($installInfo)

$cardTips=New-Card $tabHome 18 280 1050 280
$th=New-Object System.Windows.Forms.Label;$th.Text='COMO USAR';$th.Font=[System.Drawing.Font]::new('Segoe UI',[single]11,[System.Drawing.FontStyle]::Bold);$th.AutoSize=$true;$th.Location=[System.Drawing.Point]::new(18,16);$cardTips.Controls.Add($th)
$tip=New-Object System.Windows.Forms.Label;$tip.Text="1. Clique em Instalar / Atualizar uma única vez.`r`n`r`n2. Clique no botão Configurações no topo (ou pressione F2), informe usuário/senha, Shopee e Telegram e clique em Salvar.`r`n`r`n3. Clique em Conectar conta leitora para receber o código do Telegram em uma janela visual.`r`n`r`n4. Volte aqui e clique em Iniciar tudo. Depois use Abrir painel para gerenciar ofertas, fontes, scores e conversões.`r`n`r`n5. Se algo ficar vermelho, use Diagnóstico. Ative a inicialização automática depois que tudo estiver OK.";$tip.AutoSize=$false;$tip.Size=[System.Drawing.Size]::new(990,220);$tip.Location=[System.Drawing.Point]::new(22,52);$tip.ForeColor=$Theme.Muted;$tip.Font=[System.Drawing.Font]::new('Segoe UI',[single]10);$cardTips.Controls.Add($tip)
$statusBar=New-Object System.Windows.Forms.Label;$statusBar.Text='Pronto.';$statusBar.Dock='Bottom';$statusBar.Height=30;$statusBar.BackColor=$Theme.Card;$statusBar.ForeColor=$Theme.Muted;$statusBar.Padding=[System.Windows.Forms.Padding]::new(12,6,0,0);$tabHome.Controls.Add($statusBar)
function Set-Status([string]$statusText,$color){
    $statusBar.Text = $statusText
    $statusBar.ForeColor = $color
    [System.Windows.Forms.Application]::DoEvents()
}

# Configuration page
$cfgPanel=New-Object System.Windows.Forms.Panel;$cfgPanel.Dock='Fill';$cfgPanel.AutoScroll=$true;$cfgPanel.BackColor=$Theme.Bg;$tabCfg.Controls.Add($cfgPanel)
$fields=@{}
function Add-Field([string]$labelText,[string]$key,[int]$x,[int]$y,[int]$w=470,[bool]$secret=$false){
    $label = New-Object System.Windows.Forms.Label
    $label.Text = $labelText
    $label.ForeColor = $Theme.Muted
    $label.AutoSize = $true
    $label.Location = [System.Drawing.Point]::new($x,$y)
    [void]$cfgPanel.Controls.Add($label)

    $textbox = New-Object System.Windows.Forms.TextBox
    $textbox.Name = $key
    $textbox.Location = [System.Drawing.Point]::new($x,($y + 21))
    $textbox.Size = [System.Drawing.Size]::new($w,31)
    $textbox.BackColor = $Theme.Input
    $textbox.ForeColor = $Theme.Text
    $textbox.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
    $textbox.UseSystemPasswordChar = $secret
    [void]$cfgPanel.Controls.Add($textbox)
    $fields[$key] = $textbox
    return $textbox
}
$sec1=New-Object System.Windows.Forms.Label;$sec1.Text='ACESSO AO PAINEL';$sec1.Font=[System.Drawing.Font]::new('Segoe UI',[single]11,[System.Drawing.FontStyle]::Bold);$sec1.Location=[System.Drawing.Point]::new(22,20);$sec1.AutoSize=$true;$cfgPanel.Controls.Add($sec1)
Add-Field 'Usuário do painel' 'ADMIN_USER' 22 52 470 $false|Out-Null;Add-Field 'Senha do painel' 'ADMIN_PASSWORD' 530 52 470 $true|Out-Null
$gen=New-Button $cfgPanel 'Gerar senha forte' 830 111 170 34 ([System.Drawing.Color]::FromArgb(43,55,78)) {$fields['ADMIN_PASSWORD'].Text=Random-Password} 
$show=New-Object System.Windows.Forms.CheckBox;$show.Text='Mostrar senhas/segredos';$show.ForeColor=$Theme.Muted;$show.BackColor=$Theme.Bg;$show.AutoSize=$true;$show.Location=[System.Drawing.Point]::new(530,119);$show.Add_CheckedChanged({try{foreach($k in @('ADMIN_PASSWORD','SHOPEE_SECRET','TELEGRAM_BOT_TOKEN','TELEGRAM_API_HASH')){if($fields.ContainsKey($k)){$fields[$k].UseSystemPasswordChar=-not $show.Checked}}}catch{Show-UiError 'Mostrar senhas/segredos' $_}});$cfgPanel.Controls.Add($show)
$sec2=New-Object System.Windows.Forms.Label;$sec2.Text='SHOPEE AFFILIATE';$sec2.Font=[System.Drawing.Font]::new('Segoe UI',[single]11,[System.Drawing.FontStyle]::Bold);$sec2.Location=[System.Drawing.Point]::new(22,168);$sec2.AutoSize=$true;$cfgPanel.Controls.Add($sec2)
Add-Field 'App ID' 'SHOPEE_APP_ID' 22 200 470 $false|Out-Null;Add-Field 'Secret' 'SHOPEE_SECRET' 530 200 470 $true|Out-Null
$sec3=New-Object System.Windows.Forms.Label;$sec3.Text='TELEGRAM · PUBLICAÇÃO';$sec3.Font=[System.Drawing.Font]::new('Segoe UI',[single]11,[System.Drawing.FontStyle]::Bold);$sec3.Location=[System.Drawing.Point]::new(22,290);$sec3.AutoSize=$true;$cfgPanel.Controls.Add($sec3)
Add-Field 'Token do BotFather' 'TELEGRAM_BOT_TOKEN' 22 322 470 $true|Out-Null;Add-Field 'Canal/grupo de destino (ex.: @meucanal)' 'TELEGRAM_TARGET_CHAT' 530 322 470 $false|Out-Null;Add-Field 'Chat administrativo para alertas (opcional)' 'TELEGRAM_ADMIN_CHAT' 22 393 470 $false|Out-Null
$sec4=New-Object System.Windows.Forms.Label;$sec4.Text='TELEGRAM · CONTA LEITORA';$sec4.Font=[System.Drawing.Font]::new('Segoe UI',[single]11,[System.Drawing.FontStyle]::Bold);$sec4.Location=[System.Drawing.Point]::new(22,484);$sec4.AutoSize=$true;$cfgPanel.Controls.Add($sec4)
Add-Field 'API ID (my.telegram.org)' 'TELEGRAM_API_ID' 22 516 300 $false|Out-Null;Add-Field 'API Hash' 'TELEGRAM_API_HASH' 340 516 390 $true|Out-Null;Add-Field 'Telefone com DDI (+55...)' 'TELEGRAM_PHONE' 748 516 252 $false|Out-Null
$reader=New-Object System.Windows.Forms.CheckBox;$reader.Text='Ativar Radar Telegram';$reader.ForeColor=$Theme.Text;$reader.BackColor=$Theme.Bg;$reader.AutoSize=$true;$reader.Location=[System.Drawing.Point]::new(22,586);$cfgPanel.Controls.Add($reader)
New-Button $cfgPanel '💾  Salvar configuração' 22 628 220 42 $Theme.Accent {Save-Config $true} | Out-Null
New-Button $cfgPanel '📡  Conectar conta leitora' 258 628 220 42 $Theme.Blue {Connect-Reader} | Out-Null
New-Button $cfgPanel 'Testar Shopee' 494 628 160 42 ([System.Drawing.Color]::FromArgb(34,72,58)) {Test-Integration 'shopee'} | Out-Null
New-Button $cfgPanel 'Testar Bot' 670 628 160 42 ([System.Drawing.Color]::FromArgb(34,72,58)) {Test-Integration 'telegram'} | Out-Null
$cfgHint=New-Object System.Windows.Forms.Label;$cfgHint.Text='As chaves ficam somente no arquivo local da VPS. A Central não exibe seus segredos no painel web.';$cfgHint.ForeColor=$Theme.Muted;$cfgHint.AutoSize=$true;$cfgHint.Location=[System.Drawing.Point]::new(22,690);$cfgPanel.Controls.Add($cfgHint)
function Load-Config {$e=Read-Env;foreach($k in $fields.Keys){$fields[$k].Text=if($e.ContainsKey($k)){$e[$k]}else{''}};$reader.Checked=($e['TELEGRAM_READER_ENABLED'] -ne 'false')}
function Save-Config([bool]$notify=$true){
    $u=@{};foreach($k in $fields.Keys){$u[$k]=$fields[$k].Text.Trim()};$existing=Read-Env;if(-not $existing.ContainsKey('APP_SESSION_SECRET') -or [string]::IsNullOrWhiteSpace($existing['APP_SESSION_SECRET'])){$u['APP_SESSION_SECRET']=(Random-Password)+(Random-Password)};$u['COOKIE_SECURE']='false';$u['PUBLIC_BASE_URL']='';$u['TELEGRAM_READER_ENABLED']=if($reader.Checked){'true'}else{'false'};$u['APP_ENV']='windows';$u['APP_HOST']='127.0.0.1';$u['APP_REQUIRE_AUTH']='true';$u['DATABASE_URL']='sqlite:///./data/windows/deals.db';$u['REDIS_URL']='';$u['REDIS_REQUIRED']='false';Write-Env $u
    if($notify){Set-Status 'Configuração salva ✅' $Theme.Green;if(Runtime-Running){Restart-Runtime};[System.Windows.Forms.MessageBox]::Show('Configuração salva. Se o robô estava ligado, ele foi reiniciado para aplicar as alterações.','Configuração','OK','Information')|Out-Null}
}

# Logs
$logTop=New-Object System.Windows.Forms.Panel;$logTop.Dock='Top';$logTop.Height=55;$logTop.BackColor=$Theme.Bg;$tabLogs.Controls.Add($logTop)
$logSelect=New-Object System.Windows.Forms.ComboBox;$logSelect.Items.AddRange(@('supervisor.log','web.log','worker.log','listener.log'));$logSelect.SelectedIndex=1;$logSelect.DropDownStyle='DropDownList';$logSelect.Location=[System.Drawing.Point]::new(18,15);$logSelect.Width=220;$logTop.Controls.Add($logSelect)
New-Button $logTop 'Atualizar' 255 11 120 34 $Theme.Blue {Refresh-Logs}|Out-Null
$logBox=New-Object System.Windows.Forms.RichTextBox;$logBox.Dock='Fill';$logBox.BackColor=[System.Drawing.Color]::FromArgb(7,10,16);$logBox.ForeColor=[System.Drawing.Color]::FromArgb(189,203,225);$logBox.Font=[System.Drawing.Font]::new('Consolas',[single]9);$logBox.ReadOnly=$true;$tabLogs.Controls.Add($logBox);$logBox.BringToFront()
function Refresh-Logs {$p=Join-Path $LogsDir $logSelect.SelectedItem;if(Test-Path $p){$lines=Get-Content $p -Tail 250 -ErrorAction SilentlyContinue;$logBox.Text=($lines -join "`r`n");$logBox.SelectionStart=$logBox.TextLength;$logBox.ScrollToCaret()}else{$logBox.Text='Ainda não há log para este componente.'}}
$logSelect.Add_SelectedIndexChanged({try{Refresh-Logs}catch{Show-UiError 'Atualizar logs' $_}})

# Backup
$bkCard=New-Card $tabBackup 18 18 1045 520
$bh=New-Object System.Windows.Forms.Label;$bh.Text='BACKUPS LOCAIS';$bh.Font=[System.Drawing.Font]::new('Segoe UI',[single]11,[System.Drawing.FontStyle]::Bold);$bh.AutoSize=$true;$bh.Location=[System.Drawing.Point]::new(18,16);$bkCard.Controls.Add($bh)
New-Button $bkCard 'Criar backup agora' 18 52 190 40 $Theme.Accent {Create-Backup}|Out-Null;New-Button $bkCard 'Restaurar backup…' 222 52 190 40 $Theme.Blue {Restore-Backup}|Out-Null
$bkInfo=New-Object System.Windows.Forms.Label;$bkInfo.Text='Backups automáticos também são criados pelo supervisor enquanto o robô está ligado.';$bkInfo.ForeColor=$Theme.Muted;$bkInfo.AutoSize=$true;$bkInfo.Location=[System.Drawing.Point]::new(430,65);$bkCard.Controls.Add($bkInfo)
$bkList=New-Object System.Windows.Forms.ListView;$bkList.Location=[System.Drawing.Point]::new(18,112);$bkList.Size=[System.Drawing.Size]::new(1000,375);$bkList.View='Details';$bkList.FullRowSelect=$true;$bkList.BackColor=$Theme.Input;$bkList.ForeColor=$Theme.Text;[void]$bkList.Columns.Add('Arquivo',640);[void]$bkList.Columns.Add('Data',190);[void]$bkList.Columns.Add('Tamanho',130);$bkCard.Controls.Add($bkList)
function Refresh-Backups {$bkList.Items.Clear();Get-ChildItem (Join-Path $Root 'backups') -Filter '*.db' -ErrorAction SilentlyContinue|Sort-Object LastWriteTime -Descending|ForEach-Object{$i=[System.Windows.Forms.ListViewItem]::new([string]$_.Name);[void]$i.SubItems.Add($_.LastWriteTime.ToString('dd/MM/yyyy HH:mm'));[void]$i.SubItems.Add(('{0:N1} MB' -f ($_.Length/1MB)));[void]$bkList.Items.Add($i)}}

function Refresh-Autostart {$script:loadingAuto=$true;$auto.Checked=Autostart-Enabled;$script:loadingAuto=$false}
function Set-Dot($pair,[bool]$ok,[string]$detail=''){$pair[0].ForeColor=if($ok){$Theme.Green}else{$Theme.Red};if($detail){$pair[1].Text=$detail}}
function Refresh-Status {
    $run=Runtime-Running;Set-Dot $stSupervisor $run 'Supervisor'
    $comp=@{};if(Test-Path $StateFile){try{$j=Get-Content $StateFile -Raw|ConvertFrom-Json;foreach($p in $j.components.PSObject.Properties){$comp[$p.Name]=$p.Value}}catch{}}
    Set-Dot $stWeb ([bool]($comp['web'] -and $comp['web'].running)) 'Painel web';Set-Dot $stWorker ([bool]($comp['worker'] -and $comp['worker'].running)) 'Worker de ofertas';Set-Dot $stReader ([bool]($comp['listener'] -and $comp['listener'].running)) 'Radar Telegram'
    $db=Test-Path (Join-Path $Root 'data\windows\deals.db');Set-Dot $stDb $db 'Banco local (SQLite)'
    $sess=(Test-Path (Join-Path $Root 'data\telegram\reader.authorized'));Set-Dot $stSession $sess 'Sessão Telegram'
    $statusTop.Text=if($run){'● ROBÔ ONLINE'}else{'● ROBÔ PARADO'};$statusTop.ForeColor=if($run){$Theme.Green}else{$Theme.Red}
    $py=Get-Python;$installInfo.Text=if($py){'Ambiente instalado'}else{'Ambiente ainda não instalado'};$installInfo.ForeColor=if($py){$Theme.Green}else{$Theme.Muted}
}
function Refresh-All {Load-Config;Refresh-Status;Refresh-Autostart;Refresh-Backups;Refresh-Logs}
$timer=New-Object System.Windows.Forms.Timer;$timer.Interval=3500;$timer.Add_Tick({try{Refresh-Status}catch{}});$timer.Start()
$form.Add_Shown({try{Refresh-All}catch{Show-UiError 'Inicialização da interface' $_}})
$form.Add_FormClosed({try{$timer.Stop()}catch{}})
[void]$form.ShowDialog()

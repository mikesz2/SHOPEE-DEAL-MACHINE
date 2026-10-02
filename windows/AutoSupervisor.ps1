$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUNBUFFERED = '1'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
$RuntimeDir = Join-Path $Root 'data\runtime'
$LogsDir = Join-Path $Root 'logs'
New-Item -ItemType Directory -Force -Path $RuntimeDir,$LogsDir | Out-Null
$PythonFile = Join-Path $RuntimeDir 'python_path.txt'
$SelfHeal = Join-Path $ScriptDir 'self_heal.py'
$Supervisor = Join-Path $ScriptDir 'supervisor.py'
$Log = Join-Path $LogsDir 'autostart.log'
function Log([string]$m){ try{ Add-Content -Path $Log -Value ("[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'),$m) -Encoding UTF8 }catch{} }
function Find-Python {
    $c=@()
    if(Test-Path $PythonFile){try{$c+=(Get-Content $PythonFile -Raw).Trim()}catch{}}
    $c+=(Join-Path $env:ProgramData 'ShopeeDealMachine\Python312\python.exe')
    if($env:LOCALAPPDATA){$c+=(Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe')}
    if($env:ProgramFiles){$c+=(Join-Path $env:ProgramFiles 'Python312\python.exe')}
    foreach($p in $c){if($p -and (Test-Path -LiteralPath $p -PathType Leaf)){return $p}}
    return $null
}
try{
    $py=Find-Python
    if(-not $py){Log 'Python não encontrado'; exit 2}
    Log ("Python: " + $py)
    & $py $SelfHeal *>> $Log
    if($LASTEXITCODE -ne 0){Log ("self_heal falhou: " + $LASTEXITCODE); exit $LASTEXITCODE}
    Log 'Iniciando supervisor em primeiro plano.'
    & $py $Supervisor *>> $Log
    $code=$LASTEXITCODE
    Log ("Supervisor encerrou com código " + $code)
    exit $code
}catch{
    Log ("FATAL: " + $_.Exception.Message)
    exit 1
}

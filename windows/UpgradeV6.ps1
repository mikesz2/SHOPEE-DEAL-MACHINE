$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$source = Split-Path $PSScriptRoot -Parent
try {
    [System.Windows.Forms.MessageBox]::Show('Na Central Windows, pare os servicos antes de continuar. Selecione a pasta da instalacao atual. O atualizador preserva dados, credenciais e sessoes, e cria um backup do painel anterior.', 'Atualizar painel V6', 'OK', 'Information') | Out-Null
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = 'Selecione a pasta atual do Shopee Deal Machine (a que contem app e windows).'
    if ($dialog.ShowDialog() -ne 'OK') { exit 0 }
    $target = $dialog.SelectedPath
    if ([IO.Path]::GetFullPath($target).TrimEnd('\') -eq [IO.Path]::GetFullPath($source).TrimEnd('\')) { throw 'Selecione a instalacao anterior, nao a pasta deste pacote novo.' }
    if (-not (Test-Path (Join-Path $target 'app\main.py'))) { throw 'Pasta invalida: app\main.py nao encontrado.' }
    $entry = Get-Content (Join-Path $target 'app\main.py') -Raw
    if (-not $entry.Contains('/api/dashboard') -or -not $entry.Contains('/api/offers/bulk')) { throw 'Este atualizador exige a base Enterprise V5. Para instalacao mais antiga, use o pacote completo e o guia V6.' }
    $backup = Join-Path $target ('backups\painel-pre-v6-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    Copy-Item (Join-Path $target 'app\static') (Join-Path $backup 'static') -Recurse -Force
    $static = Join-Path $target 'app\static'
    foreach ($name in @('index.html','app.css','app.js','command-center.js','login.html','inter-latin.woff2','FONT-LICENSE.txt')) {
        Copy-Item (Join-Path $source ('app\static\' + $name)) (Join-Path $static $name) -Force
    }
    [System.Windows.Forms.MessageBox]::Show("Painel V6 instalado. Reinicie os servicos na Central Windows e abra o painel. Se o visual anterior persistir, pressione Ctrl+F5. Backup: $backup", 'Atualizacao concluida', 'OK', 'Information') | Out-Null
} catch {
    Write-Error $_ -ErrorAction Continue
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'Atualizacao nao concluida', 'OK', 'Error') | Out-Null
    exit 1
}

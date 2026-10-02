@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Deal Machine - Atualizar painel V6
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0windows\UpgradeV6.ps1"
if errorlevel 1 (
  echo A atualizacao nao foi concluida. Veja o erro acima.
  pause
)

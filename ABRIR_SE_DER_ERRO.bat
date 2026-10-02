@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Shopee Deal Machine - Diagnostico

echo ============================================================
echo  SHOPEE DEAL MACHINE - DIAGNOSTICO DE INICIALIZACAO
 echo ============================================================
echo Esta janela NAO fecha sozinha.
echo.
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0windows\Launcher.ps1"
echo.
echo ------------------------------------------------------------
echo Codigo de saida: %ERRORLEVEL%
echo Log: %~dp0logs\central_startup_error.txt
echo ------------------------------------------------------------
pause

@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Shopee Deal Machine - Iniciar robo / Diagnostico
echo ============================================================
echo  SHOPEE DEAL MACHINE - INICIAR ROBO / DIAGNOSTICO
echo ============================================================
echo Esta janela NAO fecha sozinha se ocorrer erro.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\StartRobot.ps1"
set "SDM_EXIT=%ERRORLEVEL%"
echo.
echo ------------------------------------------------------------
echo Codigo de saida: %SDM_EXIT%
echo Log de erro: %~dp0logs\start_robot_error.txt
echo ------------------------------------------------------------
pause
exit /b %SDM_EXIT%

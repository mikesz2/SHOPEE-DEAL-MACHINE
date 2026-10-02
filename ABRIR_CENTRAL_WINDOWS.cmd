@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Shopee Deal Machine - Central Windows

echo ============================================================
echo  SHOPEE DEAL MACHINE - CENTRAL WINDOWS V4.0
echo ============================================================
echo Esta janela pode ficar aberta atras da interface.
echo Se houver qualquer erro, ela NAO vai fechar sozinha.
echo.

powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0windows\Launcher.ps1"
set "SDM_EXIT=%ERRORLEVEL%"

if not "%SDM_EXIT%"=="0" (
    echo.
    echo ============================================================
    echo  A CENTRAL TERMINOU COM ERRO - codigo %SDM_EXIT%
    echo ============================================================
    echo O erro completo esta acima e tambem em:
    echo %~dp0logs\central_startup_error.txt
    echo.
    echo Esta janela ficara aberta. Tire um print se precisar.
    pause
)

exit /b %SDM_EXIT%

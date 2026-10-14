@echo off
title Sistema Marmoraria Marmobraz - Calculadora & Gestao
echo ========================================================
echo   SISTEMA DE GESTAO E ORCAMENTOS - MARMORARIA MARMOBRAZ
echo ========================================================
echo.
echo Abrindo o sistema no seu navegador padrao...
echo.

set "INDEX_PATH=%~dp0index.html"
if exist "%INDEX_PATH%" (
    start "" "%INDEX_PATH%"
) else (
    start "" "%~dp0frontend\index.html"
)

exit /b 0

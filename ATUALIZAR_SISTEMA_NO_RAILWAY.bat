@echo off
title Atualizar Sistema no Railway (MN)
color 0B
cd /d "%~dp0"

echo ======================================================================
echo       ATUALIZAR SISTEMA NO RAILWAY - PROJETO MN (NUVEM)
echo ======================================================================
echo.
echo Enviando alteracoes do codigo diretamente para o Railway...
echo.

railway up --detach

echo.
echo ======================================================================
echo  ATUALIZACAO ENVIADA COM SUCESSO!
echo ======================================================================
echo.
echo O Railway esta aplicando as mudancas na nuvem.
echo Em cerca de 1 minuto a versao atualizada estara ativa em:
echo https://marmoraria-saas-production.up.railway.app
echo.
timeout /t 5 >nul
exit /b 0

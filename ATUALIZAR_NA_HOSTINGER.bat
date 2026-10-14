@echo off
title Atualizar Sistema na Hostinger VPS
color 0A
cd /d "%~dp0"

echo ======================================================================
echo       ATUALIZAR SISTEMA NA HOSTINGER VPS (179.236.78.80)
echo ======================================================================
echo.
echo 1. Enviando alteracoes locais para o GitHub...
git push origin main

echo.
echo 2. Atualizando e reiniciando a aplicacao no servidor Hostinger...
ssh root@179.236.78.80 "cd /opt/marmoraria-saas && git pull origin main && docker compose up -d --build"

echo.
echo ======================================================================
echo  ATUALIZACAO CONCLUIDA COM SUCESSO!
echo  Acesse: http://179.236.78.80
echo ======================================================================
echo.
pause

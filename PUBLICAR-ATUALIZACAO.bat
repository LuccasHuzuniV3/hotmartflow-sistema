@echo off
chcp 65001 >nul
title Publicar atualizacao do HotmartFlow
cd /d "%~dp0"
echo.
echo  ================================================
echo    Publicando a ultima versao no GitHub...
echo  ================================================
echo.

where git >nul 2>nul
if errorlevel 1 ( echo  [ERRO] Git nao instalado. Rode o CONFIGURAR-SISTEMA-GIT.bat antes. & pause & exit /b )

.venv\Scripts\python.exe tools\make_manifest.py
if errorlevel 1 ( python tools\make_manifest.py )

git add -A
git commit -m "atualizacao do sistema"
git push

echo.
echo  ------------------------------------------------------------
echo   Pronto! Agora o operador pode clicar em "Atualizar" na aba
echo   Config do painel que ele baixa essa versao.
echo  ------------------------------------------------------------
echo.
pause

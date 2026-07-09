@echo off
chcp 65001 >nul
title Configurar atualizacoes (GitHub) - SO nesta pasta
cd /d "%~dp0"
echo.
echo  ==============================================================
echo    CONFIGURAR ATUALIZACOES AUTOMATICAS (GitHub) - HotmartFlow
echo  ==============================================================
echo.
echo  IMPORTANTE: use a conta GitHub dos projetos de ebook (NAO a do
echo  trabalho). Este script mexe SO nesta pasta e NAO toca na conta
echo  git do resto do PC.
echo.

where git >nul 2>nul
if errorlevel 1 (
  echo  [ATENCAO] O Git nao esta instalado.
  echo    1^) Baixe e instale: https://git-scm.com/download/win
  echo    2^) Depois rode este arquivo de novo.
  echo.
  pause
  exit /b
)

echo  Voce vai precisar de 3 coisas (da conta do ebook):
echo    - usuario do GitHub
echo    - nome do repositorio PUBLICO (crie um vazio antes, ex: hotmartflow-sistema)
echo    - um token (Settings ^> Developer settings ^> Tokens ^> generate)
echo.
set /p GUSER=Usuario do GitHub:
set /p GREPO=Nome do repositorio:
set /p GTOKEN=Token (cole e de Enter):
echo.
echo  Configurando SO nesta pasta...

git init
git branch -M main
git config --local user.name "%GUSER%"
git config --local user.email "%GUSER%@users.noreply.github.com"
git remote remove origin 2>nul
git remote add origin https://%GTOKEN%@github.com/%GUSER%/%GREPO%.git

REM grava o sys-config.json apontando pro raw do GitHub
> sys-config.json echo {
>> sys-config.json echo   "rawBase": "https://raw.githubusercontent.com/%GUSER%/%GREPO%/main"
>> sys-config.json echo }

.venv\Scripts\python.exe tools\make_manifest.py
if errorlevel 1 ( python tools\make_manifest.py )

git add -A
git commit -m "primeira versao do sistema"
git push -u origin main --force

echo.
echo  ------------------------------------------------------------
echo   Se NAO apareceu erro de push, deu certo!
echo   - Daqui pra frente: edite e rode PUBLICAR-ATUALIZACAO.bat
echo   - O operador clica "Atualizar" na aba Config do painel
echo  ------------------------------------------------------------
echo.
pause

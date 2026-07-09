@echo off
chcp 65001 >nul
title Gerar pacote para o operador
cd /d "%~dp0"
echo.
echo  ================================================
echo    Gerando o pacote (zip) PRONTO para o operador
echo  ================================================
echo.
echo  Inclui: codigo do painel + start.bat + sys-config.json (link das atualizacoes).
echo  NAO inclui: .venv, dados (data/), config do operador, testes.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$src=(Get-Location).Path; $tmp=Join-Path $env:TEMP ('hf_'+[System.IO.Path]::GetRandomFileName()); $dst=Join-Path $tmp 'HotmartFlow'; New-Item -ItemType Directory -Path $dst -Force | Out-Null; $inc=@('start.bat','requirements.txt','README.md','version.json','sys-config.json','manifest.json','app','core'); foreach($i in $inc){ $p=Join-Path $src $i; if(Test-Path $p){ Copy-Item $p (Join-Path $dst $i) -Recurse -Force } }; Get-ChildItem -Path $dst -Recurse -Directory -Include '__pycache__','.pytest_cache' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue; $out=Join-Path $src 'PACOTE-OPERADOR.zip'; if(Test-Path $out){Remove-Item $out -Force}; Compress-Archive -Path $dst -DestinationPath $out -Force; Remove-Item $tmp -Recurse -Force; Write-Host ('OK -> ' + $out)"
echo.
echo  ------------------------------------------------
echo   Pronto! Foi criado:  PACOTE-OPERADOR.zip
echo   Manda esse .zip pro operador (so na primeira vez).
echo   Depois, atualizacoes ele pega pelo botao "Atualizar".
echo  ------------------------------------------------
echo.
pause

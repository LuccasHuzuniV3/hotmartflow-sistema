@echo off
cd /d "%~dp0"

REM Cria venv na primeira execucao
if not exist ".venv\Scripts\python.exe" (
    echo Criando ambiente virtual...
    python -m venv .venv
    if errorlevel 1 (
        echo ERRO: python nao encontrado no PATH. Instale Python 3.10+ e tente novamente.
        pause
        exit /b 1
    )
    call .venv\Scripts\activate.bat
    echo Instalando dependencias...
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERRO: falha ao instalar dependencias. Veja o erro acima.
        pause
        exit /b 1
    )
) else (
    call .venv\Scripts\activate.bat
    REM Instala dependencias novas se o requirements mudou (ex.: playwright da Fase B)
    python -c "import playwright" >nul 2>nul
    if errorlevel 1 (
        echo Instalando dependencias novas...
        python -m pip install -r requirements.txt
    )
)

REM Roda o agy via WSL (contorna bug do agy.exe nao redirecionar stdout no Windows).
REM Precisa: WSL2 + Ubuntu + agy instalado e autenticado dentro do Ubuntu (igual EbookFlow).
REM Pra desativar (agy Windows nativo), comente a linha abaixo com REM.
set HOTMARTFLOW_USE_WSL=1

REM 2 CONTAS EM PARALELO: a porta do Chrome agora fica na aba CONFIG do painel
REM (campo "Porta do Chrome"), NAO aqui — assim o botao Atualizar nao apaga.
REM Na 1a copia deixe 9222; na 2a copia coloque 9223 na Config.

echo.
echo Iniciando HotmartFlow...
python -m app.launcher
if errorlevel 1 (
    echo.
    echo ===========================================
    echo ERRO: o app fechou com erro. Veja acima.
    echo ===========================================
    pause
)

@echo off
REM Lanzador integral de la app Streamlit forzando Python 3.12
setlocal

cd /d "%~dp0"

REM Verificar disponibilidad de Python 3.12 mediante el launcher
for /f "tokens=2" %%A in ('py -3.12 -V 2^>nul') do set "TARGET_VER=%%A"
if not defined TARGET_VER (
    echo No se encontro Python 3.12 instalado. Instala Python 3.12 desde https://www.python.org/downloads/ y vuelve a intentarlo.
    pause
    exit /b 1
)
for /f "tokens=1-3 delims=." %%A in ("%TARGET_VER%") do (
    set "TARGET_MAJOR=%%A"
    set "TARGET_MINOR=%%B"
)
if "%TARGET_MAJOR%" NEQ "3" (
    echo Se detecto una version de Python inesperada: %TARGET_VER%. Instala Python 3.12.
    pause
    exit /b 1
)
if "%TARGET_MINOR%" NEQ "12" (
    echo El launcher esta resolviendo a Python %TARGET_VER%. Instala Python 3.12 y vuelve a ejecutarlo.
    pause
    exit /b 1
)

set "VENV_DIR=%~dp0venv"
set "VENV_CFG=%VENV_DIR%\pyvenv.cfg"
set "RECREATE_VENV=0"

if not exist "%VENV_DIR%\Scripts\python.exe" (
    set "RECREATE_VENV=1"
) else (
    for /f "tokens=2 delims==" %%A in ('findstr /b "version" "%VENV_CFG%" 2^>nul') do set "VENV_VERSION_RAW=%%A"
    for /f "tokens=* delims= " %%A in ("%VENV_VERSION_RAW%") do set "VENV_VERSION=%%A"
    set "VENV_PREFIX=%VENV_VERSION:~0,4%"
    if /I not "%VENV_PREFIX%"=="3.12" if /I not "%VENV_PREFIX%"=="3.11" (
        set "RECREATE_VENV=1"
    )
)

if "%RECREATE_VENV%"=="1" (
    echo Creando entorno virtual con Python 3.12...
    if exist "%VENV_DIR%" (
        rmdir /s /q "%VENV_DIR%" 2>nul
    )
    py -3.12 -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo No se pudo crear el entorno virtual con Python 3.12.
        pause
        exit /b 1
    )
)

call "%VENV_DIR%\Scripts\activate.bat"

python --version

REM Comprobar si streamlit esta disponible en el entorno
python -m streamlit --version >nul 2>&1
if errorlevel 1 (
    echo Instalando dependencias desde requirements.txt...
    python -m pip install --upgrade pip >nul 2>&1
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo No se pudieron instalar las dependencias. Revisa los mensajes anteriores.
        pause
        exit /b 1
    )
)

REM Verificacion final
python -m streamlit --version >nul 2>&1
if errorlevel 1 (
    echo No se encontro streamlit tras la instalacion. Revisa tu entorno virtual.
    pause
    exit /b 1
)

echo Iniciando Streamlit...
python -m streamlit run streamlit_app.py

endlocal

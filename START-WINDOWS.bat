@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Sofia

echo.
echo  ==================== Sofia ====================
echo.

rem ---- 1. Find Python 3.12 or newer -------------------------------------
set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    where python >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY goto nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul
if errorlevel 1 goto nopython

rem ---- 2. Own Python environment, first time only ------------------------
if exist ".venv\Scripts\python.exe" goto haveenv
echo  Eerste keer: ik maak een eigen Python-omgeving. Even geduld...
%PY% -m venv .venv
if errorlevel 1 goto fail
:haveenv
set "VPY=.venv\Scripts\python.exe"

rem ---- 3. Install or update the building blocks --------------------------
echo  Onderdelen installeren of bijwerken. Dit kan een paar minuten duren...
"%VPY%" -m pip install --disable-pip-version-check --quiet -r requirements.txt
if errorlevel 1 goto fail

rem ---- 4. First-time questions (or forced with --setup) ---------------------
if /i "%~1"=="--setup" goto setup
if exist ".env" goto start
:setup
"%VPY%" -m app --setup
if errorlevel 1 goto fail
if not exist ".env" goto fail

rem ---- 5. Start Sofia -------------------------------------------------------
:start
echo.
echo  Sofia start nu. LAAT DIT VENSTER OPEN STAAN.
echo  Venster dicht = Sofia offline. Opnieuw starten = dit bestand weer dubbelklikken.
echo.
"%VPY%" -m app
echo.
echo  Sofia is gestopt.
pause
exit /b 0

:nopython
echo  Python 3.12 of nieuwer is niet gevonden op deze computer.
echo  Ik open nu de downloadpagina. Installeer Python en dubbelklik daarna dit bestand opnieuw.
start "" "https://www.python.org/downloads/"
pause
exit /b 1

:fail
echo.
echo  Er ging iets mis. Maak een foto of screenshot van dit venster en vraag om hulp.
pause
exit /b 1

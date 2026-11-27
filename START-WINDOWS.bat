@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Sofia

echo.
echo  ==================== Sofia ====================
echo.

rem ---- 0. Started from inside the ZIP? That doesn't work. --------------------
if not exist "requirements.txt" goto notunzipped

rem ---- 0b. Remove the "downloaded from the internet" mark from all files, so
rem      Windows only shows its blue warning screen this one time. --------------
if not exist ".venv" powershell -NoProfile -Command "Get-ChildItem -LiteralPath . -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue" >nul 2>nul

rem ---- 1. Find Python 3.14, 3.13 or 3.12 (3.15 is still too new) -------------
set "PY="
for %%V in (3.14 3.13 3.12) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>nul
        if not errorlevel 1 set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys; sys.exit(0 if (3, 12) <= sys.version_info[:2] <= (3, 14) else 1)" >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY goto nopython

rem ---- 2. Own Python environment (rebuilt when missing, broken or wrong version) ----
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys, pip; sys.exit(0 if (3, 12) <= sys.version_info[:2] <= (3, 14) else 1)" >nul 2>nul || rmdir /s /q ".venv"
)
if exist ".venv\Scripts\python.exe" goto haveenv
echo  Eerste keer: ik maak een eigen Python-omgeving. Even geduld...
%PY% -m venv .venv
if errorlevel 1 goto fail
:haveenv
set "VPY=.venv\Scripts\python.exe"

rem ---- 3. Install or update the building blocks --------------------------
echo  Onderdelen installeren. De eerste keer kan dit 5 minuten duren.
echo  Je ziet dan niets gebeuren. Dat is normaal. Klik niet in dit venster.
"%VPY%" -m pip install --disable-pip-version-check --quiet -r requirements.txt
if errorlevel 1 goto fail

rem ---- 4. First-time questions (or forced with --setup) ---------------------
if /i "%~1"=="--setup" goto setup
if exist ".env" goto start
:setup
"%VPY%" -m app --setup
if errorlevel 1 goto setupfail
if not exist ".env" goto setupfail

rem ---- 5. Start Sofia -------------------------------------------------------
:start
rem Desktop shortcut "Sofia" (refreshed every start, so it always points at this folder).
set "SOFIA_DIR=%~dp0"
powershell -NoProfile -Command "$l=Join-Path ([Environment]::GetFolderPath('Desktop')) 'Sofia.lnk'; $s=(New-Object -ComObject WScript.Shell).CreateShortcut($l); $s.TargetPath=(Join-Path $env:SOFIA_DIR 'START-WINDOWS.bat'); $s.WorkingDirectory=$env:SOFIA_DIR; $s.Save()" >nul 2>nul
echo.
echo  Sofia start nu. LAAT DIT VENSTER OPEN STAAN.
echo  Venster dicht = Sofia offline. Klik niet in dit venster.
echo.
"%VPY%" -m app
echo.
echo  Sofia is gestopt.
pause
exit /b 0

:notunzipped
echo  Je hebt START-WINDOWS geopend vanuit het ZIP-bestand. Dat werkt niet.
echo  Klik met de rechtermuisknop op het ZIP-bestand en kies: Alles uitpakken... en dan: Uitpakken.
echo  Open daarna de uitgepakte map en dubbelklik daar op START-WINDOWS.
pause
exit /b 1

:nopython
echo  Python 3.14 is niet gevonden op deze computer.
echo  Let op: Python 3.15 of nieuwer werkt nog NIET met Sofia.
echo  Ik download nu Python 3.14 voor je. Open het bestand als het klaar is.
echo  Zet een vinkje bij "Add python.exe to PATH" en klik op "Install Now".
echo  Dubbelklik daarna opnieuw op START-WINDOWS.
start "" "https://www.python.org/ftp/python/3.14.7/python-3.14.7-amd64.exe"
pause
exit /b 1

:setupfail
echo.
echo  Het instellen is gestopt. Lees hierboven de regel die begint met STOP.
if /i "%~1"=="--setup" (
    echo  Doe wat daar staat. Dubbelklik daarna opnieuw op INSTELLEN-WINDOWS.
) else (
    echo  Doe wat daar staat. Dubbelklik daarna opnieuw op START-WINDOWS.
)
echo  Lukt het niet? Vraag om hulp.
pause
exit /b 1

:fail
echo.
echo  Er ging iets mis. Controleer of je internet werkt.
echo  Sluit dit venster en dubbelklik opnieuw op START-WINDOWS.
echo  Lukt het weer niet? Maak een foto van dit venster en vraag om hulp.
pause
exit /b 1

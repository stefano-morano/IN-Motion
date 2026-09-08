@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title IN-Motion

rem Double-clickable launcher for IN-Motion (Windows).
rem Finds Python 3.10+, installs requirements.txt if needed, then starts the server.

set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"
set "BACKEND=%DIR%\web\backend"
set "PORT=8080"
set "LOG=%TEMP%\inmotion.log"
set "RUNBAT=%TEMP%\inmotion_run.bat"
set "PYEXE="
set "PYLAUNCH="

echo.
echo   IN-Motion
echo.
echo ------------------------------------------------------
echo.

rem Prefer the Python launcher, then python / python3
where py >nul 2>&1 && (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PYLAUNCH=py -3"
)
if not defined PYLAUNCH (
    where python >nul 2>&1 && (
        python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PYLAUNCH=python"
    )
)
if not defined PYLAUNCH (
    where python3 >nul 2>&1 && (
        python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PYLAUNCH=python3"
    )
)

if not defined PYLAUNCH (
    echo [X] Python 3.10+ not found.
    echo     Install from https://www.python.org/downloads/
    echo     and tick "Add python.exe to PATH", then run this again.
    echo.
    pause
    exit /b 1
)

rem Resolve to a full python.exe path so start/redirect never break on "py -3"
for /f "delims=" %%P in ('!PYLAUNCH! -c "import sys; print(sys.executable)"') do set "PYEXE=%%P"
if not defined PYEXE (
    echo [X] Could not resolve Python executable.
    pause
    exit /b 1
)

for /f "delims=" %%V in ('"%PYEXE%" --version 2^>^&1') do echo [OK] %%V
echo      %PYEXE%

"%PYEXE%" -c "import uvicorn, fastapi, dotenv, anthropic" >nul 2>&1
if errorlevel 1 (
    echo [!] Installing dependencies ^(first run may take a few minutes^)...
    "%PYEXE%" -m pip install -r "%BACKEND%\requirements.txt"
    if errorlevel 1 (
        echo [X] Install failed.
        pause
        exit /b 1
    )
)
echo [OK] Dependencies ready

rem Load .env from project root (server also loads it itself)
if exist "%DIR%\.env" (
    for /f "usebackq tokens=1* delims== eol=#" %%A in ("%DIR%\.env") do (
        if not "%%A"=="" if not "%%B"=="" set "%%A=%%B"
    )
    echo [OK] .env loaded
)

rem Free the port if something is already listening
for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr /R /C:":%PORT% .*LISTENING"') do (
    echo [!] Stopping previous process on port %PORT% ^(PID %%P^)...
    taskkill /F /PID %%P >nul 2>&1
)
timeout /t 1 /nobreak >nul

echo.
echo   Starting server...
cd /d "%BACKEND%" || (
    echo [X] Cannot open "%BACKEND%"
    pause
    exit /b 1
)

if exist "%LOG%" del /f /q "%LOG%" >nul 2>&1

rem Helper .bat avoids broken quoting around "py -3" + redirects inside start
> "%RUNBAT%" (
    echo @echo off
    echo cd /d "%BACKEND%"
    echo "%PYEXE%" -m uvicorn server:app --host 127.0.0.1 --port %PORT%
)
start "IN-Motion server" /MIN cmd /c ""%RUNBAT%" >"%LOG%" 2>&1"

echo   Waiting for http://127.0.0.1:%PORT%/
set "PRONTO=0"
for /l %%I in (1,1,90) do (
    if "!PRONTO!"=="0" (
        timeout /t 1 /nobreak >nul
        <nul set /p=.
        rem Prefer curl; fall back to PowerShell if curl is missing
        set "CODE="
        where curl.exe >nul 2>&1 && (
            for /f "delims=" %%C in ('curl.exe -s -o nul -w "%%{http_code}" "http://127.0.0.1:%PORT%/" 2^>nul') do set "CODE=%%C"
        )
        if not defined CODE (
            for /f "delims=" %%C in ('powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:%PORT%/ -TimeoutSec 2).StatusCode } catch { 0 }"') do set "CODE=%%C"
        )
        if "!CODE!"=="200" set "PRONTO=1"
    )
)

echo.
if not "!PRONTO!"=="1" (
    echo [X] Server did not become ready in time.
    echo.
    echo ----- server log ^(%LOG%^) -----
    if exist "%LOG%" (
        type "%LOG%"
    ) else (
        echo ^(log file missing — the server process may not have started^)
    )
    echo --------------------------------
    echo.
    echo Tip: open Command Prompt and run:
    echo   cd /d "%BACKEND%"
    echo   "%PYEXE%" -m uvicorn server:app --host 127.0.0.1 --port %PORT%
    echo.
    pause
    exit /b 1
)

echo.
echo   [OK] Ready at http://localhost:%PORT%
echo.
timeout /t 1 /nobreak >nul
start "" "http://localhost:%PORT%"

echo ------------------------------------------------------
echo   Keep this window open during the experience.
echo   Press any key to stop the server and exit.
echo ------------------------------------------------------
echo.
pause >nul

for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr /R /C:":%PORT% .*LISTENING"') do (
    taskkill /F /PID %%P >nul 2>&1
)
echo   Stopped.
endlocal

@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title IN-Motion

rem Keep the window open if anything fails unexpectedly.
set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"
set "BACKEND=%DIR%\web\backend"
set "PORT=8080"
set "LOG=%TEMP%\inmotion.log"
set "PYFILE=%TEMP%\inmotion_pyexe.txt"
set "RUNBAT=%TEMP%\inmotion_run.bat"
set "PYEXE="

echo.
echo   IN-Motion
echo.
echo ------------------------------------------------------
echo.

rem --- find Python 3.10+ and write sys.executable to a file (avoids for /f quote bugs)
if exist "%PYFILE%" del /f /q "%PYFILE%" >nul 2>&1

where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
    if not errorlevel 1 (
        py -3 -c "import sys; open(sys.argv[1],'w',encoding='utf-8').write(sys.executable)" "%PYFILE%" >nul 2>&1
    )
)

if not exist "%PYFILE%" (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
        if not errorlevel 1 (
            python -c "import sys; open(sys.argv[1],'w',encoding='utf-8').write(sys.executable)" "%PYFILE%" >nul 2>&1
        )
    )
)

if not exist "%PYFILE%" (
    where python3 >nul 2>&1
    if not errorlevel 1 (
        python3 -c "import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
        if not errorlevel 1 (
            python3 -c "import sys; open(sys.argv[1],'w',encoding='utf-8').write(sys.executable)" "%PYFILE%" >nul 2>&1
        )
    )
)

if not exist "%PYFILE%" (
    echo [X] Python 3.10+ not found.
    echo     Install from https://www.python.org/downloads/
    echo     Enable "Add python.exe to PATH", then retry.
    echo.
    goto :end_fail
)

set /p PYEXE=<"%PYFILE%"
if not defined PYEXE (
    echo [X] Could not read Python path.
    goto :end_fail
)

echo [OK] Python:
"%PYEXE%" --version
echo      %PYEXE%
echo.

rem --- dependencies
"%PYEXE%" -c "import uvicorn, fastapi, dotenv, anthropic" >nul 2>&1
if errorlevel 1 (
    echo [!] Installing dependencies from requirements.txt ...
    echo     First run can take several minutes.
    echo.
    "%PYEXE%" -m pip install -r "%BACKEND%\requirements.txt"
    if errorlevel 1 (
        echo.
        echo [X] pip install failed.
        goto :end_fail
    )
)
echo [OK] Dependencies ready
echo.

rem --- .env
if exist "%DIR%\.env" (
    for /f "usebackq tokens=1* delims== eol=#" %%A in ("%DIR%\.env") do (
        if not "%%A"=="" if not "%%B"=="" set "%%A=%%B"
    )
    echo [OK] .env loaded
) else (
    echo [!] No .env in project root — API keys may be missing
)
echo.

rem --- free port 8080
for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    echo [!] Stopping PID %%P on port %PORT%
    taskkill /F /PID %%P >nul 2>&1
)

if not exist "%BACKEND%\server.py" (
    echo [X] server.py not found in:
    echo     %BACKEND%
    goto :end_fail
)

cd /d "%BACKEND%"
if errorlevel 1 (
    echo [X] Cannot cd to backend folder.
    goto :end_fail
)

if exist "%LOG%" del /f /q "%LOG%" >nul 2>&1

rem Write a tiny runner so quoting stays simple
(
    echo @echo off
    echo cd /d "%BACKEND%"
    echo "%PYEXE%" -m uvicorn server:app --host 127.0.0.1 --port %PORT%
) > "%RUNBAT%"

echo Starting server...
echo Log: %LOG%
echo.

start "IN-Motion server" /MIN cmd /c "call \"%RUNBAT%\" >\"%LOG%\" 2>&1"

rem --- wait until HTTP 200 (up to ~90s)
set "PRONTO=0"
echo Waiting
for /l %%I in (1,1,90) do (
    if "!PRONTO!"=="0" (
        ping -n 2 127.0.0.1 >nul
        <nul set /p=.
        set "CODE=000"
        rem PowerShell is always present on modern Windows
        for /f "delims=" %%C in ('powershell -NoProfile -Command "try{(Invoke-WebRequest -UseBasicParsing http://127.0.0.1:%PORT%/ -TimeoutSec 1).StatusCode}catch{'000'}"') do set "CODE=%%C"
        if "!CODE!"=="200" set "PRONTO=1"
    )
)
echo.
echo.

if not "!PRONTO!"=="1" (
    echo [X] Server did not start in time.
    echo.
    echo ----- %LOG% -----
    if exist "%LOG%" (type "%LOG%") else (echo Log file was not created.)
    echo ------------------
    echo.
    echo Manual test:
    echo   cd /d "%BACKEND%"
    echo   "%PYEXE%" -m uvicorn server:app --host 127.0.0.1 --port %PORT%
    echo.
    goto :end_fail
)

echo [OK] Ready at http://localhost:%PORT%
start "" "http://localhost:%PORT%"
echo.
echo ------------------------------------------------------
echo   Keep this window open during the experience.
echo   Press any key to stop the server and exit.
echo ------------------------------------------------------
echo.
pause >nul

for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%P >nul 2>&1
)
echo Stopped.
goto :eof

:end_fail
echo.
pause
exit /b 1

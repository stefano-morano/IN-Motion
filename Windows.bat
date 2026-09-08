@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title IN-Motion

rem Double-clickable launcher for IN-Motion (Windows).
rem Same role as "Lancia IN-Motion.command" on macOS.

set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"
set "BACKEND=%DIR%\web\backend"
set "PORT=8080"
set "LOG=%TEMP%\inmotion.log"
set "PYTHON="

echo.
echo   IN-Motion
echo.
echo ------------------------------------------------------
echo.

rem Find a Python that already has uvicorn
where py >nul 2>&1 && (
    py -3 -c "import uvicorn" >nul 2>&1 && set "PYTHON=py -3"
)
if not defined PYTHON (
    where python >nul 2>&1 && (
        python -c "import uvicorn" >nul 2>&1 && set "PYTHON=python"
    )
)
if not defined PYTHON (
    where python3 >nul 2>&1 && (
        python3 -c "import uvicorn" >nul 2>&1 && set "PYTHON=python3"
    )
)

if not defined PYTHON (
    echo [X] Python with IN-Motion dependencies not found.
    echo     Open Command Prompt and run:
    echo       cd "%BACKEND%"
    echo       python -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

for /f "delims=" %%V in ('!PYTHON! --version 2^>^&1') do echo [OK] %%V  ^(!PYTHON!^)

!PYTHON! -c "import fastapi, dotenv, anthropic" >nul 2>&1
if errorlevel 1 (
    echo [!] Installing dependencies...
    !PYTHON! -m pip install -r "%BACKEND%\requirements.txt"
    if errorlevel 1 (
        echo [X] Install failed.
        pause
        exit /b 1
    )
)
echo [OK] Dependencies ready

rem Load .env from project root
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

rem Start uvicorn minimized in its own window; log to %%TEMP%%
start "IN-Motion server" /MIN cmd /c "!PYTHON! -m uvicorn server:app --host 0.0.0.0 --port %PORT% > \"%LOG%\" 2>&1"

echo   Waiting
set "PRONTO=0"
for /l %%I in (1,1,60) do (
    if "!PRONTO!"=="0" (
        timeout /t 1 /nobreak >nul
        <nul set /p=.
        curl.exe -s -o nul -w "%%{http_code}" "http://127.0.0.1:%PORT%/" > "%TEMP%\inmotion_http.txt" 2>nul
        set "CODE="
        set /p CODE=<"%TEMP%\inmotion_http.txt"
        if "!CODE!"=="200" set "PRONTO=1"
    )
)

echo.
if not "!PRONTO!"=="1" (
    echo [X] Timeout. Server log:
    echo.
    if exist "%LOG%" type "%LOG%"
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

@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title IN-Motion

rem Windows launcher for IN-Motion.
rem No nested PowerShell inside if/for — that left stray commands like "t".

set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"
set "BACKEND=%DIR%\web\backend"
set "PORT=8080"
set "LOG=%TEMP%\inmotion.log"
set "PYFILE=%TEMP%\inmotion_pyexe.txt"
set "PYEXE="

echo.
echo   IN-Motion
echo.
echo ------------------------------------------------------
echo.

if exist "%PYFILE%" del /f /q "%PYFILE%" >nul 2>&1

call :find_python
if not defined PYEXE goto :no_python

echo [OK] Python:
"%PYEXE%" --version
echo      %PYEXE%
echo.

"%PYEXE%" -c "import uvicorn, fastapi, dotenv, anthropic" >nul 2>&1
if errorlevel 1 goto :install_deps
echo [OK] Dependencies ready
echo.
goto :after_deps

:install_deps
echo [!] Installing dependencies from requirements.txt ...
echo     First run can take several minutes.
echo.
"%PYEXE%" -m pip install -r "%BACKEND%\requirements.txt"
if errorlevel 1 goto :pip_fail
echo [OK] Dependencies ready
echo.

:after_deps
if exist "%DIR%\.env" goto :load_env
echo [!] No .env in project root — API keys may be missing
echo.
goto :after_env

:load_env
for /f "usebackq tokens=1* delims== eol=#" %%A in ("%DIR%\.env") do (
    if not "%%A"=="" if not "%%B"=="" set "%%A=%%B"
)
echo [OK] .env loaded
echo.

:after_env
for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    echo [!] Stopping PID %%P on port %PORT%
    taskkill /F /PID %%P >nul 2>&1
)

if not exist "%BACKEND%\server.py" goto :no_server

cd /d "%BACKEND%"
if errorlevel 1 goto :no_cd

echo Starting server...
echo.

rem Title must be the first quoted arg of START; then the real exe.
start "IN-Motion server" /MIN "%PYEXE%" -m uvicorn "server:app" --host 127.0.0.1 --port %PORT%

echo Waiting for http://127.0.0.1:%PORT%/
set "N=0"

:wait_loop
set /a N+=1
if %N% GTR 90 goto :wait_fail
ping -n 2 127.0.0.1 >nul
<nul set /p=.
"%PYEXE%" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:%PORT%/', timeout=1)" >nul 2>&1
if errorlevel 1 goto :wait_loop
echo.
echo.
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

:wait_fail
echo.
echo.
echo [X] Server did not start in time.
echo.
echo Manual test:
echo   cd /d "%BACKEND%"
echo   "%PYEXE%" -m uvicorn "server:app" --host 127.0.0.1 --port %PORT%
echo.
echo Check the minimized "IN-Motion server" window for the Python traceback.
echo.
goto :fail

:no_python
echo [X] Python 3.10+ not found.
echo     Install from https://www.python.org/downloads/
echo     Enable "Add python.exe to PATH", then retry.
echo.
goto :fail

:pip_fail
echo.
echo [X] pip install failed.
goto :fail

:no_server
echo [X] server.py not found in:
echo     %BACKEND%
goto :fail

:no_cd
echo [X] Cannot cd to backend folder.
goto :fail

:find_python
where py >nul 2>&1
if errorlevel 1 goto :find_python_python
py -3 -c "import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
if errorlevel 1 goto :find_python_python
py -3 -c "import sys; open(sys.argv[1],'w',encoding='utf-8').write(sys.executable)" "%PYFILE%" >nul 2>&1
if exist "%PYFILE%" set /p PYEXE=<"%PYFILE%"
if defined PYEXE goto :eof

:find_python_python
where python >nul 2>&1
if errorlevel 1 goto :find_python_python3
python -c "import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
if errorlevel 1 goto :find_python_python3
python -c "import sys; open(sys.argv[1],'w',encoding='utf-8').write(sys.executable)" "%PYFILE%" >nul 2>&1
if exist "%PYFILE%" set /p PYEXE=<"%PYFILE%"
if defined PYEXE goto :eof

:find_python_python3
where python3 >nul 2>&1
if errorlevel 1 goto :eof
python3 -c "import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1
if errorlevel 1 goto :eof
python3 -c "import sys; open(sys.argv[1],'w',encoding='utf-8').write(sys.executable)" "%PYFILE%" >nul 2>&1
if exist "%PYFILE%" set /p PYEXE=<"%PYFILE%"
goto :eof

:fail
echo.
pause
exit /b 1

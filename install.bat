@echo off
echo Installing Octo Agent...

set NEEDS_RESTART=0
set PYTHON_CMD=python

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed. Attempting to install Python 3.14 via winget...
    winget install --id Python.Python.3.14
    set NEEDS_RESTART=1
)

node --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Node.js is not installed. Attempting to install Node.js 25 via winget...
    winget install --id OpenJS.NodeJS -e
    set NEEDS_RESTART=1
)

if %NEEDS_RESTART% equ 1 (
    echo =======================================================
    echo Installations completed successfully.
    echo PLEASE RESTART YOUR TERMINAL, then run install.bat again!
    echo =======================================================
    pause
    exit /b 0
)

echo Moving all code to %USERPROFILE%\octo...
mkdir "%USERPROFILE%\octo" 2>nul
xcopy /E /I /Y "%~dp0*" "%USERPROFILE%\octo\"

cd /d "%USERPROFILE%\octo"

echo Creating virtual environment in %USERPROFILE%\octo\.venv...
%PYTHON_CMD% -m venv .venv
call .venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt
pip install fastapi uvicorn[standard]

echo Installation complete!
echo The code has been moved to %USERPROFILE%\octo
if not exist "%USERPROFILE%\.local\bin" mkdir "%USERPROFILE%\.local\bin"
copy /Y "%USERPROFILE%\octo\bin\octo.bat" "%USERPROFILE%\.local\bin\octo.bat" >nul
echo To use the octo command from anywhere, add %USERPROFILE%\.local\bin to your PATH.
echo.
echo To onboard, run:
echo   "%USERPROFILE%\.local\bin\octo" onboard
echo To start the web dashboard, run:
echo   "%USERPROFILE%\.local\bin\octo" web
pause

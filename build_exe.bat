@echo off
REM xAI Remaining
REM Copyright (c) 2026 Clayton Pippenger
REM Licensed under the MIT License.

setlocal EnableExtensions DisableDelayedExpansion

cd /d "%~dp0"

set "PYTHON_ARGS="
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=py"
    set "PYTHON_ARGS=-3"
)

"%PYTHON_EXE%" %PYTHON_ARGS% -m pip install --upgrade pip
if errorlevel 1 goto :error

"%PYTHON_EXE%" %PYTHON_ARGS% -m pip install -r requirements.txt
if errorlevel 1 goto :error

"%PYTHON_EXE%" %PYTHON_ARGS% -m pip install "pyinstaller>=6.19,<7"
if errorlevel 1 goto :error

"%PYTHON_EXE%" %PYTHON_ARGS% -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "xAI Remaining" ^
    --hidden-import PIL.Image ^
    --hidden-import PIL.ImageDraw ^
    --hidden-import PIL.ImageFont ^
    --hidden-import pystray._win32 ^
    --hidden-import providers.xai_provider ^
    xai_remaining.py
if errorlevel 1 goto :error

echo.
echo Build complete: dist\xAI Remaining.exe
exit /b 0

:error
echo.
echo Build failed.
exit /b 1

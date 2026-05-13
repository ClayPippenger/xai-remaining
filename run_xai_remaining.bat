@echo off
REM xAI Remaining
REM Copyright (c) 2026 Clayton Pippenger
REM Licensed under the MIT License.

setlocal

cd /d "%~dp0"

set "PYTHONW=%~dp0.venv\Scripts\pythonw.exe"
if exist "%PYTHONW%" (
    start "xAI Remaining" "%PYTHONW%" "%~dp0xai_remaining.py"
) else (
    start "xAI Remaining" pyw "%~dp0xai_remaining.py"
)

endlocal

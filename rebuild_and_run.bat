@echo off
REM xAI Remaining
REM Copyright (c) 2026 Clayton Pippenger
REM Licensed under the MIT License.

if defined DEBUG echo on
setlocal EnableExtensions DisableDelayedExpansion

set "DRY_RUN=0"
if /I "%~1"=="--dry-run" set "DRY_RUN=1"

cd /d "%~dp0"
if errorlevel 1 goto fail

set "PROJECT_ROOT=%CD%"
set "SCRIPT_PATH=%PROJECT_ROOT%\xai_remaining.py"
set "EXE_PATH=%PROJECT_ROOT%\dist\xAI Remaining.exe"
set "MAX_STOP_ATTEMPTS=10"
set "MATCH_COUNT=0"
set "EXE_TIMESTAMP="

echo([INFO] Project root "%PROJECT_ROOT%"

if "%DRY_RUN%"=="1" goto dry_run

set "ATTEMPT=1"

:stop_loop
set "MATCH_COUNT=0"
set "COUNT_FILE=%TEMP%\xai_remaining_count_%RANDOM%%RANDOM%.txt"
REM Match only this project's EXE path and Python commands running this project's script.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; $project = [IO.Path]::GetFullPath($env:PROJECT_ROOT); $script = [IO.Path]::GetFullPath($env:SCRIPT_PATH); $exePath = [IO.Path]::GetFullPath($env:EXE_PATH); $names = @('python.exe','pythonw.exe','py.exe','pyw.exe'); $processes = Get-CimInstance Win32_Process; $py = @($processes | Where-Object { ($names -contains $_.Name) -and $_.CommandLine -and (($_.CommandLine -like ('*' + $script + '*')) -or ($_.CommandLine -like '*xai_remaining.py*' -and $_.CommandLine -like ('*' + $project + '*'))) }); $exe = @($processes | Where-Object { $_.Name -eq 'xAI Remaining.exe' -and (($_.ExecutablePath -and ($_.ExecutablePath -ieq $exePath)) -or ($_.CommandLine -and $_.CommandLine -like ('*' + $exePath + '*'))) }); Write-Output ($py.Count + $exe.Count)" > "%COUNT_FILE%"
if errorlevel 1 goto count_failed
if exist "%COUNT_FILE%" set /p MATCH_COUNT=<"%COUNT_FILE%"
if exist "%COUNT_FILE%" del "%COUNT_FILE%" >nul 2>&1
if not defined MATCH_COUNT set "MATCH_COUNT=0"
if "%MATCH_COUNT%"=="0" goto stop_done
if %ATTEMPT% GTR %MAX_STOP_ATTEMPTS% goto stop_failed

echo([INFO] Stop attempt %ATTEMPT% of %MAX_STOP_ATTEMPTS% for %MATCH_COUNT% matching processes.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; $project = [IO.Path]::GetFullPath($env:PROJECT_ROOT); $script = [IO.Path]::GetFullPath($env:SCRIPT_PATH); $exePath = [IO.Path]::GetFullPath($env:EXE_PATH); $names = @('python.exe','pythonw.exe','py.exe','pyw.exe'); $processes = Get-CimInstance Win32_Process; $py = @($processes | Where-Object { ($names -contains $_.Name) -and $_.CommandLine -and (($_.CommandLine -like ('*' + $script + '*')) -or ($_.CommandLine -like '*xai_remaining.py*' -and $_.CommandLine -like ('*' + $project + '*'))) }); $exe = @($processes | Where-Object { $_.Name -eq 'xAI Remaining.exe' -and (($_.ExecutablePath -and ($_.ExecutablePath -ieq $exePath)) -or ($_.CommandLine -and $_.CommandLine -like ('*' + $exePath + '*'))) }); foreach ($p in $exe) { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop; Write-Host ('[INFO] Stopped EXE process PID ' + $p.ProcessId) } catch { Write-Host ('[WARN] Could not stop EXE process PID ' + $p.ProcessId + ': ' + $_.Exception.GetType().Name) } }; foreach ($p in $py) { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop; Write-Host ('[INFO] Stopped Python process PID ' + $p.ProcessId) } catch { Write-Host ('[WARN] Could not stop Python process PID ' + $p.ProcessId + ': ' + $_.Exception.GetType().Name) } }"
if not errorlevel 1 goto stop_no_warning
echo([WARN] Stop command reported a warning.

:stop_no_warning
set /a ATTEMPT=%ATTEMPT%+1
timeout /t 1 /nobreak >nul
goto stop_loop

:stop_done
echo([INFO] Existing matching processes stopped.

echo([INFO] Installing/updating dependencies.
py -3 -m pip install -r requirements.txt
if errorlevel 1 goto dependency_failed

echo([INFO] Running py_compile.
py -3 -m py_compile xai_remaining.py providers\base.py providers\xai_provider.py providers\__init__.py
if errorlevel 1 goto compile_failed

echo([INFO] Running diagnostics. This does not call xAI.
py -3 xai_remaining.py --diagnose
if errorlevel 1 goto diagnose_failed

if not exist "%EXE_PATH%" goto skip_delete_exe
echo([INFO] Deleting stale EXE before build: "%EXE_PATH%"
del /f /q "%EXE_PATH%" >nul 2>&1
if exist "%EXE_PATH%" goto delete_failed

:skip_delete_exe
echo([INFO] Building EXE.
call "%PROJECT_ROOT%\build_exe.bat"
if errorlevel 1 goto build_failed

if not exist "%EXE_PATH%" goto exe_missing

set "TIMESTAMP_FILE=%TEMP%\xai_remaining_timestamp_%RANDOM%%RANDOM%.txt"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; (Get-Item -LiteralPath $env:EXE_PATH).LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')" > "%TIMESTAMP_FILE%"
if errorlevel 1 goto timestamp_failed
if exist "%TIMESTAMP_FILE%" set /p EXE_TIMESTAMP=<"%TIMESTAMP_FILE%"
if exist "%TIMESTAMP_FILE%" del "%TIMESTAMP_FILE%" >nul 2>&1
if not defined EXE_TIMESTAMP set "EXE_TIMESTAMP=unavailable"

echo([INFO] Launching EXE path: "%EXE_PATH%"
echo([INFO] Launching EXE modified timestamp: %EXE_TIMESTAMP%
start "xAI Remaining" "%EXE_PATH%"
if errorlevel 1 goto start_failed

echo([INFO] Done.
exit /b 0

:dry_run
echo([WARN] Dry run mode: no processes will be stopped, no packages installed, no build run, no EXE launched.
set "MATCH_COUNT=0"
set "COUNT_FILE=%TEMP%\xai_remaining_count_%RANDOM%%RANDOM%.txt"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; $project = [IO.Path]::GetFullPath($env:PROJECT_ROOT); $script = [IO.Path]::GetFullPath($env:SCRIPT_PATH); $exePath = [IO.Path]::GetFullPath($env:EXE_PATH); $names = @('python.exe','pythonw.exe','py.exe','pyw.exe'); $processes = Get-CimInstance Win32_Process; $py = @($processes | Where-Object { ($names -contains $_.Name) -and $_.CommandLine -and (($_.CommandLine -like ('*' + $script + '*')) -or ($_.CommandLine -like '*xai_remaining.py*' -and $_.CommandLine -like ('*' + $project + '*'))) }); $exe = @($processes | Where-Object { $_.Name -eq 'xAI Remaining.exe' -and (($_.ExecutablePath -and ($_.ExecutablePath -ieq $exePath)) -or ($_.CommandLine -and $_.CommandLine -like ('*' + $exePath + '*'))) }); Write-Output ($py.Count + $exe.Count)" > "%COUNT_FILE%"
if errorlevel 1 goto count_failed
if exist "%COUNT_FILE%" set /p MATCH_COUNT=<"%COUNT_FILE%"
if exist "%COUNT_FILE%" del "%COUNT_FILE%" >nul 2>&1
if not defined MATCH_COUNT set "MATCH_COUNT=0"
echo([INFO] Matching process count: %MATCH_COUNT%
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; $project = [IO.Path]::GetFullPath($env:PROJECT_ROOT); $script = [IO.Path]::GetFullPath($env:SCRIPT_PATH); $exePath = [IO.Path]::GetFullPath($env:EXE_PATH); $names = @('python.exe','pythonw.exe','py.exe','pyw.exe'); $processes = Get-CimInstance Win32_Process; $py = @($processes | Where-Object { ($names -contains $_.Name) -and $_.CommandLine -and (($_.CommandLine -like ('*' + $script + '*')) -or ($_.CommandLine -like '*xai_remaining.py*' -and $_.CommandLine -like ('*' + $project + '*'))) }); $exe = @($processes | Where-Object { $_.Name -eq 'xAI Remaining.exe' -and (($_.ExecutablePath -and ($_.ExecutablePath -ieq $exePath)) -or ($_.CommandLine -and $_.CommandLine -like ('*' + $exePath + '*'))) }); foreach ($p in $exe) { Write-Host ('[INFO] Match: project EXE PID ' + $p.ProcessId + ' Path ' + $p.ExecutablePath) }; foreach ($p in $py) { Write-Host ('[INFO] Match: project Python process PID ' + $p.ProcessId + ' Name ' + $p.Name) }; if (($py.Count + $exe.Count) -eq 0) { Write-Host '[INFO] No matching processes found.' }"
if errorlevel 1 goto count_failed
if not exist "%EXE_PATH%" goto dry_run_no_exe
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference = 'Stop'; Write-Host ('[INFO] Existing EXE modified timestamp: ' + (Get-Item -LiteralPath $env:EXE_PATH).LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'))"
if errorlevel 1 goto timestamp_failed
goto dry_run_after_exe_timestamp

:dry_run_no_exe
echo([INFO] Existing EXE modified timestamp: not found

:dry_run_after_exe_timestamp
echo([INFO] Would stop matching processes for up to %MAX_STOP_ATTEMPTS% attempts.
echo([INFO] Would install requirements with: py -3 -m pip install -r requirements.txt
echo([INFO] Would run py_compile.
echo([INFO] Would run diagnostics.
echo([INFO] Would delete stale EXE before build: "%EXE_PATH%"
echo([INFO] Would call build_exe.bat.
echo([INFO] Would verify "%EXE_PATH%" exists and print its modified timestamp.
echo([INFO] Would start only the rebuilt EXE.
echo([INFO] Dry run complete.
exit /b 0

:count_failed
echo([ERROR] Could not inspect matching processes.
if exist "%COUNT_FILE%" del "%COUNT_FILE%" >nul 2>&1
goto fail

:stop_failed
echo([ERROR] Failed to stop all matching processes.
goto fail

:dependency_failed
echo([ERROR] Dependency install failed.
goto fail

:compile_failed
echo([ERROR] py_compile failed.
goto fail

:diagnose_failed
echo([ERROR] Diagnostics failed.
goto fail

:delete_failed
echo([ERROR] Could not delete stale EXE at "%EXE_PATH%".
goto fail

:build_failed
echo([ERROR] EXE build failed.
goto fail

:exe_missing
echo([ERROR] Built EXE not found at "%EXE_PATH%".
goto fail

:timestamp_failed
echo([ERROR] Could not read built EXE modified timestamp.
if exist "%TIMESTAMP_FILE%" del "%TIMESTAMP_FILE%" >nul 2>&1
goto fail

:start_failed
echo([ERROR] Failed to start "%EXE_PATH%".
goto fail

:fail
echo(
echo([ERROR] Workflow failed.
pause
exit /b 1

@echo off
rem PhotoCruller for Windows: drag a photo folder onto this file, or run
rem   pc_crull.bat "C:\path\to\folder" [--apply] [--undo "job"] ...
>nul chcp 65001
set PYTHONIOENCODING=utf-8
where py >nul 2>nul && (set "PYRUN=py -3") || (set "PYRUN=python")
if "%~1"=="--dashboard" (
    %PYRUN% "%~dp0scripts\dashboard.py" %2 %3 %4
) else (
    %PYRUN% "%~dp0scripts\cull.py" %*
)
pause

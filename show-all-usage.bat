@echo off
where py >nul 2>nul
if errorlevel 1 (
    python "%~dp0show-all-usage.py" %*
) else (
    py -3 "%~dp0show-all-usage.py" %*
)
exit /b %errorlevel%

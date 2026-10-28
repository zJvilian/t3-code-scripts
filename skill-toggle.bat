@echo off
where py >nul 2>nul
if errorlevel 1 (
    python "%~dp0skill-toggle.py" %*
) else (
    py -3 "%~dp0skill-toggle.py" %*
)
exit /b %errorlevel%
